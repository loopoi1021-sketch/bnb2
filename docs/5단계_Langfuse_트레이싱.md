# 5단계: Langfuse 트레이싱 + 개인정보 마스킹

> 질문 하나가 그래프를 지나가는 과정을 **Langfuse 웹 화면에 자동으로 기록**한다.
> 노드별 입력, 출력, 걸린 시간, Claude 토큰, 비용을 클릭해서 볼 수 있다. Langfuse로 보내기 전에 개인정보는 가린다.

## 한 일

| 파일 | 설명 |
|---|---|
| `src/bnb2/tracing.py` | Langfuse 클라이언트 생성, 마스킹 함수, CallbackHandler |
| `src/bnb2/graph.py` | `run()`에서 그래프 실행에 CallbackHandler 연결 |
| `tests/test_tracing.py` | 마스킹 테스트 |
| `.env` / `.env.example` | `LANGFUSE_HOST` → `LANGFUSE_BASE_URL` (SDK v5에서 이름 변경), `MASK_TERMS` 추가 |
| 추가 라이브러리 | `langfuse` 5.0 |

## 연결 방법: CallbackHandler

```python
config = {"callbacks": [handler()], "run_name": "bnb2"}
with propagate_attributes(trace_name="bnb2", tags=["cli"]):
    build().stream({"question": question}, config, stream_mode="updates")
client().flush()
```

| 코드 | 뜻 |
|---|---|
| `CallbackHandler` | LangChain·LangGraph가 일을 시작하고 끝낼 때마다 알려주는 **"알림 수신기"**. 받은 알림을 Langfuse 기록으로 바꾼다 |
| `config={"callbacks": [...]}` | 그래프 실행에 수신기를 꽂는다. **노드 코드는 한 줄도 안 바꿨다** |
| `run_name="bnb2"` | 트리 맨 위 이름 (기본값은 `LangGraph`) |
| `propagate_attributes(trace_name, tags)` | 기록 전체에 이름과 태그를 붙인다. 7단계 슬랙에서는 `tags=["slack"]`, 질문자 ID를 붙일 예정 |
| `flush()` | 기록은 모았다가 한꺼번에 보낸다. CLI는 바로 끝나므로 끝나기 전에 강제로 보낸다 |

**4단계에서 Claude 호출에 `langchain-anthropic`을 쓴 이유가 여기서 나온다.** LangChain 부품을 쓰면 CallbackHandler가 프롬프트, 응답, 토큰, 비용까지 자동으로 기록한다. Voyage 검색(`retrieve`)은 LangChain 부품이 아니지만, **LangGraph 노드라서** 노드의 입력과 출력(찾은 청크 4개)이 기록된다.

## Langfuse에 남는 기록 (실제)

질문: "체크아웃 몇 시까지예요?"
```
- bnb2 [CHAIN] 3.99s                                         ← 질문 하나 = 트레이스 하나
  - classify [CHAIN] 1.24s
    - ChatAnthropic [GENERATION] claude-haiku-5-5  927 토큰   $0.000133
    - route [CHAIN]                                         ← 분기 결정도 기록됨
  - retrieve [CHAIN] 0.34s                                  ← 찾은 청크 4개와 점수
  - generate [CHAIN] 1.13s
    - ChatAnthropic [GENERATION] claude-haiku-5-5  1519 토큰  $0.000215
  - check [CHAIN] 1.26s
    - ChatAnthropic [GENERATION] claude-haiku-5-5  1610 토큰  $0.000235
                                                 합계 약 $0.00058 (1원 미만)
```
- **CHAIN**: 노드나 처리 단계. 클릭하면 State 입력과 출력이 보인다.
- **GENERATION**: Claude 호출. 클릭하면 **Claude에게 보낸 프롬프트 전문**(system 지시서, `<문서>`, `<질문>`)과 응답, 토큰 수, 비용이 보인다.
- 가장 느린 곳이 Claude 호출 3번(각 1.1~1.3초)이고, 검색은 0.34초라는 걸 바로 알 수 있다.

## 개인정보 마스킹

```python
Langfuse(mask=mask, should_export_span=is_langfuse_span)
```

`mask` 함수는 **Langfuse로 보내기 직전의 모든 입력·출력**에 적용된다. Claude 호출 같은 실제 처리에는 원문이 쓰이고, **기록만** 가려진다.

| 대상 | 방법 | 예 |
|---|---|---|
| 전화번호 | 정규식 `01[016789]-xxxx-xxxx` | `010-1234-5678` → `[전화번호]` |
| 이메일 | 정규식 | `a.b@gmail.com` → `[이메일]` |
| 주소, 와이파이 비밀번호 등 | `.env`의 `MASK_TERMS`에 쉼표로 나열 | `MASK_TERMS=비밀번호1234,마포구 ...` → `[비공개]` |

**왜 이게 필요한가:** 검색된 청크가 기록에 그대로 남는다. 예를 들어 "와이파이 비번 뭐야?"라고 물으면 `02_와이파이.md` 청크(실제 비밀번호 포함)가 Langfuse 서버(일본)로 간다. 패턴으로 잡을 수 없는 값은 `MASK_TERMS`에 직접 적어서 가린다.

`mask`는 dict와 list 안쪽까지 들어가서 글자만 바꾼다. 점수 같은 숫자는 그대로 둔다 (`tests/test_tracing.py`).

## 중복 기록 문제와 해결

처음 연결했을 때 Claude 호출이 **두 번씩** 기록됐다.
```
- ChatAnthropic [GENERATION]                933 토큰 $0.000139
  - anthropic.messages.create [GENERATION]  933 토큰 $0.000139   ← 같은 호출이 또 기록됨
```
`anthropic` 라이브러리가 자체적으로 남기는 기록(OpenTelemetry)을 Langfuse SDK v5가 함께 받아서 생긴 문제다. 그대로 두면 **대시보드의 토큰과 비용이 2배로 잡힌다.**

→ `should_export_span=is_langfuse_span`으로 **Langfuse가 직접 만든 기록만** 보내게 해서 해결했다.

## 참고: Langfuse API 변경

새로 만든 조직(2026년 9월 16일 이후)에서는 기존 `GET /api/public/traces` API를 쓸 수 없고 `GET /api/public/v2/observations`를 써야 한다. 6단계에서 결과를 API로 가져올 때 v2를 쓴다.

## 🔍 직접 확인

**1) 질문 보내기**
```bash
uv run bnb2 ask "체크아웃 몇 시까지예요?"
```

**2) Langfuse 화면**: https://jp.cloud.langfuse.com 에 접속해 왼쪽 메뉴에서 **Tracing → Traces**로 간다.
- 맨 위 `bnb2` 트레이스를 클릭한다.
- 왼쪽 트리에서 `classify`, `retrieve`, `generate`, `check`를 하나씩 눌러 입력과 출력을 확인한다.
- `ChatAnthropic`(GENERATION)을 누르면 Claude에게 보낸 프롬프트 전문과 토큰, 비용이 보인다.

**3) 마스킹 테스트**
```bash
uv run pytest -q
```

**4) (할 일) `MASK_TERMS` 채우기**: `.env`에 주소, 와이파이 이름과 비밀번호처럼 Langfuse에 남으면 안 되는 값을 쉼표로 적는다.
