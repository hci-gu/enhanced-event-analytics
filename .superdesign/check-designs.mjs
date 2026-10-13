import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve, sep } from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require('C:/Users/arret/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')
let browser
try {
  try { browser = await chromium.launch({ headless: true }) }
  catch { browser = await chromium.launch({ channel: 'msedge', headless: true }) }
  for (const name of (process.argv.slice(2).length ? process.argv.slice(2) : ['signal', 'editorial', 'atlas'])) {
    const root = `C:/Users/arret/.codex/worktrees/design-${name}/enhanced-event-analytics/frontend`
    const directory = resolve(root, 'dist')
    const server = createServer(async (request, response) => {
      const pathname = new URL(request.url, 'http://localhost').pathname
      if (pathname === '/api/health') {
        response.setHeader('Content-Type', 'application/json')
        response.end('{"status":"ok"}')
        return
      }
      try {
        const path = resolve(directory, pathname === '/' ? 'index.html' : `.${pathname}`)
        if (!path.startsWith(directory + sep)) throw new Error('Invalid path')
        response.setHeader('Content-Type', path.endsWith('.js') ? 'text/javascript' : path.endsWith('.css') ? 'text/css' : 'text/html')
        response.end(await readFile(path))
      } catch { response.writeHead(404); response.end() }
    })
    await new Promise((done) => server.listen(0, '127.0.0.1', done))
    try {
      for (const width of [1440, 390]) {
        const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' })
        await page.goto(`http://127.0.0.1:${server.address().port}`)
        assert.equal(await page.getByRole('button', { name: 'Analysera', exact: true }).isDisabled(), true)
        await page.screenshot({ path: `${root}/design-${width}.png`, fullPage: true })
        await page.getByRole('button', { name: 'Prova en exempeltext' }).click()
        assert.ok((await page.getByLabel('Händelsetext', { exact: true }).inputValue()).length > 100)
        assert.equal(await page.getByRole('button', { name: 'Analysera', exact: true }).isDisabled(), false)
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
        assert.equal(await page.locator('.perspective-card').first().evaluate((element) => getComputedStyle(element).animationName), 'none')
        await page.close()
      }
      console.log(`${name}: desktop/mobile, sample input, overflow and reduced-motion checks passed`)
    } finally {
      server.closeAllConnections()
      await new Promise((done) => server.close(done))
    }
  }
} finally { await browser?.close() }
