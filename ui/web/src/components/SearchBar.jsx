import { useEffect, useRef, useState } from 'react'
import { apiSearch } from '../api'
import { useLanguage } from '../i18n/LanguageContext'
import { debounce } from '../utils'

// A bare numeric code entered while in the "China" market bucket is
// normalized to its Yahoo-style A-share ticker; anything already carrying a
// suffix (or entered in US mode) passes through untouched. A-share codes are
// always exactly 6 digits (6xxxxx on Shanghai/.SS, 0xxxxx/3xxxxx on
// Shenzhen/.SZ). Any other digit count has no A-share reading — Hong Kong
// listings are out of scope — so it passes through unchanged and is allowed
// to fail as the invalid ticker it is, rather than being silently rewritten
// into an unsupported market.
function normalizeTicker(raw, market) {
  const v = raw.trim().toUpperCase()
  if (market === 'cn' && /^\d{6}$/.test(v)) {
    return v + (v.startsWith('6') ? '.SS' : '.SZ')
  }
  return v
}

export default function SearchBar({ market, onAdd }) {
  const { t } = useLanguage()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(-1)
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
    }, 320)
  ).current

  useEffect(() => {
    function onClickOutside(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('click', onClickOutside)
    return () => document.removeEventListener('click', onClickOutside)
  }, [])

  // A fresh result set always starts with the top match highlighted, so
  // Enter picks something sensible even before the user touches the arrow keys.
  useEffect(() => {
    setHighlight(results.length > 0 ? 0 : -1)
  }, [results])

  function handleChange(e) {
    const v = e.target.value
    setQuery(v)
    latestQueryRef.current = v
    debouncedSearch(v)
  }

  function handleKeyDown(e) {
    if (open && results.length > 0 && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault()
      const delta = e.key === 'ArrowDown' ? 1 : -1
      setHighlight((h) => (h + delta + results.length) % results.length)
      return
    }
    if (e.key === 'Enter') {
      // With matches showing, Enter must pick the highlighted suggestion —
      // not the raw text the user typed (e.g. a company name like "Apple"
      // isn't a valid ticker; its real symbol, AAPL, is what the dropdown
      // resolved it to).
      if (open && results.length > 0) {
        pick(results[highlight >= 0 ? highlight : 0].symbol)
        return
      }
      const v = normalizeTicker(query, market)
      if (v) {
        onAdd(v)
        setQuery('')
        latestQueryRef.current = ''
        setOpen(false)
      }
      return
    }
    if (e.key === 'Escape') setOpen(false)
  }

  function pick(symbol) {
    onAdd(symbol)
    setQuery('')
    latestQueryRef.current = ''
    setOpen(false)
  }

  const hasQuery = query.trim().length > 0

  return (
    <div ref={wrapRef} className="relative">
      <div
        className={`flex h-[58px] items-center gap-3.5 rounded-2xl border bg-white/[0.035] px-5 transition-all duration-200 ${
          hasQuery
            ? 'border-accent/45 ring-[3px] ring-sky/[0.12]'
            : 'border-accent/16 focus-within:border-accent/45 focus-within:ring-[3px] focus-within:ring-sky/[0.12]'
        }`}
      >
        <svg
          className="pointer-events-none h-5 w-5 flex-shrink-0 stroke-muted"
          viewBox="0 0 24 24"
          fill="none"
          strokeWidth="2"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          type="text"
          autoComplete="off"
          spellCheck="false"
          placeholder={t(`search.placeholder.${market}`)}
          className="min-w-0 flex-1 bg-transparent text-base text-slate-100 outline-none placeholder:text-muted sm:text-[17px]"
        />
        <kbd className="hidden flex-shrink-0 rounded-md border border-accent/[0.18] bg-white/[0.05] px-2 py-1 text-[11px] font-semibold text-muted sm:inline-block">
          ⏎ Enter
        </kbd>
      </div>
      {open && (
        <div className="glass absolute left-0 right-0 top-[calc(100%+8px)] z-20 animate-fade-in overflow-hidden rounded-2xl border border-accent/28 p-2 shadow-[0_24px_60px_rgba(0,0,0,0.55)]">
          {results.map((r, i) => (
            <div
              key={r.symbol}
              onClick={() => pick(r.symbol)}
              onMouseEnter={() => setHighlight(i)}
              className={`flex animate-fade-in cursor-pointer items-center justify-between rounded-xl px-3.5 py-3 transition-colors duration-150 active:scale-[0.98] ${
                i === highlight ? 'bg-accent/[0.14]' : ''
              }`}
              style={{
                animationDelay: `${Math.min(i, 6) * 30}ms`,
                animationFillMode: 'backwards',
                animationDuration: '0.18s',
              }}
            >
              <div className="flex flex-col gap-0.5">
                <span className="font-display text-[15px] font-bold text-slate-100">
                  {r.symbol}
                </span>
                <span className="text-xs text-muted">{r.name}</span>
              </div>
              <span className="text-[11px] tracking-wide text-muted">{r.exchange}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
