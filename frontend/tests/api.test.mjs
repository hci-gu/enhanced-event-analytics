import assert from 'node:assert/strict'
import { test } from 'node:test'
import { checkHealth, streamAnalysis } from '../src/api.ts'

test('checks health through the API proxy and accepts status ok with extra fields', async (t) => {
  const fetchMock = t.mock.method(globalThis, 'fetch', async () =>
    Response.json({ status: 'ok', model_loaded: true }))
  await checkHealth()
  assert.equal(fetchMock.mock.callCount(), 1)
  const [url, options] = fetchMock.mock.calls[0].arguments
  assert.equal(url, '/api/health')
  assert.equal(options.cache, 'no-store')
  assert.ok(options.signal instanceof AbortSignal)
})

test('rejects missing or unhealthy statuses', async (t) => {
  for (const body of [null, {}, { status: 'error' }, { status: 'OK' }]) {
    t.mock.method(globalThis, 'fetch', async () => Response.json(body))
    await assert.rejects(checkHealth(), /inte status "ok"/)
    t.mock.restoreAll()
  }
})

test('rejects failed HTTP health checks', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('', { status: 503 }))
  await assert.rejects(checkHealth(), /HTTP 503/)
})

test('rejects invalid JSON in health checks', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('invalid'))
  await assert.rejects(checkHealth(), /ogiltigt svar/)
})

test('rejects network failures and timeouts during health checks', async (t) => {
  for (const error of [new TypeError('Failed to fetch'), new DOMException('Timed out', 'TimeoutError')]) {
    t.mock.method(globalThis, 'fetch', async () => { throw error })
    await assert.rejects(checkHealth(), /inte att nå servern/)
    t.mock.restoreAll()
  }
})

function event(type, data) {
  return `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`
}

const analysisId = '6e2a1df4-657b-4a75-b899-d42afdc50953'
const success = event('analysis_started', { analysis_id: analysisId, workflows: [{ id: 'risks', label: 'Riskområden' }] }) +
  event('workflow_started', { id: 'risks' }) +
  event('workflow_completed', { id: 'risks', results: [{ ID: 'flood', name: 'Översvämningar' }] }) +
  event('analysis_completed', {})

function streamResponse(contents = success) {
  return new Response(contents, { headers: { 'Content-Type': 'text/event-stream' } })
}

test('posts trimmed text and streams actual results', async (t) => {
  const fetchMock = t.mock.method(globalThis, 'fetch', async () => streamResponse())
  const states = []
  await streamAnalysis('  Händelsetext\n  ', (state) => states.push(state))
  const [url, options] = fetchMock.mock.calls[0].arguments
  assert.equal(url, '/api/analyze-event/stream')
  assert.equal(options.method, 'POST')
  assert.equal(options.headers.Accept, 'text/event-stream')
  assert.deepEqual(JSON.parse(options.body), { text: 'Händelsetext' })
  assert.deepEqual(states.map((state) => state.status), ['running', 'running', 'running', 'completed'])
  assert.equal(states.at(-1).workflows[0].results[0].name, 'Översvämningar')
  assert.equal(states.at(-1).analysisId, analysisId)
})

test('does not send whitespace-only input', async (t) => {
  const fetchMock = t.mock.method(globalThis, 'fetch')
  await assert.rejects(streamAnalysis(' \n\t ', () => {}), /Skriv en händelsetext/)
  assert.equal(fetchMock.mock.callCount(), 0)
})

test('reports HTTP errors including validation and server failures', async (t) => {
  for (const status of [422, 500, 503]) {
    t.mock.method(globalThis, 'fetch', async () => new Response('', { status }))
    await assert.rejects(streamAnalysis('Test', () => {}), new RegExp(`HTTP ${status}`))
    t.mock.restoreAll()
  }
})

test('reports network failures', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('Failed to fetch') })
  await assert.rejects(streamAnalysis('Test', () => {}), /inte att nå servern/)
})

test('rejects non-stream responses', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ status: 'ok' }))
  await assert.rejects(streamAnalysis('Test', () => {}), /ogiltigt analysflöde/)
})
