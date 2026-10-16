// Usage: node tests/auth-browser-smoke.mjs <path-to-playwright-package>
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFile, mkdtemp } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { join, resolve, sep } from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require(process.argv[2] || 'playwright')
const directory = resolve('dist')
const screenshots = await mkdtemp(join(tmpdir(), 'event-analytics-auth-'))
let sessionUnavailable = false
let loginFailure = false
let accountCreated = false
let expireAnalysis = false
let analysisResponse
let aborted = false
let healthRequests = 0
const user = { id: 'testuser0000001', email: 'user@example.com' }
const server = createServer(async (request, res) => {
  const pathname = new URL(request.url, 'http://localhost').pathname
  if (pathname.startsWith('/api/')) {
    res.setHeader('Content-Type', 'application/json')
    const json = (status, data) => { res.writeHead(status); res.end(JSON.stringify(data)) }
    if (pathname === '/api/auth/session') {
      if (sessionUnavailable) return json(503, { detail: 'Inloggningstjänsten är inte tillgänglig.' })
      return request.headers.cookie?.includes('test_session=active') ? json(200, user) : json(401, {})
    }
    if (pathname === '/api/auth/login' || pathname === '/api/auth/register') {
      if (pathname.endsWith('/register') && accountCreated) return json(503, { detail: { message: 'Kontot har skapats. Logga in för att fortsätta.', account_created: true } })
      if (loginFailure) return json(401, { detail: 'E-postadressen eller lösenordet är felaktigt.' })
      res.setHeader('Set-Cookie', 'test_session=active; Path=/; HttpOnly; SameSite=Lax')
      return json(200, user)
    }
    if (pathname === '/api/auth/logout') {
      res.setHeader('Set-Cookie', 'test_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax')
      res.writeHead(204); res.end(); return
    }
    if (pathname === '/api/health') { healthRequests++; return json(200, { status: 'ok' }) }
    if (pathname === '/api/analyze-event/stream') {
      if (expireAnalysis) return json(401, {})
      analysisResponse = res
      aborted = false
      res.on('close', () => { aborted = true })
      res.writeHead(200, { 'Content-Type': 'text/event-stream' })
      res.write('event: analysis_started\ndata: {"analysis_id":"mock","workflows":[{"id":"risks","label":"Riskområden"}]}\n\n')
      return
    }
    return json(404, {})
  }
  try {
    const path = resolve(directory, pathname === '/' ? 'index.html' : `.${pathname}`)
    if (!path.startsWith(directory + sep)) throw new Error('Invalid path')
    res.setHeader('Content-Type', path.endsWith('.js') ? 'text/javascript' : path.endsWith('.css') ? 'text/css' : 'text/html')
    res.end(await readFile(path))
  } catch { res.writeHead(404); res.end() }
})
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
let browser
try {
  try { browser = await chromium.launch({ headless: true }) }
  catch { browser = await chromium.launch({ channel: 'msedge', headless: true }) }
  for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
    const context = await browser.newContext({ viewport, reducedMotion: 'reduce' })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    const healthBefore = healthRequests
    await page.goto(`http://127.0.0.1:${server.address().port}`)
    await page.locator('#auth-email').waitFor()
    assert.equal(await page.locator('#homepage-title').count(), 0)
    assert.equal(healthRequests, healthBefore)
    assert.equal(await page.getByLabel('E-post', { exact: true }).evaluate((element) => element === document.activeElement), true)
    await page.keyboard.press('Tab')
    assert.equal(await page.getByLabel('Lösenord', { exact: true }).evaluate((element) => element === document.activeElement), true)
    await page.screenshot({ path: join(screenshots, `login-${viewport.width}.png`) })
    loginFailure = true
    await page.getByLabel('E-post', { exact: true }).fill(user.email)
    await page.getByLabel('Lösenord', { exact: true }).fill('password123')
    await page.getByRole('button', { name: 'Logga in', exact: true }).click()
    await page.getByRole('alert').waitFor()
    assert.equal(await page.locator('#homepage-title').count(), 0)
    loginFailure = false
    await page.getByRole('button', { name: 'Skapa konto', exact: true }).click()
    await page.getByLabel('Lösenord', { exact: true }).fill('password123')
    await page.getByLabel('Bekräfta lösenord').fill('different123')
    await page.locator('button[type=submit]').click()
    await page.getByText('Lösenorden stämmer inte överens.').waitFor()
    await page.getByLabel('Bekräfta lösenord').fill('password123')
    await page.screenshot({ path: join(screenshots, `registration-${viewport.width}.png`) })
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
    await page.locator('button[type=submit]').click()
    await page.locator('#homepage-title').waitFor()
    await page.reload()
    await page.locator('#homepage-title').waitFor()
    assert.equal(await page.locator('#auth-email').count(), 0)
    await page.getByLabel('Händelsetext', { exact: true }).fill('Private draft')
    await page.getByLabel('Sök händelser').fill('Private search')
    await page.getByRole('button', { name: 'Analysera', exact: true }).click()
    await page.locator('.workflow-queued').waitFor()
    await page.getByRole('button', { name: 'Logga ut', exact: true }).click()
    await page.locator('#auth-email').waitFor()
    await page.waitForFunction(() => !document.querySelector('.analysis-screen'))
    assert.equal(aborted, true)
    analysisResponse?.end()
    await page.getByLabel('E-post', { exact: true }).fill(user.email)
    await page.getByLabel('Lösenord', { exact: true }).fill('password123')
    await page.locator('button[type=submit]').click()
    await page.locator('#homepage-title').waitFor()
    assert.equal(await page.getByLabel('Händelsetext', { exact: true }).inputValue(), '')
    assert.equal(await page.getByLabel('Sök händelser').inputValue(), '')
    expireAnalysis = true
    await page.getByLabel('Händelsetext', { exact: true }).fill('Event')
    await page.getByRole('button', { name: 'Analysera', exact: true }).click()
    await page.locator('#auth-email').waitFor()
    await page.getByText('Din session har gått ut. Logga in igen.').waitFor()
    expireAnalysis = false
    accountCreated = true
    await page.getByRole('button', { name: 'Skapa konto', exact: true }).click()
    await page.getByLabel('E-post', { exact: true }).fill(user.email)
    await page.getByLabel('Lösenord', { exact: true }).fill('password123')
    await page.getByLabel('Bekräfta lösenord').fill('password123')
    await page.locator('button[type=submit]').click()
    await page.getByText('Kontot har skapats. Logga in för att fortsätta.').waitFor()
    assert.equal(await page.getByLabel('Bekräfta lösenord').count(), 0)
    accountCreated = false
    sessionUnavailable = true
    await page.reload()
    await page.getByRole('button', { name: 'Försök igen' }).waitFor()
    assert.equal(await page.locator('#homepage-title').count(), 0)
    sessionUnavailable = false
    await context.clearCookies()
    await page.getByRole('button', { name: 'Försök igen' }).click()
    await page.locator('#auth-email').waitFor()
    assert.deepEqual(errors, [])
    await context.close()
  }
  console.log(JSON.stringify({ checked: ['login', 'registration', 'restoration', 'logout', 'expiry', 'outages', 'keyboard', 'desktop', 'narrow'], screenshots }, null, 2))
} finally {
  analysisResponse?.end()
  await browser?.close()
  server.closeAllConnections()
  await new Promise((resolve) => server.close(resolve))
}
