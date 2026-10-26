"""4단계: LangGraph. 분류 → 검색 → 답변 → 근거 검사, 분기로 사람 판단/잡담 처리."""

import time
from typing import Annotated, Literal, TypedDict

from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from bnb2.retrieve import search

MODEL = "claude-haiku-5-5"  # 기존 bnb 와 같은 모델 → 공정 비교
PRICE = (0.10, 0.50)  # MODEL 의 USD / 100만 토큰 (입력, 출력). 모델을 바꾸면 같이 고친다

NOT_FOUND = "문서에서 찾지 못했어요. 담당자에게 확인 후 알려드릴게요."
ESCALATE = "🚨 담당자 판단이 필요한 질문이에요. 담당자에게 전달할게요."


def merge(a: dict, b: dict) -> dict:
    return {**a, **b}


class State(TypedDict, total=False):
    question: str
    intent: str  # ① classify
    reason: str  # ① classify: 왜 그렇게 분류했는지
    chunks: list[dict]  # ② retrieve
    answer: str  # ③ generate ("" = 문서에 없음)
    sources: list[str]  # ③ generate: 답에 쓴 청크 source
    grounded: bool  # ④ check: 답변 내용이 전부 문서에 있나
    direct: bool  # ④ check: 질문에 직접 답했나 ("문서엔 없고 참고로…" 같은 부분 답변이면 False)
    check_reason: str  # ④ check: 판정 이유
    reply: str  # 최종 답변 (슬랙에 보낼 글)
    latency_ms: Annotated[dict, merge]  # 노드별 걸린 시간. 노드마다 자기 칸만 써서 합친다
    tokens: Annotated[dict, merge]  # 노드별 Claude 토큰 {"input": n, "output": n}


# ── Claude 응답 형식 (with_structured_output 이 이 모양의 JSON 만 받도록 강제) ──


class Classification(BaseModel):
    intent: Literal["faq", "escalate", "chitchat"] = Field(
        description="faq: 숙소 문서로 답할 수 있는 정보 질문 / escalate: 사람 판단이 필요 / chitchat: 인사·감사·잡담"
    )
    reason: str = Field(description="그렇게 분류한 이유 한 문장")


class Answer(BaseModel):
    answer: str = Field(description="질문에 직접 답하는 내용. 문서에 직접적인 답이 없으면 빈 문자열")
    sources: list[str] = Field(description="답변에 사용한 문서의 출처(source) 목록")


class Check(BaseModel):
    grounded: bool = Field(description="답변의 모든 내용이 문서에 실제로 있으면 true")
    direct: bool = Field(description="답변이 질문의 핵심에 답하면 true. 핵심에 '문서에 없다'는 말이나 관련 정보만 있으면 false")
    reason: str = Field(description="판정 이유 한 문장. false 면 문서에 없는 내용이 무엇인지")


def llm() -> ChatAnthropic:
    return ChatAnthropic(model=MODEL, max_tokens=1024)


def usage(msg) -> dict:
    u = msg.usage_metadata or {}
    return {"input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0)}


def ask(schema, messages):
    """구조화 출력 + 토큰 수. include_raw: 파싱 결과와 원본 응답(토큰 수가 들어 있음)을 같이 받는다."""
    r = llm().with_structured_output(schema, include_raw=True).invoke(messages)
    if r["parsed"] is None:  # include_raw 를 켜면 파싱 실패가 예외로 안 올라와서 직접 올린다
        raise r["parsing_error"] or ValueError(f"{schema.__name__} 응답을 읽지 못함")
    return r["parsed"], usage(r["raw"])


def cost(state: dict) -> float:
    """질문 1개의 Claude 비용 (USD)."""
    t = state.get("tokens", {}).values()
    return (sum(x["input"] for x in t) * PRICE[0] + sum(x["output"] for x in t) * PRICE[1]) / 1_000_000


# ── 노드: State 를 받아서, 바꿀 칸만 dict 로 돌려준다 ──

CLASSIFY_PROMPT = """너는 숙소 운영팀의 사내 도우미야. 직원(공동호스트, 청소 담당자)의 질문을 분류해.

- faq: 숙소 문서(입실·퇴실, 와이파이, 비품, 하우스룰, 주차·주변 등)로 답할 수 있는 정보 질문
- escalate: 사람이 판단해야 하는 일. 환불, 불만·클레임, 파손, 예약 변경, 인원 추가, 규칙 예외 허락, 호스트가 직접 움직여야 하는 요청
- chitchat: 인사, 감사, 잡담"""


def classify(state: State) -> State:
    r, t = ask(Classification, [("system", CLASSIFY_PROMPT), ("human", state["question"])])
    return {"intent": r.intent, "reason": r.reason, "tokens": {"classify": t}}


def retrieve(state: State) -> State:
    return {"chunks": search(state["question"])}


GENERATE_PROMPT = """너는 숙소 운영팀의 사내 도우미야. 직원의 질문에 <문서>만 보고 답해.

- <문서>에 있는 내용만 써. 상식이나 추측으로 채우지 마.
- 첫 문장에 결론(예/아니오, 시간, 장소)을 먼저 말해. 문서의 사실에서 바로 따라 나오는 결론은 말해도 돼.
  예: 문서에 "입실 당일 11시부터 짐 보관 가능"이 있으면 "12시부터 가능하냐"에 "네, 가능합니다".
- 질문과 같은 표현이 문서에 없어도, 문서 내용으로 답할 수 있으면 그 답을 결론으로 말해. "문서에는 ~가 없어요"로 시작하지 마.
- 질문이 여러 개면 문서에 있는 부분은 답하고, 문서에 없는 부분은 끝에 "○○는 담당자 확인이 필요해요"라고 한 줄만 붙여.
- <문서>에 질문의 핵심에 대한 답이 없으면 answer 를 빈 문자열로 둬.
  "문서에는 없지만 참고로…"처럼 없다는 말이나 관련 정보로 대신 채우지 마.
- 직원에게 하는 말이니 1~3문장으로 간결하게, 존댓말로.
- 답에 쓴 문서의 [출처]를 sources 에 그대로 적어."""


def format_docs(chunks: list[dict]) -> str:
    return "\n\n".join(f"[출처: {c['source']}]\n{c['content']}" for c in chunks)


def generate(state: State) -> State:
    user = f"<문서>\n{format_docs(state['chunks'])}\n</문서>\n\n<질문>\n{state['question']}\n</질문>"
    r, t = ask(Answer, [("system", GENERATE_PROMPT), ("human", user)])
    return {"answer": r.answer.strip(), "sources": r.sources, "tokens": {"generate": t}}


CHECK_PROMPT = """너는 사실 검증 담당이야. 두 가지를 판정해.

- grounded: <답변>의 모든 내용이 <문서>에 적혀 있거나 문서의 사실에서 바로 따라 나오나 (예: "11시부터 가능" → "12시에 가능").
  문서에 없는 숫자·조건·약속이 하나라도 있으면 false. 문서를 바꿔 말한 것은 괜찮아.
- direct: <답변>이 <질문>의 핵심에 답하나. 질문이 여러 개일 때 핵심을 답하고 나머지를 "확인이 필요하다"고 했으면 true.
  핵심 질문에 "문서에 없다"고만 하거나 관련 정보만 늘어놓으면 false."""


def check(state: State) -> State:
    # 답변 노드가 이미 "문서에 없음"(빈 답)이라고 했으면 Claude 를 부르지 않는다.
    if not state["answer"]:
        return {"grounded": False, "direct": False, "check_reason": "답변 노드가 문서에서 답을 찾지 못함",
                "reply": NOT_FOUND}
    user = (f"<문서>\n{format_docs(state['chunks'])}\n</문서>\n\n<질문>\n{state['question']}\n</질문>\n\n"
            f"<답변>\n{state['answer']}\n</답변>")
    r, t = ask(Check, [("system", CHECK_PROMPT), ("human", user)])
    out = {"grounded": r.grounded, "direct": r.direct, "check_reason": r.reason, "tokens": {"check": t}}
    if not (r.grounded and r.direct):
        return {**out, "reply": NOT_FOUND}
    cite = "\n".join(f"📄 출처: {s}" for s in known_sources(state))
    return {**out, "reply": f"{state['answer']}\n{cite}"}


def known_sources(state: State) -> list[str]:
    # 실제 검색된 청크 중 Claude 가 출처로 적은 것만 남긴다 (출처를 지어내는 경우 방지).
    # 포함 여부로 비교: Claude 가 "[출처: 05.md > 수건]" 처럼 괄호째 적어도 인정된다.
    return [c["source"] for c in state["chunks"] if any(c["source"] in s for s in state["sources"])]


def escalate(state: State) -> State:
    return {"reply": ESCALATE}


def chitchat(state: State) -> State:
    r = llm().invoke(
        [("system", "너는 숙소 운영팀의 사내 도우미야. 직원의 인사·잡담에 한 문장으로 짧게 답해."),
         ("human", state["question"])]
    )
    return {"reply": r.text.strip(), "tokens": {"chitchat": usage(r)}}


# ── 분기: ① 분류 결과(intent)를 보고 다음 노드를 고른다 ──


def route(state: State) -> str:
    return {"faq": "retrieve", "escalate": "escalate", "chitchat": "chitchat"}[state["intent"]]


def timed(name: str, fn):
    def node(state: State) -> State:
        start = time.perf_counter()
        out = fn(state)
        return {**out, "latency_ms": {name: round((time.perf_counter() - start) * 1000)}}

    return node


def build():
    g = StateGraph(State)
    for name, fn in [("classify", classify), ("retrieve", retrieve), ("generate", generate),
                     ("check", check), ("escalate", escalate), ("chitchat", chitchat)]:
        g.add_node(name, timed(name, fn))
    g.add_edge(START, "classify")
    g.add_conditional_edges("classify", route, ["retrieve", "escalate", "chitchat"])
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "check")
    for end in ("check", "escalate", "chitchat"):
        g.add_edge(end, END)
    return g.compile()


def answer(question: str, *, user_id: str | None = None, session_id: str | None = None,
           tags: list[str] | None = None) -> State:
    """질문 하나를 끝까지 처리해 최종 State 를 돌려준다. 실행 기록은 Langfuse 로 간다 (슬랙 봇용).

    돌려주는 dict 의 trace_id 는 이 실행의 Langfuse 트레이스 ID. 👍/👎 피드백을 이 트레이스에 붙인다.
    """
    from langfuse import propagate_attributes

    from bnb2.tracing import handler

    h = handler()
    start = time.perf_counter()
    with propagate_attributes(trace_name="bnb2", user_id=user_id, session_id=session_id, tags=tags):
        state = build().invoke({"question": question}, {"callbacks": [h], "run_name": "bnb2"})
    return {**state, "trace_id": h.last_trace_id, "total_ms": round((time.perf_counter() - start) * 1000)}


def run(question: str) -> None:
    """노드가 하나 끝날 때마다 그 노드가 State 에 쓴 값을 출력한다. 실행 기록은 Langfuse 와 우리 DB 로 간다."""
    from langfuse import propagate_attributes

    from bnb2 import store
    from bnb2.tracing import client, handler

    print(f"❓ {question}\n")
    h = handler()
    config = {"callbacks": [h], "run_name": "bnb2"}
    start = time.perf_counter()
    with propagate_attributes(trace_name="bnb2", tags=["cli"]):
        # updates: 노드별로 바뀐 칸 (출력용), values: 그때까지의 전체 State (마지막 것 = 최종 State)
        chunks = list(build().stream({"question": question}, config, stream_mode=["updates", "values"]))
    total_ms = round((time.perf_counter() - start) * 1000)
    client().flush()  # 프로그램이 바로 끝나므로, 쌓인 기록을 지금 전송
    final = [c for mode, c in chunks if mode == "values"][-1]
    store.record({**final, "trace_id": h.last_trace_id, "total_ms": total_ms}, channel="cli")
    for step in (c for mode, c in chunks if mode == "updates"):
        for node, update in step.items():
            print(f"── {node} ──")
            for k, v in update.items():
                if k == "chunks":
                    for c in v:
                        print(f"  chunks: [{c['score']:.3f}] {c['source']}")
                else:
                    print(f"  {k}: {v}")
            print()
