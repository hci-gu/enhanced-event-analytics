import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { componentUrl } from './tsx.mjs'

const { default: SummaryScreen } = await import(await componentUrl('SummaryScreen'))

test('summary renders title, registry order, accessible highlights and evidence fallbacks', () => {
  const analysis = { analysisId: 'analysis-uuid', title: 'Vatten stiger', status: 'completed', workflows: [
    { id: 'risks', label: 'Riskområden', status: 'completed', results: [{ ID: 'flood', name: 'Översvämningar', evidence: ['vatten'] }] },
    { id: 'reach', label: 'Räckvidd', status: 'completed', results: [{ ID: 'local', name: 'Lokalt', evidence: [] }] },
    { id: 'service', label: 'Verksamheter', status: 'completed', results: [] },
  ], completedIds: ['service', 'reach', 'risks'], error: null }
  const html = renderToStaticMarkup(createElement(SummaryScreen, { analysis, text: '  vatten\n<script>  ' }))
  assert.match(html, /Vatten stiger/)
  assert.doesNotMatch(html, /analysis-uuid/)
  assert.match(html, /<mark[^>]*role="button"[^>]*tabindex="0"/)
  assert.match(html, /Textstöd: Riskområden: Översvämningar/)
  assert.match(html, /Verifierat textstöd saknas/)
  assert.match(html, /Inga kategorier matchade/)
  assert.match(html, /&lt;script&gt;/)
  assert.doesNotMatch(html, /<details[^>]*\bopen\b|progressbar|workflow-spinner/)
  assert.ok(html.indexOf('class="workflow-label">Riskområden') < html.indexOf('class="workflow-label">Räckvidd'))
})
