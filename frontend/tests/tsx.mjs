import { readFile } from 'node:fs/promises'
import ts from 'typescript'

// Compile JSX only in memory; production uses Vite.
export async function componentUrl(name, dependencies = {}) {
  const source = await readFile(new URL(`../src/${name}.tsx`, import.meta.url), 'utf8')
  let { outputText } = ts.transpileModule(source.replace(/import '\.\/.*\.css'/g, ''), {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 },
  })
  const imports = {
    react: import.meta.resolve('react'), 'react/jsx-runtime': import.meta.resolve('react/jsx-runtime'),
    './analysis': new URL('../src/analysis.ts', import.meta.url).href,
    './navigation': new URL('../src/navigation.ts', import.meta.url).href,
    './evidence': new URL('../src/evidence.ts', import.meta.url).href,
    './dates': new URL('../src/dates.ts', import.meta.url).href,
    ...dependencies,
  }
  if (source.includes("from './WorkflowRow'")) imports['./WorkflowRow'] = await componentUrl('WorkflowRow')
  if (source.includes("from './DateTimeline'")) imports['./DateTimeline'] = await componentUrl('DateTimeline')
  for (const [specifier, resolved] of Object.entries(imports)) {
    outputText = outputText.replaceAll(`'${specifier}'`, `'${resolved}'`).replaceAll(`"${specifier}"`, `"${resolved}"`)
  }
  return `data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`
}
