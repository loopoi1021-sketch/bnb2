import { useMemo } from "react"
import { Link, useSearchParams } from "react-router"

import {
  Empty,
  ErrorState,
  Field,
  Legend,
  LoadingGrid,
  OutcomeLabel,
  PageHeader,
  Section,
  StackBar,
  StatCard,
} from "@/components/common"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { pct, useApi, when, type DocItem } from "@/lib/api"

// 항목 하나의 쓰임: 답에 쓰임 > 검색만 됨 > 한 번도 검색 안 됨
const USE = {
  used: { label: "답에 쓰임", color: "var(--series-1)" },
  retrieved: { label: "검색만 됨", color: "var(--series-4)" },
  never: { label: "한 번도 검색 안 됨", color: "var(--neutral)" },
}

const SORTS: Record<string, { label: string; key: (d: DocItem) => number | string }> = {
  retrieved: { label: "검색 많은 순", key: (d) => -d.retrieved },
  top1: { label: "1위 많은 순", key: (d) => -d.top1 },
  used: { label: "답에 쓰인 순", key: (d) => -d.used },
  not_found: { label: "못 찾은 질문 1위 순", key: (d) => -d.not_found_top1 },
  name: { label: "파일 순", key: (d) => d.id },
}

const split = (source: string) => {
  const [file, ...rest] = source.split(" > ")
  return { file, heading: rest.join(" > ") || file }
}

const use = (d: DocItem) => (d.used ? "used" : d.retrieved ? "retrieved" : "never")

export function Docs() {
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

  const { data, error } = useApi<{ searched: number; items: DocItem[] }>("/api/docs")
  const sort = SORTS[get("sort")] ? get("sort") : "retrieved"
  const view = get("view", "all")

  const files = useMemo(() => {
    const out = new Map<string, DocItem[]>()
    for (const d of data?.items ?? []) {
      const f = split(d.source).file
      out.set(f, [...(out.get(f) ?? []), d])
    }
    return [...out.entries()]
  }, [data])

  if (error) return <ErrorState message={error} />
  if (!data) return <LoadingGrid />

  const items = data.items
  const max = Math.max(1, ...items.map((d) => d.retrieved))
  const never = items.filter((d) => d.retrieved === 0)
  const misses = items.filter((d) => d.not_found_top1 > 0).sort((a, b) => b.not_found_top1 - a.not_found_top1)
  const rows = items
    .filter((d) => view === "all" || use(d) === view)
    .sort((a, b) => {
      const [x, y] = [SORTS[sort].key(a), SORTS[sort].key(b)]
      return x < y ? -1 : x > y ? 1 : a.id.localeCompare(b.id)
    })
  const selected = items.find((d) => d.id === get("id"))

  return (
    <div className="space-y-6">
      <PageHeader
        title="문서"
        description={`문서 항목마다 검색과 답변에 얼마나 쓰였는지. 검색한 질문 ${data.searched.toLocaleString()}건 기준 (다시 돌려본 것 제외)`}
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="문서 항목" value={items.length} sub={`파일 ${files.length}개`} />
        <StatCard
          label="한 번이라도 검색됨"
          value={pct((items.length - never.length) / (items.length || 1))}
          sub={`${items.length - never.length}개 항목`}
          hint="질문마다 유사도가 높은 4개 항목을 가져온다. 그 4개에 한 번이라도 들어간 항목"
        />
        <StatCard
          label="한 번도 검색 안 됨"
          value={never.length}
          sub="질문이 없었거나, 제목·내용이 질문과 동떨어짐"
        />
        <StatCard
          label="답에 쓰인 항목"
          value={items.filter((d) => d.used > 0).length}
          sub="근거 검사를 통과한 답의 출처"
          hint="봇이 답 끝에 📄 출처로 단 항목"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>못 찾은 질문이 몰린 항목</CardTitle>
            <CardDescription>'찾지 못함'으로 끝난 질문에서 가장 비슷하다고 나온 항목. 여기에 정보를 보강하면 풀릴 가능성이 크다</CardDescription>
          </CardHeader>
          <CardContent>
            {misses.length === 0 ? (
              <Empty>'찾지 못함' 질문이 없어요</Empty>
            ) : (
              <ul className="space-y-3">
                {misses.slice(0, 6).map((d) => (
                  <li key={d.id} className="space-y-1">
                    <button
                      type="button"
                      onClick={() => set({ id: d.id })}
                      className="flex w-full items-baseline gap-2 text-left text-sm hover:underline"
                    >
                      <span className="font-medium">{split(d.source).heading}</span>
                      <span className="text-xs text-muted-foreground">{split(d.source).file}</span>
                      <span className="ml-auto shrink-0 text-xs tabular-nums">{d.not_found_top1}건</span>
                    </button>
                    <ul className="space-y-0.5 border-l pl-3">
                      {d.questions
                        .filter((q) => q.rank === 1 && q.outcome === "not_found")
                        .slice(0, 3)
                        .map((q) => (
                          <li key={q.id}>
                            <Link to={`/inbox?status=all&id=${q.id}`} className="line-clamp-1 text-xs text-muted-foreground hover:text-foreground">
                              {q.question}
                            </Link>
                          </li>
                        ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>파일별 쓰임</CardTitle>
            <CardDescription>항목 수 기준. 회색이 많은 파일은 질문이 안 오거나 검색에 안 걸린다</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Legend items={Object.values(USE)} />
            <ul className="space-y-2.5">
              {files.map(([file, ds]) => (
                <li key={file} className="grid grid-cols-[minmax(0,11rem)_1fr_3rem] items-center gap-3 text-sm">
                  <span className="truncate">{file.replace(/\.md$/, "")}</span>
                  <StackBar
                    parts={(Object.keys(USE) as (keyof typeof USE)[]).map((k) => ({
                      key: k,
                      ...USE[k],
                      value: ds.filter((d) => use(d) === k).length,
                      text: `${ds.filter((d) => use(d) === k).length}개`,
                    }))}
                  />
                  <span className="text-right text-xs text-muted-foreground tabular-nums">{ds.length}개</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={view}
          onValueChange={(v) => v && set({ view: v === "all" ? "" : v })}
          aria-label="쓰임"
        >
          <ToggleGroupItem value="all" className="px-3">
            전체
          </ToggleGroupItem>
          {(Object.keys(USE) as (keyof typeof USE)[]).map((k) => (
            <ToggleGroupItem key={k} value={k} className="px-3">
              {USE[k].label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <Select value={sort} onValueChange={(v) => set({ sort: v === "retrieved" ? "" : v })}>
          <SelectTrigger size="sm" className="min-w-40" aria-label="정렬">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(SORTS).map(([k, s]) => (
              <SelectItem key={k} value={k}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="ml-auto text-sm text-muted-foreground tabular-nums">{rows.length}개</span>
      </div>

      <Card className="overflow-hidden py-0">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-4">항목</TableHead>
              <TableHead className="w-56">검색됨</TableHead>
              <TableHead className="w-20 text-right">1위</TableHead>
              <TableHead className="w-24 text-right">답에 쓰임</TableHead>
              <TableHead className="w-28 pr-4 text-right">못 찾음 1위</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((d) => {
              const { file, heading } = split(d.source)
              return (
                <TableRow
                  key={d.id}
                  className="cursor-pointer"
                  data-state={get("id") === d.id ? "selected" : undefined}
                  onClick={() => set({ id: d.id })}
                >
                  <TableCell className="max-w-0 pl-4">
                    <div className="truncate font-medium">{heading}</div>
                    <div className="truncate text-xs text-muted-foreground">{file}</div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                        <span className="block h-full rounded-full bg-series-1" style={{ width: `${(d.retrieved / max) * 100}%` }} />
                      </span>
                      <span className="w-8 text-right tabular-nums">{d.retrieved}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{d.top1 || "–"}</TableCell>
                  <TableCell className="text-right tabular-nums">{d.used || "–"}</TableCell>
                  <TableCell className="pr-4 text-right tabular-nums">{d.not_found_top1 || "–"}</TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
        {rows.length === 0 && <Empty>해당하는 항목이 없어요</Empty>}
      </Card>

      <Sheet open={!!selected} onOpenChange={(open) => !open && set({ id: "" })}>
        <SheetContent className="w-full gap-0 overflow-y-auto data-[side=right]:sm:max-w-2xl">
          {selected && <DocDetail doc={selected} />}
        </SheetContent>
      </Sheet>
    </div>
  )
}

function DocDetail({ doc }: { doc: DocItem }) {
  const { file, heading } = split(doc.source)
  const body = doc.content.split("\n").slice(1).join("\n").trim() || doc.content
  return (
    <>
      <SheetHeader className="border-b p-6">
        <div className="text-xs text-muted-foreground">{file}</div>
        <SheetTitle className="text-lg leading-snug">{heading}</SheetTitle>
        <SheetDescription className="sr-only">문서 항목 상세</SheetDescription>
      </SheetHeader>
      <div className="space-y-6 p-6">
        <Section title="내용">
          <div className="rounded-lg border bg-muted/40 p-3 text-sm whitespace-pre-wrap">{body}</div>
        </Section>
        <Section title="쓰임">
          <dl className="divide-y rounded-lg border px-3">
            <Field label="검색됨">
              <span className="tabular-nums">{doc.retrieved}번</span>
            </Field>
            <Field label="1위로 검색됨">
              <span className="tabular-nums">{doc.top1}번</span>
            </Field>
            <Field label="답에 쓰임">
              <span className="tabular-nums">{doc.used}번</span>
            </Field>
            <Field label="못 찾음 1위">
              <span className="tabular-nums">{doc.not_found_top1}번</span>
            </Field>
          </dl>
        </Section>
        <Section title="이 항목이 검색된 질문" aside={<span className="text-xs text-muted-foreground">최근 20건까지</span>}>
          {doc.questions.length === 0 ? (
            <Empty>아직 이 항목을 가져온 질문이 없어요</Empty>
          ) : (
            <ul className="space-y-0.5">
              {doc.questions.map((q) => (
                <li key={q.id}>
                  <Link
                    to={`/conversations?id=${q.id}`}
                    className="flex items-center gap-3 rounded-md px-2 py-2 text-sm transition-colors hover:bg-muted"
                  >
                    <span className="w-8 shrink-0 text-xs text-muted-foreground tabular-nums">{q.rank}위</span>
                    <span className="min-w-0 flex-1 truncate">{q.question}</span>
                    <OutcomeLabel outcome={q.outcome} />
                    <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{when(q.created_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
    </>
  )
}
