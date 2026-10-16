import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { parseDateResults, displaySourceDate } from '../src/dates.ts'
import { advanceAnalysis, initialAnalysis, parseAnalysisEvent } from '../src/analysis.ts'
import { componentUrl } from './tsx.mjs'
import { pageAfterUpdate } from '../src/navigation.ts'

const { default: SummaryScreen } = await import(await componentUrl('SummaryScreen'))
const dates = {
  published_at: '2026-10-15T06:05', event_start: '2026-10-14T22:35', event_end: '2026-10-15T00:30',
  end_status: 'dated', duration_hint: '~2H',
  evidence: { published_at: ['Publicerad igår 06:05'], event_start: ['Branden startade'], event_end: ['Branden släcktes'] },
}
const analysis = {
  ...initialAnalysis, status: 'completed', title: 'Brand', analyzedAt: '2026-10-16T12:56:00Z', dates,
  workflows: [{ id: 'risks', label: 'Riskområden', status: 'completed', results: [] }],
}
const render = (data) => renderToStaticMarkup(createElement(SummaryScreen, {
  analysis: data, text: 'Branden startade. Branden släcktes. Publicerad igår 06:05',
}))

test('completion retains valid dates and records completion time without changing category results', () => {
  const event = parseAnalysisEvent('analysis_completed', JSON.stringify({ dates, dates_error: null }))
  const before = Date.now()
  const result = advanceAnalysis({ ...initialAnalysis, status: 'running' }, event)
  assert.deepEqual(result.dates, dates)
  assert.ok(Date.parse(result.analyzedAt) >= before)
  assert.deepEqual(result.workflows, [])
  assert.equal(advanceAnalysis(initialAnalysis, { type: 'analysis_started', analysisId: 'new', workflows: [] }).dates, null)
})

test('invalid or absent date outputs preserve successful category completion and hide the timeline', () => {
  const empty = { ...dates, published_at: null, event_start: null, event_end: null }
  for (const value of [null, {}, [], empty, { ...dates, evidence: null }]) {
    const event = parseAnalysisEvent('analysis_completed', JSON.stringify({ dates: value }))
    assert.equal(event.dates, null)
    assert.equal(advanceAnalysis({ ...initialAnalysis, status: 'running' }, event).status, 'completed')
    assert.doesNotMatch(render({ ...analysis, dates: event.dates }), /class="date-timeline"/)
  }
  assert.equal(parseAnalysisEvent('analysis_completed', JSON.stringify({ dates, dates_error: { code: 502 } })).dates, null)
})

test('date parsing rejects impossible dates, times and offsets, and preserves date-only precision', () => {
  for (const value of ['2026-02-30', '2026-13-15', '2026-10-15T24:00', '2026-10-15T00:99', '2026-10-15T00:30+00:99']) {
    assert.equal(parseDateResults({ ...dates, event_start: value }).event_start, null)
  }
  assert.equal(displaySourceDate('2026-10-15'), '15 okt')
  assert.equal(displaySourceDate('2026-10-15T06:05+09:00'), '15 okt · 06:05')
})

test('timeline follows categories, uses the approved copy and offers selectable chronological points', () => {
  const html = render(analysis)
  assert.ok(html.indexOf('class="date-timeline"') > html.indexOf('class="workflow-label"'))
  assert.match(html, /class="date-timeline-toggle" aria-expanded="false"/)
  assert.match(html, /class="date-timeline-details"[^>]*aria-hidden="true" inert=""/)
  assert.doesNotMatch(html, /Välj en tidpunkt|Tidslinje &amp; textstöd|Kategoriseringsresultat|proportionell/)
  assert.match(html, /Grov varaktighet: <strong>~2 timmar/)
  assert.match(html, /aria-pressed="true" aria-controls=/)
  assert.match(html, /“Branden startade”/)
  assert.ok(html.indexOf('>Händelsestart<') < html.indexOf('>Händelseslut<'))
  assert.ok(html.indexOf('>Händelseslut<') < html.indexOf('>Källan publicerad<'))
})

test('partial dates do not fabricate missing points; ongoing intervals have a separate open end', () => {
  const html = render({ ...analysis, dates: { ...dates, published_at: null, event_end: null, end_status: 'until_further_notice' } })
  assert.doesNotMatch(html, /data-kind="published_at"|data-kind="event_end"/)
  assert.match(html, /data-kind="ongoing"/)
  assert.match(html, /Tills vidare/)
  assert.match(html, /data-kind="analysis"/)
})

test('date progress stays active after categories and nonfatal failure still opens summary', () => {
  let state = advanceAnalysis(initialAnalysis, { type: 'analysis_started', analysisId: 'test', workflows: [
    { id: 'risks', label: 'Riskområden' }, { id: 'dates', label: 'Datum' },
  ] })
  state = advanceAnalysis(state, { type: 'workflow_started', id: 'risks' })
  state = advanceAnalysis(state, { type: 'workflow_completed', id: 'risks', results: [] })
  state = advanceAnalysis(state, { type: 'workflow_started', id: 'dates' })
  assert.equal(state.status, 'running')
  assert.equal(state.workflows[1].status, 'running')
  assert.throws(() => advanceAnalysis(state, { type: 'analysis_completed' }), /oväntad ordning/)
  const event = parseAnalysisEvent('workflow_completed', JSON.stringify({
    id: 'dates', results: [], dates: null, dates_error: { code: 502, message: 'Date extraction failed' },
  }))
  state = advanceAnalysis(state, event)
  assert.equal(state.workflows[1].status, 'failed')
  assert.equal(state.error, null)
  state = advanceAnalysis(state, { type: 'analysis_completed', dates: null })
  assert.equal(state.status, 'completed')
  assert.equal(pageAfterUpdate('status', 'running', state.status), 'summary')
  assert.doesNotMatch(render(state), /class="date-timeline"|workflow-label">Datum/)
})
