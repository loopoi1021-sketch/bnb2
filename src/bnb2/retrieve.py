"""3단계: 검색. 질문 → Voyage 임베딩(query) → pgvector 에서 가까운 청크 top-k."""

import os
import time

import psycopg
import voyageai

from bnb2.ingest import EMBED_MODEL

TOP_K = 4

# 시험(6단계)처럼 질문이 많을 때 미리 한 번에 임베딩해 두는 곳. Voyage 무료 한도가 분당 3회라서.
_query_cache: dict[str, list[float]] = {}


def _embed(texts: list[str]) -> list[list[float]]:
    # 문서는 input_type="document", 질문은 "query". 같은 모델이어야 같은 '의미 지도'에서 비교된다.
    client = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
    # shortcut: 무료 한도(분당 3회)에 걸리면 20초씩 기다려 최대 3번 재시도. Voyage 에 카드를 등록하면 필요 없다
    for wait in (20, 20, 20, None):
        try:
            return client.embed(texts, model=EMBED_MODEL, input_type="query").embeddings
        except voyageai.error.RateLimitError:
            if wait is None:
                raise
            time.sleep(wait)


def warm_query_cache(questions: list[str]) -> None:
    """질문 여러 개를 Voyage 한 번 호출로 임베딩해 둔다 (최대 1,000개)."""
    todo = [q for q in dict.fromkeys(questions) if q not in _query_cache]
    if todo:
        _query_cache.update(zip(todo, _embed(todo)))


def embed_query(question: str) -> list[float]:
    if question not in _query_cache:
        _query_cache[question] = _embed([question])[0]
    return _query_cache[question]


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
