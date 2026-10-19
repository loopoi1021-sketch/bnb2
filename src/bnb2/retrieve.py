"""3단계: 검색. 질문 → Voyage 임베딩(query) → pgvector 에서 가까운 청크 top-k."""

import os

import psycopg
import voyageai

from bnb2.ingest import EMBED_MODEL

TOP_K = 4


def embed_query(question: str) -> list[float]:
    # 문서는 input_type="document", 질문은 "query". 같은 모델이어야 같은 '의미 지도'에서 비교된다.
    client = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
    return client.embed([question], model=EMBED_MODEL, input_type="query").embeddings[0]


def search(question: str, k: int = TOP_K) -> list[dict]:
    """가까운 순으로 k개. score = 코사인 유사도(1 - 코사인 거리), 1에 가까울수록 비슷하다."""
    vec = str(embed_query(question))
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        rows = conn.execute(
            """SELECT id, source, content, 1 - (embedding <=> %s::vector) AS score
               FROM chunks ORDER BY embedding <=> %s::vector LIMIT %s""",
            (vec, vec, k),
        ).fetchall()
    return [{"id": r[0], "source": r[1], "content": r[2], "score": round(r[3], 3)} for r in rows]


def run(question: str) -> None:
    print(f"❓ {question}\n")
    for i, c in enumerate(search(question), 1):
        print(f"[{i}] {c['score']:.3f}  {c['source']}")
        print(f"    {c['content'].splitlines()[-1][:80]}")
