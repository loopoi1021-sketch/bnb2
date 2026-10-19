import sys

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "ingest":
        from bnb2.ingest import run

        run()
    else:
        print("사용법: uv run bnb2 ingest")
