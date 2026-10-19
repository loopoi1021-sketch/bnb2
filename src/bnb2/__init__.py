import sys

from dotenv import load_dotenv

USAGE = """사용법:
  uv run bnb2 ingest            문서 적재 (kb → 청크 → 임베딩 → pgvector)
  uv run bnb2 search "질문"     검색 결과 top-4 보기"""


def main() -> None:
    load_dotenv()
    args = sys.argv[1:]
    if args[:1] == ["ingest"]:
        from bnb2.ingest import run

        run()
    elif args[:1] == ["search"] and len(args) > 1:
        from bnb2.retrieve import run

        run(" ".join(args[1:]))
    else:
        print(USAGE)
