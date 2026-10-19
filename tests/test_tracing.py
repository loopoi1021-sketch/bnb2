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
