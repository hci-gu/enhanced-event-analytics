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
const sourceText = `${'Bakgrund till händelsen.\n'.repeat(70)}Vatten stiger och påverkar vägarna.\n${'Fortsatt rapportering.\n'.repeat(70)}`.trim()
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
  if (pathname === '/api/auth/session') {
    res.setHeader('Content-Type', 'application/json')
    res.end('{"id":"testuser0000001","email":"user@example.com"}')
    return
  }
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
    const page = await browser.newPage({ viewport, reducedMotion: 'reduce' })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto(`http://127.0.0.1:${server.address().port}`)
    await page.locator('#homepage-title').waitFor()
    await page.screenshot({ path: join(screenshots, `home-${viewport.width}.png`) })
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
    await page.getByLabel('Händelsetext', { exact: true }).fill(sourceText)
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
    assert.equal(await page.getByLabel('Sök händelser', { exact: true }).count(), 1)
    assert.equal(await page.getByRole('progressbar').getAttribute('aria-valuenow'), '11')
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
    assert.equal(await page.getByLabel('Händelsetext', { exact: true }).inputValue(), sourceText)
    for (const item of workflows.slice(1)) {
      if (item.id !== 'reach') send('workflow_started', { id: item.id })
      send('workflow_completed', { id: item.id, results: item.id === 'reach'
        ? [{ ID: 'local', name: 'Lokalt', evidence: ['stiger'] }] : [] })
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
    assert.equal(await page.getByLabel('Sök händelser', { exact: true }).count(), 1)
    const mark = page.locator('mark').first()
    const result = page.locator('.summary-results .workflow-result').first()
    const dotColor = await result.locator('.workflow-color-dot').evaluate((element) => getComputedStyle(element).backgroundColor)
    assert.equal(dotColor, await mark.evaluate((element) => getComputedStyle(element).backgroundColor))
    await mark.evaluate((element) => element.click())
    assert.equal(await mark.getAttribute('aria-pressed'), 'true')
    assert.equal(await page.locator('.workflow-result[data-active]').count(), 1)
    await page.keyboard.press('Escape')
    const highlightToggle = result.getByRole('switch', { name: 'Textmarkeringar för Riskområden' })
    assert.equal(await highlightToggle.getAttribute('aria-checked'), 'true')
    await highlightToggle.click()
    assert.equal(await result.getAttribute('open'), null)
    assert.equal(await highlightToggle.getAttribute('aria-checked'), 'false')
    assert.equal(await page.locator('mark').count(), 1)
    assert.equal(await page.locator('mark').textContent(), 'stiger')
    // Keyboard activation restores highlights without expanding the disclosure.
    await highlightToggle.focus()
    await page.keyboard.press('Space')
    assert.equal(await highlightToggle.getAttribute('aria-checked'), 'true')
    assert.equal(await result.getAttribute('open'), null)
    await page.locator('.summary-results summary').first().click()
    const quoteButton = result.getByRole('button', { name: 'Visa textstöd i händelsetexten: Vatten stiger', exact: true })
    const assertQuotePosition = async () => {
      const fraction = await page.locator('.summary-text').evaluate((element) => {
        const passage = [...element.querySelectorAll('[data-segment-start]')].find((segment) => segment.textContent === 'Vatten ')
        return (passage.getClientRects()[0].top - element.getBoundingClientRect().top - element.clientTop) / element.clientHeight
      })
      assert.ok(Math.abs(fraction - 0.25) < 0.03, `Quote position: ${fraction}`)
    }
    await quoteButton.click()
    await assertQuotePosition()
    await highlightToggle.click()
    assert.equal(await result.getAttribute('open'), '')
    await page.locator('.summary-text').evaluate((element) => { element.scrollTop = 0 })
    await quoteButton.focus()
    await page.keyboard.press('Enter')
    await assertQuotePosition()
    await highlightToggle.click()
    assert.notEqual(await result.evaluate((element) => getComputedStyle(element).backgroundColor), dotColor)
    assert.ok((await menu.boundingBox()).y >= 0)
    assert.ok((await page.locator('#summary-title').boundingBox()).y >= 0)
    await page.screenshot({ path: join(screenshots, `summary-${viewport.width}.png`) })
    if (viewport.width === 1280) {
      await page.emulateMedia({ reducedMotion: 'no-preference' })
      // Closing keeps native details open while the body contracts, then hides it.
      await result.locator('summary').click()
      assert.equal(await result.getAttribute('open'), '')
      await page.waitForFunction(() => !document.querySelector('.summary-results details').open)
      await result.locator('summary').click()
      assert.equal(await result.locator('.workflow-disclosure-body').evaluate((element) => element.getAnimations().length > 0), true)
      await page.waitForFunction(() => document.querySelector('.summary-results .workflow-disclosure-body').getAnimations().length === 0)
      // Closed menus remain inert while their visible exit transition finishes.
      await menu.click()
      await page.keyboard.press('Escape')
      assert.equal(await page.locator('.page-navigation').getAttribute('inert'), '')
      await page.waitForFunction(() => getComputedStyle(document.querySelector('.page-navigation')).visibility === 'hidden')
      await page.emulateMedia({ reducedMotion: 'reduce' })
    }
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
    await page.getByRole('button', { name: 'Ny analys', exact: true }).click()
    assert.equal(await page.getByLabel('Händelsetext', { exact: true }).inputValue(), '')
    assert.equal(await page.getByLabel('Händelsetext', { exact: true }).evaluate((element) => element === document.activeElement), true)
    assert.equal(await page.getByRole('button', { name: 'Analysera', exact: true }).isDisabled(), true)
    await menu.click()
    assert.equal(await page.getByRole('button', { name: 'Sammanfattning', exact: true }).isDisabled(), false)
    await page.keyboard.press('Escape')
    await page.emulateMedia({ reducedMotion: 'reduce' })
    assert.equal(await page.locator('.event-section').evaluate((element) => getComputedStyle(element).animationName), 'none')
    assert.deepEqual(errors, [])
    await page.close()
  }
  console.log(`Desktop/mobile UI checks passed. Screenshots: ${screenshots}`)
} finally {
  await browser?.close()
  server.closeAllConnections()
  await new Promise((resolve) => server.close(resolve))
}
