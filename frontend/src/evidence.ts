import type { WorkflowState } from './analysis.ts'

export type EvidenceOwner = { workflowId: string; categoryId: string; categoryName: string }
export type TextSegment = { start: number; end: number; text: string; owners: EvidenceOwner[] }
export type Selection = { workflowIds: string[]; segmentStart?: number } | null
export type Interaction = { pinned: Selection; hovered: Selection; focused: Selection }
export const initialInteraction: Interaction = { pinned: null, hovered: null, focused: null }
export type InteractionAction =
  | { type: 'hover' | 'focus' | 'pin'; selection: Selection }
  | { type: 'clear' }

export function interact(state: Interaction, action: InteractionAction): Interaction {
  if (action.type === 'clear') return initialInteraction
  if (action.type === 'hover') return { ...state, hovered: action.selection }
  if (action.type === 'focus') return { ...state, focused: action.selection }
  const same = JSON.stringify(state.pinned) === JSON.stringify(action.selection)
  return { ...state, pinned: same ? null : action.selection }
}

export function activeSelection(state: Interaction): Selection {
  return state.hovered ?? state.focused ?? state.pinned
}

export function workflowColor(id: string): string {
  return `var(--evidence-${['risks', 'reach', 'service'].includes(id) ? id : 'fallback'}-color)`
}

// JS indices consistently use UTF-16, including quotes containing emoji.
export function evidenceSegments(text: string, workflows: WorkflowState[]): TextSegment[] {
  const ranges: { start: number; end: number; owner: EvidenceOwner }[] = []
  for (const workflow of workflows) for (const match of workflow.results) {
    for (const quote of new Set(match.evidence ?? [])) {
      if (!quote.trim()) continue
      let start = text.indexOf(quote)
      while (start !== -1) {
        ranges.push({ start, end: start + quote.length, owner: {
          workflowId: workflow.id, categoryId: match.ID, categoryName: match.name,
        } })
        start = text.indexOf(quote, start + 1)
      }
    }
  }
  const boundaries = [...new Set([0, text.length, ...ranges.flatMap(({ start, end }) => [start, end])])].sort((a, b) => a - b)
  return boundaries.slice(0, -1).map((start, index) => {
    const end = boundaries[index + 1]
    const owners = new Map<string, EvidenceOwner>()
    for (const range of ranges) if (range.start <= start && range.end >= end) {
      owners.set(JSON.stringify([range.owner.workflowId, range.owner.categoryId]), range.owner)
    }
    return { start, end, text: text.slice(start, end), owners: [...owners.values()] }
  })
}

export function highlightBands(ids: string[]): string {
  if (ids.length === 1) return workflowColor(ids[0])
  return `linear-gradient(to bottom, ${ids.map((id, index) =>
    `${workflowColor(id)} ${100 * index / ids.length}% ${100 * (index + 1) / ids.length}%`).join(', ')})`
}
