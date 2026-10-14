export type User = { id: string; email: string }

export class AuthError extends Error {
  status: number
  accountCreated: boolean
  constructor(message: string, status = 0, accountCreated = false) {
    super(message)
    this.status = status
    this.accountCreated = accountCreated
  }
}

export class SessionExpiredError extends AuthError {
  constructor() { super('Din session har gått ut. Logga in igen.', 401) }
}

async function requestAuth(path: string, body?: Record<string, string>): Promise<Response> {
  let response: Response
  try {
    response = await fetch(`/api/auth/${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(10000),
      ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
    })
  } catch {
    throw new AuthError('Det gick inte att nå inloggningstjänsten. Försök igen.')
  }
  if (!response.ok) {
    let detail: unknown
    try { detail = (await response.json()).detail } catch { /* Use the safe fallback. */ }
    const accountCreated = typeof detail === 'object' && detail !== null && 'account_created' in detail && detail.account_created === true
    const message = typeof detail === 'string' ? detail
      : typeof detail === 'object' && detail !== null && 'message' in detail && typeof detail.message === 'string' ? detail.message
        : response.status === 422 ? 'Kontrollera e-postadress och lösenord.' : 'Inloggningstjänsten är inte tillgänglig. Försök igen.'
    throw new AuthError(message, response.status, accountCreated)
  }
  return response
}

async function readUser(response: Response): Promise<User> {
  let data: unknown
  try { data = await response.json() } catch { throw new AuthError('Inloggningstjänsten gav ett ogiltigt svar.') }
  if (typeof data !== 'object' || data === null || !('id' in data) || typeof data.id !== 'string'
    || !data.id || !('email' in data) || typeof data.email !== 'string' || !data.email) {
    throw new AuthError('Inloggningstjänsten gav ett ogiltigt svar.')
  }
  return { id: data.id, email: data.email }
}

export async function checkSession(): Promise<User | null> {
  try { return await readUser(await requestAuth('session')) }
  catch (error) {
    if (error instanceof AuthError && error.status === 401) return null
    throw error
  }
}

export async function login(email: string, password: string): Promise<User> {
  return readUser(await requestAuth('login', { email: email.trim(), password }))
}

export async function register(email: string, password: string, passwordConfirm: string): Promise<User> {
  return readUser(await requestAuth('register', { email: email.trim(), password, password_confirm: passwordConfirm }))
}

export async function logout(): Promise<void> {
  await requestAuth('logout', {})
}
