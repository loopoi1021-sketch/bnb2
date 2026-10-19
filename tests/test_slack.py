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
