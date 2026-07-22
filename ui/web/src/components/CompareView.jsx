import { useEffect, useState } from 'react'
import { apiScore } from '../api'
import { CATEGORY_ORDER } from '../data/categoryMeta'
import { betaReading, LEVEL_TONE, rsiReading, varReading, volReading } from '../explain/readings'
import { useLanguage } from '../i18n/LanguageContext'
import { fmt, riskColor } from '../utils'

// Side-by-side comparison: one column per stock, one row per measure, so the
// same number sits on the same line across every stock. Stacking full
// dashboards (the default view) shows everything but makes "is AAPL's tail
// risk worse than Tencent's?" a scrolling memory test — this exists purely to
// make that read horizontal.
//
// Fetches each ticker's score independently so one failure degrades to a
// single "—" column instead of blanking the table.
export default function CompareView({ tickers, onRemove }) {
  const { t } = useLanguage()
  const [scores, setScores] = useState({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all(
      tickers.map((tk) =>
        apiScore(tk)
          .then((s) => [tk, s])
          .catch(() => [tk, null])
      )
    )
      .then((pairs) => {
        if (!cancelled) setScores(Object.fromEntries(pairs))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [tickers.join(',')]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return (
      <div className="panel mt-7 space-y-2 p-5">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="skeleton-shimmer animate-shimmer h-10 w-full rounded-lg" />
        ))}
      </div>
    )
  }

  // Metric rows below the factor rows: value + a deterministic level chip, the
  // same reading layer the single-stock card uses (explain/readings.js).
  const metricRows = [
    {
      key: 'vol30d',
      label: t('metrics.vol30d'),
      value: (s) => fmt(s.volatility_30d, 100, 1, '%'),
      level: (s) => volReading(s.volatility_30d),
    },
    {
      key: 'var95',
      label: t('metrics.var95'),
      value: (s) => fmt(s.var_95, 100, 2, '%'),
      level: (s) => varReading(s.var_95),
    },
    {
      key: 'beta',
      label: t('metrics.beta'),
      value: (s) => (s.beta != null ? (+s.beta).toFixed(2) : '—'),
      level: (s) => betaReading(s.beta != null ? +s.beta : null),
    },
    {
      key: 'rsi',
      label: t('metrics.rsi'),
      value: (s) => fmt(s.indicators?.rsi_14, 1, 1),
      level: (s) => rsiReading(s.indicators?.rsi_14),
    },
  ]

  const colWidth = 'min-w-[9rem]'

  return (
    <section className="panel animate-rise-in mt-7 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-border">
              <th className="sticky left-0 z-10 bg-surface/80 px-5 py-4 text-[0.65rem] font-semibold uppercase tracking-wide text-muted backdrop-blur">
                {t('compare.measure')}
              </th>
              {tickers.map((tk) => (
                <th key={tk} className={`px-4 py-4 ${colWidth}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-display text-base font-bold text-slate-100">{tk}</span>
                    <button
                      onClick={() => onRemove(tk)}
                      title={t('card.remove')}
                      className="text-xs leading-none text-muted transition hover:text-down"
                    >
                      ✕
                    </button>
                  </div>
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {/* Headline score */}
            <tr className="border-b border-border">
              <td className="sticky left-0 z-10 bg-surface/80 px-5 py-4 text-xs font-semibold text-slate-300 backdrop-blur">
                {t('compare.riskScore')}
              </td>
              {tickers.map((tk) => {
                const s = scores[tk]
                if (!s) {
                  return (
                    <td key={tk} className="px-4 py-4 text-sm text-muted">
                      {t('compare.unavailable')}
                    </td>
                  )
                }
                const color = riskColor(s.risk_label)
                return (
                  <td key={tk} className="px-4 py-4">
                    <div className="flex items-baseline gap-1.5">
                      <span
                        className="font-display text-2xl font-extrabold tabular-nums"
                        style={{ color }}
                      >
                        {Math.round(s.risk_score)}
                      </span>
                      <span className="text-[0.6rem] text-muted">/100</span>
                    </div>
                    <span
                      className="mt-1 inline-block rounded-full px-2 py-0.5 text-[0.55rem] font-bold uppercase tracking-wide"
                      style={{ color, background: `${color}22` }}
                    >
                      {t(`riskLabel.${s.risk_label}`)}
                    </span>
                  </td>
                )
              })}
            </tr>

            {/* The five risk factors, each on its own aligned row */}
            {CATEGORY_ORDER.map((cat) => (
              <tr key={cat} className="border-b border-border">
                <td className="sticky left-0 z-10 bg-surface/80 px-5 py-3 text-xs text-slate-300 backdrop-blur">
                  {t(`categories.${cat}.label`)}
                </td>
                {tickers.map((tk) => {
                  const c = scores[tk]?.risk_breakdown?.[cat]
                  if (!c || c.score == null) {
                    return (
                      <td key={tk} className="px-4 py-3 text-sm text-muted">
                        —
                      </td>
                    )
                  }
                  const color = riskColor(
                    c.score >= 75
                      ? 'EXTREME'
                      : c.score >= 50
                        ? 'HIGH'
                        : c.score >= 25
                          ? 'MODERATE'
                          : 'LOW'
                  )
                  return (
                    <td key={tk} className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span
                          className="font-display text-sm font-bold tabular-nums"
                          style={{ color }}
                        >
                          {Math.round(c.score)}
                        </span>
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
                          <div
                            className="h-full rounded-full transition-all duration-700"
                            style={{ width: `${c.score}%`, background: color }}
                          />
                        </div>
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}

            {/* Quant metrics with their deterministic level chips */}
            {metricRows.map((row) => (
              <tr key={row.key} className="border-b border-border last:border-b-0">
                <td className="sticky left-0 z-10 bg-surface/80 px-5 py-3 text-xs text-slate-300 backdrop-blur">
                  {row.label}
                </td>
                {tickers.map((tk) => {
                  const s = scores[tk]
                  if (!s) {
                    return (
                      <td key={tk} className="px-4 py-3 text-sm text-muted">
                        —
                      </td>
                    )
                  }
                  const lvl = row.level(s)
                  return (
                    <td key={tk} className="px-4 py-3">
                      <div className="text-sm font-bold tabular-nums text-slate-100">
                        {row.value(s)}
                      </div>
                      {lvl && (
                        <div
                          className={`mt-0.5 text-[0.55rem] font-bold uppercase tracking-wide ${
                            LEVEL_TONE[lvl] || 'text-muted'
                          }`}
                        >
                          {t(`readings.chip.${lvl}`)}
                        </div>
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="border-t border-border px-5 py-3 text-[0.62rem] leading-relaxed text-muted">
        {t('compare.note')}
      </p>
    </section>
  )
}
