import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { checkHealth, streamAnalysis } from './api'
import { failAnalysis, initialAnalysis } from './analysis'
import type { AnalysisState } from './analysis'
import AnalysisView from './AnalysisView'
import PageMenu from './PageMenu'
import { canSubmit, pageAfterUpdate } from './navigation'
import type { Page } from './navigation'
import './App.css'
import { SessionExpiredError } from './auth'

function App({ onLogout, onSessionExpired }: { onLogout: () => void; onSessionExpired: () => void }) {
  const [text, setText] = useState('')
  const [search, setSearch] = useState('')
  const [keyboardFocus, setKeyboardFocus] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [analysis, setAnalysis] = useState<AnalysisState | null>(null)
  const [submittedText, setSubmittedText] = useState('')
  const [page, setPage] = useState<Page>('home')
  const [healthError, setHealthError] = useState<string | null>(null)
  const healthRequest = useRef<Promise<void> | null>(null)
  const healthDialogRef = useRef<HTMLDialogElement>(null)
  const requestPending = useRef(false)
  const requestController = useRef<AbortController | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const focusComposer = useRef(false)

  useEffect(() => () => requestController.current?.abort(), [])

  useEffect(() => {
    if (page === 'home' && focusComposer.current) {
      textareaRef.current?.focus()
      focusComposer.current = false
    }
  }, [page])

  useEffect(() => {
    let active = true
    // Reuse the request during StrictMode's development effect replay.
    healthRequest.current ??= checkHealth()
    void healthRequest.current.catch((error: unknown) => {
      if (active) {
        setHealthError(error instanceof Error ? error.message : 'Hälsokontrollen misslyckades.')
      }
    })
    return () => { active = false }
  }, [])

  useEffect(() => {
    const dialog = healthDialogRef.current
    if (!dialog) return
    if (healthError && !dialog.open) dialog.showModal()
    else if (!healthError && dialog.open) dialog.close()
  }, [healthError])

  useLayoutEffect(() => {
    const textarea = textareaRef.current
    const form = formRef.current
    if (!textarea || !form) return

    // Measure content at its current width; flex sizing supplies the height cap.
    function resizeTextarea() {
      if (!textarea) return
      textarea.style.height = '0px'
      textarea.style.height = `${textarea.scrollHeight}px`
    }

    resizeTextarea()
    const observer = new ResizeObserver(resizeTextarea)
    observer.observe(form)
    return () => observer.disconnect()
  }, [text, page])

  async function analyzeEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedText = text.trim()
    if (!canSubmit(trimmedText, requestPending.current)) return

    requestPending.current = true
    setIsLoading(true)
    setSubmittedText(text)
    setAnalysis(initialAnalysis)
    setPage('status')
    const controller = new AbortController()
    requestController.current = controller

    let previousStatus = initialAnalysis.status
    try {
      await streamAnalysis(trimmedText, (state) => {
        if (!controller.signal.aborted) {
          setAnalysis(state)
          const previous = previousStatus
          setPage((current) => pageAfterUpdate(current, previous, state.status))
          previousStatus = state.status
        }
      }, controller.signal)
    } catch (error) {
      if (error instanceof SessionExpiredError && !controller.signal.aborted) {
        onSessionExpired()
        return
      }
      if (!controller.signal.aborted) {
        const message = error instanceof Error ? error.message : 'Anslutningen avbröts. Försök igen genom att ladda om sidan.'
        setAnalysis((current) => failAnalysis(current ?? initialAnalysis, message))
      }
    } finally {
      requestPending.current = false
      if (!controller.signal.aborted) setIsLoading(false)
    }
  }

  function startNewAnalysis() {
    focusComposer.current = true
    setText('')
    setPage('home')
  }

  return (
    <main
      className="homepage"
      data-keyboard-focus={keyboardFocus}
      onPointerDownCapture={() => setKeyboardFocus(false)}
      onKeyDownCapture={(event) => {
        if (event.key === 'Tab') setKeyboardFocus(true)
      }}
    >
      <dialog
        ref={healthDialogRef}
        className="health-dialog"
        role="alertdialog"
        aria-labelledby="health-error-title"
        aria-describedby="health-error-message"
        onCancel={() => setHealthError(null)}
      >
        <h2 id="health-error-title">Tjänsten är inte tillgänglig</h2>
        <p id="health-error-message">{healthError}</p>
        <button type="button" autoFocus onClick={() => setHealthError(null)}>Stäng</button>
      </dialog>
      <header className="app-toolbar">
        <button type="button" className="app-brand" onClick={() => setPage('home')} aria-label="Förstärkt analysförmåga – Hem">
          <span>Underrättelse &amp; Analys</span>
          <span>Förstärkt analysförmåga</span>
        </button>
        <div className="toolbar-controls">
          <div className="search-row">
            <label className="search-widget">
              <span className="visually-hidden">Sök händelser</span>
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle cx="10.5" cy="10.5" r="6.5" />
                <path d="m16 16 5 5" />
              </svg>
              <input
                type="search"
                placeholder="Sök händelser…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
          </div>
          <PageMenu page={page} analysis={analysis} onNavigate={setPage} />
          <button type="button" className="text-action logout-action" onClick={() => {
            requestController.current?.abort()
            onLogout()
          }}>Logga ut</button>
        </div>
      </header>
      {page !== 'home' && analysis ? (
        <AnalysisView analysis={analysis} text={submittedText} page={page} onNewAnalysis={startNewAnalysis} />
      ) : (
        <section className="event-section" aria-labelledby="homepage-title">
          <h1 id="homepage-title">Förstärkt Analysförmåga</h1>
          <form ref={formRef} onSubmit={analyzeEvent} aria-busy={isLoading}>
            <div className="event-widget">
              <div className="event-widget-inner">
                <label className="field-label" htmlFor="event-text">Källtext</label>
                <textarea
                  ref={textareaRef}
                  rows={1}
                  id="event-text"
                  aria-label="Händelsetext"
                  placeholder="Skriv eller klistra in text här…"
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  readOnly={isLoading}
                  required
                />
              </div>
            </div>
            <div className="event-actions">
              <button type="submit" disabled={!text.trim() || isLoading}>
                {isLoading ? 'Analyserar…' : 'Analysera'}
              </button>
            </div>
          </form>
        </section>
      )}
    </main>
  )
}

export default App
