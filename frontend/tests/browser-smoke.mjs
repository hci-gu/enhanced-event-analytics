// Local UI smoke check against a production build and a mocked SSE API.
// Usage: node tests/browser-smoke.mjs <path-to-playwright-package>
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFile, mkdtemp } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { join, resolve, sep } from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require(process.argv[2] || 'playwright')
const directory = resolve('dist')
const screenshots = await mkdtemp(join(tmpdir(), 'event-analytics-ui-'))
const workflows = [
  { id: 'risks', label: 'Riskområden' }, { id: 'reach', label: 'Räckvidd' },
  { id: 'service', label: 'Verksamheter' },
  ...Array.from({ length: 6 }, (_, index) => ({ id: `extra${index}`, label: `Arbetsflöde ${index + 4}` })),
]
let response
let requests = 0
const send = (type, data) => response.write(`event: ${type}\ndata: ${JSON.stringify(data)}\n\n`)
const server = createServer(async (request, res) => {
  const pathname = new URL(request.url, 'http://localhost').pathname
  if (pathname === '/api/health') {
    res.setHeader('Content-Type', 'application/json')
    res.end('{"status":"ok"}')
    return
  }
  if (pathname === '/api/analyze-event/stream') {
    requests++
    response = res
    res.writeHead(200, { 'Content-Type': 'text/event-stream' })
    send('analysis_started', { analysis_id: `mock-${requests}`, workflows })
    return
  }
  try {
    const path = resolve(directory, pathname === '/' ? 'index.html' : `.${pathname}`)
    if (!path.startsWith(directory + sep)) throw new Error('Invalid path')
    res.setHeader('Content-Type', path.endsWith('.js') ? 'text/javascript' : path.endsWith('.css') ? 'text/css' : 'text/html')
    res.end(await readFile(path))
  } catch {
    res.writeHead(404)
    res.end()
  }
})
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
let browser
try {
  try { browser = await chromium.launch({ headless: true }) }
  catch { browser = await chromium.launch({ channel: 'msedge', headless: true }) }
  for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto(`http://127.0.0.1:${server.address().port}`)
    const menu = page.getByRole('button', { name: 'Sidmeny' })
    await menu.click()
    assert.equal(await page.getByRole('button', { name: 'Status', exact: true }).isDisabled(), true)
    assert.equal(await page.getByRole('button', { name: 'Sammanfattning', exact: true }).isDisabled(), true)
    await page.keyboard.press('Escape')
    assert.equal(await menu.getAttribute('aria-expanded'), 'false')
    assert.equal(await menu.evaluate((element) => element === document.activeElement), true)
    await menu.click()
    await page.mouse.click(4, 4)
    assert.equal(await menu.getAttribute('aria-expanded'), 'false')
    await page.getByLabel('Händelsetext', { exact: true }).fill('Vatten stiger och påverkar vägarna.')
    await page.getByRole('button', { name: 'Analysera', exact: true }).click()
    await page.locator('.workflow-queued').first().waitFor()
    assert.equal(await page.locator('#analysis-title').textContent(), '')
    const before = await page.locator('.workflow-status-panel').boundingBox()
    send('title_completed', { title: 'Vatten stiger och påverkar vägarna' })
    send('workflow_started', { id: 'risks' })
    send('workflow_completed', { id: 'risks', results: [
      { ID: 'flood', name: 'Översvämningar', evidence: ['Vatten stiger'] },
      { ID: 'rain', name: 'Stora regnmängder påverkar samhällsviktig infrastruktur', evidence: [] },
    ] })
    send('workflow_started', { id: 'reach' })
    await page.locator('.workflow-spinner').waitFor()
    assert.equal(await page.locator('.workflow-tag').count(), 2)
    const after = await page.locator('.workflow-status-panel').boundingBox()
    assert.equal(before.y, after.y)
    const row = page.locator('details').first()
    await row.locator('summary').click()
    await page.getByText('Vatten stiger', { exact: true }).waitFor()
    assert.equal(await page.locator('.workflow-status-list').evaluate((element) => element.scrollHeight > element.clientHeight), true)
    await page.screenshot({ path: join(screenshots, `status-${viewport.width}.png`) })
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
    await menu.click()
    await page.getByRole('button', { name: 'Hem', exact: true }).click()
    assert.equal(await page.getByRole('button', { name: 'Analyserar…' }).isDisabled(), true)
    assert.equal(await page.getByLabel('Händelsetext', { exact: true }).inputValue(), 'Vatten stiger och påverkar vägarna.')
    for (const item of workflows.slice(1)) {
      if (item.id !== 'reach') send('workflow_started', { id: item.id })
      send('workflow_completed', { id: item.id, results: [] })
    }
    send('analysis_completed', {})
    response.end()
    await page.getByRole('button', { name: 'Analysera', exact: true }).waitFor()
    await menu.click()
    await page.keyboard.press('ArrowDown')
    assert.equal(await page.getByRole('button', { name: 'Status', exact: true }).evaluate((element) => element === document.activeElement), true)
    await page.keyboard.press('Enter')
    await page.locator('.analysis-screen').waitFor()
    assert.equal(await page.getByRole('progressbar').count(), 0)
    await menu.click()
    await page.getByRole('button', { name: 'Sammanfattning', exact: true }).click()
    await page.locator('.summary-screen').waitFor()
    const mark = page.locator('mark').first()
    await mark.click()
    assert.equal(await mark.getAttribute('aria-pressed'), 'true')
    assert.equal(await page.locator('.workflow-result[data-active]').count(), 1)
    await page.keyboard.press('Escape')
    await page.locator('.summary-results summary').first().click()
    assert.ok((await menu.boundingBox()).y >= 0)
    assert.ok((await page.locator('#summary-title').boundingBox()).y >= 0)
    await page.screenshot({ path: join(screenshots, `summary-${viewport.width}.png`) })
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
    await menu.click()
    await page.getByRole('button', { name: 'Hem', exact: true }).click()
    await page.getByLabel('Händelsetext', { exact: true }).fill('En ny händelse.')
    const previousRequests = requests
    await page.getByRole('button', { name: 'Analysera', exact: true }).click()
    await page.locator('.workflow-queued').first().waitFor()
    assert.equal(requests, previousRequests + 1)
    assert.equal(await page.locator('#analysis-title').textContent(), '')
    send('title_completed', { title: 'En ny händelse' })
    for (const item of workflows) {
      send('workflow_started', { id: item.id })
      send('workflow_completed', { id: item.id, results: [] })
    }
    send('analysis_completed', {})
    response.end()
    await page.locator('.summary-screen').waitFor()
    assert.equal(await page.getByRole('heading', { name: 'En ny händelse', exact: true }).count(), 1)
    assert.deepEqual(errors, [])
    await page.close()
  }
  console.log(`Desktop/mobile UI checks passed. Screenshots: ${screenshots}`)
} finally {
  await browser?.close()
  server.closeAllConnections()
  await new Promise((resolve) => server.close(resolve))
}
