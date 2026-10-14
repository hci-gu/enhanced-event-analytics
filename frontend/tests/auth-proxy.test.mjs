import assert from 'node:assert/strict'
import { createServer as createHttpServer } from 'node:http'
import { test } from 'node:test'
import { createServer, preview } from 'vite'

test('auth proxy preserves Origin, Cookie and Set-Cookie in development and preview', { timeout: 20000 }, async () => {
  const requests = []
  const backend = createHttpServer((request, response) => {
    requests.push({ path: request.url, origin: request.headers.origin, cookie: request.headers.cookie })
    response.writeHead(200, { 'Content-Type': 'application/json',
      'Set-Cookie': 'event_analytics_session=user-token; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800' })
    response.end('{"id":"testuser0000001","email":"user@example.com"}')
  })
  await new Promise((resolve) => backend.listen(0, '127.0.0.1', resolve))
  const original = process.env.VITE_API_URL
  process.env.VITE_API_URL = `http://127.0.0.1:${backend.address().port}`
  let dev
  let productionPreview
  try {
    dev = await createServer({ server: { host: '127.0.0.1', port: 0, open: false } })
    await dev.listen()
    productionPreview = await preview({ preview: { host: '127.0.0.1', port: 0, open: false } })
    for (const server of [dev.httpServer, productionPreview.httpServer]) {
      const response = await fetch(`http://127.0.0.1:${server.address().port}/api/auth/session`, {
        headers: { Origin: 'http://localhost:5173', Cookie: 'event_analytics_session=existing-token' },
      })
      assert.equal(response.status, 200)
      assert.match(response.headers.get('set-cookie'), /event_analytics_session=user-token; Path=\/; HttpOnly/)
      await response.json()
    }
    assert.deepEqual(requests, Array.from({ length: 2 }, () => ({
      path: '/auth/session', origin: 'http://localhost:5173', cookie: 'event_analytics_session=existing-token',
    })))
  } finally {
    await dev?.close()
    if (productionPreview) await new Promise((resolve) => productionPreview.httpServer.close(resolve))
    backend.closeAllConnections()
    await new Promise((resolve) => backend.close(resolve))
    if (original === undefined) delete process.env.VITE_API_URL
    else process.env.VITE_API_URL = original
  }
})
