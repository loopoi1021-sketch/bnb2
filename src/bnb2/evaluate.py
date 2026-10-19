"""6단계: 평가. 시험지(실제 게스트 질문 + 호스트 실제 답)를 Langfuse Dataset 으로 올리고 실험한다."""

import json
from pathlib import Path

from bnb2.tracing import client, mask_text

DATASET = "bnb2-testset"
TESTSET = Path("data/testset.jsonl")  # 기존 bnb 에서 복사. 실제 대화라 git 제외


def load_testset() -> list[dict]:
    return [json.loads(line) for line in TESTSET.read_text().splitlines() if line.strip()]


def to_item(row: dict) -> dict:
    """원문 메시지(guest)와 대화방 ID(thread)는 올리지 않는다. 한국어로 정리된 질문과 답만 쓴다."""
    return {
        "id": f"testset-{row['id']}",  # 같은 id 로 다시 올리면 새로 생기지 않고 덮어쓴다
        "input": {"question": mask_text(row["question_ko"])},
        "expected_output": {"answer": mask_text(row["answer_ko"])},
        "metadata": {"topic": row["topic"], "kind": row["kind"], "at": row["at"][:10]},
    }


def upload() -> None:
    lf = client()
    rows = load_testset()
    lf.create_dataset(
        name=DATASET,
        description="실제 게스트 질문 94개(2026-07 이후)와 호스트의 실제 답. 문서 보강(~2026-06)과 기간 분리",
    )
    for row in rows:
        lf.create_dataset_item(dataset_name=DATASET, **to_item(row))
    lf.flush()
    print(f"📤 Langfuse Dataset '{DATASET}' 에 {len(rows)}문제 등록")
