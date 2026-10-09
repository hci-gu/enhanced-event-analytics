import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ts from 'typescript'
import { advanceAnalysis, failAnalysis, initialAnalysis } from '../src/analysis.ts'

async function compile(name, dependencies) {
  const source = await readFile(new URL(`../src/${name}.tsx`, import.meta.url), 'utf8')
  let { outputText } = ts.transpileModule(source.replace(/import '\.\/.*\.css'/g, ''), {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 },
  })
  for (const [specifier, resolved] of Object.entries({
    react: import.meta.resolve('react'), 'react/jsx-runtime': import.meta.resolve('react/jsx-runtime'),
    './analysis': new URL('../src/analysis.ts', import.meta.url).href,
    './evidence': new URL('../src/evidence.ts', import.meta.url).href, ...dependencies,
  })) outputText = outputText.replaceAll(`'${specifier}'`, `'${resolved}'`).replaceAll(`"${specifier}"`, `"${resolved}"`)
  return `data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`
}
const url = await compile('AnalysisView', {
  './AnalysisScreen': await compile('AnalysisScreen'), './SummaryScreen': await compile('SummaryScreen'),
})
const { default: AnalysisView } = await import(url)
const render = (analysis) => renderToStaticMarkup(createElement(AnalysisView, { analysis, text: ' original\ntext ' }))

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
})
