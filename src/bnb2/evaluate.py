"""6단계: 평가. 시험지(실제 게스트 질문 + 호스트 실제 답)를 Langfuse Dataset 으로 올리고 실험한다."""

import json
from pathlib import Path
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langfuse import Evaluation
from pydantic import BaseModel, Field

from bnb2.tracing import client, mask_text

DATASET = "bnb2-testset"
TESTSET = Path("data/testset.jsonl")  # 기존 bnb 에서 복사. 실제 대화라 git 제외


def load_testset() -> list[dict]:
    return [json.loads(line) for line in TESTSET.read_text().splitlines() if line.strip()]


def to_item(row: dict) -> dict:
    """원문 메시지(guest)와 대화방 ID(thread)는 올리지 않는다. 한국어로 정리된 질문과 답만 쓴다."""
    return {
        "id": f"testset-{row['id']}",  # 같은 id 로 다시 올리면 새로 생기지 않고 덮어쓴다
        "input": {"question": mask_text(row["question_ko"])},
        "expected_output": {"answer": mask_text(row["answer_ko"])},
        "metadata": {"topic": row["topic"], "kind": row["kind"], "at": row["at"][:10]},
    }


def upload() -> None:
    lf = client()
    rows = load_testset()
    lf.create_dataset(
        name=DATASET,
        description="실제 게스트 질문 94개(2026-07 이후)와 호스트의 실제 답. 문서 보강(~2026-06)과 기간 분리",
    )
    for row in rows:
        lf.create_dataset_item(dataset_name=DATASET, **to_item(row))
    lf.flush()
    print(f"📤 Langfuse Dataset '{DATASET}' 에 {len(rows)}문제 등록")


# ── 6-2: 시험 + 채점 ──

JUDGE_MODEL = "claude-sonnet-5-5"  # 기존 bnb 채점과 같은 모델. 답변 모델(haiku)보다 강한 모델로 채점한다
# sonnet-5-5 는 "도구 호출 강제" 방식 구조화 출력을 지원하지 않아 json_schema 방식을 쓴다.

JUDGE_PROMPT = """너는 숙소 운영 Q&A 봇의 채점관이야. <질문>에 대한 <봇 답변>을, 호스트가 실제로 보낸 <정답>과 비교해 채점해.

grade (호스트 정답 기준):
- correct: 정답의 핵심 정보(시간, 장소, 가능 여부 등)가 모두 맞다. 표현이 달라도 된다.
- partial: 핵심 정보 일부만 맞거나 빠진 것이 있다. 틀린 정보는 없다.
- wrong: 정답과 어긋나는 정보가 하나라도 있다.
- abstain: 봇이 답을 주지 않았다 ("문서에서 찾지 못했어요", "담당자 판단이 필요", 인사만 함).

hallucination (<검색된 문서> 기준, 정답과 무관):
- true: 봇 답변에 <검색된 문서>에 없는 정보가 들어 있다.
- false: 답변의 모든 정보가 <검색된 문서>에 있다. abstain 이면 항상 false.

retrieval_hit: <검색된 문서> 안에 정답의 핵심 정보가 들어 있으면 true. 검색된 문서가 없으면 false.

reason: 판정 이유를 한두 문장으로."""


class Judgement(BaseModel):
    grade: Literal["correct", "partial", "wrong", "abstain"]
    hallucination: bool
    retrieval_hit: bool
    reason: str = Field(description="판정 이유 한두 문장")


def task(*, item, **kwargs) -> dict:
    """시험 문제 하나를 그래프에 통과시킨다. 노드별 기록은 이 문제의 트레이스 아래에 남는다."""
    from bnb2.graph import build
    from bnb2.tracing import handler

    s = build().invoke({"question": item.input["question"]}, {"callbacks": [handler()]})
    return {
        "reply": s["reply"],
        "intent": s["intent"],
        # faq 인데 근거 검사에서 막혔으면 blocked. (빈 답이었거나, 근거 없음, 직접 답 아님)
        "blocked": s["intent"] == "faq" and not (s.get("grounded") and s.get("direct")),
        "chunks": [{"source": c["source"], "content": c["content"]} for c in s.get("chunks", [])],
    }


def judge(*, input, output, expected_output, **kwargs) -> list[Evaluation]:
    docs = "\n\n".join(f"[{c['source']}]\n{c['content']}" for c in output["chunks"]) or "(검색 안 함)"
    user = (f"<질문>\n{input['question']}\n</질문>\n\n<정답>\n{expected_output['answer']}\n</정답>\n\n"
            f"<봇 답변>\n{output['reply']}\n</봇 답변>\n\n<검색된 문서>\n{docs}\n</검색된 문서>")
    j = ChatAnthropic(model=JUDGE_MODEL, max_tokens=1024).with_structured_output(Judgement, method="json_schema").invoke(
        [("system", JUDGE_PROMPT), ("human", user)]
    )
    return [
        Evaluation(name="grade", value=j.grade, comment=j.reason, data_type="CATEGORICAL"),
        Evaluation(name="hallucination", value=j.hallucination, data_type="BOOLEAN"),
        Evaluation(name="retrieval_hit", value=j.retrieval_hit, data_type="BOOLEAN"),
        Evaluation(name="blocked", value=output["blocked"], data_type="BOOLEAN"),
    ]


def sample(items: list, n: int) -> list:
    """주제가 겹치지 않게 앞에서부터 n개 (채점기 검토용)."""
    seen, out = set(), []
    for i in items:
        if i.metadata["topic"] not in seen:
            seen.add(i.metadata["topic"])
            out.append(i)
    return out[:n]


def to_row(r) -> dict | None:
    """실험 결과 한 문제 → 저장·집계용 한 줄. 실행이나 채점이 실패한 문제는 None."""
    ev = {e.name: e for e in r.evaluations}
    if not r.output or "grade" not in ev:
        return None
    return {
        "id": r.item.id, "topic": r.item.metadata["topic"], "question": r.item.input["question"],
        "expected": r.item.expected_output["answer"], "reply": r.output["reply"],
        "intent": r.output["intent"], "blocked": r.output["blocked"],
        "grade": ev["grade"].value, "hallucination": ev["hallucination"].value,
        "retrieval_hit": ev["retrieval_hit"].value, "reason": ev["grade"].comment,
    }


# ── 6-3: 집계 ──

# 비교 기준: 기존 n8n 봇(bnb)의 마지막 시험 "프롬프트 개선 후" (94문제, 같은 Sonnet 채점)
BASELINE = {"name": "bnb (n8n)", "n": 94, "correct": 34, "partial": 29, "wrong": 9, "abstain": 22,
            "retrieval_hit": 43}


def summarize(rows: list[dict]) -> dict:
    """정답률·오답률·보류율·환각률 등 비율(0~1)과 종합 점수(0~100)."""
    n = len(rows)
    rate = lambda pred: round(sum(map(pred, rows)) / n, 3) if n else 0.0  # noqa: E731
    out = {"n": n}
    for g in ("correct", "partial", "wrong", "abstain"):
        out[g] = rate(lambda r: r["grade"] == g)
    for k in ("hallucination", "retrieval_hit", "blocked"):
        out[k] = rate(lambda r: r[k] is True)
    # 종합 점수: partial 을 반만 인정. 기준이 임의라 정답률·환각률과 함께 본다.
    out["score"] = round((out["correct"] + 0.5 * out["partial"]) * 100, 1)
    return out


def run_summary(*, item_results, **kwargs) -> list[Evaluation]:
    """Langfuse 실험 화면에 시험 전체 지표를 붙인다."""
    s = summarize([row for r in item_results if (row := to_row(r))])
    names = ["correct", "partial", "wrong", "abstain", "hallucination", "retrieval_hit", "blocked"]
    return [Evaluation(name=f"{k}_rate", value=s[k], data_type="NUMERIC") for k in names] + [
        Evaluation(name="score", value=s["score"], data_type="NUMERIC", comment="correct + 0.5×partial, 100점 만점")
    ]


def print_summary(rows: list[dict]) -> None:
    s = summarize(rows)
    b = BASELINE
    pct = lambda v: f"{v * 100:5.1f}%"  # noqa: E731
    print(f"\n📊 {s['n']}문제   (비교: {b['name']}, {b['n']}문제)")
    for label, k in [("정답률", "correct"), ("부분정답률", "partial"), ("오답률", "wrong"), ("보류율", "abstain"),
                     ("검색 적중률", "retrieval_hit")]:
        print(f"  {label:<7} {pct(s[k])}   | {pct(b[k] / b['n'])}")
    print(f"  {'환각률':<7} {pct(s['hallucination'])}   | (측정 안 함)")
    print(f"  {'차단율':<7} {pct(s['blocked'])}   | (해당 없음)")
    print(f"  {'종합 점수':<6} {s['score']:5.1f}점  | {(b['correct'] + 0.5 * b['partial']) / b['n'] * 100:5.1f}점")

    by_topic: dict[str, list] = {}
    for r in rows:
        by_topic.setdefault(r["topic"], []).append(r)
    print("\n  주제별 정답률")
    for topic, rs in sorted(by_topic.items(), key=lambda kv: -len(kv[1])):
        print(f"  - {topic:<10} {len(rs):>3}문제  {pct(summarize(rs)['correct'])}")


def report(run_name: str) -> None:
    """저장된 결과 파일로 집계만 다시 한다 (API 호출 없음, 비용 0)."""
    path = Path(f"data/eval-{run_name}.jsonl")
    print_summary([json.loads(line) for line in path.read_text().splitlines() if line.strip()])


def experiment(limit: int | None, run_name: str) -> None:
    from bnb2.retrieve import warm_query_cache

    lf = client()
    items = lf.get_dataset(DATASET).items
    items = sample(items, limit) if limit else items
    warm_query_cache([i.input["question"] for i in items])  # Voyage 1회로 전부 임베딩
    print(f"🧪 {len(items)}문제 시험 시작 (run: {run_name})")
    result = lf.run_experiment(
        name="bnb2", run_name=run_name, data=items, task=task, evaluators=[judge],
        run_evaluators=[run_summary], max_concurrency=4,
        metadata={"answer_model": "claude-haiku-5-5", "judge_model": JUDGE_MODEL},
    )
    lf.flush()

    rows = [row for r in result.item_results if (row := to_row(r))]
    failed = len(result.item_results) - len(rows)
    out = Path(f"data/eval-{run_name}.jsonl")  # 문제별 결과 (git 제외)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    if limit:  # 소수 검토용이면 문제별로 자세히
        for r in rows:
            print(f"\n[{r['id']}] {r['topic']} | {r['grade']} | 환각={r['hallucination']} "
                  f"검색적중={r['retrieval_hit']} 차단={r['blocked']}\n  Q: {r['question']}\n  정답: {r['expected']}"
                  f"\n  봇: {r['reply']}\n  채점 이유: {r['reason']}")
    print_summary(rows)
    if failed:
        print(f"\n⚠️ 실행 또는 채점에 실패한 문제 {failed}개는 집계에서 뺐다")
    print(f"\n💾 {out}\n🔗 {result.dataset_run_url}")
