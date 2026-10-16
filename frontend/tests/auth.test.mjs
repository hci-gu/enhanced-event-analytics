import assert from 'node:assert/strict'
import { test } from 'node:test'
import { AuthError, checkSession, login, logout, register, SessionExpiredError } from '../src/auth.ts'
import { streamAnalysis } from '../src/api.ts'

const user = { id: 'testuser0000001', email: 'user@example.com' }

test('restores a session with cookies and does not expose returned extra fields', async (t) => {
  const fetchMock = t.mock.method(globalThis, 'fetch', async () => Response.json({ ...user, token: 'ignored' }))
  assert.deepEqual(await checkSession(), user)
  const [path, options] = fetchMock.mock.calls[0].arguments
  assert.equal(path, '/api/auth/session')
  assert.equal(options.method, 'GET')
  assert.equal(options.credentials, 'same-origin')
  assert.equal(options.cache, 'no-store')
})

test('only an unauthorized session returns anonymous; an outage remains an error', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Expired' }, { status: 401 }))
  assert.equal(await checkSession(), null)
  t.mock.restoreAll()
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Unavailable' }, { status: 503 }))
  await assert.rejects(checkSession(), /Unavailable/)
})

test('login trims email without changing passwords and registration includes confirmation', async (t) => {
  const fetchMock = t.mock.method(globalThis, 'fetch', async () => Response.json(user))
  await login(' user@example.com ', ' password ')
  await register(' user@example.com ', ' password ', ' password ')
  assert.deepEqual(JSON.parse(fetchMock.mock.calls[0].arguments[1].body), { email: user.email, password: ' password ' })
  assert.deepEqual(JSON.parse(fetchMock.mock.calls[1].arguments[1].body), {
    email: user.email, password: ' password ', password_confirm: ' password ',
  })
})

test('reports successful account creation separately from automatic login failure', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: { message: 'Account created', account_created: true } }, { status: 503 }))
  await assert.rejects(register(user.email, 'password123', 'password123'), (error) =>
    error instanceof AuthError && error.accountCreated && error.message === 'Account created')
})

test('logout posts with cookies and accepts an empty response', async (t) => {
  const fetchMock = t.mock.method(globalThis, 'fetch', async () => new Response(null, { status: 204 }))
  await logout()
  assert.equal(fetchMock.mock.calls[0].arguments[1].method, 'POST')
  assert.equal(fetchMock.mock.calls[0].arguments[1].credentials, 'same-origin')
})

test('rejects malformed users and network failures', async (t) => {
  for (const response of [Response.json({}), new Response('invalid')]) {
    t.mock.method(globalThis, 'fetch', async () => response)
    await assert.rejects(checkSession(), /ogiltigt svar/)
    t.mock.restoreAll()
  }
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('network') })
  await assert.rejects(login(user.email, 'password'), /inte att nå inloggningstjänsten/)
})

test('expired analysis authentication is distinguished from inference failures', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(null, { status: 401 }))
  await assert.rejects(streamAnalysis('Event', () => {}), SessionExpiredError)
})
