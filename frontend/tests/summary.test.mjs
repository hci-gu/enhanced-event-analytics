import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ts from 'typescript'

const source = await readFile(new URL('../src/SummaryScreen.tsx', import.meta.url), 'utf8')
let { outputText } = ts.transpileModule(source.replace(/import '\.\/.*\.css'/g, ''), {
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 },
})
for (const specifier of ['react/jsx-runtime', 'react', './evidence']) {
  const resolved = specifier === './evidence' ? new URL('../src/evidence.ts', import.meta.url).href : import.meta.resolve(specifier)
  outputText = outputText.replaceAll(`'${specifier}'`, `'${resolved}'`).replaceAll(`"${specifier}"`, `"${resolved}"`)
}
const { default: SummaryScreen } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)

test('summary renders UUID, registry order, accessible highlights and evidence fallbacks', () => {
  const analysis = { analysisId: 'analysis-uuid', status: 'completed', workflows: [
    { id: 'risks', label: 'Riskområden', results: [{ ID: 'flood', name: 'Översvämningar', evidence: ['vatten'] }] },
    { id: 'reach', label: 'Räckvidd', results: [{ ID: 'local', name: 'Lokalt', evidence: [] }] },
    { id: 'service', label: 'Verksamheter', results: [] },
  ], completedIds: ['service', 'reach', 'risks'], error: null }
  const html = renderToStaticMarkup(createElement(SummaryScreen, { analysis, text: '  vatten\n<script>  ' }))
  assert.match(html, /analysis-uuid/)
  assert.match(html, /<mark[^>]*role="button"[^>]*tabindex="0"/)
  assert.match(html, /Textstöd: Riskområden: Översvämningar/)
  assert.match(html, /Verifierat textstöd saknas/)
  assert.match(html, /Inga kategorier matchade/)
  assert.match(html, /&lt;script&gt;/)
  assert.doesNotMatch(html, /<details[^>]*\bopen\b|progressbar|workflow-spinner/)
  assert.ok(html.indexOf('<summary>Riskområden') < html.indexOf('<summary>Räckvidd'))
})
