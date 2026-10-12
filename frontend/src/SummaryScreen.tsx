import { useEffect, useMemo, useReducer, useRef } from 'react'
import type { CSSProperties } from 'react'
import type { AnalysisState } from './analysis'
import { activeSelection, evidenceSegments, highlightBands, initialInteraction, interact, workflowColor } from './evidence'
import type { Selection } from './evidence'
import WorkflowRow from './WorkflowRow'
import './AnalysisScreen.css'
import './SummaryScreen.css'

export default function SummaryScreen({ analysis, text, onNewAnalysis }: {
  analysis: AnalysisState; text: string; onNewAnalysis?: () => void
}) {
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
      <div className="summary-heading">
        <div>
          <p className="screen-label">Sammanfattning</p>
          <h1 id="summary-title" ref={heading} tabIndex={-1}>{analysis.title}</h1>
        </div>
        {onNewAnalysis && <button type="button" className="text-action" onClick={onNewAnalysis}>Ny analys</button>}
      </div>
      <p className="visually-hidden" role="status">Analysen är färdig. Sammanfattning med markerat textstöd.</p>
      <div className="summary-columns">
        <section className="summary-pane" aria-labelledby="source-label">
          <h2 id="source-label" className="pane-label">Händelsetext</h2>
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
        </section>
        <section className="summary-pane" aria-labelledby="results-label">
          <h2 id="results-label" className="pane-label">Analysresultat</h2>
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
        </section>
      </div>
    </section>
  )
}
