import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { componentUrl } from './tsx.mjs'
import { advanceAnalysis, failAnalysis, initialAnalysis } from '../src/analysis.ts'

const url = await componentUrl('AnalysisView', {
  './AnalysisScreen': await componentUrl('AnalysisScreen'), './SummaryScreen': await componentUrl('SummaryScreen'),
})
const { default: AnalysisView } = await import(url)
const render = (analysis, page) => renderToStaticMarkup(createElement(AnalysisView, { analysis, page, text: ' original\ntext ' }))

test('opens summary only after successful terminal confirmation, never after failure', () => {
  let state = advanceAnalysis(initialAnalysis, { type: 'analysis_started', analysisId: 'uuid', workflows: [{ id: 'risks', label: 'Riskområden' }] })
  state = advanceAnalysis(state, { type: 'workflow_started', id: 'risks' })
  state = advanceAnalysis(state, { type: 'workflow_completed', id: 'risks', results: [] })
  assert.match(render(state), /class="analysis-screen"/)
  assert.match(render(failAnalysis(state, 'Anslutningen avbröts')), /class="analysis-screen"/)
  state = advanceAnalysis(state, { type: 'analysis_completed' })
  assert.match(render(state), /class="summary-screen"/)
  assert.match(render(state), / original\ntext /)
  assert.doesNotMatch(render(state), /progressbar/)
  assert.match(render(state, 'status'), /class="analysis-screen"/)
})
