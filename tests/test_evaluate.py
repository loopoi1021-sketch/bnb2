from types import SimpleNamespace as NS

from langfuse import Evaluation

from bnb2.evaluate import run_summary, summarize


def row(grade, hallucination=False, retrieval_hit=False, blocked=False):
    return {"grade": grade, "hallucination": hallucination, "retrieval_hit": retrieval_hit, "blocked": blocked}


def test_summarize_rates_and_score():
    rows = [row("correct", retrieval_hit=True), row("partial"), row("partial"), row("abstain", blocked=True)]
    s = summarize(rows)
    assert (s["n"], s["correct"], s["partial"], s["wrong"], s["abstain"]) == (4, 0.25, 0.5, 0.0, 0.25)
    assert (s["retrieval_hit"], s["blocked"], s["hallucination"]) == (0.25, 0.25, 0.0)
    assert s["score"] == 50.0  # (0.25 + 0.5×0.5) × 100


def test_run_summary_skips_failed_items():
    item = NS(id="testset-1", metadata={"topic": "짐 보관"}, input={"question": "q"}, expected_output={"answer": "a"})
    ok = NS(item=item, output={"reply": "r", "intent": "faq", "blocked": False},
            evaluations=[Evaluation(name="grade", value="correct"), Evaluation(name="hallucination", value=False),
                         Evaluation(name="retrieval_hit", value=True)])
    failed = NS(item=item, output=None, evaluations=[])
    ev = {e.name: e.value for e in run_summary(item_results=[ok, failed])}
    assert ev["correct_rate"] == 1.0 and ev["score"] == 100.0
