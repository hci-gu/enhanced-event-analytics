export type Match = { ID: string; name: string }
export type WorkflowInfo = { id: string; label: string }
export type WorkflowState = WorkflowInfo & {
  status: 'queued' | 'running' | 'completed' | 'failed' | 'skipped'
  results: Match[]
}
export type AnalysisState = {
  status: 'preparing' | 'running' | 'completed' | 'failed'
  workflows: WorkflowState[]
  completedIds: string[]
  error: string | null
}
export type AnalysisEvent =
  | { type: 'analysis_started'; workflows: WorkflowInfo[] }
  | { type: 'workflow_started'; id: string }
  | { type: 'workflow_completed'; id: string; results: Match[] }
  | { type: 'workflow_failed'; id: string | null; message: string; code: number }
  | { type: 'analysis_completed' }

export const initialAnalysis: AnalysisState = {
  status: 'preparing', workflows: [], completedIds: [], error: null,
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isText(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

export function parseAnalysisEvent(type: string, json: string): AnalysisEvent {
  const data: unknown = JSON.parse(json)
  if (!isRecord(data)) throw new Error('Servern skickade ett ogiltigt analysmeddelande.')
  if (type === 'analysis_started' && Array.isArray(data.workflows)) {
    const workflows: WorkflowInfo[] = []
    for (const item of data.workflows) {
      if (!isRecord(item) || !isText(item.id) || !isText(item.label)) break
      workflows.push({ id: item.id, label: item.label })
    }
    if (workflows.length === data.workflows.length && new Set(workflows.map((item) => item.id)).size === workflows.length) {
      return { type, workflows }
    }
  }
  if (type === 'workflow_started' && isText(data.id)) return { type, id: data.id }
  if (type === 'workflow_completed' && isText(data.id) && Array.isArray(data.results)) {
    const results: Match[] = []
    for (const item of data.results) {
      if (!isRecord(item) || !isText(item.ID) || !isText(item.name)) break
      results.push({ ID: item.ID, name: item.name })
    }
    if (results.length === data.results.length) return { type, id: data.id, results }
  }
  if (type === 'workflow_failed' && (data.id === null || isText(data.id)) &&
    isText(data.message) && typeof data.code === 'number' && Number.isInteger(data.code)) {
    return { type, id: data.id, message: data.message, code: data.code }
  }
  if (type === 'analysis_completed') return { type }
  throw new Error('Servern skickade ett ogiltigt analysmeddelande.')
}

export function failAnalysis(state: AnalysisState, message: string): AnalysisState {
  return {
    ...state, status: 'failed', error: message,
    workflows: state.workflows.map((workflow) => ({
      ...workflow,
      status: workflow.status === 'running' ? 'failed' : workflow.status === 'queued' ? 'skipped' : workflow.status,
    })),
  }
}

export function advanceAnalysis(state: AnalysisState, event: AnalysisEvent): AnalysisState {
  const invalid = () => { throw new Error('Servern skickade analysuppdateringar i oväntad ordning.') }
  if (state.status === 'completed' || state.status === 'failed') return invalid()
  if (event.type === 'analysis_started') {
    if (state.status !== 'preparing') return invalid()
    return {
      ...initialAnalysis, status: 'running',
      workflows: event.workflows.map((workflow) => ({ ...workflow, status: 'queued', results: [] })),
    }
  }
  if (event.type === 'workflow_failed') {
    if (event.id !== null && !state.workflows.some((workflow) => workflow.id === event.id && workflow.status === 'running')) return invalid()
    return failAnalysis(state, event.message)
  }
  if (state.status !== 'running') return invalid()
  if (event.type === 'analysis_completed') {
    if (state.workflows.some((workflow) => workflow.status !== 'completed')) return invalid()
    return { ...state, status: 'completed' }
  }
  const workflow = state.workflows.find((item) => item.id === event.id)
  if (!workflow) return invalid()
  if (event.type === 'workflow_started') {
    if (workflow.status !== 'queued' || state.workflows.some((item) => item.status === 'running')) return invalid()
    return { ...state, workflows: state.workflows.map((item) => item.id === event.id ? { ...item, status: 'running' } : item) }
  }
  if (workflow.status === 'completed') return state
  if (workflow.status !== 'running') return invalid()
  return {
    ...state,
    workflows: state.workflows.map((item) => item.id === event.id ? { ...item, status: 'completed', results: event.results } : item),
    completedIds: [...state.completedIds, event.id],
  }
}

export function analysisProgress(state: AnalysisState): number | null {
  if (state.status === 'completed') return null
  return state.workflows.length ? Math.round(100 * state.completedIds.length / state.workflows.length) : 0
}

export async function readAnalysisStream(
  stream: ReadableStream<Uint8Array>, onState: (state: AnalysisState) => void,
): Promise<void> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let eventType = ''
  let data: string[] = []
  let state = initialAnalysis
  try {
    while (true) {
      let chunk: ReadableStreamReadResult<Uint8Array>
      try {
        chunk = await reader.read()
      } catch (error) {
        throw new Error('Anslutningen till servern avbröts. Redan klara resultat har sparats på sidan.', { cause: error })
      }
      const { value, done } = chunk
      buffer += decoder.decode(value, { stream: !done })
      let newline = buffer.indexOf('\n')
      while (newline !== -1) {
        const line = buffer.slice(0, newline).replace(/\r$/, '')
        buffer = buffer.slice(newline + 1)
        if (line === '') {
          if (data.length) {
            state = advanceAnalysis(state, parseAnalysisEvent(eventType, data.join('\n')))
            onState(state)
            if (state.status === 'completed' || state.status === 'failed') return
          }
          eventType = ''
          data = []
        } else if (line.startsWith('event:')) eventType = line.slice(6).trim()
        else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
        newline = buffer.indexOf('\n')
      }
      if (done) throw new Error('Anslutningen avbröts innan analysen var färdig. Redan klara resultat har sparats på sidan.')
    }
  } catch (error) {
    if (error instanceof SyntaxError) throw new Error('Servern skickade ett ogiltigt analysmeddelande.', { cause: error })
    throw error
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
