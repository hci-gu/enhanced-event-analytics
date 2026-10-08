import assert from 'node:assert/strict'
import { test } from 'node:test'
import { checkHealth, submitEvent } from '../src/api.ts'

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

test('sends trimmed Swedish event text and reports the backend placeholder', async (t) => {
  const fetchMock = t.mock.method(globalThis, 'fetch', async () =>
    Response.json({ status: 'not_implemented', results: {} }))
  const message = await submitEvent('  Händelsetext\n  ')
  assert.match(message, /inte tillgänglig ännu/)
  assert.equal(fetchMock.mock.callCount(), 1)
  assert.deepEqual(fetchMock.mock.calls[0].arguments, [
    '/api/analyze-event',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: 'Händelsetext' }),
    },
  ])
})

test('does not send whitespace-only input', async (t) => {
  const fetchMock = t.mock.method(globalThis, 'fetch')
  await assert.rejects(submitEvent(' \n\t '), /Skriv en händelsetext/)
  assert.equal(fetchMock.mock.callCount(), 0)
})

test('reports HTTP errors including validation and server failures', async (t) => {
  for (const status of [422, 500, 503]) {
    t.mock.method(globalThis, 'fetch', async () => new Response('', { status }))
    await assert.rejects(submitEvent('Test'), new RegExp(`HTTP ${status}`))
    t.mock.restoreAll()
  }
})

test('reports network failures', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('Failed to fetch') })
  await assert.rejects(submitEvent('Test'), /inte att nå servern/)
})

test('reports non-JSON responses', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('<html>Proxy error</html>'))
  await assert.rejects(submitEvent('Test'), /ogiltigt svar/)
})

test('reports unexpected JSON response shapes', async (t) => {
  for (const body of [null, [], {}, { status: 'done', results: {} },
    { status: 'not_implemented', results: null }, { status: 'not_implemented', results: [] }]) {
    t.mock.method(globalThis, 'fetch', async () => Response.json(body))
    await assert.rejects(submitEvent('Test'), /oväntat svar/)
    t.mock.restoreAll()
  }
})
