"""10단계: 운영 대시보드 API (FastAPI). 화면(web/dist)도 같이 서빙한다.

Langfuse 를 부르지 않고 우리 Postgres(conversations, feedback, eval_*)만 읽는다.
게스트 질문이 들어 있어 이 컴퓨터(127.0.0.1)에서만 열린다.
"""

from datetime import timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from pydantic import BaseModel, StringConstraints

from bnb2 import store
from bnb2.dashboard import NODES
from bnb2.evaluate import BASELINE, CAUSES, add_to_testset, cause, load_testset, summarize

TZ = "Asia/Seoul"  # 일별 집계 기준 시간대
DIST = Path(__file__).resolve().parents[2] / "web" / "dist"
OUTCOMES = ["answered", "not_found", "escalated", "chitchat", "error"]
OPS = "c.channel <> 'rerun'"  # 대시보드에서 다시 돌려본 것은 운영 지표에서 뺀다

app = FastAPI(title="bnb2 운영", docs_url=None, redoc_url=None)  # /docs 는 문서 화면이 쓴다


def query(sql: str, params: dict | None = None) -> list[dict]:
    with store.connect() as conn:
        conn.row_factory = dict_row
        return conn.execute(sql, params or {}).fetchall()


# 처리함에 들어가는 질문: 봇이 못 했거나(찾지 못함·담당자 호출·오류) 직원이 👎 를 누른 것
INBOX = f"({OPS} AND (c.outcome IN ('not_found', 'escalated', 'error') OR f.down))"

# 피드백은 (트레이스, 사람)마다 한 줄이라 트레이스별로 묶는다. 한 명이라도 👎 면 👎
FEEDBACK = """(SELECT trace_id, bool_or(NOT good) AS down, bool_or(good) AS up,
                      string_agg(comment, ' / ') AS comment
               FROM feedback GROUP BY trace_id)"""


def period_stats(start: str, end: str, days: int) -> dict:
    p = {"days": days, "tz": TZ}
    where = f"created_at >= now() - ({start} * interval '1 day') AND created_at < now() - ({end} * interval '1 day')"
    row = query(f"""
        SELECT count(*) AS questions,
               count(*) FILTER (WHERE outcome = 'answered') AS answered,
               count(*) FILTER (WHERE outcome = 'not_found') AS not_found,
               count(*) FILTER (WHERE outcome = 'escalated') AS escalated,
               count(*) FILTER (WHERE outcome = 'error') AS errors,
               coalesce(sum(cost_usd), 0) AS cost,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY total_ms) AS p50_ms,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms) AS p95_ms,
               count(*) FILTER (WHERE f.up AND NOT f.down) AS thumbs_up,
               count(*) FILTER (WHERE f.down) AS thumbs_down,
               count(*) FILTER (WHERE {INBOX}) AS needs_check
        FROM conversations c LEFT JOIN {FEEDBACK} f USING (trace_id)
        WHERE {where} AND {OPS}""", p)[0]
    faq = row["answered"] + row["not_found"]
    rated = row["thumbs_up"] + row["thumbs_down"]
    return {**row, "resolution_rate": row["answered"] / faq if faq else None,
            "satisfaction": row["thumbs_up"] / rated if rated else None}


@app.get("/api/overview")
def overview(days: int = Query(7, ge=1, le=365)) -> dict:
    p = {"days": days, "tz": TZ}
    daily = query(f"""
        SELECT to_char(d, 'YYYY-MM-DD') AS day,
               {', '.join(f"count(c.id) FILTER (WHERE c.outcome = '{o}') AS {o}" for o in OUTCOMES)}
        FROM generate_series((now() AT TIME ZONE %(tz)s)::date - (%(days)s::int - 1) + time '00:00', (now() AT TIME ZONE %(tz)s)::date + time '00:00',
                             interval '1 day') AS d
        LEFT JOIN conversations c ON (c.created_at AT TIME ZONE %(tz)s)::date = d AND {OPS}
        GROUP BY d ORDER BY d""", p)
    nodes = query(f"""
        SELECT key AS node, percentile_cont(0.5) WITHIN GROUP (ORDER BY value::int) AS p50_ms, count(*) AS n
        FROM conversations c, jsonb_each_text(latency_ms)
        WHERE created_at >= now() - %(days)s * interval '1 day' AND {OPS}
        GROUP BY key""", p)
    issues = query(f"""
        SELECT c.id, c.created_at, c.question, c.outcome, f.down AS thumbs_down, f.comment
        FROM conversations c LEFT JOIN {FEEDBACK} f USING (trace_id)
        WHERE c.created_at >= now() - %(days)s * interval '1 day' AND {INBOX}
        ORDER BY c.created_at DESC LIMIT 8""", p)
    runs = query("SELECT name, created_at FROM eval_runs ORDER BY created_at DESC LIMIT 1")
    latest = None
    if runs:
        latest = {**runs[0], "summary": summarize(eval_items(runs[0]["name"]))}
    order = {n: i for i, n in enumerate(NODES)}
    return {
        "days": days,
        "current": period_stats("%(days)s", "0", days),
        "previous": period_stats("2 * %(days)s", "%(days)s", days),
        "daily": daily,
        "nodes": sorted(nodes, key=lambda r: order.get(r["node"], 99)),
        "issues": issues,
        "latest_eval": latest,
    }


@app.get("/api/conversations")
def conversations(days: int = Query(30, ge=1, le=3650), outcome: str | None = None, channel: str | None = None,
                  feedback: str | None = None, q: str | None = None,
                  limit: int = Query(50, le=200), offset: int = 0) -> dict:
    where = ["c.created_at >= now() - %(days)s * interval '1 day'"]
    if outcome:
        where.append("c.outcome = %(outcome)s")
    if channel:
        where.append("c.channel = %(channel)s")
    if feedback in ("up", "down", "none"):
        where.append({"up": "f.up AND NOT f.down", "down": "f.down", "none": "f.trace_id IS NULL"}[feedback])
    if q:
        where.append("(c.question ILIKE %(q)s OR c.reply ILIKE %(q)s)")
    p = {"days": days, "outcome": outcome, "channel": channel, "q": f"%{q}%", "limit": limit, "offset": offset}
    base = f"FROM conversations c LEFT JOIN {FEEDBACK} f USING (trace_id) WHERE {' AND '.join(where)}"
    rows = query(f"""
        SELECT c.id, c.created_at, c.channel, c.slack_user, c.question, c.intent, c.outcome, c.reply,
               c.total_ms, c.cost_usd, (c.chunks -> 0 ->> 'score')::float AS top_score,
               CASE WHEN f.down THEN 'down' WHEN f.up THEN 'up' END AS feedback, f.comment
        {base} ORDER BY c.created_at DESC LIMIT %(limit)s OFFSET %(offset)s""", p)
    return {"total": query(f"SELECT count(*) AS n {base}", p)[0]["n"], "rows": rows}


def one(cid: int) -> dict:
    rows = query("SELECT * FROM conversations WHERE id = %(id)s", {"id": cid})
    if not rows:
        raise HTTPException(404, "그런 질문이 없어요")
    return rows[0]


@app.get("/api/conversations/{cid}")
def conversation(cid: int) -> dict:
    c = one(cid)
    p = {"id": cid, "t": c["trace_id"], "thread": f"rerun-{cid}"}
    fb = query("SELECT slack_user, good, comment, created_at FROM feedback WHERE trace_id = %(t)s ORDER BY created_at", p)
    review = query("SELECT status, note, testset_id, updated_at FROM conversation_reviews WHERE conversation_id = %(id)s", p)
    reruns = query("""SELECT id, created_at, outcome, reply, total_ms FROM conversations
                      WHERE channel = 'rerun' AND thread = %(thread)s ORDER BY created_at DESC""", p)
    return {**c, "feedback": fb, "review": review[0] if review else None, "reruns": reruns}


# ── 처리함 ──

@app.get("/api/inbox")
def inbox(status: str | None = "open", reason: str | None = None) -> dict:
    where = [INBOX]
    if status in store.REVIEW_STATUSES:
        where.append("coalesce(r.status, 'open') = %(status)s")
    if reason in ("not_found", "escalated", "error"):
        where.append("c.outcome = %(reason)s")
    elif reason == "down":
        where.append("f.down")
    base = f"""FROM conversations c LEFT JOIN {FEEDBACK} f USING (trace_id)
               LEFT JOIN conversation_reviews r ON r.conversation_id = c.id"""
    p = {"status": status, "reason": reason}
    rows = query(f"""
        SELECT c.id, c.created_at, c.channel, c.slack_user, c.question, c.outcome, c.reply,
               coalesce(f.down, false) AS thumbs_down, f.comment,
               coalesce(r.status, 'open') AS status, r.note, r.testset_id, rr.outcome AS rerun_outcome
        {base}
        LEFT JOIN LATERAL (SELECT outcome FROM conversations x WHERE x.channel = 'rerun' AND x.thread = 'rerun-' || c.id
                           ORDER BY x.created_at DESC LIMIT 1) rr ON true
        WHERE {' AND '.join(where)}
        ORDER BY c.created_at DESC LIMIT 200""", p)  # shortcut: 최근 200건만, 처리 대기가 그보다 쌓이면 페이지 나누기
    counts = query(f"SELECT coalesce(r.status, 'open') AS status, count(*) AS n {base} WHERE {INBOX} GROUP BY 1")
    try:
        topics = list(dict.fromkeys(r["topic"] for r in load_testset()))
    except FileNotFoundError:
        topics = []
    return {"rows": rows, "counts": {s: 0 for s in store.REVIEW_STATUSES} | {r["status"]: r["n"] for r in counts},
            "topics": topics}


@app.get("/api/inbox/count")
def inbox_count() -> dict:
    return query(f"""SELECT count(*) AS open FROM conversations c LEFT JOIN {FEEDBACK} f USING (trace_id)
                     LEFT JOIN conversation_reviews r ON r.conversation_id = c.id
                     WHERE {INBOX} AND coalesce(r.status, 'open') = 'open'""")[0]


class ReviewIn(BaseModel):
    status: Literal["open", "fixed", "ignored"] = "open"  # 보낸 칸만 바꾼다 (exclude_unset)
    note: str | None = None


@app.patch("/api/conversations/{cid}/review")
def review(cid: int, body: ReviewIn) -> dict:
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "바꿀 칸이 없어요")
    one(cid)
    with store.connect() as conn:
        conn.row_factory = dict_row
        return store.save_review(conn, cid, fields)


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TestsetIn(BaseModel):
    topic: Text
    question_ko: Text
    answer_ko: Text
    kind: Literal["question", "request", "problem"] = "question"


@app.post("/api/conversations/{cid}/testset")
def to_testset(cid: int, body: TestsetIn) -> dict:
    """정답을 받아 data/testset.jsonl 에 한 문제를 붙인다. Langfuse Dataset 은 `bnb2 dataset` 으로 따로 올린다."""
    c = one(cid)
    if query("SELECT 1 FROM conversation_reviews WHERE conversation_id = %(id)s AND testset_id IS NOT NULL", {"id": cid}):
        raise HTTPException(409, "이미 시험지에 추가한 질문이에요")
    at = c["created_at"].astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    row = add_to_testset({"thread": c["thread"] or f"conversation-{cid}", "at": at, "kind": body.kind,
                          "topic": body.topic, "guest": c["question"], "question_ko": body.question_ko,
                          "answer_ko": body.answer_ko})
    with store.connect() as conn:
        store.save_review(conn, cid, {"testset_id": row["id"]})
    return row


@app.post("/api/conversations/{cid}/rerun")
def rerun(cid: int) -> dict:
    """같은 질문을 지금의 봇으로 다시 돌려 새 행(channel 'rerun')으로 남긴다. 문서를 보강한 뒤 확인용."""
    from bnb2.graph import answer

    c = one(cid)
    try:
        state = answer(c["question"], session_id=f"rerun-{cid}", tags=["rerun"])
    except Exception as e:
        raise HTTPException(502, f"다시 돌리지 못했어요: {type(e).__name__}: {e}") from e
    new = store.record(state, channel="rerun", thread=f"rerun-{cid}")
    if new is None:
        raise HTTPException(500, "답은 받았지만 기록하지 못했어요 (서버 로그 확인)")
    return conversation(new)


# ── 문서 ──

def doc_usage(docs: list[dict], convs: list[dict], keep: int = 20) -> list[dict]:
    """문서 항목마다 검색된 횟수, 1위로 검색된 횟수, 실제로 나간 답의 출처였던 횟수, '찾지 못함' 질문에서 1위였던 횟수.

    convs 는 최근 것부터. 항목마다 그 항목이 검색된 질문을 최근 keep 개까지 붙인다.
    """
    stats = {d["id"]: {**d, "retrieved": 0, "top1": 0, "used": 0, "not_found_top1": 0, "questions": []} for d in docs}
    by_source = {d["source"]: d["id"] for d in docs}
    for c in convs:
        for rank, ch in enumerate(c["chunks"] or []):
            s = stats.get(ch.get("id") or by_source.get(ch["source"]))
            if s is None:  # 문서를 다시 적재하면서 사라진 항목
                continue
            s["retrieved"] += 1
            s["top1"] += rank == 0
            s["not_found_top1"] += rank == 0 and c["outcome"] == "not_found"
            if len(s["questions"]) < keep:
                s["questions"].append({"id": c["id"], "created_at": c["created_at"], "question": c["question"],
                                       "outcome": c["outcome"], "rank": rank + 1})
        if c["outcome"] != "answered":  # 근거 검사에 막힌 초안의 출처는 답으로 나가지 않았다
            continue
        for src in set(c["sources"] or []):
            if src in by_source:
                stats[by_source[src]]["used"] += 1
    return list(stats.values())


@app.get("/api/docs")
def docs() -> dict:
    # shortcut: 대화 전체를 파이썬으로 집계한다. 수만 건이 넘으면 jsonb_array_elements 로 SQL 집계
    convs = query(f"""SELECT id, created_at, question, outcome, chunks, sources FROM conversations c
                      WHERE {OPS} AND jsonb_typeof(chunks) = 'array' ORDER BY created_at DESC""")
    return {"searched": len(convs), "items": doc_usage(query("SELECT id, source, content FROM chunks ORDER BY id"), convs)}


# ── 시험 ──

def eval_items(name: str) -> list[dict]:
    return query("SELECT * FROM eval_items WHERE run = %(run)s ORDER BY id", {"run": name})


def baseline() -> dict:
    b = BASELINE
    rates = {k: b[k] / b["n"] for k in ("correct", "partial", "wrong", "abstain", "retrieval_hit")}
    return {"name": b["name"], "n": b["n"], **rates, "hallucination": None, "blocked": None,
            "score": round((rates["correct"] + 0.5 * rates["partial"]) * 100, 1)}


@app.get("/api/evals")
def evals() -> dict:
    runs = query("SELECT * FROM eval_runs ORDER BY created_at DESC")
    return {"baseline": baseline(), "causes": CAUSES,
            "runs": [{**r, "summary": summarize(eval_items(r["name"]))} for r in runs]}


@app.get("/api/evals/{name}")
def eval_run(name: str) -> dict:
    runs = query("SELECT * FROM eval_runs WHERE name = %(n)s", {"n": name})
    if not runs:
        raise HTTPException(404)
    items = [{**r, "cause": cause(r)} for r in eval_items(name)]
    topics: dict[str, list] = {}
    for r in items:
        topics.setdefault(r["topic"] or "기타", []).append(r)
    return {
        "run": runs[0], "summary": summarize(items),
        "causes": {k: sum(r["cause"] == k for r in items) for k in CAUSES},
        "topics": sorted(({"topic": t, **summarize(rs)} for t, rs in topics.items()), key=lambda t: -t["n"]),
        "items": items,
    }


# ── 화면 (web/dist). API 가 아닌 주소는 전부 index.html 로 보내 React 라우터가 처리한다 ──

if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    if not (DIST / "index.html").is_file():
        return PlainTextResponse("화면이 아직 빌드되지 않았어요: cd web && npm install && npm run build", 503)
    f = (DIST / path).resolve()
    if path and f.is_file() and f.is_relative_to(DIST):  # favicon 등 dist 바로 아래 파일
        return FileResponse(f)
    return FileResponse(DIST / "index.html")


def run() -> None:
    import uvicorn

    print("📊 http://127.0.0.1:8000 (Ctrl+C 로 종료)")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
