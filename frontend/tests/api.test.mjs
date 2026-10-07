import assert from 'node:assert/strict'
import { test } from 'node:test'
import { submitEvent } from '../src/api.ts'

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
