from bnb2.tracing import mask


def test_mask_patterns_and_terms(monkeypatch):
    monkeypatch.setenv("MASK_TERMS", "비밀번호1234, 마포구 어딘가 ")
    data = {
        "question": "010-1234-5678 로 연락 주세요, a.b@gmail.com",
        "chunks": [{"content": "와이파이 비밀번호1234, 주소 마포구 어딘가"}],
        "score": 0.61,
    }
    assert mask(data=data) == {
        "question": "[전화번호] 로 연락 주세요, [이메일]",
        "chunks": [{"content": "와이파이 [비공개], 주소 [비공개]"}],
        "score": 0.61,
    }


def test_dataset_item_drops_raw_guest_message():
    from bnb2.evaluate import to_item

    row = {"id": 7, "thread": "t1", "at": "2026-07-03T10:00:00Z", "kind": "question", "topic": "짐 보관",
           "guest": "Hi, call me 010-1111-2222", "question_ko": "짐 맡길 수 있나요?", "answer_ko": "네 가능해요"}
    item = to_item(row)
    assert item["id"] == "testset-7"
    assert item["input"] == {"question": "짐 맡길 수 있나요?"}
    assert "guest" not in str(item) and "t1" not in str(item) and "010-1111" not in str(item)
