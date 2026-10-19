"""4단계: LangGraph. 분류 → 검색 → 답변 → 근거 검사, 분기로 사람 판단/잡담 처리."""

from typing import Literal, TypedDict

from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from bnb2.retrieve import search

MODEL = "claude-haiku-5-5"  # 기존 bnb 와 같은 모델 → 공정 비교

NOT_FOUND = "문서에서 찾지 못했어요. 담당자에게 확인 후 알려드릴게요."
ESCALATE = "🚨 담당자 판단이 필요한 질문이에요. 담당자에게 전달할게요."


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
    direct: bool = Field(description="답변이 질문에 직접 답하면 true. '문서에 없다'는 말이나 관련 정보만 있으면 false")
    reason: str = Field(description="판정 이유 한 문장. false 면 문서에 없는 내용이 무엇인지")


def llm() -> ChatAnthropic:
    return ChatAnthropic(model=MODEL, max_tokens=1024)


# ── 노드: State 를 받아서, 바꿀 칸만 dict 로 돌려준다 ──

CLASSIFY_PROMPT = """너는 숙소 운영팀의 사내 도우미야. 직원(공동호스트, 청소 담당자)의 질문을 분류해.

- faq: 숙소 문서(입실·퇴실, 와이파이, 비품, 하우스룰, 주차·주변 등)로 답할 수 있는 정보 질문
- escalate: 사람이 판단해야 하는 일. 환불, 불만·클레임, 파손, 예약 변경, 인원 추가, 규칙 예외 허락, 호스트가 직접 움직여야 하는 요청
- chitchat: 인사, 감사, 잡담"""


def classify(state: State) -> State:
    r = llm().with_structured_output(Classification).invoke(
        [("system", CLASSIFY_PROMPT), ("human", state["question"])]
    )
    return {"intent": r.intent, "reason": r.reason}


def retrieve(state: State) -> State:
    return {"chunks": search(state["question"])}


GENERATE_PROMPT = """너는 숙소 운영팀의 사내 도우미야. 직원의 질문에 <문서>만 보고 답해.

- <문서>에 있는 내용만 써. 상식이나 추측으로 채우지 마.
- <문서>에 질문에 대한 직접적인 답이 없으면 answer 를 빈 문자열로 둬.
  "문서에는 없지만 참고로…"처럼 없다는 말이나 관련 정보로 대신 채우지 마.
- 직원에게 하는 말이니 1~3문장으로 간결하게, 존댓말로.
- 답에 쓴 문서의 [출처]를 sources 에 그대로 적어."""


def format_docs(chunks: list[dict]) -> str:
    return "\n\n".join(f"[출처: {c['source']}]\n{c['content']}" for c in chunks)


def generate(state: State) -> State:
    user = f"<문서>\n{format_docs(state['chunks'])}\n</문서>\n\n<질문>\n{state['question']}\n</질문>"
    r = llm().with_structured_output(Answer).invoke([("system", GENERATE_PROMPT), ("human", user)])
    return {"answer": r.answer.strip(), "sources": r.sources}


CHECK_PROMPT = """너는 사실 검증 담당이야. 두 가지를 판정해.

- grounded: <답변>의 모든 내용이 <문서>에 실제로 적혀 있나. 문서에 없는 숫자·조건·약속이 하나라도 있으면 false. 문서를 바꿔 말한 것은 괜찮아.
- direct: <답변>이 <질문>에 직접 답하나. "문서에 없다"고 하거나 관련 정보만 늘어놓으면 false."""


def check(state: State) -> State:
    # 답변 노드가 이미 "문서에 없음"(빈 답)이라고 했으면 Claude 를 부르지 않는다.
    if not state["answer"]:
        return {"grounded": False, "direct": False, "check_reason": "답변 노드가 문서에서 답을 찾지 못함",
                "reply": NOT_FOUND}
    user = (f"<문서>\n{format_docs(state['chunks'])}\n</문서>\n\n<질문>\n{state['question']}\n</질문>\n\n"
            f"<답변>\n{state['answer']}\n</답변>")
    r = llm().with_structured_output(Check).invoke([("system", CHECK_PROMPT), ("human", user)])
    out = {"grounded": r.grounded, "direct": r.direct, "check_reason": r.reason}
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
    return {"reply": r.text.strip()}


# ── 분기: ① 분류 결과(intent)를 보고 다음 노드를 고른다 ──


def route(state: State) -> str:
    return {"faq": "retrieve", "escalate": "escalate", "chitchat": "chitchat"}[state["intent"]]


def build():
    g = StateGraph(State)
    for name, fn in [("classify", classify), ("retrieve", retrieve), ("generate", generate),
                     ("check", check), ("escalate", escalate), ("chitchat", chitchat)]:
        g.add_node(name, fn)
    g.add_edge(START, "classify")
    g.add_conditional_edges("classify", route, ["retrieve", "escalate", "chitchat"])
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "check")
    for end in ("check", "escalate", "chitchat"):
        g.add_edge(end, END)
    return g.compile()


def run(question: str) -> None:
    """노드가 하나 끝날 때마다 그 노드가 State 에 쓴 값을 출력한다."""
    print(f"❓ {question}\n")
    for step in build().stream({"question": question}, stream_mode="updates"):
        for node, update in step.items():
            print(f"── {node} ──")
            for k, v in update.items():
                if k == "chunks":
                    for c in v:
                        print(f"  chunks: [{c['score']:.3f}] {c['source']}")
                else:
                    print(f"  {k}: {v}")
            print()
