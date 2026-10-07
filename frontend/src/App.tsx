import { useLayoutEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { submitEvent } from './api'
import './App.css'

type Feedback = { kind: 'info' | 'error'; message: string }

function App() {
  const [text, setText] = useState('')
  const [search, setSearch] = useState('')
  const [keyboardFocus, setKeyboardFocus] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const requestPending = useRef(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const formRef = useRef<HTMLFormElement>(null)

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
  }, [text])

  async function analyzeEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedText = text.trim()
    if (!trimmedText || requestPending.current) return

    requestPending.current = true
    setIsLoading(true)
    setFeedback(null)

    try {
      const message = await submitEvent(trimmedText)
      setFeedback({ kind: 'info', message })
    } catch (error) {
      setFeedback({
        kind: 'error',
        message: error instanceof Error ? error.message : 'Förfrågan misslyckades. Försök igen.',
      })
    } finally {
      requestPending.current = false
      setIsLoading(false)
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
                if (!requestPending.current) setFeedback(null)
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
          <div className="feedback" role="status" aria-live="polite" aria-atomic="true">
            {isLoading && <p>Skickar händelsetexten…</p>}
            {feedback && <p className={`feedback-${feedback.kind}`}>{feedback.message}</p>}
          </div>
        </form>
      </section>
    </main>
  )
}

export default App
