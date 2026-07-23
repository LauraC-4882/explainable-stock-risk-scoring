import { Download, GitCompareArrows, Star } from 'lucide-react'
import { useEffect, useState } from 'react'
import { apiWatchlistOverview } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import { dateLocale, riskColor } from '../utils'

// Landing board for signed-in users: every watchlisted stock with its latest
// risk reading and how that reading moved since the previous one. Now also the
// jump-off for comparison (select 2-3 rows) and a CSV export of the readings.
//
// COLOR SEMANTICS — deliberately market-independent. A rising risk score is
// coloured as a warning (rose) and a falling one as calming (emerald) for US
// and China alike. The local red/green convention (US green-up, CN red-up) is
// a *price* convention: it encodes "gained value". A risk score has no such
// reading — "up" always means more turbulent — so inheriting the price
// convention would paint a worsening US stock green and read as good news.
function deltaTone(delta) {
  if (delta == null || delta === 0) return { cls: 'text-muted', arrow: '→' }
  return delta > 0
    ? { cls: 'text-risk-extreme', arrow: '▲' } // risk rose — warn
    : { cls: 'text-risk-low', arrow: '▼' } // risk fell — calmer
}

// Pure and exported for tests. 'added' preserves server order; risk/delta sort
// descending with unreadable rows (no score yet) sinking to the bottom rather
// than interleaving with real numbers.
export function sortRows(rows, mode) {
  const list = [...rows]
  const val = (v) => (v == null ? -Infinity : v)
  if (mode === 'risk') list.sort((a, b) => val(b.risk_score) - val(a.risk_score))
  if (mode === 'delta') list.sort((a, b) => val(b.delta) - val(a.delta))
  if (mode === 'ticker') list.sort((a, b) => a.ticker.localeCompare(b.ticker))
  return list
}

// CSV of the visible readings. First line is the board's own descriptive-not-
// advice note as a comment, same convention as the simulation reports — an
// exported file gets forwarded, and the caveat must travel with the numbers.
export function buildCsv(rows, note) {
  const header = 'ticker,risk_score,risk_label,delta,as_of'
  const body = rows.map((r) =>
    [r.ticker, r.risk_score ?? '', r.risk_label ?? '', r.delta ?? '', r.as_of ?? ''].join(',')
  )
  return [`# ${note}`, header, ...body].join('\n')
}

export default function WatchlistBoard({ onOpen, onCompare }) {
  const { t, lang } = useLanguage()
  const { token, watchlist } = useAuth()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [sort, setSort] = useState('added')
  const [selected, setSelected] = useState([])

  // Re-fetch whenever the watchlist itself changes (star toggled elsewhere),
  // so the board never shows a stock the user just removed.
  useEffect(() => {
    if (!token) return
    let cancelled = false
    setLoading(true)
    apiWatchlistOverview(token)
      .then((res) => {
        if (!cancelled) setRows(res || [])
      })
      .catch(() => {
        if (!cancelled) setRows([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [token, watchlist.length])

  if (!token || (!loading && rows.length === 0)) return null

  // `new Date('2026-07-20')` is parsed as UTC midnight, which then renders as
  // the *previous* day for any viewer west of UTC — an "as of" label that's
  // silently off by one defeats its own purpose. Appending a time component
  // makes it parse as local midnight instead, so the label matches the date
  // the reading is actually stamped with.
  const fmtDate = (iso) =>
    iso
      ? new Date(`${iso}T00:00:00`).toLocaleDateString(dateLocale(lang), {
          month: 'short',
          day: 'numeric',
        })
      : null

  const visible = sortRows(rows, sort)

  function toggleSelect(ticker) {
    setSelected((prev) =>
      prev.includes(ticker)
        ? prev.filter((tk) => tk !== ticker)
        : prev.length >= 3
          ? prev // compare caps at 3; a 4th selection is a no-op, not a silent drop
          : [...prev, ticker]
    )
  }

  function exportCsv() {
    const csv = buildCsv(visible, t('board.note'))
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `riscore-watchlist-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const sortPill = (mode, label) => (
    <button
      key={mode}
      onClick={() => setSort(mode)}
      aria-pressed={sort === mode}
      className={`rounded-full border px-2.5 py-0.5 text-[0.62rem] font-semibold transition ${
        sort === mode
          ? 'border-accent/50 bg-accent/10 text-accent'
          : 'border-border text-muted hover:text-slate-200'
      }`}
    >
      {label}
    </button>
  )

  return (
    <section className="panel animate-rise-in mt-6 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-5 py-4">
        <div className="flex items-center gap-2">
          <span className="icon-badge h-7 w-7 text-sm">
            <Star aria-hidden="true" size={15} />
          </span>
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate-100">
            {t('board.title')}
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {sortPill('added', t('board.sortAdded'))}
          {sortPill('risk', t('board.sortRisk'))}
          {sortPill('delta', t('board.sortDelta'))}
          {sortPill('ticker', t('board.sortTicker'))}
          <button
            onClick={exportCsv}
            title={t('board.exportCsv')}
            className="ml-1 inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-0.5 text-[0.62rem] font-semibold text-muted transition hover:text-slate-200"
          >
            <Download aria-hidden="true" size={11} /> CSV
          </button>
        </div>
      </div>

      {loading ? (
        <div className="space-y-2 p-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton-shimmer animate-shimmer h-12 w-full rounded-lg" />
          ))}
        </div>
      ) : (
        <div className="divide-y divide-border">
          {visible.map((row) => {
            const tone = deltaTone(row.delta)
            const color = row.risk_label ? riskColor(row.risk_label) : '#8b83a6'
            const checked = selected.includes(row.ticker)
            return (
              <div
                key={row.ticker}
                className="flex w-full items-center gap-3 px-5 py-3 transition-colors duration-150 hover:bg-accent/[0.06]"
              >
                {onCompare && (
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleSelect(row.ticker)}
                    aria-label={t('board.selectForCompare', { ticker: row.ticker })}
                    className="h-3.5 w-3.5 flex-shrink-0 accent-accent"
                  />
                )}
                <button onClick={() => onOpen(row.ticker)} className="min-w-0 flex-1 text-left">
                  <div className="font-display text-sm font-bold text-slate-100">{row.ticker}</div>
                  {row.as_of && (
                    <div className="mt-0.5 text-[0.62rem] text-muted">
                      {t('board.asOf')} {fmtDate(row.as_of)}
                    </div>
                  )}
                </button>

                {row.risk_score != null ? (
                  <>
                    <div className="flex items-baseline gap-1.5">
                      <span
                        className="font-display text-lg font-extrabold tabular-nums"
                        style={{ color }}
                      >
                        {Math.round(row.risk_score)}
                      </span>
                      <span className="text-[0.6rem] text-muted">/100</span>
                    </div>
                    <div
                      className={`w-20 text-right font-display text-sm font-bold tabular-nums ${tone.cls}`}
                    >
                      {row.delta == null ? (
                        <span className="text-[0.62rem] font-normal text-muted">
                          {t('board.firstReading')}
                        </span>
                      ) : (
                        <>
                          {tone.arrow} {row.delta > 0 ? '+' : ''}
                          {row.delta}
                        </>
                      )}
                    </div>
                  </>
                ) : (
                  <span className="text-[0.68rem] text-muted">{t('board.noReading')}</span>
                )}
              </div>
            )
          })}
        </div>
      )}

      {onCompare && selected.length >= 2 && (
        <div className="border-t border-border px-5 py-2.5">
          <button
            onClick={() => onCompare(selected)}
            className="inline-flex items-center gap-1.5 rounded-full border border-accent/50 bg-accent/10 px-3.5 py-1.5 text-[0.72rem] font-bold text-accent transition hover:bg-accent/20 active:scale-95"
          >
            <GitCompareArrows aria-hidden="true" size={13} />
            {t('board.compareSelected', { n: selected.length })}
          </button>
        </div>
      )}

      <p className="border-t border-border px-5 py-2.5 text-[0.62rem] leading-relaxed text-muted">
        {t('board.note')}
      </p>
    </section>
  )
}
