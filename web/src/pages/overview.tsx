import { useState } from "react"
import { ArrowRight, MessageSquareWarning, ThumbsDown } from "lucide-react"
import { Bar, BarChart, CartesianGrid, LabelList, XAxis, YAxis } from "recharts"
import { Link } from "react-router"

import {
  Delta,
  Empty,
  ErrorState,
  GradeLabel,
  Legend,
  LoadingGrid,
  OutcomeLabel,
  PageHeader,
  PeriodToggle,
  StackBar,
  StatCard,
} from "@/components/common"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { GRADE, NODE_LABEL, OUTCOME, pct, secs, usd, useApi, when, type Grade, type Outcome, type Overview } from "@/lib/api"

const OUTCOMES = Object.keys(OUTCOME) as Outcome[]
const dailyConfig = Object.fromEntries(OUTCOMES.map((o) => [o, OUTCOME[o]])) satisfies ChartConfig
// 범례·툴팁을 이름순이 아닌 고정 순서로 (색은 항목을 따라간다)
const byOutcome = (item: { dataKey?: unknown }) => OUTCOMES.indexOf(item.dataKey as Outcome)
const nodeConfig = { p50_ms: { label: "p50", color: "var(--series-1)" } } satisfies ChartConfig

function countDelta(cur: number, prev: number, days: number, good = true) {
  if (!prev) return <Delta diff={null} text="" />
  const d = cur - prev
  return <Delta diff={d} good={good} text={`${d > 0 ? "+" : ""}${d} · 이전 ${days}일 대비`} />
}

function rateDelta(cur: number | null, prev: number | null, good = true) {
  if (cur == null || prev == null) return <Delta diff={null} text="" />
  const d = (cur - prev) * 100
  return <Delta diff={d} good={good} text={`${d > 0 ? "+" : ""}${d.toFixed(1)}%p`} />
}

function ratioDelta(cur: number | null, prev: number | null, good: boolean) {
  if (cur == null || !prev) return <Delta diff={null} text="" />
  const d = (cur - prev) / prev
  return <Delta diff={d} good={good} text={`${d > 0 ? "+" : ""}${(d * 100).toFixed(0)}%`} />
}

export function OverviewPage() {
  const [days, setDays] = useState(7)
  const { data, error } = useApi<Overview>(`/api/overview?days=${days}`)

  return (
    <div className="space-y-6">
      <PageHeader
        title="개요"
        description="봇이 얼마나 답하고, 어디서 막히고, 얼마나 쓰는지"
        actions={<PeriodToggle value={days} onChange={setDays} />}
      />
      {error ? <ErrorState message={error} /> : !data ? <LoadingGrid cards={6} /> : <Body data={data} />}
    </div>
  )
}

function Body({ data }: { data: Overview }) {
  const { current: c, previous: p, days } = data

  return (
    <>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="질문 수" value={c.questions.toLocaleString()} delta={countDelta(c.questions, p.questions, days)} />
        <StatCard
          label="문서 질문 해결률"
          hint="문서로 답해야 하는 질문 중, 근거 검사를 통과해 실제로 답한 비율. 나머지는 '찾지 못했어요'로 답했다."
          value={pct(c.resolution_rate)}
          delta={rateDelta(c.resolution_rate, p.resolution_rate)}
          sub={<span>{c.answered} / {c.answered + c.not_found}건</span>}
        />
        <StatCard
          label="확인 필요"
          hint="찾지 못함 + 담당자 호출 + 오류 + 👎 받은 답변. 문서를 보강하거나 담당자가 답해야 하는 질문."
          value={c.needs_check}
          delta={countDelta(c.needs_check, p.needs_check, days, false)}
        />
        <StatCard
          label="직원 만족도"
          hint="슬랙에서 👍/👎 를 누른 답변 중 👍 비율"
          value={pct(c.satisfaction)}
          delta={rateDelta(c.satisfaction, p.satisfaction)}
          sub={<span>👍 {c.thumbs_up} · 👎 {c.thumbs_down}</span>}
        />
        <StatCard
          label="응답 시간 (중앙값)"
          hint="질문을 받고 답을 만들기까지 걸린 시간. 절반의 질문이 이 시간 안에 끝났다."
          value={secs(c.p50_ms)}
          delta={ratioDelta(c.p50_ms, p.p50_ms, false)}
          sub={<span>p95 {secs(c.p95_ms)}</span>}
        />
        <StatCard
          label="Claude 비용"
          value={usd(c.cost)}
          delta={ratioDelta(c.cost, p.cost, false)}
          sub={<span>질문당 {usd(c.questions ? c.cost / c.questions : null)}</span>}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>일별 질문</CardTitle>
            <CardDescription>봇이 어떻게 처리했는지로 나눠서</CardDescription>
          </CardHeader>
          <CardContent>
            {c.questions === 0 ? (
              <Empty>이 기간에 질문이 없어요</Empty>
            ) : (
              <ChartContainer config={dailyConfig} className="aspect-auto h-64 w-full">
                <BarChart data={data.daily} margin={{ left: -20, right: 4 }}>
                  <CartesianGrid vertical={false} />
                  <XAxis
                    dataKey="day"
                    tickLine={false}
                    axisLine={false}
                    tickMargin={8}
                    minTickGap={16}
                    tickFormatter={(d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8))}`}
                  />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={40} />
                  <ChartTooltip cursor={false} content={<ChartTooltipContent />} itemSorter={byOutcome} />
                  <ChartLegend content={<ChartLegendContent />} itemSorter={byOutcome} />
                  {OUTCOMES.map((o, i) => (
                    <Bar
                      key={o}
                      dataKey={o}
                      stackId="a"
                      fill={`var(--color-${o})`}
                      maxBarSize={24}
                      stroke="var(--card)"
                      strokeWidth={1}
                      radius={i === OUTCOMES.length - 1 ? [4, 4, 0, 0] : 0}
                    />
                  ))}
                </BarChart>
              </ChartContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>확인이 필요한 질문</CardTitle>
            <CardDescription>찾지 못함 · 담당자 호출 · 오류 · 👎</CardDescription>
            <CardAction>
              <Link to="/conversations" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                전체 <ArrowRight className="size-3" />
              </Link>
            </CardAction>
          </CardHeader>
          <CardContent className="px-2">
            {data.issues.length === 0 ? (
              <Empty>확인할 질문이 없어요</Empty>
            ) : (
              <ul className="space-y-0.5">
                {data.issues.map((i) => (
                  <li key={i.id}>
                    <Link
                      to={`/conversations?id=${i.id}`}
                      className="block space-y-1 rounded-md px-2 py-2 transition-colors hover:bg-muted"
                    >
                      <div className="line-clamp-1 text-sm">{i.question}</div>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <OutcomeLabel outcome={i.outcome} />
                        {i.thumbs_down && <ThumbsDown className="size-3 text-delta-bad" aria-label="👎 받음" />}
                        {i.comment && <MessageSquareWarning className="size-3" aria-label="코멘트 있음" />}
                        <span className="ml-auto tabular-nums">{when(i.created_at)}</span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>단계별 응답 시간</CardTitle>
            <CardDescription>중앙값. 어느 단계가 느린가</CardDescription>
          </CardHeader>
          <CardContent>
            {data.nodes.length === 0 ? (
              <Empty>기록이 없어요</Empty>
            ) : (
              <ChartContainer config={nodeConfig} className="aspect-auto w-full" style={{ height: data.nodes.length * 36 + 8 }}>
                <BarChart data={data.nodes} layout="vertical" margin={{ left: 0, right: 48 }}>
                  <XAxis type="number" hide />
                  <YAxis
                    type="category"
                    dataKey="node"
                    tickLine={false}
                    axisLine={false}
                    width={84}
                    tickFormatter={(n: string) => NODE_LABEL[n] ?? n}
                  />
                  <ChartTooltip
                    cursor={false}
                    content={<ChartTooltipContent formatter={(v) => secs(Number(v))} labelFormatter={(n) => NODE_LABEL[n] ?? n} />}
                  />
                  <Bar dataKey="p50_ms" fill="var(--color-p50_ms)" radius={4} maxBarSize={20}>
                    <LabelList
                      dataKey="p50_ms"
                      position="right"
                      className="fill-foreground"
                      fontSize={12}
                      formatter={(v) => secs(Number(v))}
                    />
                  </Bar>
                </BarChart>
              </ChartContainer>
            )}
          </CardContent>
        </Card>

        <LatestEval data={data} />
      </div>
    </>
  )
}

function LatestEval({ data }: { data: Overview }) {
  const e = data.latest_eval
  return (
    <Card>
      <CardHeader>
        <CardTitle>최근 시험</CardTitle>
        <CardDescription>{e ? `${e.name} · ${e.summary.n}문제 · ${when(e.created_at)}` : "아직 시험 기록이 없어요"}</CardDescription>
        <CardAction>
          <Link to="/evals" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            자세히 <ArrowRight className="size-3" />
          </Link>
        </CardAction>
      </CardHeader>
      {e && (
        <CardContent className="space-y-5">
          <div className="flex items-baseline gap-2">
            <span className="text-4xl font-semibold tracking-tight">{e.summary.score.toFixed(1)}</span>
            <span className="text-sm text-muted-foreground">점 / 100</span>
          </div>
          <div className="space-y-2">
            <StackBar
              className="h-3"
              parts={(Object.keys(GRADE) as Grade[]).map((g) => ({
                key: g,
                label: GRADE[g].label,
                value: e.summary[g],
                color: GRADE[g].color,
              }))}
            />
            <Legend
              items={(Object.keys(GRADE) as Grade[]).map((g) => ({
                label: GRADE[g].label,
                color: GRADE[g].color,
                value: pct(e.summary[g]),
              }))}
            />
          </div>
          <div className="grid grid-cols-3 gap-2 border-t pt-4 text-sm">
            <Mini label="환각률" value={pct(e.summary.hallucination, 1)} />
            <Mini label="검색 적중률" value={pct(e.summary.retrieval_hit)} />
            <Mini label="근거 검사 차단율" value={pct(e.summary.blocked)} />
          </div>
          <p className="text-xs text-muted-foreground">
            점수 = 정답 + 부분정답×0.5. <GradeLabel grade="correct" /> 기준은 호스트의 실제 답.
          </p>
        </CardContent>
      )}
    </Card>
  )
}

const Mini = ({ label, value }: { label: string; value: string }) => (
  <div>
    <div className="text-xs text-muted-foreground">{label}</div>
    <div className="font-medium tabular-nums">{value}</div>
  </div>
)
