import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { checkHealth, streamAnalysis } from './api'
import { failAnalysis, initialAnalysis } from './analysis'
import type { AnalysisState } from './analysis'
import AnalysisScreen from './AnalysisScreen'
import './App.css'

function App() {
  const [text, setText] = useState('')
  const [search, setSearch] = useState('')
  const [keyboardFocus, setKeyboardFocus] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [analysis, setAnalysis] = useState<AnalysisState | null>(null)
  const hasAnalysis = analysis !== null
  const [healthError, setHealthError] = useState<string | null>(null)
  const healthRequest = useRef<Promise<void> | null>(null)
  const healthDialogRef = useRef<HTMLDialogElement>(null)
  const requestPending = useRef(false)
  const requestController = useRef<AbortController | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const formRef = useRef<HTMLFormElement>(null)

  useEffect(() => () => requestController.current?.abort(), [])

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
  }, [text, hasAnalysis])

  async function analyzeEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedText = text.trim()
    if (!trimmedText || requestPending.current || hasAnalysis) return

    requestPending.current = true
    setIsLoading(true)
    setAnalysis(initialAnalysis)
    const controller = new AbortController()
    requestController.current = controller

    try {
      await streamAnalysis(trimmedText, (state) => {
        if (!controller.signal.aborted) setAnalysis(state)
      }, controller.signal)
    } catch (error) {
      if (!controller.signal.aborted) {
        const message = error instanceof Error ? error.message : 'Anslutningen avbröts. Försök igen genom att ladda om sidan.'
        setAnalysis((current) => failAnalysis(current ?? initialAnalysis, message))
      }
    } finally {
      requestPending.current = false
      if (!controller.signal.aborted) setIsLoading(false)
    }
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
      {analysis ? <AnalysisScreen analysis={analysis} /> : <>
      <div className="search-row">
        <label className="search-widget">
          <span className="visually-hidden">Sök händelser</span>
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="10.5" cy="10.5" r="6.5" />
            <path d="m16 16 5 5" />
          </svg>
          <input
            type="search"
            placeholder="Sök"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
      </div>

      <section className="event-section" aria-labelledby="homepage-title">
        <h1 id="homepage-title">Förstärkt Analysförmåga</h1>
        <form ref={formRef} onSubmit={analyzeEvent} aria-busy={isLoading}>
          <div className="event-widget">
            <label className="visually-hidden" htmlFor="event-text">Händelsetext</label>
            <textarea
              ref={textareaRef}
              rows={1}
              id="event-text"
              placeholder="Händelsetext…"
              value={text}
              onChange={(event) => {
                setText(event.target.value)
              }}
              readOnly={isLoading}
              required
            />
            <div className="event-actions">
              <button type="submit" disabled={!text.trim() || isLoading}>
                {isLoading ? 'Analyserar…' : 'Analysera'}
              </button>
            </div>
          </div>
        </form>
      </section>
      </>}
    </main>
  )
}

export default App
