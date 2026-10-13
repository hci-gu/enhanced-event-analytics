# Page dependency trees

All local imports were traced; React/ReactDOM and build package imports are excluded. App-level stylesheet and bootstrap tokens affect every state. Files listed here are candidates for budgeted context, not an instruction to send the entire tree.

## / — home state
Entry: `frontend/src/main.tsx` → `frontend/src/App.tsx`

```text
frontend/src/main.tsx
  frontend/src/colors.css
  frontend/src/index.css
  frontend/src/App.tsx
    frontend/src/App.css
    frontend/src/api.ts
      frontend/src/analysis.ts
    frontend/src/analysis.ts
    frontend/src/navigation.ts
      frontend/src/analysis.ts (type)
    frontend/src/PageMenu.tsx
      frontend/src/PageMenu.css
      frontend/src/navigation.ts
        frontend/src/analysis.ts (type)
      frontend/src/analysis.ts (type)
    frontend/src/AnalysisView.tsx
      frontend/src/analysis.ts (type)
      frontend/src/navigation.ts (type)
      frontend/src/AnalysisScreen.tsx
        frontend/src/AnalysisScreen.css
        frontend/src/analysis.ts
        frontend/src/WorkflowRow.tsx
          frontend/src/analysis.ts (type)
      frontend/src/SummaryScreen.tsx
        frontend/src/AnalysisScreen.css
        frontend/src/SummaryScreen.css
        frontend/src/analysis.ts (type)
        frontend/src/evidence.ts
          frontend/src/analysis.ts (type)
        frontend/src/WorkflowRow.tsx
          frontend/src/analysis.ts (type)
```

## / — status state
Entry: `frontend/src/AnalysisScreen.tsx`. Uses the App shell, PageMenu, bootstrap tokens and analysis lifecycle shown above.

```text
frontend/src/AnalysisScreen.tsx
  frontend/src/analysis.ts
  frontend/src/WorkflowRow.tsx
    frontend/src/analysis.ts (type)
  frontend/src/AnalysisScreen.css
```

### `frontend/src/AnalysisScreen.tsx`

```tsx
import { useEffect, useRef } from 'react'
import { analysisProgress } from './analysis'
import type { AnalysisState } from './analysis'
import WorkflowRow from './WorkflowRow'
import './AnalysisScreen.css'

export default function AnalysisScreen({ analysis }: { analysis: AnalysisState }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const progress = analysisProgress(analysis)
  const activeWorkflow = analysis.workflows.find((workflow) => workflow.status === 'running')
  const message = analysis.status === 'preparing' ? 'Förbereder analysen…'
    : analysis.status === 'completed' ? 'Analysen är färdig'
    : analysis.status === 'failed' ? 'Analysen avbröts'
    : activeWorkflow ? `Analys pågår: ${activeWorkflow.label}` : 'Analys pågår'

  useEffect(() => { if (analysis.title) headingRef.current?.focus() }, [analysis.title])

  return (
    <section className="analysis-screen" aria-labelledby={analysis.title ? 'analysis-title' : undefined}
      aria-label={analysis.title ? undefined : 'Händelseanalys'}>
      <h1 id="analysis-title" ref={headingRef} tabIndex={-1} aria-hidden={!analysis.title}>
        {analysis.title}
      </h1>
      <p className="visually-hidden" role="status" aria-live="polite">{message}</p>
      <div className="workflow-status-panel">
          <ol className="workflow-status-list" aria-label="Analysens arbetsflöden">
            {analysis.workflows.map((workflow) => (
              <li key={workflow.id}>
                <WorkflowRow workflow={workflow} showTags showStatus />
              </li>
            ))}
          </ol>
          {progress !== null && (
            <div className="analysis-progress" role="progressbar" aria-label="Klara arbetsflöden"
              aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
              <svg viewBox="0 0 100 100" aria-hidden="true">
                <circle className="progress-track" cx="50" cy="50" r="44" />
                <circle className="progress-value" cx="50" cy="50" r="44" pathLength="100"
                  strokeDasharray={`${progress} 100`} />
              </svg>
              <span>{progress}%</span>
            </div>
          )}
      </div>
      {analysis.error && <p className="analysis-error" role="alert">{analysis.error}</p>}
    </section>
  )
}
```

## / — summary state
Entry: `frontend/src/SummaryScreen.tsx`. Uses the same shell. Evidence ranges preserve source text exactly and support hover/focus/pinned selection and Escape clearing.

```text
frontend/src/SummaryScreen.tsx
  frontend/src/analysis.ts (type)
  frontend/src/evidence.ts
    frontend/src/analysis.ts (type)
  frontend/src/WorkflowRow.tsx
    frontend/src/analysis.ts (type)
  frontend/src/AnalysisScreen.css
  frontend/src/SummaryScreen.css
```

### `frontend/src/SummaryScreen.tsx`

```tsx
import { useEffect, useMemo, useReducer, useRef } from 'react'
import type { CSSProperties } from 'react'
import type { AnalysisState } from './analysis'
import { activeSelection, evidenceSegments, highlightBands, initialInteraction, interact, workflowColor } from './evidence'
import type { Selection } from './evidence'
import WorkflowRow from './WorkflowRow'
import './AnalysisScreen.css'
import './SummaryScreen.css'

export default function SummaryScreen({ analysis, text }: { analysis: AnalysisState; text: string }) {
  const heading = useRef<HTMLHeadingElement>(null)
  const [interaction, dispatch] = useReducer(interact, initialInteraction)
  const selection = activeSelection(interaction)
  const segments = useMemo(() => evidenceSegments(text, analysis.workflows), [text, analysis.workflows])
  useEffect(() => { heading.current?.focus() }, [])

  function events(target: Selection, hover = true) {
    return {
      onMouseEnter: hover ? () => dispatch({ type: 'hover', selection: target }) : undefined,
      onMouseLeave: hover ? () => dispatch({ type: 'hover', selection: null }) : undefined,
      onFocus: () => dispatch({ type: 'focus', selection: target }),
      onBlur: () => dispatch({ type: 'focus', selection: null }),
      onClick: () => dispatch({ type: 'pin', selection: target }),
    }
  }

  return (
    <section className="summary-screen" aria-labelledby="summary-title"
      onKeyDown={(event) => {
        if (event.key === 'Escape') dispatch({ type: 'clear' })
      }}>
      <h1 id="summary-title" ref={heading} tabIndex={-1}>{analysis.title}</h1>
      <p className="visually-hidden" role="status">Analysen är färdig. Sammanfattning med markerat textstöd.</p>
      <div className="summary-columns">
        <section className="summary-text" aria-label="Ursprunglig händelsetext" tabIndex={0}>
          {segments.map((segment) => {
            if (!segment.owners.length) return segment.text
            const ids = [...new Set(segment.owners.map((owner) => owner.workflowId))]
            const target = { workflowIds: ids, segmentStart: segment.start }
            const selected = selection?.segmentStart !== undefined
              ? selection.segmentStart === segment.start
              : ids.some((id) => selection?.workflowIds.includes(id))
            const label = segment.owners.map((owner) =>
              `${analysis.workflows.find((workflow) => workflow.id === owner.workflowId)?.label}: ${owner.categoryName}`).join('; ')
            return <mark key={segment.start} className="evidence-highlight" role="button" tabIndex={0}
              aria-label={`Textstöd: ${label}. ${segment.text}`} aria-pressed={interaction.pinned?.segmentStart === segment.start}
              data-active={selected || undefined} style={{ background: highlightBands(ids) }} {...events(target)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  dispatch({ type: 'pin', selection: target })
                }
              }}>{segment.text}</mark>
          })}
        </section>
        <section className="summary-results" aria-label="Arbetsflöden och kategorier" tabIndex={0}>
          {analysis.workflows.map((workflow) => {
            const selected = selection?.workflowIds.includes(workflow.id)
            return <WorkflowRow key={workflow.id} workflow={workflow} selected={selected}
              rowEvents={{
                onMouseEnter: () => dispatch({ type: 'hover', selection: { workflowIds: [workflow.id] } }),
                onMouseLeave: () => dispatch({ type: 'hover', selection: null }),
              }}
              summaryEvents={events({ workflowIds: [workflow.id] }, false)}
              style={{ '--workflow-evidence-color': workflowColor(workflow.id) } as CSSProperties} />
          })}
        </section>
      </div>
    </section>
  )
}
```

## Static and build dependencies
`frontend/index.html` sets lang=sv and title Förstärkt Analysförmåga. `frontend/vite.config.ts` configures React compiler and /api proxy for dev and preview. There are no imported image assets in the current app; starter SVGs and hero.png exist but are unused. Native SVG search/menu/chevron icons are embedded in components.

