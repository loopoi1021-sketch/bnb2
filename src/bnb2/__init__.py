import sys

from dotenv import load_dotenv

USAGE = """사용법:
  uv run bnb2 ingest            문서 적재 (kb → 청크 → 임베딩 → pgvector)
  uv run bnb2 search "질문"     검색 결과 top-4 보기
  uv run bnb2 ask "질문"        LangGraph 전체 실행, 노드별 State 변화 보기
  uv run bnb2 graph             그래프 구조를 Mermaid 로 출력
  uv run bnb2 dataset           시험지 94문제를 Langfuse Dataset 으로 등록
  uv run bnb2 eval 이름 [개수]   시험 + 채점 (개수를 주면 주제가 다른 문제 n개만)
  uv run bnb2 report 이름       저장된 시험 결과로 지표만 다시 집계 (API 호출 없음)
  uv run bnb2 dashboard         Langfuse 대시보드 생성 (다시 실행하면 새로 만듦)"""


def main() -> None:
    load_dotenv()
    args = sys.argv[1:]
    if args[:1] == ["ingest"]:
        from bnb2.ingest import run

        run()
    elif args[:1] == ["search"] and len(args) > 1:
        from bnb2.retrieve import run

        run(" ".join(args[1:]))
    elif args[:1] == ["ask"] and len(args) > 1:
        from bnb2.graph import run

        run(" ".join(args[1:]))
    elif args[:1] == ["graph"]:
        from bnb2.graph import build

        print(build().get_graph().draw_mermaid())
    elif args[:1] == ["dataset"]:
        from bnb2.evaluate import upload

        upload()
    elif args[:1] == ["eval"] and len(args) > 1:
        from bnb2.evaluate import experiment

        experiment(int(args[2]) if len(args) > 2 else None, run_name=args[1])
    elif args[:1] == ["report"] and len(args) > 1:
        from bnb2.evaluate import report

        report(args[1])
    elif args[:1] == ["dashboard"]:
        from bnb2.dashboard import build

        build()
    else:
        print(USAGE)
