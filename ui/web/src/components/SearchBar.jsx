import { useEffect, useRef, useState } from 'react'
import { apiSearch } from '../api'
import { debounce } from '../utils'

export default function SearchBar({ onAdd }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)
  // Tracks the input's current value so the debounced search can detect a
  // stale response — e.g. the user pressed Enter or cleared the box while an
  // apiSearch(q) fetch was still in flight, and the dropdown must not reopen
  // with results for a query that's no longer live.
  const latestQueryRef = useRef('')

  const debouncedSearch = useRef(
    debounce(async (q) => {
      if (!q.trim()) {
        setResults([])
        setOpen(false)
        return
      }
      const res = await apiSearch(q)
      if (latestQueryRef.current !== q) return // superseded — drop this response
      setResults(res)
      setOpen(res.length > 0)
    }, 320),
  ).current

  useEffect(() => {
    function onClickOutside(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('click', onClickOutside)
    return () => document.removeEventListener('click', onClickOutside)
  }, [])

  function handleChange(e) {
    const v = e.target.value
    setQuery(v)
    latestQueryRef.current = v
    debouncedSearch(v)
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') {
      const v = query.trim().toUpperCase()
      if (v) {
        onAdd(v)
        setQuery('')
        latestQueryRef.current = ''
        setOpen(false)
      }
    }
    if (e.key === 'Escape') setOpen(false)
  }

  function pick(symbol) {
    onAdd(symbol)
    setQuery('')
    latestQueryRef.current = ''
    setOpen(false)
  }

  return (
    <div ref={wrapRef} className="relative">
      <svg
        className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 stroke-muted"
        viewBox="0 0 24 24"
        fill="none"
        strokeWidth="2"
      >
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
      <input
        value={query}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        type="text"
        autoComplete="off"
        spellCheck="false"
        placeholder="Search stocks — Apple, TSLA, NVDA, 0700.HK…"
        className="w-full rounded-xl border border-border bg-surface2 py-2.5 pl-10 pr-4 text-sm text-slate-100 outline-none transition placeholder:text-muted focus:border-accent focus:ring-4 focus:ring-accent/10"
      />
      {open && (
        <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-20 animate-fade-in overflow-hidden rounded-xl border border-border bg-surface2 shadow-2xl shadow-black/50">
          {results.map((r) => (
            <div
              key={r.symbol}
              onClick={() => pick(r.symbol)}
              className="flex cursor-pointer items-center justify-between border-b border-border px-4 py-2.5 last:border-b-0 hover:bg-accent/10"
            >
              <div>
                <span className="text-sm font-bold text-accent">{r.symbol}</span>
                <span className="ml-2 text-xs text-muted">{r.name}</span>
              </div>
              <span className="text-xs text-muted">{r.exchange}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
