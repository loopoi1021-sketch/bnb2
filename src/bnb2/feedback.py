"""8단계: 슬랙 👍/👎 피드백 원본 보관 (pgvector 와 같은 Postgres).

Langfuse 무료 플랜은 30일 뒤 기록을 지우므로, 문서 개선의 근거가 되는 피드백은 여기에 영구 보관한다.
"""

import csv
import os
from pathlib import Path

import psycopg

TABLE = """CREATE TABLE IF NOT EXISTS feedback (
    trace_id   text NOT NULL,
    slack_user text NOT NULL,
    good       boolean NOT NULL,
    comment    text,
    question   text,
    reply      text,
    trace_url  text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trace_id, slack_user)  -- 같은 사람이 같은 답에 다시 누르면 덮어쓴다
)"""

COLUMNS = ["created_at", "good", "question", "reply", "comment", "slack_user", "trace_url"]


def connect() -> psycopg.Connection:
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    conn.execute(TABLE)
    return conn


def save(trace_id: str, user: str, good: bool, comment: str | None, question: str, reply: str,
         trace_url: str | None) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO feedback (trace_id, slack_user, good, comment, question, reply, trace_url)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (trace_id, slack_user) DO UPDATE SET
                 good = EXCLUDED.good,
                 comment = COALESCE(EXCLUDED.comment, feedback.comment),  -- 코멘트 없이 다시 눌러도 기존 코멘트 유지
                 updated_at = now()""",
            (trace_id, user, good, comment, question, reply, trace_url),
        )


def fetch(only_comments: bool = False) -> list[dict]:
    where = "WHERE comment IS NOT NULL" if only_comments else ""
    with connect() as conn:
        rows = conn.execute(f"SELECT {', '.join(COLUMNS)} FROM feedback {where} ORDER BY created_at DESC").fetchall()
    return [dict(zip(COLUMNS, r)) for r in rows]


def run(args: list[str]) -> None:
    """uv run bnb2 feedback [--comments] [--csv]"""
    rows = fetch(only_comments="--comments" in args)
    if "--csv" in args:
        out = Path("data/feedback.csv")  # 질문·코멘트가 들어 있어 git 제외
        out.parent.mkdir(exist_ok=True)
        with out.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: 엑셀에서 한글이 깨지지 않게
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(rows)
        print(f"💾 {out} ({len(rows)}건)")
        return
    good = sum(r["good"] for r in rows)
    print(f"📋 피드백 {len(rows)}건 (👍 {good} / 👎 {len(rows) - good})\n")
    for r in rows:
        print(f"{r['created_at'].astimezone():%m-%d %H:%M} {'👍' if r['good'] else '👎'} {r['question']}")
        if r["comment"]:
            print(f"    💬 {r['comment']}")
