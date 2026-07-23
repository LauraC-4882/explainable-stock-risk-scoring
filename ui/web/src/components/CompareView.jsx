import { useEffect, useState } from 'react'
import {
  Legend,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { apiScore, apiTimeseries } from '../api'
import { CATEGORY_ORDER } from '../data/categoryMeta'
import RiskGauge from './RiskGauge'
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
  const [series, setSeries] = useState({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all(
      tickers.map((tk) =>
        Promise.all([
          apiScore(tk).catch(() => null),
          apiTimeseries(tk, '6mo').catch(() => null),
        ]).then(([s, ts]) => [tk, s, ts])
      )
    )
      .then((rows) => {
        if (cancelled) return
        setScores(Object.fromEntries(rows.map(([tk, s]) => [tk, s])))
        setSeries(Object.fromEntries(rows.map(([tk, , ts]) => [tk, ts])))
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

  // Fixed per-ticker palette (spec: primary / secondary / purple). Position in
  // the compare set — not the risk level — picks the colour, so the same stock
  // keeps its line/radar colour across sections.
  const TICKER_COLORS = ['#38bdf8', '#f59e0b', '#818cf8']
  const tickerColor = (tk) => TICKER_COLORS[tickers.indexOf(tk) % TICKER_COLORS.length]

  // Lowest composite gets the "lowest score" badge. Scores are self-relative
  // percentiles, so this is deliberately labelled lowest SCORE, never "safest"
  // — the note at the bottom of the table carries the full caveat.
  const scored = tickers.filter((tk) => scores[tk]?.risk_score != null)
  const lowestTicker =
    scored.length > 1
      ? scored.reduce((a, b) => (scores[a].risk_score <= scores[b].risk_score ? a : b))
      : null

  // Radar rows: one row per factor, one keyed value per ticker.
  const radarData = CATEGORY_ORDER.map((cat) => {
    const row = { factor: t(`categories.${cat}.short`) }
    for (const tk of tickers) {
      const v = scores[tk]?.risk_breakdown?.[cat]?.score
      if (v != null) row[tk] = v
    }
    return row
  })

  // Price overlay: each series rebased to % change from its own first close so
  // a $400 stock and a $40 stock share one axis. Merged on date.
  const priceData = (() => {
    const byDate = new Map()
    for (const tk of tickers) {
      const rows = series[tk]
      if (!Array.isArray(rows) || rows.length === 0) continue
      const base = rows.find((r) => r.close != null)?.close
      if (!base) continue
      for (const r of rows) {
        if (r.close == null) continue
        if (!byDate.has(r.date)) byDate.set(r.date, { date: r.date })
        byDate.get(r.date)[tk] = ((r.close - base) / base) * 100
      }
    }
    return [...byDate.values()].sort((a, b) => (a.date < b.date ? -1 : 1))
  })()

  const chartTooltip = {
    contentStyle: {
      background: 'rgba(9,21,37,0.95)',
      border: '1px solid rgba(56,189,248,0.2)',
      borderRadius: 8,
      fontSize: 11,
    },
    labelStyle: { color: '#9d7cb8' },
  }

  const colWidth = 'min-w-[9rem]'

  return (
    <section className="panel animate-rise-in mt-7 overflow-hidden">
      {/* ── Parallel gauges ── */}
      <div className="flex flex-wrap items-start justify-center gap-6 border-b border-border px-5 py-6">
        {tickers.map((tk) => {
          const s = scores[tk]
          if (!s) return null
          const color = riskColor(s.risk_label)
          const lowest = tk === lowestTicker
          return (
            <div
              key={tk}
              className={`flex flex-col items-center rounded-2xl border px-6 py-4 ${
                lowest ? 'border-up/50 bg-up/[0.05]' : 'border-transparent'
              }`}
            >
              <span className="font-display text-base font-bold text-slate-100">{tk}</span>
              <RiskGauge score={s.risk_score} color={color} size={132} />
              <span
                className="rounded-full px-2 py-0.5 text-[0.55rem] font-bold uppercase tracking-wide"
                style={{ color, background: `${color}22` }}
              >
                {t(`riskLabel.${s.risk_label}`)}
              </span>
              {lowest && (
                <span className="mt-1.5 rounded-full border border-up/50 px-2 py-0.5 text-[0.55rem] font-bold uppercase tracking-wide text-up">
                  {t('compare.lowestBadge')}
                </span>
              )}
            </div>
          )
        })}
      </div>

      {/* ── Factor radar + price overlay, side by side on wide screens ── */}
      <div className="grid gap-6 border-b border-border px-5 py-6 lg:grid-cols-2">
        <div>
          <h3 className="mb-1 text-[0.7rem] font-semibold uppercase tracking-wide text-muted">
            {t('compare.radarTitle')}
          </h3>
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData} outerRadius="72%">
                <PolarGrid stroke="rgba(56,189,248,0.14)" />
                <PolarAngleAxis dataKey="factor" tick={{ fill: '#9d7cb8', fontSize: 10 }} />
                <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                {tickers.map((tk) => (
                  <Radar
                    key={tk}
                    name={tk}
                    dataKey={tk}
                    stroke={tickerColor(tk)}
                    fill={tickerColor(tk)}
                    fillOpacity={0.12}
                    isAnimationActive={false}
                  />
                ))}
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Tooltip {...chartTooltip} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-1 text-[0.62rem] leading-relaxed text-muted">{t('compare.radarNote')}</p>
        </div>

        <div>
          <h3 className="mb-1 text-[0.7rem] font-semibold uppercase tracking-wide text-muted">
            {t('compare.priceTitle')}
          </h3>
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={priceData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <XAxis dataKey="date" hide />
                <YAxis
                  width={40}
                  tick={{ fill: '#9d7cb8', fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${v.toFixed(0)}%`}
                />
                <Tooltip
                  {...chartTooltip}
                  formatter={(value, name) => [`${Number(value).toFixed(1)}%`, name]}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {tickers.map((tk) => (
                  <Line
                    key={tk}
                    type="monotone"
                    dataKey={tk}
                    stroke={tickerColor(tk)}
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-1 text-[0.62rem] leading-relaxed text-muted">{t('compare.priceNote')}</p>
        </div>
      </div>

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
                  const rowScores = tickers
                    .map((k) => scores[k]?.risk_breakdown?.[cat]?.score)
                    .filter((v) => v != null)
                  const isLowest =
                    c?.score != null && rowScores.length > 1 && c.score === Math.min(...rowScores)
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
                    <td key={tk} className={`px-4 py-3 ${isLowest ? 'bg-up/[0.05]' : ''}`}>
                      <div className="flex items-center gap-2">
                        <span
                          className="font-display text-sm font-bold tabular-nums"
                          style={{ color }}
                        >
                          {Math.round(c.score)}
                        </span>
                        {isLowest && (
                          <span
                            className="rounded-full border border-up/40 px-1.5 text-[0.5rem] font-bold uppercase text-up"
                            title={t('compare.lowestBadge')}
                          >
                            ↓
                          </span>
                        )}
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
