# Shared UI components

Framework: React 19 with TypeScript, Vite 8, vanilla CSS. No component library, router package, Tailwind, or icon library is installed.

## WorkflowRow
Source: `frontend/src/WorkflowRow.tsx`. Shared status/result accordion used by both AnalysisScreen and SummaryScreen. Props: workflow, showTags, showStatus, selected, style, rowEvents, summaryEvents. Native details/summary enables keyboard disclosure; evidence interactions are supplied by the summary page.

### `frontend/src/WorkflowRow.tsx`

```tsx
import type { CSSProperties, HTMLAttributes } from 'react'
import type { WorkflowState } from './analysis'

const stateLabels = {
  queued: 'I kö', running: 'Pågår', completed: 'Klar', failed: 'Misslyckades', skipped: 'Ej körd',
}

export default function WorkflowRow({ workflow, showTags = false, showStatus = false, selected,
  style, rowEvents, summaryEvents }: {
  workflow: WorkflowState; showTags?: boolean; showStatus?: boolean; selected?: boolean
  style?: CSSProperties; rowEvents?: HTMLAttributes<HTMLElement>; summaryEvents?: HTMLAttributes<HTMLElement>
}) {
  const completed = workflow.status === 'completed'
  const header = <>
    <span className="workflow-label">{workflow.label}</span>
    {showStatus && <>
      {(workflow.status === 'running' || completed || workflow.status === 'failed') &&
        <span className={`workflow-symbol ${workflow.status === 'running' ? 'workflow-spinner' : ''}`} aria-hidden="true">
          {completed ? '✓' : workflow.status === 'failed' ? '!' : ''}
        </span>}
      <span className="visually-hidden">: {stateLabels[workflow.status]}</span>
      {workflow.status === 'skipped' && <small>Ej körd</small>}
    </>}
    {showTags && completed && <span className="workflow-tags">
      {workflow.results.length ? workflow.results.map((match) =>
        <span className="workflow-tag" key={match.ID}>{match.name}</span>)
        : <span className="workflow-no-matches">Inga kategorier matchade.</span>}
    </span>}
    <span className="workflow-chevron" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none"><path d="m6 9 6 6 6-6" /></svg>
    </span>
  </>

  const className = `workflow-result workflow-${workflow.status}`
  if (!completed) return <div className={className}>
    <div className="workflow-row-header workflow-unavailable" aria-disabled="true">{header}</div>
  </div>

  return <details className={className} data-active={selected || undefined} style={style} {...rowEvents}>
    <summary className="workflow-row-header" {...summaryEvents}>{header}</summary>
    <div className="workflow-row-content">
      {workflow.results.length ? <ul>{workflow.results.map((match) => <li key={match.ID}>
        <strong>{match.name}</strong>
        {match.evidence?.length ? <ul className="evidence-quotes">{match.evidence.map((quote) =>
          <li key={quote}><q>{quote}</q></li>)}</ul> : <p>Verifierat textstöd saknas.</p>}
      </li>)}</ul> : <p>Inga kategorier matchade.</p>}
    </div>
  </details>
}
```

## Other primitives
Buttons, textarea, search input, progress ring and health dialog are native elements within page files; there is no separate primitive directory. Navigation source is in layouts.md. Shared workflow styling is in theme.md.

