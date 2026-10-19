from bnb2.graph import NOT_FOUND, check, known_sources, route


def test_route_by_intent():
    assert route({"intent": "faq"}) == "retrieve"
    assert route({"intent": "escalate"}) == "escalate"
    assert route({"intent": "chitchat"}) == "chitchat"


def test_empty_answer_skips_claude_and_says_not_found():
    # 빈 답이면 Claude 호출 없이 바로 "못 찾음" (키가 없어도 통과해야 함)
    out = check({"answer": "", "chunks": [], "sources": []})
    assert out["grounded"] is False and out["direct"] is False and out["reply"] == NOT_FOUND


def test_only_retrieved_sources_are_cited():
    state = {"chunks": [{"source": "05.md > 수건"}, {"source": "07.md > 퇴실"}],
             "sources": ["[출처: 05.md > 수건]", "99.md > 지어낸 출처"]}
    assert known_sources(state) == ["05.md > 수건"]
