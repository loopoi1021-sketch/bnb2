from bnb2.slack import clean, make_reply, needs_owner


def test_clean_removes_mention():
    assert clean("<@U0ABC123> 수건 몇 장 채워둬?") == "수건 몇 장 채워둬?"


def test_owner_mentioned_only_when_human_needed(monkeypatch):
    monkeypatch.setenv("SLACK_OWNER_ID", "U999")
    ok = {"intent": "faq", "grounded": True, "direct": True, "reply": "오후 2시 30분까지예요"}
    blocked = {"intent": "faq", "grounded": True, "direct": False, "reply": "문서에서 찾지 못했어요"}
    escalate = {"intent": "escalate", "reply": "🚨 담당자 판단이 필요한 질문이에요"}
    assert not needs_owner(ok) and make_reply(ok) == "오후 2시 30분까지예요"
    assert make_reply(blocked).endswith("<@U999>")
    assert make_reply(escalate).endswith("<@U999>")


def test_buttons_carry_trace_id_and_hide_on_error():
    from bnb2.slack import reply_blocks

    import json

    blocks = reply_blocks("오후 2시 30분까지예요", "trace123", "짐 몇 시까지?")
    assert [json.loads(e["value"]) for e in blocks[1]["elements"]] == [{"t": "trace123", "q": "짐 몇 시까지?"}] * 2
    assert [b["type"] for b in reply_blocks("⚠️ 지금은 답변할 수 없어요", None)] == ["section"]


def test_mark_feedback_replaces_buttons():
    from bnb2.slack import mark_feedback, reply_blocks

    calls = {}
    client = type("C", (), {"chat_update": lambda self, **kw: calls.update(kw)})()
    body = {"user": {"id": "U1"}, "channel": {"id": "C1"},
            "message": {"ts": "1.2", "text": "답", "blocks": reply_blocks("답", "t")}}
    mark_feedback(client, body, "👍 피드백 고마워요")
    assert [b["type"] for b in calls["blocks"]] == ["section", "context"]
    assert calls["ts"] == "1.2" and calls["channel"] == "C1"


def test_notify_owner_dm(monkeypatch):
    import bnb2.slack as slack

    monkeypatch.setenv("SLACK_OWNER_ID", "U999")
    monkeypatch.setattr(slack, "langfuse", lambda: type("L", (), {"get_trace_url": lambda self, trace_id: "http://lf/t"})())
    sent = {}
    client = type("C", (), {"chat_postMessage": lambda self, **kw: sent.update(kw)})()
    slack.notify_owner(client, "U1", "담배 어디서?", "문서에서 찾지 못했어요", "1층 주차장 옆", "t1")
    assert sent["channel"] == "U999"
    assert "담배 어디서?" in sent["text"] and "1층 주차장 옆" in sent["text"] and "http://lf/t" in sent["text"]
