import { useEffect, useState } from "react"

// ── API 응답 타입 (src/bnb2/api.py 와 맞춘다) ──

export type Outcome = "answered" | "not_found" | "escalated" | "chitchat" | "error"
export type Grade = "correct" | "partial" | "wrong" | "abstain"

export interface PeriodStats {
  questions: number
  answered: number
  not_found: number
  escalated: number
  errors: number
  cost: number
  p50_ms: number | null
  p95_ms: number | null
  thumbs_up: number
  thumbs_down: number
  needs_check: number
  resolution_rate: number | null
  satisfaction: number | null
}

export interface Summary {
  n: number
  correct: number
  partial: number
  wrong: number
  abstain: number
  hallucination: number | null
  retrieval_hit: number
  blocked: number | null
  score: number
}

export interface Overview {
  days: number
  current: PeriodStats
  previous: PeriodStats
  daily: ({ day: string } & Record<Outcome, number>)[]
  nodes: { node: string; p50_ms: number; n: number }[]
  issues: { id: number; created_at: string; question: string; outcome: Outcome; thumbs_down: boolean | null; comment: string | null }[]
  latest_eval: { name: string; created_at: string; summary: Summary } | null
}

export interface ConversationRow {
  id: number
  created_at: string
  channel: string
  slack_user: string | null
  question: string
  intent: string | null
  outcome: Outcome
  reply: string | null
  total_ms: number | null
  cost_usd: number | null
  top_score: number | null
  feedback: "up" | "down" | null
  comment: string | null
}

export interface Chunk {
  id?: string
  source: string
  content: string
  score?: number
}

export type ReviewStatus = "open" | "fixed" | "ignored"

export interface Review {
  status: ReviewStatus
  note: string | null
  testset_id: number | null
  updated_at: string
}

export interface ConversationDetail extends Omit<ConversationRow, "feedback" | "comment" | "top_score"> {
  thread: string | null
  classify_reason: string | null
  answer: string | null
  sources: string[] | null
  chunks: Chunk[] | null
  grounded: boolean | null
  direct: boolean | null
  check_reason: string | null
  error: string | null
  latency_ms: Record<string, number> | null
  input_tokens: number | null
  output_tokens: number | null
  trace_url: string | null
  feedback: { slack_user: string; good: boolean; comment: string | null; created_at: string }[]
  review: Review | null
  reruns: { id: number; created_at: string; outcome: Outcome; reply: string | null; total_ms: number | null }[]
}

export interface InboxRow {
  id: number
  created_at: string
  channel: string
  slack_user: string | null
  question: string
  outcome: Outcome
  reply: string | null
  thumbs_down: boolean
  comment: string | null
  status: ReviewStatus
  note: string | null
  testset_id: number | null
  rerun_outcome: Outcome | null
}

export interface Inbox {
  rows: InboxRow[]
  counts: Record<ReviewStatus, number>
  topics: string[]
}

export interface DocItem {
  id: string
  source: string
  content: string
  retrieved: number
  top1: number
  used: number
  not_found_top1: number
  questions: { id: number; created_at: string; question: string; outcome: Outcome; rank: number }[]
}

export interface EvalRun {
  name: string
  created_at: string
  answer_model: string | null
  judge_model: string | null
  git_commit: string | null
  url: string | null
}

export type Cause = "hallucination" | "routing" | "retrieval" | "blocked" | "generation"

export interface EvalItem {
  id: string
  topic: string | null
  question: string
  expected: string
  reply: string
  intent: string
  blocked: boolean
  grade: Grade
  hallucination: boolean
  retrieval_hit: boolean
  reason: string
  chunks: Chunk[] | null
  cause: Cause | null
}

export interface EvalList {
  baseline: Summary & { name: string }
  causes: Record<Cause, string>
  runs: (EvalRun & { summary: Summary })[]
}

export interface EvalDetail {
  run: EvalRun
  summary: Summary
  causes: Record<Cause, number>
  topics: (Summary & { topic: string })[]
  items: EvalItem[]
}

// ── 불러오기 ──

const CHANGED = "bnb2:changed"

/** 무언가를 저장하면 열려 있는 화면(사이드바 배지 포함)이 전부 다시 불러온다 */
function useChanged() {
  const [version, setVersion] = useState(0)
  useEffect(() => {
    const bump = () => setVersion((v) => v + 1)
    window.addEventListener(CHANGED, bump)
    return () => window.removeEventListener(CHANGED, bump)
  }, [])
  return version
}

export function useApi<T>(url: string | null) {
  const [state, setState] = useState<{ data?: T; error?: string; url?: string }>({})
  const version = useChanged()
  useEffect(() => {
    if (!url) return
    let alive = true
    fetch(url)
      .then(async (r) => {
        if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
        return r.json() as Promise<T>
      })
      .then((data) => alive && setState({ data, url }))
      .catch((e: Error) => alive && setState({ error: e.message, url }))
    return () => {
      alive = false
    }
  }, [url, version])
  // 주소가 바뀌면 이전 데이터를 잠깐 그대로 보여준다 (필터를 바꿀 때 화면이 깜빡이지 않게)
  return { data: state.data, error: state.error, loading: state.url !== url }
}

/** 저장·실행 요청. 실패하면 서버가 준 이유(detail)로 Error 를 던진다 */
export async function send<T>(url: string, method: "POST" | "PATCH", body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await r.text()
  if (!r.ok) {
    let detail: unknown = text
    try {
      detail = JSON.parse(text).detail ?? text
    } catch {
      /* JSON 이 아니면 본문 그대로 */
    }
    throw new Error(typeof detail === "string" ? detail : `입력값을 확인하세요 (${r.status})`)
  }
  window.dispatchEvent(new Event(CHANGED))
  return JSON.parse(text) as T
}

// ── 표시 형식 ──

export const pct = (v: number | null | undefined, digits = 0) =>
  v == null ? "–" : `${(v * 100).toFixed(digits)}%`

export const secs = (ms: number | null | undefined) => (ms == null ? "–" : `${(ms / 1000).toFixed(1)}초`)

export const usd = (v: number | null | undefined) =>
  v == null ? "–" : v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`

const dateTime = new Intl.DateTimeFormat("ko-KR", {
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
})
const dateOnly = new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "numeric", day: "numeric" })

export const when = (iso: string) => dateTime.format(new Date(iso))
export const day = (iso: string) => dateOnly.format(new Date(iso))

// ── 이름표 ──

export const OUTCOME: Record<Outcome, { label: string; color: string }> = {
  answered: { label: "답변함", color: "var(--series-1)" },
  not_found: { label: "찾지 못함", color: "var(--series-2)" },
  escalated: { label: "담당자 호출", color: "var(--series-3)" },
  chitchat: { label: "잡담", color: "var(--series-4)" },
  error: { label: "오류", color: "var(--series-5)" },
}

export const GRADE: Record<Grade, { label: string; color: string }> = {
  correct: { label: "정답", color: "var(--good)" },
  partial: { label: "부분정답", color: "var(--warn)" },
  wrong: { label: "오답", color: "var(--bad)" },
  abstain: { label: "보류", color: "var(--neutral)" },
}

export const REVIEW: Record<ReviewStatus, { label: string; color: string }> = {
  open: { label: "미처리", color: "var(--warn)" },
  fixed: { label: "문서 보강함", color: "var(--good)" },
  ignored: { label: "무시", color: "var(--neutral)" },
}

export const CHANNEL: Record<string, string> = { slack: "슬랙", cli: "CLI", rerun: "다시 돌려봄" }

export const NODE_LABEL: Record<string, string> = {
  classify: "① 분류",
  retrieve: "② 검색",
  generate: "③ 답변",
  check: "④ 근거 검사",
  escalate: "담당자 호출",
  chitchat: "잡담",
}
