import type { ReactNode } from "react"
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { GRADE, OUTCOME, type Grade, type Outcome } from "@/lib/api"
import { cn } from "@/lib/utils"

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

/** 색 점 + 글자. 글자는 본문 색, 색은 점에만 (색만으로 뜻을 전하지 않는다) */
export function Dot({ color, className }: { color: string; className?: string }) {
  return <span className={cn("inline-block size-2 shrink-0 rounded-full", className)} style={{ background: color }} />
}

export function Label({ color, children }: { color: string; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium">
      <Dot color={color} />
      {children}
    </span>
  )
}

export const OutcomeLabel = ({ outcome }: { outcome: Outcome }) => (
  <Label color={OUTCOME[outcome].color}>{OUTCOME[outcome].label}</Label>
)

export const GradeLabel = ({ grade }: { grade: Grade }) => <Label color={GRADE[grade].color}>{GRADE[grade].label}</Label>

/** 증감 표시. good: 올라가는 게 좋은 지표인가 (비용·응답 시간은 false, 좋고 나쁨이 없으면 null) */
export function Delta({ diff, text, good = true }: { diff: number | null; text: string; good?: boolean | null }) {
  if (diff == null) return <span className="text-xs text-muted-foreground">비교 기록 없음</span>
  const flat = Math.abs(diff) < 1e-9
  const better = flat || good == null ? null : diff > 0 === good
  const Icon = flat ? Minus : diff > 0 ? ArrowUpRight : ArrowDownRight
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 text-xs font-medium tabular-nums",
        better == null ? "text-muted-foreground" : better ? "text-delta-good" : "text-delta-bad",
      )}
    >
      <Icon className="size-3.5" />
      {text}
    </span>
  )
}

export function StatCard({
  label,
  value,
  sub,
  delta,
  hint,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  delta?: ReactNode
  hint?: string
}) {
  const title = <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
  return (
    <Card className="gap-2 py-4">
      <CardHeader className="px-4">
        {hint ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="w-fit cursor-help underline decoration-dotted decoration-muted-foreground/50 underline-offset-4">
                {title}
              </span>
            </TooltipTrigger>
            <TooltipContent className="max-w-64">{hint}</TooltipContent>
          </Tooltip>
        ) : (
          title
        )}
      </CardHeader>
      <CardContent className="space-y-1 px-4">
        <div className="text-2xl font-semibold tracking-tight">{value}</div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          {delta}
          {sub}
        </div>
      </CardContent>
    </Card>
  )
}

/** 가로 100% 누적 막대. 조각 사이 2px 틈으로 구분하고, 값은 툴팁과 범례·표에도 있다 */
export function StackBar({
  parts,
  className,
}: {
  parts: { key: string; label: string; value: number; color: string; text?: string }[]
  className?: string
}) {
  const total = parts.reduce((s, p) => s + p.value, 0)
  return (
    <div className={cn("flex h-2.5 w-full gap-[2px] overflow-hidden rounded-full bg-muted", className)}>
      {total > 0 &&
        parts
          .filter((p) => p.value > 0)
          .map((p) => (
            <Tooltip key={p.key}>
              <TooltipTrigger asChild>
                <div className="h-full first:rounded-l-full last:rounded-r-full" style={{ flex: p.value, background: p.color }} />
              </TooltipTrigger>
              <TooltipContent>
                {p.label} {p.text ?? `${((p.value / total) * 100).toFixed(0)}%`}
              </TooltipContent>
            </Tooltip>
          ))}
    </div>
  )
}

export function Legend({ items }: { items: { label: string; color: string; value?: ReactNode }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1">
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <Dot color={i.color} />
          {i.label}
          {i.value != null && <span className="font-medium text-foreground tabular-nums">{i.value}</span>}
        </span>
      ))}
    </div>
  )
}

export function PeriodToggle({ value, onChange }: { value: number; onChange: (days: number) => void }) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      value={String(value)}
      onValueChange={(v) => v && onChange(Number(v))}
      aria-label="기간"
    >
      {[7, 30, 90].map((d) => (
        <ToggleGroupItem key={d} value={String(d)} className="px-3">
          {d}일
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}

export function ErrorState({ message }: { message: string }) {
  return (
    <Card className="border-destructive/30">
      <CardContent className="py-6 text-sm">
        <p className="font-medium text-destructive">불러오지 못했어요</p>
        <p className="mt-1 break-all text-muted-foreground">{message}</p>
        <p className="mt-2 text-muted-foreground">
          서버가 켜져 있는지(<code>uv run bnb2 web</code>), DB가 켜져 있는지(<code>docker compose up -d</code>) 확인하세요.
        </p>
      </CardContent>
    </Card>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="py-10 text-center text-sm text-muted-foreground">{children}</div>
}

export function LoadingGrid({ cards = 4 }: { cards?: number }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: cards }, (_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-72 rounded-xl" />
    </div>
  )
}

/** 상세 패널 안의 "이름: 값" 한 줄 */
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[6.5rem_1fr] gap-3 py-1.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

export function Section({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  )
}
