import { useEffect, useRef, useState } from 'react'
import type { ReactNode, Ref } from 'react'
import { SessionExpiredError } from './auth'
import { historyGroups, loadHistory } from './history'
import type { HistoryPage } from './history'
import './HistorySidebar.css'

export function HistoryToggle({ expanded, onToggle, buttonRef }: {
  expanded: boolean; onToggle: () => void; buttonRef?: Ref<HTMLButtonElement>
}) {
  return <button type="button" className="history-toggle" ref={buttonRef} onClick={onToggle}
    aria-expanded={expanded} aria-controls="analysis-history" aria-label={expanded ? 'Dölj historik' : 'Visa historik'}
    title={expanded ? 'Dölj historik' : 'Visa historik'}>
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="4" width="18" height="16" rx="1" /><path d="M9 4v16" />
      <path className="history-toggle-direction" d="m16 9-3 3 3 3" />
    </svg>
    {!expanded && <span>Historik</span>}
  </button>
}

export default function HistorySidebar({ expanded, toggle, selectedId, openingId, refreshKey, onOpen, onSessionExpired }: {
  expanded: boolean; toggle: ReactNode; selectedId: string | null; openingId: string | null; refreshKey: number
  onOpen: (analysisId: string) => void; onSessionExpired: () => void
}) {
  const [history, setHistory] = useState<HistoryPage>({ items: [], nextCursor: null })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const request = useRef<AbortController | null>(null)
  const pending = useRef(false)
  const scroll = useRef<HTMLDivElement>(null)
  const firstAdded = useRef<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    request.current?.abort()
    request.current = controller
    pending.current = true
    void loadHistory(null, controller.signal).then((result) => {
      if (controller.signal.aborted) return
      setHistory(result)
      setError(null)
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return
      if (reason instanceof SessionExpiredError) onSessionExpired()
      else setError('Historiken kunde inte hämtas.')
    }).finally(() => {
      if (!controller.signal.aborted) {
        setLoading(false)
        pending.current = false
      }
    })
    return () => { request.current?.abort() }
  }, [refreshKey, attempt, onSessionExpired])

  useEffect(() => {
    if (firstAdded.current) {
      scroll.current?.querySelector<HTMLButtonElement>(`[data-history-id="${firstAdded.current}"]`)?.focus({ preventScroll: true })
      firstAdded.current = null
    }
  }, [history])

  async function showMore() {
    if (pending.current || !history.nextCursor) return
    const controller = new AbortController()
    request.current = controller
    pending.current = true
    setLoading(true)
    setError(null)
    try {
      const result = await loadHistory(history.nextCursor, controller.signal)
      if (controller.signal.aborted) return
      const seen = new Set(history.items.map((item) => item.analysisId))
      const added = result.items.filter((item) => !seen.has(item.analysisId))
      firstAdded.current = added[0]?.analysisId ?? null
      setHistory({ items: [...history.items, ...added], nextCursor: result.nextCursor })
    } catch (reason) {
      if (controller.signal.aborted) return
      if (reason instanceof SessionExpiredError) onSessionExpired()
      else setError('Fler analyser kunde inte hämtas.')
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false)
        pending.current = false
      }
    }
  }

  return <div className="history-slot">
    <aside className="history-sidebar" id="analysis-history" aria-label="Analyshistorik" inert={!expanded} aria-hidden={!expanded}>
      <div className="history-heading"><h2>Senaste analyser</h2>{toggle}</div>
      <div className="history-scroll" ref={scroll} tabIndex={expanded ? 0 : -1} role="region" aria-label="Rullbar analyshistorik" aria-busy={loading}>
        {historyGroups(history.items).map((group) => <section className="history-day" key={group.label}>
          <h3>{group.label}</h3>
          <ol>{group.items.map((item) => <li key={item.analysisId}>
            <button type="button" className="history-event" data-history-id={item.analysisId}
              aria-current={item.analysisId === selectedId ? 'page' : undefined}
              aria-busy={item.analysisId === openingId} onClick={() => onOpen(item.analysisId)}>
              <time dateTime={item.createdAt}>{new Date(item.createdAt).toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit' })}</time>
              <span><span className="history-event-title">{item.title}</span><span className="history-event-status">{item.analysisId === openingId ? 'Öppnar…' : 'Klar'}</span></span>
            </button>
          </li>)}</ol>
        </section>)}
        {!history.items.length && !loading && !error && <p className="history-message">Inga analyser ännu.</p>}
        {loading && <p className="history-message" role="status">Hämtar…</p>}
        {error && <div className="history-message" role="alert"><p>{error}</p><button type="button" className="text-action" onClick={() => {
          if (history.nextCursor) void showMore()
          else setAttempt((value) => value + 1)
        }}>Försök igen</button></div>}
        {history.nextCursor && !error && <div className="history-more"><button type="button" disabled={loading} onClick={() => void showMore()}>Visa fler <span aria-hidden="true">↓</span></button></div>}
      </div>
      <p className="visually-hidden" role="status" aria-live="polite">{history.items.length ? `${history.items.length} analyser hämtade` : ''}</p>
    </aside>
  </div>
}
