import { useState } from "react"
import { ArrowRight, ExternalLink, FlaskConical, Loader2, RotateCcw, ThumbsDown } from "lucide-react"
import { Link, useSearchParams } from "react-router"

import { Empty, ErrorState, Label, OutcomeLabel, PageHeader, Section } from "@/components/common"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Sheet, SheetContent } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Detail, FilterSelect } from "@/pages/conversations"
import {
  OUTCOME,
  REVIEW,
  secs,
  send,
  useApi,
  when,
  type ConversationDetail,
  type Inbox as InboxData,
  type InboxRow,
  type ReviewStatus,
} from "@/lib/api"
import { cn } from "@/lib/utils"

const STATUSES = Object.keys(REVIEW) as ReviewStatus[]

const StatusLabel = ({ status }: { status: ReviewStatus }) => <Label color={REVIEW[status].color}>{REVIEW[status].label}</Label>

/** 처리함에 들어온 이유: 봇의 결과(찾지 못함·담당자 호출·오류) 그리고/또는 👎 */
function Reason({ row }: { row: Pick<InboxRow, "outcome" | "thumbs_down"> }) {
  return (
    <div className="flex flex-col gap-1">
      {row.outcome !== "answered" && row.outcome !== "chitchat" && <OutcomeLabel outcome={row.outcome} />}
      {row.thumbs_down && (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium whitespace-nowrap">
          <ThumbsDown className="size-3 text-delta-bad" />
          👎 받음
        </span>
      )}
    </div>
  )
}

export function Inbox() {
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
        return next
      },
      { replace: "id" in patch },
    )

  const status = get("status", "open")
  const qs = new URLSearchParams({ status })
  if (get("reason")) qs.set("reason", get("reason"))
  const { data, error, loading } = useApi<InboxData>(`/api/inbox?${qs}`)
  const total = data ? STATUSES.reduce((s, k) => s + data.counts[k], 0) : 0

  return (
    <div className="space-y-6">
      <PageHeader
        title="처리함"
        description="봇이 답하지 못했거나 👎 받은 질문. 원인을 보고 문서를 보강한 뒤 다시 돌려보거나, 시험지에 넣어 둡니다"
      />

      <div className="flex flex-wrap items-center gap-2">
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={status}
          onValueChange={(v) => v && set({ status: v === "open" ? "" : v })}
          aria-label="처리 상태"
        >
          {STATUSES.map((s) => (
            <ToggleGroupItem key={s} value={s} className="gap-1.5 px-3">
              {REVIEW[s].label}
              {data && <span className="text-muted-foreground tabular-nums">{data.counts[s]}</span>}
            </ToggleGroupItem>
          ))}
          <ToggleGroupItem value="all" className="gap-1.5 px-3">
            전체
            {data && <span className="text-muted-foreground tabular-nums">{total}</span>}
          </ToggleGroupItem>
        </ToggleGroup>
        <FilterSelect
          label="이유"
          value={get("reason")}
          onChange={(v) => set({ reason: v })}
          options={[
            ["not_found", OUTCOME.not_found.label],
            ["escalated", OUTCOME.escalated.label],
            ["error", OUTCOME.error.label],
            ["down", "👎 받음"],
          ]}
        />
        {data && <span className="ml-auto text-sm text-muted-foreground tabular-nums">{data.rows.length}건</span>}
      </div>

      {error ? (
        <ErrorState message={error} />
      ) : (
        <Card className={cn("overflow-hidden py-0 transition-opacity", loading && data && "opacity-60")}>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-28 pl-4">시각</TableHead>
                <TableHead>질문 · 봇의 답</TableHead>
                <TableHead className="w-28">이유</TableHead>
                <TableHead className="w-32">다시 돌려본 결과</TableHead>
                <TableHead className="w-32 pr-4">처리</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {!data
                ? Array.from({ length: 6 }, (_, i) => (
                    <TableRow key={i}>
                      <TableCell colSpan={5} className="px-4">
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
                      <TableCell className="pl-4 align-top text-xs text-muted-foreground tabular-nums">{when(r.created_at)}</TableCell>
                      <TableCell className="max-w-0 whitespace-normal">
                        <div className="truncate font-medium">{r.question}</div>
                        <div className="truncate text-xs text-muted-foreground">{r.reply?.split("\n📄")[0]}</div>
                        {r.comment && <div className="truncate text-xs text-delta-bad">💬 {r.comment}</div>}
                        {r.note && <div className="truncate text-xs text-muted-foreground">📝 {r.note}</div>}
                      </TableCell>
                      <TableCell className="align-top">
                        <Reason row={r} />
                      </TableCell>
                      <TableCell className="align-top">
                        {r.rerun_outcome ? (
                          <OutcomeLabel outcome={r.rerun_outcome} />
                        ) : (
                          <span className="text-muted-foreground">–</span>
                        )}
                      </TableCell>
                      <TableCell className="pr-4 align-top">
                        <div className="flex flex-col items-start gap-1">
                          <StatusLabel status={r.status} />
                          {r.testset_id != null && (
                            <Badge variant="outline" className="tabular-nums">
                              시험지 #{r.testset_id}
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
            </TableBody>
          </Table>
          {data && data.rows.length === 0 && (
            <Empty>{status === "open" && !get("reason") ? "처리할 질문이 없어요 🎉" : "조건에 맞는 질문이 없어요"}</Empty>
          )}
        </Card>
      )}

      <Sheet open={!!get("id")} onOpenChange={(open) => !open && set({ id: "" })}>
        <SheetContent className="w-full gap-0 overflow-y-auto data-[side=right]:sm:max-w-2xl">
          {get("id") && (
            <Detail id={get("id")} extra={(d) => <ReviewPanel key={d.id} data={d} topics={data?.topics ?? []} />} />
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}

/** 버튼 하나의 요청 상태: 무엇이 도는 중인지, 실패 이유 */
function useAction() {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const run = async (name: string, fn: () => Promise<unknown>) => {
    setBusy(name)
    setError(null)
    try {
      await fn()
      return true
    } catch (e) {
      setError((e as Error).message)
      return false
    } finally {
      setBusy(null)
    }
  }
  return { busy, error, run }
}

function ReviewPanel({ data, topics }: { data: ConversationDetail; topics: string[] }) {
  const base = `/api/conversations/${data.id}`
  const saved = data.review?.note ?? ""
  const [note, setNote] = useState(saved)
  const { busy, error, run } = useAction()

  return (
    <>
      <Section title="처리">
        <div className="space-y-4 rounded-lg border p-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="w-16 text-sm text-muted-foreground">상태</span>
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={data.review?.status ?? "open"}
              onValueChange={(v) => v && run("status", () => send(`${base}/review`, "PATCH", { status: v }))}
              disabled={busy === "status"}
              aria-label="처리 상태"
            >
              {STATUSES.map((s) => (
                <ToggleGroupItem key={s} value={s} className="gap-1.5 px-3">
                  <span className="size-2 rounded-full" style={{ background: REVIEW[s].color }} />
                  {REVIEW[s].label}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>
          <div className="flex gap-3">
            <label htmlFor="review-note" className="w-16 shrink-0 pt-2 text-sm text-muted-foreground">
              메모
            </label>
            <div className="min-w-0 flex-1 space-y-2">
              <Textarea
                id="review-note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="무엇을 고쳤는지, 왜 무시했는지"
              />
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={note === saved || busy === "note"}
                  onClick={() => run("note", () => send(`${base}/review`, "PATCH", { note: note.trim() || null }))}
                >
                  {busy === "note" && <Loader2 className="animate-spin" />}
                  메모 저장
                </Button>
                {data.review && (
                  <span className="text-xs text-muted-foreground tabular-nums">마지막 저장 {when(data.review.updated_at)}</span>
                )}
              </div>
            </div>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
      </Section>

      <Rerun data={data} />
      <Testset data={data} topics={topics} />
    </>
  )
}

function Rerun({ data }: { data: ConversationDetail }) {
  const { busy, error, run } = useAction()
  return (
    <Section
      title="다시 돌려보기"
      aside={
        <Button
          size="sm"
          variant="outline"
          disabled={!!busy}
          onClick={() => run("rerun", () => send(`/api/conversations/${data.id}/rerun`, "POST"))}
        >
          {busy ? <Loader2 className="animate-spin" /> : <RotateCcw />}
          {busy ? "답을 만드는 중…" : "지금 봇으로 다시 돌리기"}
        </Button>
      }
    >
      <p className="text-xs text-muted-foreground">
        문서를 보강하고 다시 적재한 뒤(<code>uv run bnb2 ingest</code>) 같은 질문을 지금의 봇에 다시 물어봅니다. 결과는 운영 지표에 섞이지 않게
        따로 남습니다.
      </p>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {data.reruns.length > 0 && (
        <ul className="space-y-2">
          {data.reruns.map((r) => (
            <li key={r.id} className="rounded-lg border p-3 text-sm">
              <div className="flex items-center gap-2 text-xs">
                <OutcomeLabel outcome={data.outcome} />
                <ArrowRight className="size-3 text-muted-foreground" aria-label="에서" />
                <OutcomeLabel outcome={r.outcome} />
                <span className="ml-auto text-muted-foreground tabular-nums">
                  {when(r.created_at)} · {secs(r.total_ms)}
                </span>
                <Link
                  to={`/conversations?id=${r.id}`}
                  className="inline-flex items-center gap-0.5 text-muted-foreground hover:text-foreground"
                >
                  자세히 <ExternalLink className="size-3" />
                </Link>
              </div>
              <p className="mt-2 whitespace-pre-wrap">{r.reply ?? "–"}</p>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

function Testset({ data, topics }: { data: ConversationDetail; topics: string[] }) {
  const [topic, setTopic] = useState("")
  const [question, setQuestion] = useState(data.question)
  const [answer, setAnswer] = useState("")
  const { busy, error, run } = useAction()
  const added = data.review?.testset_id
  const ready = topic && question.trim() && answer.trim()

  return (
    <Section title="시험지에 추가">
      <div className="space-y-3 rounded-lg border p-4">
        {added != null ? (
          <p className="flex items-center gap-2 text-sm">
            <FlaskConical className="size-4 text-delta-good" />
            시험지 <span className="font-medium tabular-nums">#{added}</span> 번 문제로 추가했어요
          </p>
        ) : (
          <>
            <div className="grid grid-cols-[4rem_1fr] items-center gap-3">
              <span className="text-sm text-muted-foreground">주제</span>
              <Select value={topic} onValueChange={setTopic}>
                <SelectTrigger size="sm" className="w-56" aria-label="주제">
                  <SelectValue placeholder="주제 고르기" />
                </SelectTrigger>
                <SelectContent>
                  {topics.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <label htmlFor="testset-q" className="text-sm text-muted-foreground">
                질문
              </label>
              <Input id="testset-q" value={question} onChange={(e) => setQuestion(e.target.value)} />
              <label htmlFor="testset-a" className="self-start pt-2 text-sm text-muted-foreground">
                정답
              </label>
              <Textarea
                id="testset-a"
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder="호스트라면 이렇게 답한다 (채점 기준이 됩니다)"
              />
            </div>
            <div className="flex justify-end">
              <Button
                size="sm"
                disabled={!ready || !!busy}
                onClick={() =>
                  run("add", () =>
                    send(`/api/conversations/${data.id}/testset`, "POST", { topic, question_ko: question, answer_ko: answer }),
                  )
                }
              >
                {busy ? <Loader2 className="animate-spin" /> : <FlaskConical />}
                시험지에 추가
              </Button>
            </div>
          </>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
        <p className="text-xs text-muted-foreground">
          <code>data/testset.jsonl</code> 끝에 한 줄로 붙습니다. Langfuse Dataset 에는 <code>uv run bnb2 dataset</code> 으로 다시
          올려야 다음 시험에 들어갑니다.
        </p>
      </div>
    </Section>
  )
}
