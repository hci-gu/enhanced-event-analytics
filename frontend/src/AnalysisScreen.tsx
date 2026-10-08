import { useEffect, useRef } from 'react'
import { analysisProgress } from './analysis'
import type { AnalysisState } from './analysis'
import './AnalysisScreen.css'

const stateLabels = {
  queued: 'I kö', running: 'Pågår', completed: 'Klar', failed: 'Misslyckades', skipped: 'Ej körd',
}

export default function AnalysisScreen({ analysis }: { analysis: AnalysisState }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const progress = analysisProgress(analysis)
  const activeWorkflow = analysis.workflows.find((workflow) => workflow.status === 'running')
  const message = analysis.status === 'preparing' ? 'Förbereder analysen…'
    : analysis.status === 'completed' ? 'Analysen är färdig'
    : analysis.status === 'failed' ? 'Analysen avbröts'
    : activeWorkflow ? `Analys pågår: ${activeWorkflow.label}` : 'Analys pågår'

  useEffect(() => { headingRef.current?.focus() }, [])

  return (
    <section className="analysis-screen" aria-labelledby="analysis-title">
      <h1 id="analysis-title" ref={headingRef} tabIndex={-1}>
        {analysis.analysisId ?? <span className="visually-hidden">Händelseanalys</span>}
      </h1>
      <p className="visually-hidden" role="status" aria-live="polite">{message}</p>
      <div className="analysis-columns">
        <div className="workflow-status-panel">
          <ol className="workflow-status-list" aria-label="Analysens arbetsflöden">
            {analysis.workflows.map((workflow) => (
              <li key={workflow.id} className={`workflow-status workflow-${workflow.status}`}>
                <span className={`workflow-symbol ${workflow.status === 'running' ? 'workflow-spinner' : ''}`} aria-hidden="true">
                  {workflow.status === 'completed' ? '✓' : workflow.status === 'failed' ? '!' : ''}
                </span>
                <span>{workflow.label}<span className="visually-hidden">: {stateLabels[workflow.status]}</span></span>
                {workflow.status === 'skipped' && <small>Ej körd</small>}
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
        <section className="workflow-results-panel" aria-labelledby="results-title" tabIndex={0}>
          <h2 id="results-title" className="visually-hidden">Klara resultat</h2>
          {analysis.completedIds.map((id) => {
            const workflow = analysis.workflows.find((item) => item.id === id)!
            return (
              <details className="workflow-result" key={id}>
                <summary>{workflow.label}</summary>
                {workflow.results.length ? (
                  <ul>{workflow.results.map((match) => <li key={match.ID}>{match.name}</li>)}</ul>
                ) : <p>Inga kategorier matchade.</p>}
              </details>
            )
          })}
        </section>
      </div>
      {analysis.error && <p className="analysis-error" role="alert">{analysis.error}</p>}
    </section>
  )
}
