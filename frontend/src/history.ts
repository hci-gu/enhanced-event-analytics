import { initialAnalysis, parseAnalysisEvent } from './analysis.ts'
import type { AnalysisState, WorkflowState } from './analysis.ts'
import { SessionExpiredError } from './auth.ts'
import { parseDateResults } from './dates.ts'

export type HistoryEntry = { analysisId: string; title: string; createdAt: string }
export type HistoryPage = { items: HistoryEntry[]; nextCursor: string | null }
export type SavedAnalysis = { analysis: AnalysisState; text: string }

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function timestamp(value: unknown): string {
  if (typeof value !== 'string') throw new Error('Ogiltig tid i historiken.')
  const normalized = value.replace(' ', 'T')
  if (!Number.isFinite(Date.parse(normalized))) throw new Error('Ogiltig tid i historiken.')
  return normalized
}

function entry(value: unknown): HistoryEntry {
  if (!record(value) || typeof value.analysis_id !== 'string' ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value.analysis_id) ||
    typeof value.title !== 'string' || value.status !== 'Complete') throw new Error('Ogiltigt svar från historiken.')
  return { analysisId: value.analysis_id, title: value.title.trim() || 'Händelseanalys', createdAt: timestamp(value.created) }
}

async function requestHistory(path: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(`/api/analyses${path}`, {
    cache: 'no-store', credentials: 'same-origin',
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(10000)]) : AbortSignal.timeout(10000),
  })
  if (response.status === 401) throw new SessionExpiredError()
  if (!response.ok) throw new Error(response.status === 404 ? 'Analysen kunde inte hittas.' : 'Historiken är inte tillgänglig. Försök igen.')
  return response.json()
}

export async function loadHistory(cursor: string | null = null, signal?: AbortSignal): Promise<HistoryPage> {
  const query = new URLSearchParams({ limit: cursor ? '20' : '5' })
  if (cursor) query.set('cursor', cursor)
  const data = await requestHistory(`?${query}`, signal)
  if (!record(data) || !Array.isArray(data.items) ||
    !(data.next_cursor === null || typeof data.next_cursor === 'string')) throw new Error('Ogiltigt svar från historiken.')
  return { items: data.items.map(entry), nextCursor: data.next_cursor }
}

export async function loadSavedAnalysis(analysisId: string, signal?: AbortSignal): Promise<SavedAnalysis> {
  const data = await requestHistory(`/${encodeURIComponent(analysisId)}`, signal)
  const item = entry(data)
  if (!record(data) || typeof data.original_text !== 'string' || !data.original_text.trim() ||
    !record(data.predictions) || item.analysisId !== analysisId) throw new Error('Den sparade analysen är ogiltig.')
  const start = parseAnalysisEvent('analysis_started', JSON.stringify({ analysis_id: item.analysisId, workflows: data.workflows }))
  if (start.type !== 'analysis_started') throw new Error('Den sparade analysen är ogiltig.')
  const text = data.original_text
  const workflows: WorkflowState[] = start.workflows.map((workflow) => {
    if (workflow.id === 'dates') return {
      ...workflow, status: data.dates_error ? 'failed' : 'completed', results: [],
      ...(data.dates_error ? { error: 'Datum kunde inte extraheras. Kategoriseringsresultaten finns kvar.' } : {}),
    }
    const parsed = parseAnalysisEvent('workflow_completed', JSON.stringify({ id: workflow.id, results: (data.predictions as Record<string, unknown>)[workflow.id] }))
    if (parsed.type !== 'workflow_completed') throw new Error('Den sparade analysen är ogiltig.')
    return { ...workflow, status: 'completed', results: parsed.results.map((match) => ({
      ...match, evidence: match.evidence?.filter((quote) => text.includes(quote)),
    })) }
  })
  return { text, analysis: {
    ...initialAnalysis, analysisId: item.analysisId, title: item.title, status: 'completed', workflows,
    completedIds: workflows.map((workflow) => workflow.id),
    dates: data.dates_error ? null : parseDateResults(data.dates),
    analyzedAt: data.finished_at ? timestamp(data.finished_at) : item.createdAt,
  } }
}

export function historyGroups(items: HistoryEntry[], now = new Date()): { label: string; items: HistoryEntry[] }[] {
  const dayKey = (date: Date) => `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
  const today = dayKey(now)
  const yesterday = dayKey(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1))
  const groups = new Map<string, { label: string; items: HistoryEntry[] }>()
  for (const item of items) {
    const date = new Date(item.createdAt)
    const key = dayKey(date)
    if (!groups.has(key)) groups.set(key, {
      label: key === today ? 'I dag' : key === yesterday ? 'I går' : date.toLocaleDateString('sv-SE', {
        day: 'numeric', month: 'long', ...(date.getFullYear() !== now.getFullYear() ? { year: 'numeric' } : {}),
      }), items: [],
    })
    groups.get(key)!.items.push(item)
  }
  return [...groups.values()]
}
