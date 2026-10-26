"""10단계: 운영 기록 저장소 (pgvector 와 같은 Postgres).

질문 1건 = conversations 1행, 시험 1회 = eval_runs 1행 + eval_items n행.
Langfuse 는 30일 뒤 지워지고 화면에서 훑어보기 어려워서, 대시보드는 이 표들만 읽는다.
"""

import logging
import os
import subprocess

import psycopg
from psycopg.types.json import Jsonb

from bnb2.feedback import TABLE as FEEDBACK_TABLE

SCHEMA = [
    FEEDBACK_TABLE,
    """CREATE TABLE IF NOT EXISTS conversations (
        id             bigserial PRIMARY KEY,
        created_at     timestamptz NOT NULL DEFAULT now(),
        channel        text NOT NULL,       -- slack / cli / rerun (대시보드에서 다시 돌려본 것)
        slack_user     text,
        thread         text,                -- 슬랙 '채널-스레드'. Langfuse session_id 와 같다
        question       text NOT NULL,
        intent         text,                -- faq / escalate / chitchat (실패하면 NULL)
        outcome        text NOT NULL,       -- answered / not_found / escalated / chitchat / error
        reply          text,
        classify_reason text,
        answer         text,                -- 답변 노드의 초안 (근거 검사 전)
        sources        jsonb,
        chunks         jsonb,               -- [{id, source, score, content}] 검색 당시 그대로
        grounded       boolean,
        direct         boolean,
        check_reason   text,
        error          text,
        latency_ms     jsonb,               -- {"classify": 1200, ...}
        total_ms       integer,
        input_tokens   integer,
        output_tokens  integer,
        cost_usd       double precision,
        trace_id       text UNIQUE,
        trace_url      text
    )""",
    "CREATE INDEX IF NOT EXISTS conversations_created_at ON conversations (created_at DESC)",
    """CREATE TABLE IF NOT EXISTS eval_runs (
        name         text PRIMARY KEY,
        created_at   timestamptz NOT NULL DEFAULT now(),
        answer_model text,
        judge_model  text,
        git_commit   text,
        url          text                   -- Langfuse 실험 화면
    )""",
    """CREATE TABLE IF NOT EXISTS eval_items (
        run           text NOT NULL REFERENCES eval_runs (name) ON DELETE CASCADE,
        id            text NOT NULL,
        topic         text,
        question      text,
        expected      text,
        reply         text,
        intent        text,
        blocked       boolean,
        grade         text,                 -- correct / partial / wrong / abstain
        hallucination boolean,
        retrieval_hit boolean,
        reason        text,                 -- 채점 이유
        chunks        jsonb,
        PRIMARY KEY (run, id)
    )""",
    """CREATE TABLE IF NOT EXISTS conversation_reviews (
        conversation_id bigint PRIMARY KEY REFERENCES conversations (id) ON DELETE CASCADE,
        status          text NOT NULL DEFAULT 'open',   -- open 미처리 / fixed 문서 보강함 / ignored 무시
        note            text,
        testset_id      integer,                        -- 시험지에 추가한 문제 번호
        updated_at      timestamptz NOT NULL DEFAULT now()
    )""",
]
REVIEW_STATUSES = ("open", "fixed", "ignored")


def connect() -> psycopg.Connection:
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    for sql in SCHEMA:
        conn.execute(sql)
    return conn


def outcome(state: dict) -> str:
    if state.get("error"):
        return "error"
    if state.get("intent") in ("escalate", "chitchat"):
        return {"escalate": "escalated", "chitchat": "chitchat"}[state["intent"]]
    return "answered" if state.get("grounded") and state.get("direct") else "not_found"


def to_row(state: dict) -> dict:
    """그래프의 최종 State → conversations 한 행."""
    from bnb2.graph import cost

    tokens = state.get("tokens", {}).values()
    return {
        "question": state["question"], "intent": state.get("intent"), "outcome": outcome(state),
        "reply": state.get("reply"), "classify_reason": state.get("reason"), "answer": state.get("answer"),
        "sources": Jsonb(state.get("sources")), "chunks": Jsonb(state.get("chunks")),
        "grounded": state.get("grounded"), "direct": state.get("direct"), "check_reason": state.get("check_reason"),
        "error": state.get("error"), "latency_ms": Jsonb(state.get("latency_ms")), "total_ms": state.get("total_ms"),
        "input_tokens": sum(t["input"] for t in tokens), "output_tokens": sum(t["output"] for t in tokens),
        "cost_usd": cost(state), "trace_id": state.get("trace_id"),
    }


def insert(conn: psycopg.Connection, row: dict) -> int | None:
    cols = list(row)
    r = conn.execute(
        f"INSERT INTO conversations ({', '.join(cols)}) VALUES ({', '.join('%s' for _ in cols)})"
        " ON CONFLICT (trace_id) DO NOTHING RETURNING id",  # 같은 트레이스를 두 번 가져와도 한 번만
        [row[c] for c in cols],
    ).fetchone()
    return r[0] if r else None


def record(state: dict, *, channel: str, user: str | None = None, thread: str | None = None) -> int | None:
    """질문 1건을 남기고 새 행 id 를 돌려준다. 기록이 실패해도 답변은 나가야 하므로 예외를 밖으로 내지 않는다."""
    try:
        row = {**to_row(state), "channel": channel, "slack_user": user, "thread": thread}
        if row["trace_id"]:
            from bnb2.tracing import client

            row["trace_url"] = client().get_trace_url(trace_id=row["trace_id"])
        with connect() as conn:
            return insert(conn, row)
    except Exception:
        logging.getLogger(__name__).exception("질문 기록 실패: %s", state.get("question"))
        return None


def save_review(conn: psycopg.Connection, cid: int, fields: dict) -> dict:
    """처리함: 대화 1건의 처리 상태·메모·시험지 번호 중 준 칸만 바꾼다 (대화마다 한 행)."""
    if fields.get("status", "open") not in REVIEW_STATUSES:
        raise ValueError(f"처리 상태가 아니에요: {fields['status']}")
    cols = list(fields)
    return conn.execute(
        f"INSERT INTO conversation_reviews (conversation_id, {', '.join(cols)})"
        f" VALUES (%s, {', '.join('%s' for _ in cols)}) ON CONFLICT (conversation_id) DO UPDATE SET"
        f" {', '.join(f'{c} = EXCLUDED.{c}' for c in cols)}, updated_at = now()"
        " RETURNING status, note, testset_id, updated_at",
        [cid, *fields.values()],
    ).fetchone()


# ── 시험 ──

EVAL_COLUMNS = ["id", "topic", "question", "expected", "reply", "intent", "blocked", "grade", "hallucination",
                "retrieval_hit", "reason", "chunks"]


def git_commit() -> str | None:
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or None


def save_eval(name: str, rows: list[dict], *, answer_model: str, judge_model: str, url: str | None = None,
              created_at=None, commit: str | None = None) -> None:
    """같은 이름으로 다시 돌리면 이전 결과를 지우고 새로 넣는다."""
    with connect() as conn:
        conn.execute("DELETE FROM eval_runs WHERE name = %s", (name,))
        conn.execute(
            "INSERT INTO eval_runs (name, created_at, answer_model, judge_model, git_commit, url)"
            " VALUES (%s, COALESCE(%s, now()), %s, %s, %s, %s)",
            (name, created_at, answer_model, judge_model, commit, url),
        )
        with conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO eval_items (run, {', '.join(EVAL_COLUMNS)})"
                f" VALUES (%s, {', '.join('%s' for _ in EVAL_COLUMNS)})",
                [[name] + [Jsonb(r.get(c)) if c == "chunks" else r.get(c) for c in EVAL_COLUMNS] for r in rows],
            )

