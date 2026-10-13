import { useEffect, useRef } from 'react'
import type { CSSProperties, HTMLAttributes, MouseEvent } from 'react'
import type { WorkflowState } from './analysis'

const stateLabels = {
  queued: 'I kö', running: 'Pågår', completed: 'Klar', failed: 'Misslyckades', skipped: 'Ej körd',
}

export default function WorkflowRow({ workflow, showTags = false, showStatus = false, selected,
  style, rowEvents, summaryEvents }: {
  workflow: WorkflowState; showTags?: boolean; showStatus?: boolean; selected?: boolean
  style?: CSSProperties; rowEvents?: HTMLAttributes<HTMLElement>; summaryEvents?: HTMLAttributes<HTMLElement>
}) {
  const detailsRef = useRef<HTMLDetailsElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const animation = useRef<Animation | null>(null)
  const targetOpen = useRef<boolean | null>(null)
  useEffect(() => () => animation.current?.cancel(), [])

  function toggle(event: MouseEvent<HTMLElement>) {
    summaryEvents?.onClick?.(event)
    if (event.defaultPrevented) return
    event.preventDefault()
    const details = detailsRef.current
    const body = bodyRef.current
    if (!details || !body) return

    const opening = !(targetOpen.current ?? details.open)
    const height = body.getBoundingClientRect().height
    const opacity = details.open ? getComputedStyle(body).opacity : '0'
    animation.current?.cancel()
    targetOpen.current = opening
    body.inert = !opening
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      details.open = opening
      targetOpen.current = null
      animation.current = null
      return
    }

    // Keep native details open until its content has finished collapsing.
    details.open = true
    const motion = body.animate({
      height: [`${height}px`, opening ? `${body.scrollHeight}px` : '0px'],
      opacity: [opacity, opening ? '1' : '0'],
    }, { duration: 180, easing: 'ease-out' })
    animation.current = motion
    motion.onfinish = () => {
      details.open = opening
      targetOpen.current = null
      animation.current = null
    }
  }

  const completed = workflow.status === 'completed'
  const header = <>
    {showStatus &&
      <span className={`workflow-symbol ${workflow.status === 'running' ? 'workflow-spinner' : ''}`} aria-hidden="true">
        {completed ? '✓' : workflow.status === 'failed' ? '!' : ''}
      </span>
    }
    <div className="workflow-heading">
      <span className="workflow-label">{workflow.label}{!showStatus &&
        <span className="workflow-color-dot" aria-hidden="true" />}</span>
      {showTags && completed && <span className="workflow-tags">
        {workflow.results.length ? workflow.results.map((match) =>
          <span className="workflow-tag" key={match.ID}>{match.name}</span>)
          : <span className="workflow-no-matches">Inga kategorier matchade.</span>}
      </span>}
      {!showStatus && <span className="workflow-category-names">
        {workflow.results.length ? workflow.results.map((match) => match.name).join(', ') : 'Inga kategorier matchade.'}
      </span>}
    </div>
    {showStatus && <span className="workflow-state-text">{stateLabels[workflow.status]}</span>}
    {completed && <span className="workflow-chevron" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none"><path d="m6 9 6 6 6-6" /></svg>
    </span>}
  </>

  const className = `workflow-result workflow-${workflow.status}`
  if (!completed) return <div className={className}>
    <div className="workflow-row-header workflow-unavailable" aria-disabled="true">{header}</div>
  </div>

  return <details ref={detailsRef} className={className} data-active={selected || undefined} style={style} {...rowEvents}>
    <summary className="workflow-row-header" {...summaryEvents} onClick={toggle}>{header}</summary>
    <div className="workflow-disclosure-body" ref={bodyRef}>
    <div className="workflow-row-content">
      {workflow.results.length ? <ul>{workflow.results.map((match) => <li key={match.ID}>
        <strong>{match.name}</strong>
        {match.evidence?.length ? <ul className="evidence-quotes">{match.evidence.map((quote) =>
          <li key={quote}><q>{quote}</q></li>)}</ul> : <p>Verifierat textstöd saknas.</p>}
      </li>)}</ul> : <p>Inga kategorier matchade.</p>}
    </div>
    </div>
  </details>
}
