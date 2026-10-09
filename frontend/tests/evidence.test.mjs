import assert from 'node:assert/strict'
import { test } from 'node:test'
import { activeSelection, evidenceSegments, highlightBands, initialInteraction, interact, workflowColor } from '../src/evidence.ts'
import { parseAnalysisEvent } from '../src/analysis.ts'

const workflow = (id, evidence) => ({ id, label: id, status: 'completed', results: [{ ID: 'category', name: 'Kategori', evidence }] })

test('preserves all whitespace and Unicode and highlights repeated exact occurrences', () => {
  const text = '  Å😀\nÅ😀  '
  const segments = evidenceSegments(text, [workflow('risks', ['Å😀', 'Å😀', 'wrong', ' '])])
  assert.equal(segments.map((segment) => segment.text).join(''), text)
  assert.deepEqual(segments.filter((segment) => segment.owners.length).map((segment) => segment.text), ['Å😀', 'Å😀'])
  assert.ok(segments.every((segment) => segment.owners.length <= 1))
})

test('splits overlaps and preserves every category association', () => {
  const first = workflow('risks', ['abc'])
  first.results.push({ ID: 'other', name: 'Annan', evidence: ['bc'] })
  const segments = evidenceSegments('abcd', [first, workflow('reach', ['bcd'])])
  assert.deepEqual(segments.map((segment) => segment.text), ['a', 'bc', 'd'])
  assert.equal(segments[1].owners.length, 3)
  assert.deepEqual([...new Set(segments[1].owners.map((owner) => owner.workflowId))], ['risks', 'reach'])
  assert.match(highlightBands(['risks', 'reach']), /linear-gradient.*risks.*reach/)
  assert.equal(workflowColor('new-registry-workflow'), 'var(--evidence-fallback-color)')
})

test('finds overlapping occurrences of a repeated quote', () => {
  assert.equal(evidenceSegments('aaa', [workflow('risks', ['aa'])]).map((segment) => segment.text).join(''), 'aaa')
  assert.ok(evidenceSegments('aaa', [workflow('risks', ['aa'])]).every((segment) => segment.owners.length === 1))
})

test('pins either direction, transient selection overrides and restores, Escape clears', () => {
  const passage = { workflowIds: ['risks', 'reach'], segmentStart: 2 }
  const row = { workflowIds: ['service'] }
  let state = interact(initialInteraction, { type: 'pin', selection: passage })
  assert.equal(activeSelection(state), passage)
  state = interact(state, { type: 'focus', selection: row })
  assert.equal(activeSelection(state), row)
  state = interact(state, { type: 'focus', selection: null })
  assert.equal(activeSelection(state), passage)
  state = interact(state, { type: 'hover', selection: row })
  assert.equal(activeSelection(state), row)
  state = interact(state, { type: 'hover', selection: null })
  assert.equal(activeSelection(state), passage)
  state = interact(state, { type: 'pin', selection: passage })
  assert.equal(activeSelection(state), null)
  state = interact(state, { type: 'pin', selection: row })
  assert.deepEqual(interact(state, { type: 'clear' }), initialInteraction)
})

test('stream parser validates evidence arrays and accepts older metadata without evidence', () => {
  const parse = (evidence) => parseAnalysisEvent('workflow_completed', JSON.stringify({ id: 'risks', results: [{ ID: 'a', name: 'A', evidence }] }))
  assert.deepEqual(parse(['Å😀']).results[0].evidence, ['Å😀'])
  assert.deepEqual(parse(undefined).results[0].evidence, [])
  for (const invalid of [null, 'quote', [12], [' ']]) assert.throws(() => parse(invalid), /ogiltigt/)
})
