import assert from 'node:assert/strict'
import { createServer as createHttpServer } from 'node:http'
import { test } from 'node:test'
import { createServer, preview } from 'vite'

test('development and preview proxy VITE_API_URL and strip /api', { timeout: 20000 }, async () => {
  const requests = []
  const backend = createHttpServer(async (request, response) => {
    let body = ''
    for await (const chunk of request) body += chunk
    requests.push({ path: request.url, method: request.method, body })
    response.writeHead(200, { 'Content-Type': 'application/json' })
    response.end(JSON.stringify({ status: 'not_implemented', results: {} }))
  })
  await new Promise((resolve) => backend.listen(0, '127.0.0.1', resolve))
  const originalApiUrl = process.env.VITE_API_URL
  process.env.VITE_API_URL = `http://127.0.0.1:${backend.address().port}/`
  let dev
  let productionPreview

  try {
    dev = await createServer({ server: { host: '127.0.0.1', port: 0, open: false } })
    await dev.listen()
    productionPreview = await preview({ preview: { host: '127.0.0.1', port: 0, open: false } })

    for (const server of [dev.httpServer, productionPreview.httpServer]) {
      const response = await fetch(`http://127.0.0.1:${server.address().port}/api/analyze-event`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'Testhändelse' }),
      })
      assert.equal(response.status, 200)
      assert.deepEqual(await response.json(), { status: 'not_implemented', results: {} })
    }

    assert.deepEqual(requests, Array.from({ length: 2 }, () => ({
      path: '/analyze-event',
      method: 'POST',
      body: JSON.stringify({ text: 'Testhändelse' }),
    })))
  } finally {
    await dev?.close()
    if (productionPreview) {
      await new Promise((resolve, reject) => productionPreview.httpServer.close((error) =>
        error ? reject(error) : resolve()))
    }
    await new Promise((resolve) => backend.close(resolve))
    if (originalApiUrl === undefined) delete process.env.VITE_API_URL
    else process.env.VITE_API_URL = originalApiUrl
  }
})
