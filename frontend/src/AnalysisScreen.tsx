import { useEffect, useRef } from 'react'
import { analysisProgress } from './analysis'
import type { AnalysisState } from './analysis'
import WorkflowRow from './WorkflowRow'
import './AnalysisScreen.css'

export default function AnalysisScreen({ analysis }: { analysis: AnalysisState }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const listRef = useRef<HTMLOListElement>(null)
  const progress = analysisProgress(analysis)
  const activeWorkflow = analysis.workflows.find((workflow) => workflow.status === 'running')
  const message = analysis.status === 'preparing' ? 'Förbereder analysen…'
    : analysis.status === 'completed' ? 'Analysen är färdig'
    : analysis.status === 'failed' ? 'Analysen avbröts'
    : activeWorkflow ? `Analys pågår: ${activeWorkflow.label}` : 'Analys pågår'

  useEffect(() => { if (analysis.title) headingRef.current?.focus() }, [analysis.title])
  useEffect(() => {
    const list = listRef.current
    const row = [...(list?.children ?? [])].find((item) => item instanceof HTMLElement
      && item.dataset.workflowId === activeWorkflow?.id)
    if (!list || !row) return
    const bounds = list.getBoundingClientRect()
    const target = row.getBoundingClientRect()
    if (target.bottom > bounds.bottom) list.scrollTop += target.bottom - bounds.bottom
    else if (target.top < bounds.top) list.scrollTop += target.top - bounds.top
  }, [activeWorkflow?.id])

  return (
    <section className="analysis-screen" aria-labelledby={analysis.title ? 'analysis-title' : undefined}
      aria-label={analysis.title ? undefined : 'Händelseanalys'}>
      <p className="screen-label">Analysstatus</p>
      <h1 id="analysis-title" ref={headingRef} tabIndex={-1} aria-hidden={!analysis.title}>
        {analysis.title}
      </h1>
      <p className="visually-hidden" role="status" aria-live="polite">{message}</p>
      <div className="workflow-status-panel">
        <ol ref={listRef} className="workflow-status-list" aria-label="Analysens arbetsflöden">
          {analysis.workflows.map((workflow) => (
            <li key={workflow.id} data-workflow-id={workflow.id}>
              <WorkflowRow workflow={workflow} showTags showStatus />
            </li>
          ))}
        </ol>
      </div>
      {progress !== null && (
        <div className="analysis-progress">
          <div className="progress-caption">
            <span>Arbetsflöden</span>
            <span><strong>{analysis.completedIds.length}</strong> av {analysis.workflows.length} klara</span>
          </div>
          <div className="progress-track" role="progressbar" aria-label="Klara arbetsflöden"
            aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
            <div className="progress-value" style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}
      {analysis.error && <p className="analysis-error" role="alert">{analysis.error}</p>}
    </section>
  )
}
