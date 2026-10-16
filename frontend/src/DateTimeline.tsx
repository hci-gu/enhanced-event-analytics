import { useId, useState } from 'react'
import { datePosition, displayDuration, displaySourceDate } from './dates'
import type { DateField, DateResults } from './dates'
import './DateTimeline.css'

type Point = { id: string; label: string; value: string | null; quotes: string[] }

export default function DateTimeline({ dates, analyzedAt, text }: {
  dates: DateResults; analyzedAt: string; text: string
}) {
  const id = useId()
  const labels: Record<DateField, string> = {
    event_start: 'Händelsestart', event_end: 'Händelseslut', published_at: 'Källan publicerad',
  }
  const points: Point[] = (['event_start', 'event_end', 'published_at'] as const)
    .filter((field) => dates[field] !== null)
    .map((field) => ({ id: field, label: labels[field], value: dates[field],
      quotes: dates.evidence[field].filter((quote) => quote.trim() && text.includes(quote)) }))
    .sort((a, b) => datePosition(a.value!) - datePosition(b.value!))
  const analysisDate = new Date(analyzedAt)
  const analysisDay = new Intl.DateTimeFormat('sv-SE', {
    year: 'numeric', month: 'long', day: 'numeric',
  }).format(analysisDate)
  const analysisTime = new Intl.DateTimeFormat('sv-SE', { hour: '2-digit', minute: '2-digit' }).format(analysisDate)
  const analysisLabel = new Intl.DateTimeFormat('sv-SE', { day: 'numeric', month: 'short' }).format(analysisDate)
    + ` · ${analysisTime}`
  // Analystid is a system reference, not a source event date.
  const analysisPoint = { id: 'analysis', label: 'Analys · nu', value: null, quotes: [] }
  // Place the analysis reference among dated milestones, including future events.
  const referencePosition = points.findIndex((point) => datePosition(point.value!) > analysisDate.getTime())
  points.splice(referencePosition === -1 ? points.length : referencePosition, 0, analysisPoint)
  if (dates.end_status === 'until_further_notice' && !dates.event_end) {
    points.push({ id: 'ongoing', label: 'Händelseslut', value: null,
      quotes: dates.evidence.event_end.filter((quote) => quote.trim() && text.includes(quote)) })
  }
  const [selectedId, setSelectedId] = useState(points[0].id)
  const selected = points.find((point) => point.id === selectedId) ?? points[0]

  return <section className="date-timeline" aria-labelledby={`${id}-title`}>
    <h2 id={`${id}-title`}>Tidslinje</h2>
    <ol className="date-timeline-points" aria-label="Händelsens tidpunkter i kronologisk ordning">
      {points.map((point) => <li key={point.id}>
        <button type="button" className="date-timeline-point" data-kind={point.id}
          aria-pressed={selected.id === point.id} aria-controls={`${id}-evidence`}
          onClick={() => setSelectedId(point.id)}>
          <span className="date-point-label">{point.label}</span>
          {point.value ? <time dateTime={point.value}>{displaySourceDate(point.value)}</time>
            : point.id === 'analysis' ? <time dateTime={analyzedAt}>{analysisLabel}</time> : <strong>Tills vidare</strong>}
        </button>
      </li>)}
    </ol>
    <div className="date-timeline-evidence" id={`${id}-evidence`} aria-live="polite" aria-atomic="true">
      <p className="date-evidence-label">{selected.id === 'analysis' ? 'Analystid' : `Textstöd · ${selected.label.toLocaleLowerCase('sv-SE')}`}</p>
      {selected.id === 'analysis'
        ? <p>Analystiden registreras av systemet {analysisDay} kl. {analysisTime}.</p>
        : selected.quotes.length ? selected.quotes.map((quote) => <blockquote key={quote}>“{quote}”</blockquote>)
          : <p>Verifierat textstöd saknas.</p>}
    </div>
    {dates.duration_hint && <p className="date-timeline-duration">Grov varaktighet: <strong>{displayDuration(dates.duration_hint)}</strong></p>}
  </section>
}
