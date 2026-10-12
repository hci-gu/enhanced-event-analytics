import type { AnalysisState } from './analysis'

export type Page = 'home' | 'status' | 'summary'

export function canNavigate(page: Page, analysis: AnalysisState | null): boolean {
  return page === 'home' || (page === 'status' ? analysis !== null : analysis?.status === 'completed')
}

export function pageAfterUpdate(page: Page, previous: AnalysisState['status'], next: AnalysisState['status']): Page {
  return page === 'status' && previous !== 'completed' && next === 'completed' ? 'summary' : page
}

export function canSubmit(text: string, pending: boolean): boolean {
  return text.trim().length > 0 && !pending
}
