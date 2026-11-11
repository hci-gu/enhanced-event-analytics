import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { componentUrl } from './tsx.mjs'

const { default: SummaryScreen } = await import(await componentUrl('SummaryScreen'))

test('summary renders results first in display order, accessible highlights and evidence fallbacks', () => {
  const analysis = { analysisId: 'analysis-uuid', title: 'Vatten stiger', status: 'completed', workflows: [
    { id: 'risks', label: 'Riskområden', status: 'completed', results: [{ ID: 'flood', name: 'Översvämningar', evidence: ['vatten'] }] },
    { id: 'reach', label: 'Räckvidd', status: 'completed', results: [{ ID: 'local', name: 'Lokalt', evidence: [] }] },
    { id: 'service', label: 'Verksamheter', status: 'completed', results: [] },
    { id: 'extra', label: 'Extra arbetsflöde', status: 'completed', results: [] },
    { id: 'properties', label: 'Egenskaper', status: 'completed', results: [] },
    { id: 'protection', label: 'Skyddsvärden', status: 'completed', results: [] },
  ], completedIds: ['service', 'reach', 'risks'], error: null,
  analyzedAt: '2026-11-11T12:00:00Z', dates: {
    published_at: '2026-11-10', event_start: null, event_end: null,
    end_status: 'unknown', duration_hint: null,
    evidence: { published_at: [], event_start: [], event_end: [] },
  } }
  const html = renderToStaticMarkup(createElement(SummaryScreen, { analysis, text: '  vatten\n<script>  ' }))
  assert.match(html, /Vatten stiger/)
  assert.doesNotMatch(html, /analysis-uuid/)
  assert.match(html, /<mark[^>]*role="button"[^>]*tabindex="0"/)
  assert.match(html, /Textstöd: Riskområden: Översvämningar/)
  assert.match(html, /role="switch" aria-checked="true" aria-label="Textmarkeringar för Riskområden"/)
  assert.match(html, /<button[^>]*aria-label="Visa textstöd i händelsetexten: vatten"/)
  assert.match(html, /Verifierat textstöd saknas/)
  assert.match(html, /Inga kategorier matchade/)
  assert.match(html, /&lt;script&gt;/)
  assert.doesNotMatch(html, /<details[^>]*\bopen\b|progressbar|workflow-spinner/)
  assert.ok(html.indexOf('aria-labelledby="results-label"') < html.indexOf('aria-labelledby="source-label"'))
  const labels = [...html.matchAll(/class="workflow-label">([^<]+)/g)].map((match) => match[1])
  assert.deepEqual(labels, ['Verksamheter', 'Skyddsvärden', 'Räckvidd', 'Riskområden', 'Egenskaper', 'Extra arbetsflöde'])
  assert.ok(html.indexOf('class="workflow-label">Egenskaper') < html.indexOf('class="date-timeline"'))
  assert.ok(html.indexOf('class="date-timeline"') < html.indexOf('class="workflow-label">Extra arbetsflöde'))
})
