"""6-4단계: Langfuse 대시보드를 코드로 만든다 (Langfuse unstable API).

다시 실행하면 같은 이름의 대시보드와 위젯을 지우고 새로 만든다.
"""

from langfuse.api.unstable.dashboard_widgets import (
    DashboardWidgetDimension as Dim,
)
from langfuse.api.unstable.dashboard_widgets import (
    DashboardWidgetFilter as Filter,
)
from langfuse.api.unstable.dashboard_widgets import (
    DashboardWidgetMetric as Metric,
)
from langfuse.api.unstable.dashboards import CreateDashboardPlacementRequest_Widget as Placement

from bnb2.tracing import client

DASHBOARD = "bnb2 품질"
PREFIX = "bnb2 · "  # 이 대시보드가 만든 위젯 표시. 다시 만들 때 이 이름으로 찾아 지운다
NODES = ["classify", "retrieve", "generate", "check", "escalate", "chitchat"]


def eq(column: str, value: str) -> Filter:
    return Filter(column=column, operator="=", type="string", value=value)


def any_of(column: str, values: list[str]) -> Filter:
    return Filter(column=column, operator="any of", type="stringOptions", value=values)


# (이름, 설명, view, dimensions, metrics, filters, chart, x, y, w, h) — 12칸 격자
WIDGETS = [
    ("채점 분포", "시험 grade: correct / partial / wrong / abstain",
     "scores-categorical", ["stringValue"], [("count", "count")], [eq("name", "grade")], "PIE", 0, 0, 4, 6),
    ("환각률 · 검색 적중률 · 차단율", "시험 boolean 점수의 평균 (1 = 100%)",
     "scores-numeric", ["name"], [("value", "avg")],
     [any_of("name", ["hallucination", "retrieval_hit", "blocked"])], "HORIZONTAL_BAR", 4, 0, 4, 6),
    ("질문 분류", "그래프가 어느 길로 갔나 (retrieve = 문서 질문)",
     "observations", ["name"], [("count", "count")], [any_of("name", ["retrieve", "escalate", "chitchat"])],
     "PIE", 8, 0, 4, 6),
    ("질문 수 (일별)", "그래프 실행 횟수",
     "observations", [], [("count", "count")], [eq("name", "classify")], "BAR_TIME_SERIES", 0, 6, 6, 6),
    ("노드별 응답 시간 (p50)", "어느 단계가 느린가 (밀리초, 1000 = 1초)",
     "observations", ["name"], [("latency", "p50")], [any_of("name", NODES)], "HORIZONTAL_BAR", 6, 6, 6, 6),
    ("Claude 비용 (일별)", "답변 모델 호출 비용 합계 (USD)",
     "observations", [], [("totalCost", "sum")], [eq("type", "GENERATION")], "BAR_TIME_SERIES", 0, 12, 6, 6),
    ("Claude 토큰 (모델별)", "모델별 토큰 합계",
     "observations", ["providedModelName"], [("totalTokens", "sum")], [eq("type", "GENERATION")],
     "HORIZONTAL_BAR", 6, 12, 6, 6),
    ("직원 만족도 (👍 비율)", "슬랙 👍=1, 👎=0 의 평균",
     "scores-numeric", [], [("value", "avg")], [eq("name", "user_feedback")], "NUMBER", 0, 18, 4, 6),
    ("👍/👎 개수", "슬랙 피드백 수",
     "scores-numeric", ["value"], [("count", "count")], [eq("name", "user_feedback")], "PIE", 4, 18, 4, 6),
]


def build() -> None:
    api = client().api.unstable
    for d in api.dashboards.list().data:
        if d.name == DASHBOARD:
            api.dashboards.delete(d.id)
    for w in api.dashboard_widgets.list().data:
        if w.name.startswith(PREFIX):
            api.dashboard_widgets.delete(w.id)

    dash = api.dashboards.create(name=DASHBOARD, description="bnb2 사내 Q&A 봇: 시험 점수, 사용량, 속도, 비용")
    for name, desc, view, dims, metrics, filters, chart, x, y, w, h in WIDGETS:
        widget = api.dashboard_widgets.create(
            name=PREFIX + name, description=desc, view=view, dimensions=[Dim(field=f) for f in dims],
            metrics=[Metric(measure=m, agg=a) for m, a in metrics], filters=filters, chart_type=chart,
        )
        api.dashboards.add_placement(dash.id, request=Placement(widget_id=widget.id, x=x, y=y, width=w, height=h))
        print(f"  + {name}")
    print(f"📊 대시보드 '{DASHBOARD}' 생성 (위젯 {len(WIDGETS)}개)")
