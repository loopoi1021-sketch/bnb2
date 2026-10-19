"""2단계: 문서 적재. kb/*.md → `##` 섹션 청크 → Voyage 임베딩 → pgvector."""

import os
import re
from pathlib import Path

import psycopg
import voyageai

EMBED_MODEL = "voyage-4"
EMBED_DIM = 1024


def kb_dir() -> Path:
    # kb/ 는 실제 숙소 정보(git 제외). 없으면 공개용 견본 kb.example/ 로 동작한다.
    return Path("kb") if Path("kb").is_dir() else Path("kb.example")


def chunk_markdown(name: str, text: str) -> list[dict]:
    """`## 항목` 하나 = 청크 하나. 오버랩 없음.

    임베딩할 글(content) 앞에 문서 제목과 항목 제목을 붙인다.
    본문에 주제 단어가 빠진 항목("1인당 2장씩")을 위한 대비책. 효과는 6단계에서 측정.
    """
    m = re.search(r"^# (.+)$", text, re.M)
    doc = m.group(1).strip() if m else name
    chunks = []
    for sec in re.split(r"^## ", text, flags=re.M)[1:]:  # [0] 은 첫 `##` 앞부분(문서 제목)
        heading, _, body = sec.partition("\n")
        heading, body = heading.strip(), body.strip()
        chunks.append({
            "id": f"{name}#{heading}",
            "source": f"{name} > {heading}",
            "content": f"{doc} - {heading}\n{body}",
        })
    return chunks


def load_chunks(root: Path) -> list[dict]:
    return [c for f in sorted(root.glob("*.md")) for c in chunk_markdown(f.name, f.read_text())]


def embed_documents(texts: list[str]) -> list[list[float]]:
    # 무료 한도(카드 미등록 시 분당 3회) 때문에 전부 한 번에 보낸다. 한 번에 최대 1,000개.
    client = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
    return client.embed(texts, model=EMBED_MODEL, input_type="document").embeddings


def save(chunks: list[dict], vectors: list[list[float]]) -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS chunks (
                id        text PRIMARY KEY,
                source    text NOT NULL,
                content   text NOT NULL,
                embedding vector({EMBED_DIM}) NOT NULL
            )""")
        # 문서를 고치면 전체를 다시 넣는다. 55개라 부분 갱신보다 단순하고 지운 항목도 남지 않는다.
        conn.execute("TRUNCATE chunks")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (id, source, content, embedding) VALUES (%s, %s, %s, %s::vector)",
                [(c["id"], c["source"], c["content"], str(v)) for c, v in zip(chunks, vectors)],
            )


def run() -> None:
    root = kb_dir()
    chunks = load_chunks(root)
    print(f"📂 {root}/ 에서 청크 {len(chunks)}개")
    for c in chunks:
        print(f"  - {c['source']}  ({len(c['content'])}자)")
    vectors = embed_documents([c["content"] for c in chunks])
    print(f"🧮 Voyage {EMBED_MODEL} 임베딩 {len(vectors)}개 × {len(vectors[0])}차원")
    save(chunks, vectors)
    print("💾 pgvector chunks 표에 저장 완료")
