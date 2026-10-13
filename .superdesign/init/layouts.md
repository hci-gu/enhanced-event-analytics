# Shared layouts

## App shell
Source: `frontend/src/App.tsx`. Single viewport app shell with health dialog, toolbar, PageMenu and state-selected home/status/summary content. App owns text submission and streaming lifecycle. Current home search stores input only; it does not retrieve events.

### `frontend/src/App.tsx`

```tsx
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
```

## PageMenu
Source: `frontend/src/PageMenu.tsx`. Shared popover navigation, disabled page guards, focus restoration, arrow keys, Escape and outside dismissal. Props: page, analysis, onNavigate.

### `frontend/src/PageMenu.tsx`

```tsx
import { useEffect, useRef, useState } from 'react'
import type { AnalysisState } from './analysis'
import { canNavigate } from './navigation'
import type { Page } from './navigation'
import './PageMenu.css'

const pages: { id: Page; label: string }[] = [
  { id: 'home', label: 'Hem' }, { id: 'status', label: 'Status' }, { id: 'summary', label: 'Sammanfattning' },
]

export default function PageMenu({ page, analysis, onNavigate }: {
  page: Page; analysis: AnalysisState | null; onNavigate: (page: Page) => void
}) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const popup = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!open) return
    function outside(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])

  function close() {
    setOpen(false)
    trigger.current?.focus()
  }

  function focusItem(last = false) {
    const items = popup.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')
    items?.[last ? items.length - 1 : 0]?.focus()
  }

  useEffect(() => { if (open) focusItem() }, [open])

  return <div className="page-menu" ref={root} onKeyDown={(event) => {
    if (event.key === 'Escape' && open) {
      event.preventDefault()
      event.stopPropagation()
      close()
    }
  }}>
    <button className="menu-trigger" ref={trigger} type="button" aria-label="Sidmeny"
      aria-expanded={open} aria-controls="page-navigation" onClick={() => setOpen(!open)}
      onKeyDown={(event) => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault()
          if (open) focusItem(event.key === 'ArrowUp')
          else setOpen(true)
        }
      }}>
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M4 6h16M4 12h16M4 18h16" />
      </svg>
    </button>
    {open && <nav id="page-navigation" className="page-navigation" ref={popup} aria-label="Sidor"
      onKeyDown={(event) => {
        const items = [...(popup.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])]
        const index = items.indexOf(document.activeElement as HTMLButtonElement)
        const key = event.key
        if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(key)) {
          event.preventDefault()
          const next = key === 'Home' ? 0 : key === 'End' ? items.length - 1
            : (index + (key === 'ArrowDown' ? 1 : -1) + items.length) % items.length
          items[next]?.focus()
        }
      }}>
      {pages.map((item) => <button key={item.id} type="button" disabled={!canNavigate(item.id, analysis)}
        aria-current={page === item.id ? 'page' : undefined} onClick={() => {
          close()
          onNavigate(item.id)
        }}>{item.label}</button>)}
    </nav>}
  </div>
}
```

## Bootstrap
### `frontend/src/main.tsx`

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './colors.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

No shared sidebar, footer, breadcrumb or external router is implemented.

