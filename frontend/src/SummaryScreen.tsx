import { useEffect, useMemo, useReducer, useRef } from 'react'
import type { CSSProperties } from 'react'
import type { AnalysisState } from './analysis'
import { activeSelection, evidenceSegments, highlightBands, initialInteraction, interact, workflowColor } from './evidence'
import type { Selection } from './evidence'
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
            return <details key={workflow.id} className="workflow-result summary-result" data-active={selected || undefined}
              onMouseEnter={() => dispatch({ type: 'hover', selection: { workflowIds: [workflow.id] } })}
              onMouseLeave={() => dispatch({ type: 'hover', selection: null })}
              style={{ '--workflow-evidence-color': workflowColor(workflow.id) } as CSSProperties}>
              <summary {...events({ workflowIds: [workflow.id] }, false)}>{workflow.label}</summary>
              {workflow.results.length ? <ul>{workflow.results.map((match) => <li key={match.ID}>
                <strong>{match.name}</strong>
                {match.evidence?.length ? <ul className="evidence-quotes">{match.evidence.map((quote) =>
                  <li key={quote}><q>{quote}</q></li>)}</ul> : <p>Verifierat textstöd saknas.</p>}
              </li>)}</ul> : <p>Inga kategorier matchade.</p>}
            </details>
          })}
        </section>
      </div>
    </section>
  )
}
