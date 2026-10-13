# Routes and page states

The only served application URL is `/`. Navigation changes React state without changing browser URL. There is no router config.

| State | Component | Shell | Behavior |
| --- | --- | --- | --- |
| home | frontend/src/App.tsx | App homepage and toolbar | Swedish event-text composer, Analyze submission, search field |
| status | frontend/src/AnalysisScreen.tsx via AnalysisView | App homepage and toolbar | Streamed workflow statuses, expandable completed results, progress |
| summary | frontend/src/SummaryScreen.tsx via AnalysisView | App homepage and toolbar | Completed analysis, original text with interactive evidence highlights and workflow results |

Status requires an analysis. Summary requires completed analysis. Completion automatically navigates status to summary but does not override a user who returned home. All visible navigation labels are Swedish.

## Navigation guards and transition rules
### `frontend/src/navigation.ts`

```ts
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
```

## Analysis view selection
### `frontend/src/AnalysisView.tsx`

```tsx
import type { AnalysisState } from './analysis'
import AnalysisScreen from './AnalysisScreen'
import SummaryScreen from './SummaryScreen'
import type { Page } from './navigation'

export default function AnalysisView({ analysis, text, page = analysis.status === 'completed' ? 'summary' : 'status' }: {
  analysis: AnalysisState; text: string; page?: Exclude<Page, 'home'>
}) {
  return page === 'summary' && analysis.status === 'completed'
    ? <SummaryScreen analysis={analysis} text={text} />
    : <AnalysisScreen analysis={analysis} />
}
```


