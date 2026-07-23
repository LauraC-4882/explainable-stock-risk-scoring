import { useReducedMotion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { apiTickerBar } from '../api'
import { useLanguage } from '../i18n/LanguageContext'
import MarketStatus from './MarketStatus'

// Header marquee: last close + day change for a fixed universe, plus the
// US/CN market-session chips.
//
// The data comes from /api/tickerbar, which reads the daily snapshot parquets
// — deliberately NOT per-ticker scoring calls, because a marquee is
// decoration and decoration must not fire nine multi-second scoring runs per
// page load. The trade-off is honesty about age: rows are as of the last
// daily refresh, so the bar labels its data date instead of implying a live
// feed.
//
// The scroll is a CSS keyframe on a duplicated track (the standard seamless
// marquee), pausing on hover and dropping to a static row entirely under
// prefers-reduced-motion.
export default function TickerBar() {
  const { t } = useLanguage()
  const reduced = useReducedMotion()
  const [entries, setEntries] = useState([])

  useEffect(() => {
    let cancelled = false
    apiTickerBar()
      .then((rows) => {
        if (!cancelled) setEntries(rows)
      })
      .catch(() => {}) // a failed marquee is just an absent marquee
    return () => {
      cancelled = true
    }
  }, [])

  if (entries.length === 0) {
    // Still render the session chips — they're clock-derived, not data-derived.
    return (
      <div className="flex items-center justify-end gap-3 border-b border-border/60 bg-black/20 px-4 py-1.5">
        <MarketStatus />
      </div>
    )
  }

  const asOf = entries[0]?.as_of
  const track = entries.map((e) => (
    <span key={e.ticker} className="mx-4 inline-flex items-baseline gap-1.5 whitespace-nowrap">
      <span className="text-[0.68rem] font-bold text-slate-200">{e.ticker}</span>
      <span className="font-mono text-[0.68rem] text-slate-300">{e.last}</span>
      <span
        className={`font-mono text-[0.66rem] font-bold ${
          e.change_pct > 0 ? 'text-up' : e.change_pct < 0 ? 'text-down' : 'text-muted'
        }`}
      >
        {e.change_pct > 0 ? '+' : ''}
        {e.change_pct}%
      </span>
    </span>
  ))

  return (
    <div className="flex items-center gap-3 border-b border-border/60 bg-black/20 px-4 py-1.5">
      <div
        className="relative min-w-0 flex-1 overflow-hidden"
        aria-hidden={reduced ? undefined : true}
      >
        {reduced ? (
          <div className="overflow-x-auto whitespace-nowrap">{track}</div>
        ) : (
          <div className="ticker-track flex w-max">
            {/* Two copies: the animation translates -50%, so the second copy
                slides seamlessly into the first's place. */}
            <div className="flex">{track}</div>
            <div className="flex" aria-hidden="true">
              {track}
            </div>
          </div>
        )}
      </div>
      {asOf ? (
        <span className="hidden whitespace-nowrap text-[0.6rem] text-muted sm:inline">
          {t('tickerBar.asOf', { date: asOf })}
        </span>
      ) : null}
      <MarketStatus />
    </div>
  )
}
