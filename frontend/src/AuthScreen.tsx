import { useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { AuthError, login, register } from './auth'
import type { User } from './auth'
import './AuthScreen.css'

export function AuthFrame({ children }: { children: ReactNode }) {
  return <main className="homepage auth-shell">
    <header className="auth-header">
      <div className="app-brand">
        <span>Underrättelse &amp; Analys</span>
        <span>Förstärkt analysförmåga</span>
      </div>
    </header>
    <div className="auth-content">{children}</div>
  </main>
}

export default function AuthScreen({ onAuthenticated, message }: {
  onAuthenticated: (user: User) => void; message?: string
}) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const emailRef = useRef<HTMLInputElement>(null)
  const requestPending = useRef(false)
  const mounted = useRef(false)
  const registering = mode === 'register'
  const heading = registering ? 'Skapa konto' : 'Logga in'

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  useEffect(() => { emailRef.current?.focus() }, [mode])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (requestPending.current) return
    if (registering && password !== confirmation) {
      setError('Lösenorden stämmer inte överens.')
      return
    }
    requestPending.current = true
    setPending(true)
    setError(null)
    try {
      const user = registering ? await register(email, password, confirmation) : await login(email, password)
      if (mounted.current) onAuthenticated(user)
    } catch (error) {
      if (mounted.current) {
        if (error instanceof AuthError && error.accountCreated) {
          setMode('login')
          setPassword('')
          setConfirmation('')
        }
        setError(error instanceof Error ? error.message : 'Inloggningen misslyckades. Försök igen.')
      }
    } finally {
      requestPending.current = false
      if (mounted.current) setPending(false)
    }
  }

  return <AuthFrame>
    <section className="auth-section" aria-labelledby="auth-heading">
      <h1 id="auth-heading">{heading}</h1>
      <div className="auth-card">
        <form onSubmit={submit} aria-busy={pending}>
          <div className="auth-field">
            <label className="field-label" htmlFor="auth-email">E-post</label>
            <input ref={emailRef} id="auth-email" name="email" type="email" autoComplete="username"
              required value={email} onChange={(event) => setEmail(event.target.value)} readOnly={pending} />
          </div>
          <div className="auth-field">
            <label className="field-label" htmlFor="auth-password">Lösenord</label>
            <input id="auth-password" name="password" type="password" autoComplete={registering ? 'new-password' : 'current-password'}
              required minLength={registering ? 8 : 1} maxLength={1024} value={password}
              onChange={(event) => setPassword(event.target.value)} readOnly={pending}
              aria-describedby={registering ? 'password-help' : undefined} />
            {registering && <p className="auth-help" id="password-help">Minst 8 tecken.</p>}
          </div>
          {registering && <div className="auth-field">
            <label className="field-label" htmlFor="auth-confirmation">Bekräfta lösenord</label>
            <input id="auth-confirmation" name="password_confirm" type="password" autoComplete="new-password"
              required minLength={8} maxLength={1024} value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)} readOnly={pending} />
          </div>}
          {error ? <p className="auth-feedback" role="alert">{error}</p>
            : message && <p className="auth-feedback" role="status">{message}</p>}
          <button className="auth-submit" type="submit" disabled={pending}>
            {pending ? registering ? 'Skapar konto…' : 'Loggar in…' : heading}
          </button>
        </form>
      </div>
      <button className="text-action auth-switch" type="button" disabled={pending} onClick={() => {
        setMode(registering ? 'login' : 'register')
        setError(null)
        setPassword('')
        setConfirmation('')
      }}>{registering ? 'Logga in' : 'Skapa konto'}</button>
    </section>
  </AuthFrame>
}
