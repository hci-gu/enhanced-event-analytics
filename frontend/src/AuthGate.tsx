import { useEffect, useRef, useState } from 'react'
import { checkSession, logout } from './auth'
import type { User } from './auth'
import App from './App'
import AuthScreen, { AuthFrame } from './AuthScreen'

type SessionState = { status: 'loading' } | { status: 'anonymous'; message?: string }
  | { status: 'authenticated'; user: User } | { status: 'unavailable'; message: string; action: 'session' | 'logout' }

export default function AuthGate() {
  const [session, setSession] = useState<SessionState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const restoration = useRef<{ attempt: number; promise: Promise<User | null> } | null>(null)

  useEffect(() => {
    let active = true
    // Share session restoration during StrictMode's effect replay.
    if (!restoration.current || restoration.current.attempt !== attempt) {
      restoration.current = { attempt, promise: checkSession() }
    }
    void restoration.current.promise.then((user) => {
      if (active) setSession(user ? { status: 'authenticated', user } : { status: 'anonymous' })
    }).catch((error: unknown) => {
      if (active) setSession({ status: 'unavailable', action: 'session',
        message: error instanceof Error ? error.message : 'Det gick inte att kontrollera din session.' })
    })
    return () => { active = false }
  }, [attempt])

  async function signOut() {
    // Unmount the workspace immediately, aborting requests and dropping its state.
    setSession({ status: 'loading' })
    try {
      await logout()
      setSession({ status: 'anonymous' })
    } catch {
      setSession({ status: 'unavailable', action: 'logout', message: 'Det gick inte att logga ut. Försök igen.' })
    }
  }

  if (session.status === 'authenticated') return <App key={session.user.id} onLogout={() => void signOut()}
    onSessionExpired={() => setSession({ status: 'anonymous', message: 'Din session har gått ut. Logga in igen.' })} />
  if (session.status === 'anonymous') return <AuthScreen message={session.message}
    onAuthenticated={(user) => setSession({ status: 'authenticated', user })} />
  return <AuthFrame><section className="auth-section" aria-labelledby="session-heading">
    <h1 id="session-heading">{session.status === 'loading' ? 'Ett ögonblick' : 'Anslutningen avbröts'}</h1>
    {session.status === 'loading' ? <p className="auth-session-message" role="status">Kontrollerar din session…</p>
      : <><p className="auth-feedback" role="alert">{session.message}</p>
        <button className="auth-submit" type="button" onClick={() => {
          if (session.action === 'logout') void signOut()
          else {
            setSession({ status: 'loading' })
            setAttempt((value) => value + 1)
          }
        }}>Försök igen</button></>}
  </section></AuthFrame>
}
