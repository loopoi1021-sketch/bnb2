import { useEffect, useState, type ReactNode } from "react"
import { ChevronLeft, ChevronRight, ExternalLink, Search, ThumbsDown, ThumbsUp } from "lucide-react"
import { useSearchParams } from "react-router"

import {
  Empty,
  ErrorState,
  Field,
  OutcomeLabel,
  PageHeader,
  PeriodToggle,
  Section,
} from "@/components/common"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  CHANNEL,
  NODE_LABEL,
  OUTCOME,
  secs,
  usd,
  useApi,
  when,
  type Chunk,
  type ConversationDetail,
  type ConversationRow,
  type Outcome,
} from "@/lib/api"
import { cn } from "@/lib/utils"

const PAGE = 50

export function FilterSelect({
  value,
  onChange,
  label,
  options,
}: {
  value: string
  onChange: (v: string) => void
  label: string
  options: [string, string][]
}) {
  return (
    <Select value={value || "all"} onValueChange={(v) => onChange(v === "all" ? "" : v)}>
      <SelectTrigger size="sm" className="min-w-32" aria-label={label}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">{label}: 전체</SelectItem>
        {options.map(([v, l]) => (
          <SelectItem key={v} value={v}>
            {l}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function Conversations() {
  const [params, setParams] = useSearchParams()
  const get = (k: string, d = "") => params.get(k) ?? d
  const set = (patch: Record<string, string>) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        for (const [k, v] of Object.entries(patch)) {
          if (v) next.set(k, v)
          else next.delete(k)
        }
        if (!("page" in patch) && !("id" in patch)) next.delete("page") // 필터가 바뀌면 첫 페이지로
        return next
      },
      { replace: "id" in patch || "q" in patch },
    )

  const days = Number(get("days", "30"))
  const page = Number(get("page", "0"))
  const [search, setSearch] = useState(get("q"))
  useEffect(() => {
    const t = setTimeout(() => search !== get("q") && set({ q: search }), 300)
    return () => clearTimeout(t)
  }, [search]) // eslint-disable-line react-hooks/exhaustive-deps

  const qs = new URLSearchParams({ days: String(days), limit: String(PAGE), offset: String(page * PAGE) })
  for (const k of ["outcome", "channel", "feedback", "q"]) if (get(k)) qs.set(k, get(k))
  const { data, error, loading } = useApi<{ total: number; rows: ConversationRow[] }>(`/api/conversations?${qs}`)

  return (
    <div className="space-y-6">
      <PageHeader
        title="대화"
        description="봇이 받은 모든 질문. 행을 누르면 검색된 문서, 근거 검사, 피드백까지 한 번에 봅니다"
        actions={<PeriodToggle value={days} onChange={(d) => set({ days: String(d) })} />}
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="질문·답변 검색"
            className="h-8 pl-8"
          />
        </div>
        <FilterSelect
          label="결과"
          value={get("outcome")}
          onChange={(v) => set({ outcome: v })}
          options={(Object.keys(OUTCOME) as Outcome[]).map((o) => [o, OUTCOME[o].label])}
        />
        <FilterSelect
          label="피드백"
          value={get("feedback")}
          onChange={(v) => set({ feedback: v })}
          options={[
            ["down", "👎 받음"],
            ["up", "👍 받음"],
            ["none", "피드백 없음"],
          ]}
        />
        <FilterSelect
          label="경로"
          value={get("channel")}
          onChange={(v) => set({ channel: v })}
          options={Object.entries(CHANNEL)}
        />
        {data && <span className="ml-auto text-sm text-muted-foreground tabular-nums">{data.total.toLocaleString()}건</span>}
      </div>

      {error ? (
        <ErrorState message={error} />
      ) : (
        <Card className={cn("overflow-hidden py-0 transition-opacity", loading && data && "opacity-60")}>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-28 pl-4">시각</TableHead>
                <TableHead>질문 · 답변</TableHead>
                <TableHead className="w-28">결과</TableHead>
                <TableHead className="w-16 text-center">피드백</TableHead>
                <TableHead className="w-24 text-right">검색 유사도</TableHead>
                <TableHead className="w-20 text-right">응답</TableHead>
                <TableHead className="w-24 pr-4 text-right">비용</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {!data
                ? Array.from({ length: 8 }, (_, i) => (
                    <TableRow key={i}>
                      <TableCell colSpan={7} className="px-4">
                        <Skeleton className="h-9" />
                      </TableCell>
                    </TableRow>
                  ))
                : data.rows.map((r) => (
                    <TableRow
                      key={r.id}
                      className="cursor-pointer"
                      data-state={get("id") === String(r.id) ? "selected" : undefined}
                      onClick={() => set({ id: String(r.id) })}
                    >
                      <TableCell className="pl-4 align-top text-xs text-muted-foreground tabular-nums">
                        {when(r.created_at)}
                        {r.channel !== "slack" && <div className="mt-0.5">{CHANNEL[r.channel] ?? r.channel}</div>}
                      </TableCell>
                      <TableCell className="max-w-0 whitespace-normal">
                        <div className="truncate font-medium">{r.question}</div>
                        <div className="truncate text-xs text-muted-foreground">{r.reply?.split("\n📄")[0]}</div>
                        {r.comment && <div className="truncate text-xs text-delta-bad">💬 {r.comment}</div>}
                      </TableCell>
                      <TableCell className="align-top">
                        <OutcomeLabel outcome={r.outcome} />
                      </TableCell>
                      <TableCell className="text-center align-top">
                        {r.feedback === "down" ? (
                          <ThumbsDown className="mx-auto size-4 text-delta-bad" aria-label="👎" />
                        ) : r.feedback === "up" ? (
                          <ThumbsUp className="mx-auto size-4 text-delta-good" aria-label="👍" />
                        ) : (
                          <span className="text-muted-foreground">–</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right align-top tabular-nums">
                        {r.top_score == null ? "–" : r.top_score.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right align-top tabular-nums">{secs(r.total_ms)}</TableCell>
                      <TableCell className="pr-4 text-right align-top tabular-nums">{usd(r.cost_usd)}</TableCell>
                    </TableRow>
                  ))}
            </TableBody>
          </Table>
          {data && data.rows.length === 0 && <Empty>조건에 맞는 질문이 없어요</Empty>}
        </Card>
      )}

      {data && data.total > PAGE && (
        <div className="flex items-center justify-end gap-2 text-sm text-muted-foreground">
          <span className="tabular-nums">
            {page * PAGE + 1}–{Math.min((page + 1) * PAGE, data.total)} / {data.total}
          </span>
          <Button variant="outline" size="icon-sm" disabled={page === 0} onClick={() => set({ page: String(page - 1) })}>
            <ChevronLeft />
          </Button>
          <Button
            variant="outline"
            size="icon-sm"
            disabled={(page + 1) * PAGE >= data.total}
            onClick={() => set({ page: String(page + 1) })}
          >
            <ChevronRight />
          </Button>
        </div>
      )}

      <Sheet open={!!get("id")} onOpenChange={(open) => !open && set({ id: "" })}>
        <SheetContent className="w-full gap-0 overflow-y-auto data-[side=right]:sm:max-w-2xl">
          {get("id") && <Detail id={get("id")} />}
        </SheetContent>
      </Sheet>
    </div>
  )
}

const yesNo = (v: boolean | null, yes: string, no: string) =>
  v == null ? "–" : <span className={v ? "text-delta-good" : "text-delta-bad"}>{v ? yes : no}</span>

/** 대화 상세 패널. extra: 직원 피드백 다음에 끼워 넣을 내용 (처리함의 처리 칸) */
export function Detail({ id, extra }: { id: string; extra?: (data: ConversationDetail) => ReactNode }) {
  const { data, error } = useApi<ConversationDetail>(`/api/conversations/${id}`)
  if (error) return <div className="p-6"><ErrorState message={error} /></div>
  if (!data)
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-40" />
        <Skeleton className="h-60" />
      </div>
    )

  const blocked = data.intent === "faq" && data.outcome === "not_found"
  const used = new Set(data.sources ?? [])
  return (
    <>
      <SheetHeader className="border-b p-6">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <OutcomeLabel outcome={data.outcome} />
          <span>·</span>
          <span className="tabular-nums">{when(data.created_at)}</span>
          <span>·</span>
          <span>{data.channel === "slack" ? `슬랙 ${data.slack_user ?? ""}` : (CHANNEL[data.channel] ?? data.channel)}</span>
        </div>
        <SheetTitle className="text-lg leading-snug">{data.question}</SheetTitle>
        <SheetDescription className="sr-only">질문 상세</SheetDescription>
      </SheetHeader>

      <div className="space-y-6 p-6">
        <Section title="봇이 보낸 답">
          <div className="rounded-lg border bg-muted/40 p-3 text-sm whitespace-pre-wrap">{data.reply ?? "–"}</div>
          {data.error && <p className="text-sm text-delta-bad">오류: {data.error}</p>}
        </Section>

        {data.feedback.length > 0 && (
          <Section title="직원 피드백">
            <ul className="space-y-2">
              {data.feedback.map((f) => (
                <li key={f.slack_user} className="rounded-lg border p-3 text-sm">
                  <div className="flex items-center gap-2">
                    {f.good ? <ThumbsUp className="size-4 text-delta-good" /> : <ThumbsDown className="size-4 text-delta-bad" />}
                    <span className="text-muted-foreground">{f.slack_user}</span>
                    <span className="ml-auto text-xs text-muted-foreground tabular-nums">{when(f.created_at)}</span>
                  </div>
                  {f.comment && <p className="mt-2">💬 {f.comment}</p>}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {extra?.(data)}

        <Section title="처리 과정">
          <dl className="divide-y rounded-lg border px-3">
            <Field label="① 분류">
              <Badge variant="secondary">{data.intent ?? "–"}</Badge>
              {data.classify_reason && <p className="mt-1 text-muted-foreground">{data.classify_reason}</p>}
            </Field>
            {data.intent === "faq" && (
              <>
                <Field label="③ 답변 초안">
                  {data.answer ? (
                    <span className={cn(blocked && "text-muted-foreground line-through decoration-delta-bad/60")}>
                      {data.answer}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">문서에서 답을 찾지 못해 비워 둠</span>
                  )}
                </Field>
                <Field label="④ 근거 검사">
                  <div className="flex gap-3">
                    <span>문서 근거 {yesNo(data.grounded, "있음", "없음")}</span>
                    <span>직접 답 {yesNo(data.direct, "예", "아니오")}</span>
                  </div>
                  {data.check_reason && <p className="mt-1 text-muted-foreground">{data.check_reason}</p>}
                </Field>
              </>
            )}
          </dl>
        </Section>

        {data.chunks && data.chunks.length > 0 && (
          <Section title="② 검색된 문서" aside={<span className="text-xs text-muted-foreground">유사도 높은 순</span>}>
            <ul className="space-y-2">
              {data.chunks.map((c) => (
                <ChunkCard key={c.id ?? c.source} chunk={c} used={used.size > 0 && [...used].some((s) => s.includes(c.source))} />
              ))}
            </ul>
          </Section>
        )}

        <Section title="시간 · 비용">
          <dl className="divide-y rounded-lg border px-3">
            {data.latency_ms &&
              Object.entries(data.latency_ms).map(([n, ms]) => (
                <Field key={n} label={NODE_LABEL[n] ?? n}>
                  <span className="tabular-nums">{secs(ms)}</span>
                </Field>
              ))}
            <Field label="전체">
              <span className="font-medium tabular-nums">{secs(data.total_ms)}</span>
            </Field>
            <Field label="토큰 · 비용">
              <span className="tabular-nums">
                입력 {data.input_tokens?.toLocaleString() ?? "–"} · 출력 {data.output_tokens?.toLocaleString() ?? "–"} ·{" "}
                {usd(data.cost_usd)}
              </span>
            </Field>
          </dl>
        </Section>

        {data.trace_url && (
          <Button variant="outline" size="sm" asChild>
            <a href={data.trace_url} target="_blank" rel="noreferrer">
              Langfuse 트레이스 <ExternalLink />
            </a>
          </Button>
        )}
      </div>
    </>
  )
}

export function ChunkCard({ chunk, used }: { chunk: Chunk; used?: boolean }) {
  const [open, setOpen] = useState(false)
  const body = chunk.content.split("\n").slice(1).join("\n").trim() || chunk.content
  return (
    <li className={cn("rounded-lg border p-3", used && "border-series-1/50 bg-series-1/5")}>
      <div className="flex items-center gap-2 text-xs">
        <span className="min-w-0 truncate font-medium">{chunk.source}</span>
        {used && <Badge variant="outline">답에 사용</Badge>}
        {chunk.score != null && (
          <span className="ml-auto flex shrink-0 items-center gap-2 tabular-nums text-muted-foreground">
            <span className="h-1.5 w-12 overflow-hidden rounded-full bg-muted">
              <span className="block h-full rounded-full bg-series-1" style={{ width: `${Math.max(0, chunk.score) * 100}%` }} />
            </span>
            {chunk.score.toFixed(3)}
          </span>
        )}
      </div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn("mt-1.5 block text-left text-sm whitespace-pre-wrap text-muted-foreground", !open && "line-clamp-2")}
        aria-expanded={open}
      >
        {body}
      </button>
    </li>
  )
}
