import assert from 'node:assert/strict'
import { test } from 'node:test'
import { historyGroups, loadHistory, loadSavedAnalysis } from '../src/history.ts'
import { SessionExpiredError } from '../src/auth.ts'

const analysisId = '01234567-89ab-4cde-8fab-0123456789ab'
const item = { analysis_id: analysisId, title: 'Vatten stiger', status: 'Complete', created: '2026-10-16 09:00:00.000Z', finished_at: '2026-10-16 09:01:00.000Z' }
const saved = { ...item, original_text: 'Vatten stiger.', predictions: {
  risks: [{ ID: 'flood', name: 'Översvämningar', evidence: ['Vatten stiger', 'Finns inte'] }], old: [],
}, workflows: [{ id: 'risks', label: 'Riskområden' }, { id: 'old', label: 'old' }, { id: 'dates', label: 'Datum' }], dates: null, dates_error: null }

test('history requests five first, then twenty with an encoded cursor and no caching', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => Response.json({ items: [item], next_cursor: 'cursor+=' }))
  const page = await loadHistory()
  assert.equal(page.items[0].analysisId, analysisId)
  assert.equal(page.items[0].createdAt, '2026-10-16T09:00:00.000Z')
  assert.equal(mock.mock.calls[0].arguments[0], '/api/analyses?limit=5')
  assert.equal(mock.mock.calls[0].arguments[1].cache, 'no-store')
  await loadHistory(page.nextCursor)
  assert.equal(mock.mock.calls[1].arguments[0], '/api/analyses?limit=20&cursor=cursor%2B%3D')
})

test('restores workflows, source, finish time, and verified evidence without generation', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => Response.json(saved))
  const result = await loadSavedAnalysis(analysisId)
  assert.equal(mock.mock.calls[0].arguments[0], `/api/analyses/${analysisId}`)
  assert.equal(result.text, saved.original_text)
  assert.equal(result.analysis.status, 'completed')
  assert.deepEqual(result.analysis.workflows.map((workflow) => workflow.id), ['risks', 'old', 'dates'])
  assert.deepEqual(result.analysis.workflows[0].results[0].evidence, ['Vatten stiger'])
  assert.equal(result.analysis.analyzedAt, '2026-10-16T09:01:00.000Z')
})

test('retains nonfatal date failure and does not invent a date timeline', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ ...saved, dates_error: { message: 'Date extraction failed' } }))
  const result = await loadSavedAnalysis(analysisId)
  assert.equal(result.analysis.status, 'completed')
  assert.equal(result.analysis.dates, null)
  assert.equal(result.analysis.workflows.at(-1).status, 'failed')
  assert.match(result.analysis.workflows.at(-1).error, /Datum/)
})

test('rejects invalid or mismatched saved records', async (t) => {
  for (const body of [null, { ...saved, original_text: null }, { ...saved, predictions: { risks: 'invalid' } }, { ...saved, analysis_id: '11234567-89ab-4cde-8fab-0123456789ab' }]) {
    t.mock.method(globalThis, 'fetch', async () => Response.json(body))
    await assert.rejects(loadSavedAnalysis(analysisId))
    t.mock.restoreAll()
  }
})

test('expired sessions, unavailable storage and missing records are reported', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('', { status: 401 }))
  await assert.rejects(loadHistory(), SessionExpiredError)
  t.mock.restoreAll()
  t.mock.method(globalThis, 'fetch', async () => new Response('', { status: 503 }))
  await assert.rejects(loadHistory(), /inte tillgänglig/)
  t.mock.restoreAll()
  t.mock.method(globalThis, 'fetch', async () => new Response('', { status: 404 }))
  await assert.rejects(loadSavedAnalysis(analysisId), /inte hittas/)
})

test('groups by local calendar days across month and year boundaries', () => {
  const entries = [new Date(2026, 0, 1, 10), new Date(2025, 11, 31, 15), new Date(2025, 11, 30, 12)]
    .map((date, index) => ({ analysisId: String(index), title: 'Test', createdAt: date.toISOString() }))
  assert.deepEqual(historyGroups(entries, new Date(2026, 0, 1, 18)).map((group) => group.label), ['I dag', 'I går', '30 december 2025'])
})
