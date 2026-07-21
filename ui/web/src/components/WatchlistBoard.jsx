import { Star } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { apiWatchlistOverview } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import { riskColor } from '../utils'

// Landing board for signed-in users: every watchlisted stock with its latest
// risk reading and how that reading moved since the previous one.
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

export default function WatchlistBoard({ onOpen }) {
  const { t, lang } = useLanguage()
  const { token, watchlist } = useAuth()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

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
      ? new Date(`${iso}T00:00:00`).toLocaleDateString(lang === 'zh' ? 'zh-CN' : 'en-US', {
          month: 'short',
          day: 'numeric',
        })
      : null

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
        <p className="text-[0.68rem] text-muted">{t('board.subtitle')}</p>
      </div>

      {loading ? (
        <div className="space-y-2 p-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton-shimmer animate-shimmer h-12 w-full rounded-lg" />
          ))}
        </div>
      ) : (
        <div className="divide-y divide-border">
          {rows.map((row) => {
            const tone = deltaTone(row.delta)
            const color = row.risk_label ? riskColor(row.risk_label) : '#8b83a6'
            return (
              <button
                key={row.ticker}
                onClick={() => onOpen(row.ticker)}
                className="flex w-full items-center gap-3 px-5 py-3 text-left transition-colors duration-150 hover:bg-accent/[0.06]"
              >
                <div className="min-w-0 flex-1">
                  <div className="font-display text-sm font-bold text-slate-100">{row.ticker}</div>
                  {row.as_of && (
                    <div className="mt-0.5 text-[0.62rem] text-muted">
                      {t('board.asOf')} {fmtDate(row.as_of)}
                    </div>
                  )}
                </div>

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
                    <div className={`w-20 text-right font-display text-sm font-bold tabular-nums ${tone.cls}`}>
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
              </button>
            )
          })}
        </div>
      )}

      <p className="border-t border-border px-5 py-2.5 text-[0.62rem] leading-relaxed text-muted">
        {t('board.note')}
      </p>
    </section>
  )
}
