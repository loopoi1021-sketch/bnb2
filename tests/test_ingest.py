from bnb2.ingest import chunk_markdown


def test_chunk_per_section_with_titles():
    text = "# 퇴실 안내\n\n## 퇴실할 때\n11시입니다.\n\n## 퇴실 전 할 일\n수건은 수거함에.\n"
    chunks = chunk_markdown("07.md", text)
    assert [c["id"] for c in chunks] == ["07.md#퇴실할 때", "07.md#퇴실 전 할 일"]
    assert chunks[0]["source"] == "07.md > 퇴실할 때"
    assert chunks[0]["content"] == "퇴실 안내 - 퇴실할 때\n11시입니다."
    # 오버랩 없음: 다음 섹션 내용이 섞이지 않는다
    assert "수건" not in chunks[0]["content"]
