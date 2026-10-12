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
