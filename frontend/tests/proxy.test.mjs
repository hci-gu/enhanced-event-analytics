import assert from 'node:assert/strict'
import { createServer as createHttpServer } from 'node:http'
import { test } from 'node:test'
import { createServer, preview } from 'vite'

test('development and preview proxy VITE_API_URL and stream progress without buffering', { timeout: 20000 }, async () => {
  const requests = []
  let finishResponse
  const backend = createHttpServer(async (request, response) => {
    let body = ''
    for await (const chunk of request) body += chunk
    requests.push({ path: request.url, method: request.method, body })
    response.writeHead(200, { 'Content-Type': 'text/event-stream' })
    response.write('event: analysis_started\ndata: {"workflows":[]}\n\n')
    finishResponse = () => response.end('event: analysis_completed\ndata: {}\n\n')
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
      const response = await fetch(`http://127.0.0.1:${server.address().port}/api/analyze-event/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'Testhändelse' }),
      })
      assert.equal(response.status, 200)
      const reader = response.body.getReader()
      const first = await reader.read()
      assert.match(new TextDecoder().decode(first.value), /analysis_started/)
      finishResponse()
      let remaining = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        remaining += new TextDecoder().decode(value)
      }
      assert.match(remaining, /analysis_completed/)
      reader.releaseLock()
    }

    assert.deepEqual(requests, Array.from({ length: 2 }, () => ({
      path: '/analyze-event/stream',
      method: 'POST',
      body: JSON.stringify({ text: 'Testhändelse' }),
    })))
  } finally {
    finishResponse?.()
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
