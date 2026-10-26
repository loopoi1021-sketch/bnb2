"""10단계: 대시보드 이전 기록 가져오기 (한 번만 실행, 다시 실행해도 중복 없음).

1) data/eval-*.jsonl 시험 결과 → eval_runs / eval_items
2) Langfuse 에 남은 최근 30일 봇 트레이스 → conversations
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bnb2 import store
from bnb2.dashboard import NODES


def import_evals() -> None:
    from bnb2.evaluate import JUDGE_MODEL
    from bnb2.graph import MODEL

    with store.connect() as conn:
        done = {r[0] for r in conn.execute("SELECT name FROM eval_runs")}
    for path in sorted(Path("data").glob("eval-*.jsonl")):
        name = path.stem.removeprefix("eval-")
        if name in done:
            continue
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        # 예전 파일엔 실행 시각·커밋이 없어서 파일 수정 시각으로 대신한다
        at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        store.save_eval(name, rows, answer_model=MODEL, judge_model=JUDGE_MODEL, created_at=at)
        print(f"  + 시험 {name} ({len(rows)}문제)")


def from_trace(root, children) -> dict:
    """Langfuse 루트 관측(출력 = 최종 State) + 자식 관측(노드 시간, 토큰) → conversations 한 행."""
    state = json.loads(root.output)
    state["latency_ms"] = {o.name: round(o.latency * 1000) for o in children if o.name in NODES and o.latency}
    gens = [o for o in children if o.type == "GENERATION"]
    state["tokens"] = {o.id: {"input": o.usage_details.get("input", 0), "output": o.usage_details.get("output", 0)}
                       for o in gens}
    state["total_ms"] = round(root.latency * 1000) if root.latency else None
    state["trace_id"] = root.trace_id
    channel = "slack" if "slack" in root.tags else "cli"
    return {**store.to_row(state), "created_at": root.start_time, "channel": channel,
            "slack_user": root.user_id or None, "thread": root.session_id or None}


def import_traces(days: int = 30) -> None:
    from bnb2.tracing import client

    api = client().api
    since = datetime.now(timezone.utc) - timedelta(days=days)
    roots = api.observations.get_many(name="bnb2", fields="core,basic,io,metrics,trace_context",
                                      from_start_time=since, limit=1000).data
    with store.connect() as conn:
        done = {r[0] for r in conn.execute("SELECT trace_id FROM conversations WHERE trace_id IS NOT NULL")}
        new = [r for r in roots if r.trace_id not in done and r.output]
        for root in new:
            children = api.observations.get_many(trace_id=root.trace_id, fields="core,basic,usage,metrics",
                                                 limit=100).data
            row = from_trace(root, children)
            row["trace_url"] = client().get_trace_url(trace_id=root.trace_id)
            store.insert(conn, row)
    print(f"  + 대화 {len(new)}건 (Langfuse 최근 {days}일. 이미 있거나 실행이 실패한 {len(roots) - len(new)}건 제외)")


def run() -> None:
    print("📥 이전 기록 가져오기")
    import_evals()
    import_traces()
