import assert from 'node:assert/strict'
import { test } from 'node:test'
import { advanceAnalysis, analysisProgress, failAnalysis, initialAnalysis, parseAnalysisEvent, readAnalysisStream } from '../src/analysis.ts'

const workflows = [{ id: 'a', label: 'Första' }, { id: 'b', label: 'Andra' }, { id: 'c', label: 'Tredje' }]
const started = { type: 'analysis_started', workflows }
const start = (id) => ({ type: 'workflow_started', id })
const complete = (id) => ({ type: 'workflow_completed', id, results: [] })
const encode = (event) => {
  const { type, ...data } = event
  return `event: ${type}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`
}

test('tracks states, completion order, duplicate completion, and terminal progress', () => {
  let state = advanceAnalysis(initialAnalysis, started)
  assert.deepEqual(state.workflows.map((item) => item.status), ['queued', 'queued', 'queued'])
  for (const id of ['b', 'a', 'c']) {
    state = advanceAnalysis(state, start(id))
    assert.equal(state.workflows.find((item) => item.id === id).status, 'running')
    state = advanceAnalysis(state, complete(id))
    assert.equal(advanceAnalysis(state, complete(id)), state)
  }
  assert.deepEqual(state.completedIds, ['b', 'a', 'c'])
  assert.equal(analysisProgress(state), 100)
  state = advanceAnalysis(state, { type: 'analysis_completed' })
  assert.equal(analysisProgress(state), null)
})

test('preserves completed results and stops queued workflows after failure', () => {
  let state = advanceAnalysis(initialAnalysis, started)
  state = advanceAnalysis(state, start('a'))
  state = advanceAnalysis(state, complete('a'))
  state = advanceAnalysis(state, start('b'))
  state = advanceAnalysis(state, { type: 'workflow_failed', id: 'b', code: 502, message: 'Analysen misslyckades' })
  assert.equal(state.status, 'failed')
  assert.deepEqual(state.workflows.map((item) => item.status), ['completed', 'failed', 'skipped'])
  assert.deepEqual(state.completedIds, ['a'])
  assert.equal(analysisProgress(state), 33)
})

test('parses one-byte chunks, split UTF-8, CRLF and comments', async () => {
  const text = ': heartbeat\r\n\r\n' + [started, start('a'), complete('a'), start('b'), complete('b'),
    start('c'), complete('c'), { type: 'analysis_completed' }].map(encode).join('')
  const bytes = new TextEncoder().encode(text)
  let index = 0
  const stream = new ReadableStream({
    pull(controller) {
      if (index === bytes.length) controller.close()
      else controller.enqueue(bytes.slice(index, ++index))
    },
  })
  const states = []
  await readAnalysisStream(stream, (state) => states.push(state))
  assert.equal(states[0].workflows[0].label, 'Första')
  assert.equal(states.at(-1).status, 'completed')
})

test('delivers an event without waiting for stream completion', async () => {
  let controller
  const stream = new ReadableStream({ start(value) { controller = value } })
  let received
  const delivery = new Promise((resolve) => { received = resolve })
  const reading = readAnalysisStream(stream, received)
  controller.enqueue(new TextEncoder().encode(encode(started)))
  const state = await delivery
  assert.equal(state.status, 'running')
  controller.enqueue(new TextEncoder().encode(encode({ type: 'workflow_failed', id: null, message: 'Fel', code: 500 })))
  await reading
})

test('detects early EOF and retains partial results for failure rendering', async () => {
  const text = [started, start('a'), complete('a'), start('b')].map(encode).join('')
  let state = initialAnalysis
  await assert.rejects(readAnalysisStream(new Response(text).body, (value) => { state = value }), /innan analysen var färdig/)
  state = failAnalysis(state, 'Anslutningen avbröts')
  assert.deepEqual(state.completedIds, ['a'])
  assert.deepEqual(state.workflows.map((item) => item.status), ['completed', 'failed', 'skipped'])
})

test('rejects malformed events, unknown IDs and premature success', () => {
  for (const json of ['null', '{}', '{"workflows":[{"id":"a"}]}', JSON.stringify({ workflows: [workflows[0], workflows[0]] })]) {
    assert.throws(() => parseAnalysisEvent('analysis_started', json), /ogiltigt/)
  }
  const state = advanceAnalysis(initialAnalysis, started)
  assert.throws(() => advanceAnalysis(state, start('unknown')), /oväntad ordning/)
  assert.throws(() => advanceAnalysis(state, { type: 'analysis_completed' }), /oväntad ordning/)
})

test('invalid JSON and reader failures reject instead of reporting success', async () => {
  await assert.rejects(readAnalysisStream(new Response('event: analysis_started\ndata: {\n\n').body, () => {}), /ogiltigt/)
  const stream = new ReadableStream({ start(controller) { controller.error(new Error('Network lost')) } })
  await assert.rejects(readAnalysisStream(stream, () => {}), /Anslutningen till servern avbröts/)
})
