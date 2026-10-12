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
import './Design.css'

function App() {
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
      <header className="app-toolbar">
      <a className="studio-brand" href="#" onClick={(event) => { event.preventDefault(); setPage('home') }}>
        <span>Journal<small>Förstärkt analysförmåga</small></span>
      </a>
      {page === 'home' && <div className="search-row">
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
      </div>}
      <PageMenu page={page} analysis={analysis} onNavigate={setPage} />
      </header>
      {page !== 'home' && analysis ? <AnalysisView analysis={analysis} text={submittedText} page={page} /> : <>
      <section className="event-section" aria-labelledby="homepage-title">
        <div className="studio-intro">
          <p className="studio-eyebrow">ANALYSJOURNALEN / UTGÅVA 02</p>
          <h1 id="homepage-title">Se sammanhanget.<br /><em>Förstå händelsen.</em></h1>
          <p className="studio-description">En arbetsyta för eftertanke. Från den första uppgiften till en samlad bild av vad som kan påverkas.</p>
        </div>
        <div className="studio-workspace">
        <form ref={formRef} onSubmit={analyzeEvent} aria-busy={isLoading}>
          <div className="composer-heading"><span>Ny händelse</span><span>01 / UNDERLAG</span></div>
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
              <span className="character-count" aria-live="polite">{text.length.toLocaleString('sv-SE')} tecken</span>
              <button type="submit" disabled={!text.trim() || isLoading}>
                {isLoading ? 'Analyserar…' : 'Analysera'}
              </button>
            </div>
          </div>
          <div className="composer-footer"><span>Textstöd kopplas till varje resultat</span>
            <button className="sample-button" type="button" disabled={isLoading} onClick={() => setText('Kraftiga regn har orsakat översvämningar i flera bostadsområden. Vägar är avstängda och räddningstjänsten hjälper invånare att lämna sina hem. Kommunen undersöker påverkan på dricksvatten och äldreomsorg.')}>Prova en exempeltext ↗</button>
          </div>
        </form>
        <aside className="perspective-panel" aria-labelledby="perspective-title">
          <p className="studio-eyebrow">ANALYSPERSPEKTIV</p>
          <h2 id="perspective-title">En samlad bild</h2>
          <p>Tre perspektiv som hjälper dig att förstå vad händelsen betyder.</p>
          <div className="perspective-card"><div><h3>Risker & konsekvenser</h3><p>Vad kan inträffa?</p></div></div>
          <div className="perspective-card"><div><h3>Geografisk räckvidd</h3><p>Vilka områden berörs?</p></div></div>
          <div className="perspective-card"><div><h3>Berörda verksamheter</h3><p>Vad behöver fungera?</p></div></div>
          <div className="perspective-note">Resultaten länkas till din händelsetext.</div>
        </aside>
        </div>
        <footer className="studio-footer"><span>FÖRSTÄRKT ANALYSFÖRMÅGA</span><span>Underlag → Analys → Sammanfattning</span></footer>
      </section>
      </>}
    </main>
  )
}

export default App
