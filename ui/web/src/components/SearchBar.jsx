import { useEffect, useRef, useState } from 'react'
import { apiSearch } from '../api'
import { useLanguage } from '../i18n/LanguageContext'
import { debounce } from '../utils'

// An A-share code is normalized to its Yahoo-style ticker, which is the only
// form the backend recognises:
// data/fetcher.py's _is_cn_ticker() tests for a .SS/.SZ *suffix*, so anything
// else is routed to yfinance and fails as an unknown symbol. The three shapes
// a user actually types are all accepted — bare `301189`, exchange-prefixed
// `SZ301189` (what Eastmoney/Futu display), and suffixed `301189.SZ` — plus
// `.SH` for Shanghai, which is the common way to write what Yahoo spells .SS.
//
// The exchange is derived from the code, not from whatever the user wrote:
// 6xxxxx is Shanghai (600/601/603 main board, 688 STAR) and everything else
// in the 6-digit space is Shenzhen (000 main board, 300/301 ChiNext), so a
// wrong prefix/suffix is corrected rather than trusted.
//
// A-share codes are always exactly 6 digits. Any other digit count has no
// A-share reading — Hong Kong listings are out of scope — so it passes
// through unchanged and is allowed to fail as the invalid ticker it is,
// rather than being silently rewritten into an unsupported market.
//
// Deliberately not gated on the market switcher. Keying this on
// `market === 'cn'` meant that typing SZ301189 while the switcher sat on its
// "US" default — the state every visitor starts in — skipped normalization
// entirely and sent the raw string to the backend, which is exactly how a user
// hits "no price data available for 'SZ301189'" while nothing on screen says
// the switcher was the problem. Nothing here can misfire on a US symbol: US
// listings are alphabetic, so no 6-digit numeric code has a US reading to lose.
const CN_CODE = /^(?:S[HZ])?(\d{6})(?:\.S[HZS])?$/

// Exchange qualifiers people paste in from other terminals: Bloomberg writes
// "GOOGL US", Wind/Choice and several screeners write "GOOGL.US". Both mean
// the plain US symbol, which is the only form Twelve Data and yfinance accept
// — left alone, they reach the backend as unknown symbols. Anchored to the end
// and requiring a separator, so real tickers containing "US" (USB, USO) and
// the symbol "US" itself are untouched.
const US_QUALIFIER = /[.\s]US$/

export function normalizeTicker(raw) {
  // NFKC first, before anything inspects the characters: a Chinese keyboard
  // defaults to a full-width IME, so "ＡＡＰＬ" and "３０１１８９" are ordinary
  // typing here, not an edge case, and neither matches any pattern below in
  // its raw form. (Full-width spaces need no special handling — JS trim()
  // already treats U+3000 as whitespace.)
  const v = raw.normalize('NFKC').trim().toUpperCase()
  // Internal spaces stripped so "SZ 301189" reads the same as "SZ301189";
  // no A-share code has a meaningful space in it. Tried before the US
  // qualifier because a 6-digit code can never carry one.
  const match = v.replace(/\s+/g, '').match(CN_CODE)
  if (match) {
    const code = match[1]
    return code + (code.startsWith('6') ? '.SS' : '.SZ')
  }
  return v.replace(/\s+/g, ' ').replace(US_QUALIFIER, '')
}

// Which market bucket an already-normalized ticker belongs to, or null when
// the symbol says nothing about it. Read by App.addStock rather than by this
// component, so every entry point that opens a card — the watchlist, the
// header's quick-open, the empty state — moves the switcher too, not just the
// search box. A switcher stuck on "US" above a Shanghai card is its own bug:
// it drives the placeholder copy and what the *next* search is read against.
export function marketForTicker(ticker) {
  return /\.S[SZ]$/.test(ticker.trim().toUpperCase()) ? 'cn' : null
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
      const v = normalizeTicker(query)
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
