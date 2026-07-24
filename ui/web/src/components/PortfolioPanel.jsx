import { ChartPie, Plus, Trash2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { apiPortfolioRisk } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import { fmt } from '../utils'

// Portfolio risk attribution — the component-VaR/HHI library surfaced as a
// page. The panel answers one question the single-stock card cannot: WHERE
// does a small book's risk actually come from? The largest position is
// frequently not the largest risk contributor, and the whole point of the
// Euler decomposition is to show that.
//
// Concentration flags are derived CLIENT-side from the returned numbers, with
// localized copy — the backend deliberately returns no English alert strings
// (the audited stress-narrative leak class). Thresholds mirror
// portfolio/aggregate.concentration_alerts: a position is flagged when its
// risk share exceeds max(25%, 1.5x its fair share 100/N), and the book when
// effective N < 3. Worded as observations, never instructions — describing a
// measurement is not recommending a trade.

const MAX_POSITIONS = 5

export function concentrationFlags(data) {
  if (!data) return []
  const flags = []
  const entries = Object.entries(data.risk_contribution_pct || {})
  const n = entries.length
  if (n === 0) return flags
  const bar = Math.max(25, (1.5 * 100) / n)
  for (const [ticker, pct] of entries) {
    if (pct > bar) flags.push({ type: 'position', ticker, pct: Math.round(pct) })
  }
  if (data.effective_n != null && data.effective_n < 3) {
    flags.push({ type: 'effectiveN', value: data.effective_n.toFixed(1) })
  }
  return flags
}

export default function PortfolioPanel() {
  const { t } = useLanguage()
  const { portfolioPanelOpen, closePortfolioPanel } = useAuth()
  const [rows, setRows] = useState([
    { ticker: '', weight: '' },
    { ticker: '', weight: '' },
  ])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [data, setData] = useState(null)
  const closeRef = useRef(null)

  useEffect(() => {
    if (!portfolioPanelOpen) return undefined
    closeRef.current?.focus()
    const onKey = (e) => {
      if (e.key === 'Escape') closePortfolioPanel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [portfolioPanelOpen, closePortfolioPanel])

  if (!portfolioPanelOpen) return null

  const filled = rows.filter((r) => r.ticker.trim() && Number(r.weight) > 0)
  const canAnalyze = filled.length >= 2 && !busy

  function setRow(i, key, value) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, [key]: value } : r)))
  }

  async function analyze() {
    if (!canAnalyze) return
    setBusy(true)
    setError(null)
    try {
      const result = await apiPortfolioRisk(
        filled.map((r) => ({ ticker: r.ticker.trim().toUpperCase(), weight: Number(r.weight) }))
      )
      setData(result)
    } catch (err) {
      setData(null)
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const contributions = data
    ? Object.entries(data.risk_contribution_pct).sort((a, b) => b[1] - a[1])
    : []
  const topTicker = contributions[0]?.[0]
  const flags = concentrationFlags(data)

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      style={{ animationDuration: '0.15s' }}
      onClick={closePortfolioPanel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="portfolio-title"
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[88vh] w-full max-w-2xl animate-fade-in flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-black/50"
        style={{ animationDuration: '0.2s' }}
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2
            id="portfolio-title"
            className="flex items-center gap-2 text-lg font-bold text-slate-100"
          >
            <ChartPie aria-hidden="true" size={18} />
            {t('portfolio.title')}
          </h2>
          <button
            ref={closeRef}
            onClick={closePortfolioPanel}
            aria-label={t('replay.close')}
            className="rounded-md px-1.5 py-0.5 text-base leading-none text-muted transition hover:bg-down/10 hover:text-down"
          >
            <X aria-hidden="true" size={14} color="currentColor" />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5 sm:px-8">
          <p className="text-[0.8rem] leading-relaxed text-muted">{t('portfolio.intro')}</p>

          {/* Position inputs */}
          <div className="space-y-2">
            {rows.map((row, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  value={row.ticker}
                  onChange={(e) => setRow(i, 'ticker', e.target.value)}
                  placeholder={t('portfolio.tickerPlaceholder')}
                  maxLength={12}
                  aria-label={t('portfolio.tickerAria', { n: i + 1 })}
                  className="w-32 rounded-lg border border-border bg-surface2/60 px-2.5 py-1.5 text-sm font-bold uppercase text-slate-100 placeholder:font-normal placeholder:normal-case placeholder:text-muted focus:border-accent focus:outline-none"
                />
                <input
                  value={row.weight}
                  onChange={(e) => setRow(i, 'weight', e.target.value.replace(/[^0-9.]/g, ''))}
                  placeholder={t('portfolio.weightPlaceholder')}
                  inputMode="decimal"
                  aria-label={t('portfolio.weightAria', { n: i + 1 })}
                  className="w-24 rounded-lg border border-border bg-surface2/60 px-2.5 py-1.5 text-sm tabular-nums text-slate-100 placeholder:text-muted focus:border-accent focus:outline-none"
                />
                {rows.length > 2 && (
                  <button
                    onClick={() => setRows((prev) => prev.filter((_, idx) => idx !== i))}
                    aria-label={t('portfolio.removeRow', { n: i + 1 })}
                    className="rounded-md p-1 text-muted transition hover:text-down"
                  >
                    <Trash2 aria-hidden="true" size={14} />
                  </button>
                )}
              </div>
            ))}
            <div className="flex items-center gap-3">
              {rows.length < MAX_POSITIONS && (
                <button
                  onClick={() => setRows((prev) => [...prev, { ticker: '', weight: '' }])}
                  className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1 text-[0.72rem] font-semibold text-muted transition hover:text-slate-200"
                >
                  <Plus aria-hidden="true" size={12} /> {t('portfolio.addRow')}
                </button>
              )}
              <button
                onClick={analyze}
                disabled={!canAnalyze}
                className="rounded-full bg-accent px-4 py-1.5 text-xs font-bold text-white shadow-lg shadow-accent/20 transition-all duration-150 hover:brightness-110 active:scale-95 disabled:opacity-50"
              >
                {busy ? t('portfolio.analyzing') : t('portfolio.analyze')}
              </button>
            </div>
            <p className="text-[0.68rem] text-muted">{t('portfolio.weightsNote')}</p>
          </div>

          {error && (
            <p role="alert" className="text-xs text-down">
              {error}
            </p>
          )}

          {data && (
            <>
              {/* Headline metrics */}
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                {[
                  ['vol', fmt(data.volatility, 100, 1, '%')],
                  ['var', fmt(data.var_95, 100, 2, '%')],
                  ['cvar', fmt(data.cvar_95, 100, 2, '%')],
                  ['effectiveN', data.effective_n?.toFixed(1)],
                ].map(([key, value]) => (
                  <div key={key} className="panel-tile px-3 py-2.5 text-center">
                    <div className="font-display text-lg font-bold tabular-nums text-accent2">
                      {value}
                    </div>
                    <div className="mt-0.5 text-[0.62rem] leading-snug text-muted">
                      {t(`portfolio.metrics.${key}`)}
                    </div>
                  </div>
                ))}
              </div>

              {/* Attribution bars — the point of the page */}
              <div>
                <h3 className="mb-2 text-[0.7rem] font-semibold uppercase tracking-wide text-muted">
                  {t('portfolio.contributionTitle')}
                </h3>
                <div className="space-y-2">
                  {contributions.map(([ticker, pct]) => (
                    <div key={ticker}>
                      <div className="mb-0.5 flex items-baseline justify-between text-[0.75rem]">
                        <span className="font-bold text-slate-100">
                          {ticker}
                          {ticker === topTicker && (
                            <span className="ml-1.5 rounded-full border border-gold/50 bg-gold/10 px-1.5 py-px text-[0.55rem] font-bold uppercase text-gold">
                              {t('portfolio.topContributor')}
                            </span>
                          )}
                        </span>
                        <span className="font-mono text-slate-300">{pct.toFixed(1)}%</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-surface2">
                        <div
                          className="h-full rounded-full bg-accent"
                          style={{ width: `${Math.min(100, pct)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
                <p className="mt-1.5 text-[0.64rem] leading-relaxed text-muted">
                  {t('portfolio.contributionNote')}
                </p>
              </div>

              {/* Localized concentration observations */}
              {flags.length > 0 && (
                <div className="rounded-xl border border-gold/30 bg-gold/[0.06] px-4 py-3">
                  <ul className="space-y-1 text-[0.76rem] leading-relaxed text-slate-300">
                    {flags.map((f, i) => (
                      <li key={i}>
                        {f.type === 'position'
                          ? t('portfolio.flagPosition', { ticker: f.ticker, pct: f.pct })
                          : t('portfolio.flagEffectiveN', { value: f.value })}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="text-[0.66rem] italic leading-relaxed text-muted">
                {t('portfolio.disclaimer')}
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
