import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { componentUrl } from './tsx.mjs'
import { advanceAnalysis, initialAnalysis } from '../src/analysis.ts'

const { default: AnalysisScreen } = await import(await componentUrl('AnalysisScreen'))
const render = (analysis) => renderToStaticMarkup(createElement(AnalysisScreen, { analysis }))
const analysisId = '6e2a1df4-657b-4a75-b899-d42afdc50953'
const start = { type: 'analysis_started', analysisId, workflows: [{ id: 'a', label: 'Riskområden' }, { id: 'b', label: 'Räckvidd' }] }

test('screen renders preparation, queued labels and an active spinner', () => {
  assert.match(render(initialAnalysis), /Förbereder analysen/)
  let state = advanceAnalysis(initialAnalysis, start)
  state = advanceAnalysis(state, { type: 'workflow_started', id: 'a' })
  const html = render(state)
  assert.match(html, /<h1[^>]*aria-hidden="true"[^>]*><\/h1>/)
  assert.doesNotMatch(html, new RegExp(analysisId))
  assert.doesNotMatch(html, /Inga klara resultat ännu|class="analysis-message"|class="results-empty"/)
  assert.match(html, /workflow-spinner/)
  assert.match(html, /Pågår/)
  assert.match(html, /I kö/)
  assert.match(html, /role="progressbar"/)
})

test('successful screen hides progress and renders collapsed rows in registry order with tags and evidence', () => {
  let state = advanceAnalysis(initialAnalysis, start)
  state = advanceAnalysis(state, { type: 'title_completed', title: 'Översvämningar påverkar vägar' })
  state = advanceAnalysis(state, { type: 'workflow_started', id: 'b' })
  state = advanceAnalysis(state, { type: 'workflow_completed', id: 'b', results: [] })
  state = advanceAnalysis(state, { type: 'workflow_started', id: 'a' })
  state = advanceAnalysis(state, { type: 'workflow_completed', id: 'a', results: [{ ID: 'flood', name: 'Översvämningar', evidence: ['Vatten stiger'] }] })
  state = advanceAnalysis(state, { type: 'analysis_completed' })
  const html = render(state)
  assert.doesNotMatch(html, /role="progressbar"|workflow-spinner|<details[^>]*\bopen\b/)
  assert.match(html, /Analysen är färdig/)
  assert.match(html, /Översvämningar påverkar vägar/)
  assert.doesNotMatch(html, new RegExp(analysisId))
  assert.match(html, /Inga kategorier matchade/)
  assert.match(html, /Översvämningar/)
  assert.ok(html.indexOf('Riskområden') < html.indexOf('Räckvidd'))
  assert.match(html, /class="workflow-tag">Översvämningar/)
  assert.match(html, /<q>Vatten stiger<\/q>/)
})

test('failed screen retains static progress, marks skipped workflows and announces error', () => {
  let state = advanceAnalysis(initialAnalysis, start)
  state = advanceAnalysis(state, { type: 'title_completed', title: 'Översvämningar påverkar vägar' })
  state = advanceAnalysis(state, { type: 'workflow_started', id: 'a' })
  state = advanceAnalysis(state, { type: 'workflow_failed', id: 'a', code: 502, message: 'Analysen misslyckades' })
  const html = render(state)
  assert.match(html, /role="progressbar"/)
  assert.match(html, /Ej körd/)
  assert.match(html, /role="alert"/)
  assert.match(html, /Översvämningar påverkar vägar/)
  assert.doesNotMatch(html, /workflow-spinner/)
  assert.doesNotMatch(html, /<details/)
})
