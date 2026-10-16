// Production UI against mocked history, authentication and streaming APIs; no models.
// Usage: node tests/history-browser-smoke.mjs <path-to-playwright-package>
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFile, mkdtemp } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { join, resolve, sep } from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require(process.argv[2] || 'playwright')
const directory = resolve('dist')
const screenshots = await mkdtemp(join(tmpdir(), 'event-history-ui-'))
const analysisId = (index) => `${String(index).padStart(8, '0')}-1234-4234-8234-123456789abc`
const source = 'Vatten stiger. Publicerad 15 oktober.'
const records = Array.from({ length: 30 }, (_, index) => ({
  id: `record${String(index).padStart(9, '0')}`, analysis_id: analysisId(index), title: `Sparad händelse ${index + 1}`,
  created: new Date(Date.UTC(2026, 9, 16, 10 - index)).toISOString().replace('T', ' '),
  finished_at: new Date(Date.UTC(2026, 9, 16, 10 - index, 1)).toISOString().replace('T', ' '),
  status: 'Complete', original_text: source,
  predictions: { risks: [{ ID: 'flood', name: 'Översvämningar', evidence: ['Vatten stiger'] }] },
  workflows: [{ id: 'risks', label: 'Riskområden' }, { id: 'dates', label: 'Datum' }],
  dates: { published_at: '2026-10-15', event_start: null, event_end: null, end_status: 'unknown', duration_hint: null,
    evidence: { published_at: ['15 oktober'], event_start: [], event_end: [] } }, dates_error: null,
}))
let listStatus = 200
let detailStatus = 200
let stream
let analysisRequests = 0
let listRequests = []
const server = createServer(async (request, response) => {
  const url = new URL(request.url, 'http://localhost')
  const json = (body, status = 200) => {
    response.writeHead(status, { 'Content-Type': 'application/json' })
    response.end(JSON.stringify(body))
  }
  if (url.pathname === '/api/auth/session') return json({ id: 'testuser0000001', email: 'user@example.com' })
  if (url.pathname === '/api/health') return json({ status: 'ok' })
  if (url.pathname === '/api/analyses') {
    listRequests.push(Object.fromEntries(url.searchParams))
    const start = Number(url.searchParams.get('cursor') || 0)
    const limit = Number(url.searchParams.get('limit'))
    // Match the real metadata-only list response.
    return json({ items: records.slice(start, start + limit).map(({ id, analysis_id, title, created, finished_at, status }) =>
      ({ id, analysis_id, title, created, finished_at, status })),
    next_cursor: start + limit < records.length ? String(start + limit) : null }, listStatus)
  }
  if (url.pathname.startsWith('/api/analyses/')) {
    const item = records.find((item) => item.analysis_id === url.pathname.split('/').at(-1))
    return json(item || {}, item ? detailStatus : 404)
  }
  if (url.pathname === '/api/analyze-event/stream') {
    analysisRequests++
    stream = response
    response.writeHead(200, { 'Content-Type': 'text/event-stream' })
    response.write(`event: analysis_started\ndata: ${JSON.stringify({ analysis_id: analysisId(999), workflows: [{ id: 'risks', label: 'Riskområden' }] })}\n\n`)
    return
  }
  try {
    const path = resolve(directory, url.pathname === '/' ? 'index.html' : `.${url.pathname}`)
    if (!path.startsWith(directory + sep)) throw new Error('Invalid path')
    response.setHeader('Content-Type', path.endsWith('.js') ? 'text/javascript' : path.endsWith('.css') ? 'text/css' : 'text/html')
    response.end(await readFile(path))
  } catch {
    response.writeHead(404)
    response.end()
  }
})
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
let browser
try {
  try { browser = await chromium.launch({ headless: true }) }
  catch { browser = await chromium.launch({ channel: 'msedge', headless: true }) }
  for (const width of [1440, 860, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    listRequests = []
    await page.goto(`http://127.0.0.1:${server.address().port}`)
    await page.locator('#homepage-title').waitFor()
    await page.waitForFunction(() => document.querySelectorAll('.history-event').length === 5)
    assert.equal(listRequests.at(-1).limit, '5')
    await page.getByLabel('Händelsetext', { exact: true }).fill('Mitt textutkast')
    if (width <= 800) await page.getByRole('button', { name: 'Visa historik', exact: true }).click()
    assert.equal(await page.getByRole('button', { name: 'Ny analys', exact: true }).count(), 0)
    await page.getByRole('button', { name: 'Visa fler', exact: true }).click()
    await page.waitForFunction(() => document.querySelectorAll('.history-event').length === 25)
    assert.deepEqual(listRequests.at(-1), { limit: '20', cursor: '5' })
    assert.equal(await page.locator('.history-scroll').evaluate((element) => element.scrollHeight > element.clientHeight), true)
    await page.locator('.history-event').last().click()
    await page.locator('.summary-screen').waitFor()
    assert.equal(await page.locator('#summary-title').textContent(), 'Sparad händelse 25')
    assert.equal(await page.locator('.summary-text').textContent(), source)
    assert.equal(await page.locator('.evidence-highlight').count() > 0, true)
    assert.equal(await page.locator('.date-timeline').count(), 1)
    assert.equal(await page.locator('.history-event[aria-current]').count(), 1)
    if (width <= 800) await page.getByRole('button', { name: 'Visa historik', exact: true }).click()
    const scrollTop = await page.locator('.history-scroll').evaluate((element) => element.scrollTop)
    await page.getByRole('button', { name: 'Dölj historik', exact: true }).click()
    assert.equal(await page.locator('.history-sidebar').getAttribute('inert'), '')
    assert.equal(await page.locator('.history-slot').isVisible(), false)
    assert.equal(await page.locator('.workspace-tools .history-toggle').count(), 1)
    assert.equal(await page.locator('.history-toggle').evaluate((element) => element === document.activeElement), true)
    await page.keyboard.press('Enter')
    assert.equal(await page.locator('.history-scroll').evaluate((element) => element.scrollTop), scrollTop)
    await page.getByRole('button', { name: 'Visa fler', exact: true }).click()
    await page.waitForFunction(() => document.querySelectorAll('.history-event').length === 30)
    assert.equal(await page.getByRole('button', { name: 'Visa fler', exact: true }).count(), 0)
    // Failed detail requests leave the currently displayed result intact.
    detailStatus = 503
    await page.locator('.history-event').first().click()
    await page.locator('.history-open-error').waitFor()
    assert.equal(await page.locator('#summary-title').textContent(), 'Sparad händelse 25')
    detailStatus = 200
    await page.getByRole('button', { name: 'Förstärkt analysförmåga – Hem', exact: true }).click()
    if (width <= 800) await page.getByRole('button', { name: 'Dölj historik', exact: true }).click()
    assert.equal(await page.getByLabel('Händelsetext', { exact: true }).inputValue(), 'Mitt textutkast')
    const previousRequests = analysisRequests
    await page.getByRole('button', { name: 'Analysera', exact: true }).click()
    await page.locator('.workflow-queued').waitFor()
    if (width <= 800) await page.getByRole('button', { name: 'Visa historik', exact: true }).click()
    await page.locator('.history-event').first().click()
    await page.locator('.summary-screen').waitFor()
    for (const [type, data] of [
      ['title_completed', { title: 'Ny händelse' }], ['workflow_started', { id: 'risks' }],
      ['workflow_completed', { id: 'risks', results: [] }], ['analysis_completed', {}],
    ]) stream.write(`event: ${type}\ndata: ${JSON.stringify(data)}\n\n`)
    stream.end()
    await page.waitForFunction(() => document.querySelectorAll('.history-event').length === 5)
    assert.equal(analysisRequests, previousRequests + 1)
    assert.equal(await page.locator('#summary-title').textContent(), 'Sparad händelse 1')
    // Active results remain accessible after leaving history.
    await page.getByRole('button', { name: 'Förstärkt analysförmåga – Hem', exact: true }).click()
    if (width <= 800 && await page.getByRole('button', { name: 'Dölj historik', exact: true }).count()) {
      await page.getByRole('button', { name: 'Dölj historik', exact: true }).click()
    }
    await page.getByRole('button', { name: 'Sidmeny' }).click()
    await page.getByRole('button', { name: 'Sammanfattning', exact: true }).click()
    assert.equal(await page.locator('#summary-title').textContent(), 'Ny händelse')
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
    if (width === 1440) {
      await page.emulateMedia({ reducedMotion: 'no-preference' })
      await page.getByRole('button', { name: 'Dölj historik', exact: true }).click()
      await page.waitForFunction(() => document.querySelector('.app-workspace').getAnimations().length > 0)
      await page.locator('.history-slot').waitFor({ state: 'hidden' })
      await page.getByRole('button', { name: 'Visa historik', exact: true }).click()
      await page.waitForFunction(() => document.querySelector('.app-workspace').getAnimations().length === 0)
    }
    await page.screenshot({ path: join(screenshots, `history-${width}.png`) })
    // Database outages can be retried; a 401 clears all history and source state.
    listStatus = 503
    await page.reload()
    await page.locator('.history-message[role="alert"]').waitFor({ state: 'attached' })
    if (width <= 800) await page.getByRole('button', { name: 'Visa historik', exact: true }).click()
    listStatus = 200
    await page.getByRole('button', { name: 'Försök igen', exact: true }).click()
    await page.waitForFunction(() => document.querySelectorAll('.history-event').length === 5)
    listStatus = 401
    await page.reload()
    await page.getByRole('heading', { name: 'Logga in', exact: true }).waitFor()
    assert.equal(await page.locator('.history-event').count(), 0)
    listStatus = 200
    assert.deepEqual(errors, [])
    await page.close()
  }
  console.log(`History UI checks passed. Screenshots: ${screenshots}`)
} finally {
  await browser?.close()
  server.closeAllConnections()
  await new Promise((resolve) => server.close(resolve))
}
