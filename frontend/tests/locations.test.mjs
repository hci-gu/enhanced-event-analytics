import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { componentUrl } from './tsx.mjs'
import { advanceAnalysis, initialAnalysis, parseAnalysisEvent } from '../src/analysis.ts'
import { loadSavedAnalysis } from '../src/history.ts'

const { default: AnalysisScreen } = await import(await componentUrl('AnalysisScreen'))
const { default: SummaryScreen } = await import(await componentUrl('SummaryScreen'))
const { default: WorkflowRow } = await import(await componentUrl('WorkflowRow'))
const analysisId = '01234567-89ab-4cde-8fab-0123456789ab'
const location = [{ mentions: ['Secret place'], longitude: 18.062, latitude: 59.33, city: 'Secret city' }]

test('location progress finishes after nonfatal errors without retaining payload or error details', () => {
  let state = advanceAnalysis(initialAnalysis, { type: 'analysis_started', analysisId,
    workflows: [{ id: 'location', label: 'Lokalisering' }] })
  assert.match(renderToStaticMarkup(createElement(AnalysisScreen, { analysis: state })), /I kö/)
  state = advanceAnalysis(state, { type: 'workflow_started', id: 'location' })
  assert.match(renderToStaticMarkup(createElement(AnalysisScreen, { analysis: state })), /Pågår/)
  state = advanceAnalysis(state, parseAnalysisEvent('workflow_completed', JSON.stringify({
    id: 'location', results: [], location, location_error: { code: 502, message: 'Secret provider error' },
  })))
  state = advanceAnalysis(state, parseAnalysisEvent('analysis_completed', JSON.stringify({ location, location_error: { code: 502 } })))
  assert.equal(state.status, 'completed')
  assert.deepEqual(state.workflows[0].results, [])
  assert.doesNotMatch(JSON.stringify(state), /Secret|18\.062|location_error/)
  const html = renderToStaticMarkup(createElement(AnalysisScreen, { analysis: state }))
  assert.match(html, /Lokalisering|Klar/)
  assert.doesNotMatch(html, /Inga kategorier|<details|workflow-chevron|workflow-tags|Secret/)
  assert.doesNotMatch(renderToStaticMarkup(createElement(SummaryScreen, { analysis: state, text: 'Source' })), /Lokalisering|Secret/)
})

test('location row never expands or displays names, counts, highlights or errors', () => {
  const html = renderToStaticMarkup(createElement(WorkflowRow, {
    workflow: { id: 'location', label: 'Lokalisering', status: 'completed', error: 'Secret error',
      results: [{ ID: 'secret', name: 'Secret place' }] }, showTags: true, onToggleHighlights() {},
  }))
  assert.match(html, /Lokalisering/)
  assert.doesNotMatch(html, /Secret|Inga kategorier|<details|workflow-chevron|workflow-tag|role="switch"/)
})

test('disabled supplemental workflows need no progress events', () => {
  let state = advanceAnalysis(initialAnalysis, { type: 'analysis_started', analysisId, workflows: [] })
  state = advanceAnalysis(state, parseAnalysisEvent('analysis_completed', JSON.stringify({ location: null, dates: null })))
  assert.equal(state.status, 'completed')
  assert.doesNotMatch(renderToStaticMarkup(createElement(AnalysisScreen, { analysis: state })), /Lokalisering|Datum/)
})

test('saved location progress restores without treating location data as predictions', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({
    analysis_id: analysisId, title: 'Rubrik', status: 'Complete', created: '2026-10-23 12:00:00.000Z',
    original_text: 'Source', predictions: {}, workflows: [{ id: 'location', label: 'Lokalisering' }],
    location, location_error: { code: 502, message: 'Secret provider error' },
  }))
  const { analysis } = await loadSavedAnalysis(analysisId)
  assert.equal(analysis.workflows[0].status, 'completed')
  assert.deepEqual(analysis.workflows[0].results, [])
  assert.doesNotMatch(JSON.stringify(analysis), /Secret|18\.062/)
})
