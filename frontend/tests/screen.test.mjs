import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ts from 'typescript'
import { advanceAnalysis, initialAnalysis } from '../src/analysis.ts'

// Compile TSX in memory for markup tests; Node supports TS but not JSX natively.
const source = await readFile(new URL('../src/AnalysisScreen.tsx', import.meta.url), 'utf8')
let { outputText } = ts.transpileModule(source.replace("import './AnalysisScreen.css'", ''), {
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 },
})
for (const specifier of ['react/jsx-runtime', 'react', './analysis']) {
  const resolved = specifier === './analysis' ? new URL('../src/analysis.ts', import.meta.url).href : import.meta.resolve(specifier)
  outputText = outputText.replaceAll(`'${specifier}'`, `'${resolved}'`).replaceAll(`"${specifier}"`, `"${resolved}"`)
}
const { default: AnalysisScreen } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
const render = (analysis) => renderToStaticMarkup(createElement(AnalysisScreen, { analysis }))
const analysisId = '6e2a1df4-657b-4a75-b899-d42afdc50953'
const start = { type: 'analysis_started', analysisId, workflows: [{ id: 'a', label: 'Riskområden' }, { id: 'b', label: 'Räckvidd' }] }

test('screen renders preparation, queued labels and an active spinner', () => {
  assert.match(render(initialAnalysis), /Förbereder analysen/)
  let state = advanceAnalysis(initialAnalysis, start)
  state = advanceAnalysis(state, { type: 'workflow_started', id: 'a' })
  const html = render(state)
  assert.doesNotMatch(html, /<h1/)
  assert.doesNotMatch(html, new RegExp(analysisId))
  assert.doesNotMatch(html, /Inga klara resultat ännu|class="analysis-message"|class="results-empty"/)
  assert.match(html, /<h2[^>]*class="visually-hidden"/)
  assert.match(html, /workflow-spinner/)
  assert.match(html, /Pågår/)
  assert.match(html, /I kö/)
  assert.match(html, /role="progressbar"/)
})

test('successful screen hides progress and renders collapsed results in completion order', () => {
  let state = advanceAnalysis(initialAnalysis, start)
  state = advanceAnalysis(state, { type: 'title_completed', title: 'Översvämningar påverkar vägar' })
  state = advanceAnalysis(state, { type: 'workflow_started', id: 'b' })
  state = advanceAnalysis(state, { type: 'workflow_completed', id: 'b', results: [] })
  state = advanceAnalysis(state, { type: 'workflow_started', id: 'a' })
  state = advanceAnalysis(state, { type: 'workflow_completed', id: 'a', results: [{ ID: 'flood', name: 'Översvämningar' }] })
  state = advanceAnalysis(state, { type: 'analysis_completed' })
  const html = render(state)
  assert.doesNotMatch(html, /role="progressbar"|workflow-spinner|<details[^>]*\bopen\b/)
  assert.match(html, /Analysen är färdig/)
  assert.match(html, /Översvämningar påverkar vägar/)
  assert.doesNotMatch(html, new RegExp(analysisId))
  assert.match(html, /Inga kategorier matchade/)
  assert.match(html, /Översvämningar/)
  assert.ok(html.indexOf('<summary>Räckvidd') < html.indexOf('<summary>Riskområden'))
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
})
