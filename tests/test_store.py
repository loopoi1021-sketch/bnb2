from bnb2.evaluate import cause
from bnb2.graph import build, cost
from bnb2.store import outcome, to_row


def test_outcome_matches_what_the_bot_did():
    assert outcome({"intent": "faq", "grounded": True, "direct": True}) == "answered"
    assert outcome({"intent": "faq", "grounded": True, "direct": False}) == "not_found"
    assert outcome({"intent": "escalate"}) == "escalated"
    assert outcome({"intent": "chitchat"}) == "chitchat"
    assert outcome({"question": "q", "error": "RateLimitError"}) == "error"


def test_row_sums_tokens_and_prices_them():
    state = {"question": "q", "intent": "faq", "grounded": True, "direct": True,
             "tokens": {"classify": {"input": 1000, "output": 100}, "check": {"input": 1000, "output": 100}}}
    row = to_row(state)
    assert (row["input_tokens"], row["output_tokens"]) == (2000, 200)
    assert abs(row["cost_usd"] - (2000 * 0.10 + 200 * 0.50) / 1e6) < 1e-12
    assert cost({}) == 0


def test_error_row_without_graph_state():
    row = to_row({"question": "q", "error": "boom"})
    assert row["outcome"] == "error" and row["input_tokens"] == 0 and row["cost_usd"] == 0


def item(grade, intent="faq", hit=True, blocked=False, hallucination=False):
    return {"grade": grade, "intent": intent, "retrieval_hit": hit, "blocked": blocked, "hallucination": hallucination}


def test_cause_points_at_the_stage_to_fix():
    assert cause(item("correct")) is None
    assert cause(item("wrong", hallucination=True)) == "hallucination"
    assert cause(item("abstain", intent="escalate", hit=False)) == "routing"
    assert cause(item("abstain", hit=False, blocked=True)) == "retrieval"  # 검색이 먼저 실패했으면 검색 탓
    assert cause(item("abstain", blocked=True)) == "blocked"
    assert cause(item("partial")) == "generation"


def test_every_node_reports_its_latency():
    # 노드 함수를 감싼 timed 가 latency_ms 칸을 채우고, 노드끼리 합쳐지는지 (Claude 호출 없이 escalate 길로)
    from bnb2 import graph

    orig = graph.classify
    graph.classify = lambda s: {"intent": "escalate", "reason": "환불"}
    try:
        out = build().invoke({"question": "환불해 주세요"})
    finally:
        graph.classify = orig
    assert set(out["latency_ms"]) == {"classify", "escalate"} and out["reply"] == graph.ESCALATE


def test_testset_gets_next_number_after_the_largest(tmp_path):
    import json

    from bnb2.evaluate import add_to_testset

    path = tmp_path / "testset.jsonl"
    path.write_text('{"id": 0}\n{"id": 7}\n{"id": 3}')  # 마지막 줄바꿈 없음
    row = add_to_testset({"thread": "t", "question_ko": "질문", "answer_ko": "답"}, path)
    lines = path.read_text().splitlines()
    assert row["id"] == 8 and len(lines) == 4
    assert list(json.loads(lines[-1])) == ["id", "thread", "question_ko", "answer_ko"]
    assert add_to_testset({}, tmp_path / "new.jsonl")["id"] == 0


def test_doc_usage_counts_search_rank_and_use():
    from bnb2.api import doc_usage

    docs = [{"id": "a#1", "source": "a > 1", "content": ""}, {"id": "a#2", "source": "a > 2", "content": ""},
            {"id": "b#1", "source": "b > 1", "content": ""}]
    convs = [
        {"id": 2, "created_at": None, "question": "q2", "outcome": "not_found", "sources": ["a > 2"],  # 막혀서 안 나감
         "chunks": [{"id": "a#2", "source": "a > 2"}, {"source": "a > 1"}]},  # id 없는 예전 기록은 source 로
        {"id": 1, "created_at": None, "question": "q1", "outcome": "answered", "sources": ["a > 1"],
         "chunks": [{"id": "a#1", "source": "a > 1"}, {"id": "a#2", "source": "a > 2"}, {"id": "gone", "source": "x"}]},
    ]
    got = {d["id"]: (d["retrieved"], d["top1"], d["used"], d["not_found_top1"]) for d in doc_usage(docs, convs)}
    assert got == {"a#1": (2, 1, 1, 0), "a#2": (2, 1, 0, 1), "b#1": (0, 0, 0, 0)}
    assert [q["rank"] for q in doc_usage(docs, convs)[0]["questions"]] == [2, 1]


def test_review_keeps_fields_it_was_not_given():
    import pytest
    from dotenv import load_dotenv

    from bnb2 import store

    load_dotenv()
    try:
        conn = store.connect()
    except Exception:
        pytest.skip("DB 가 꺼져 있음")
    try:  # 커밋하지 않고 되돌린다
        cid = store.insert(conn, {"channel": "cli", "question": "q", "outcome": "not_found"})
        assert store.save_review(conn, cid, {"status": "fixed"})[:3] == ("fixed", None, None)
        assert store.save_review(conn, cid, {"note": "문서 보강"})[:3] == ("fixed", "문서 보강", None)
        assert store.save_review(conn, cid, {"testset_id": 94})[:3] == ("fixed", "문서 보강", 94)
        with pytest.raises(ValueError):
            store.save_review(conn, cid, {"status": "done"})
    finally:
        conn.rollback()
        conn.close()
