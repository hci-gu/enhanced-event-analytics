import assert from 'node:assert/strict'
import { test } from 'node:test'
import { canNavigate, canSubmit, pageAfterUpdate } from '../src/navigation.ts'
import { initialAnalysis } from '../src/analysis.ts'

test('page availability follows the current analysis without clearing results', () => {
  assert.equal(canNavigate('home', null), true)
  assert.equal(canNavigate('status', null), false)
  assert.equal(canNavigate('summary', null), false)
  for (const status of ['preparing', 'running', 'failed', 'completed']) {
    const analysis = { ...initialAnalysis, status, title: 'Rubrik' }
    assert.equal(canNavigate('status', analysis), true)
    assert.equal(canNavigate('summary', analysis), status === 'completed')
    assert.equal(analysis.title, 'Rubrik')
  }
})

test('completion redirects only from Status and allows revisiting completed Status', () => {
  assert.equal(pageAfterUpdate('status', 'running', 'completed'), 'summary')
  assert.equal(pageAfterUpdate('home', 'running', 'completed'), 'home')
  assert.equal(pageAfterUpdate('status', 'completed', 'completed'), 'status')
  assert.equal(pageAfterUpdate('status', 'running', 'failed'), 'status')
})

test('another event may replace an analysis only after the current request finishes', () => {
  assert.equal(canSubmit('New event', false), true)
  assert.equal(canSubmit('New event', true), false)
  assert.equal(canSubmit('  \n ', false), false)
})
