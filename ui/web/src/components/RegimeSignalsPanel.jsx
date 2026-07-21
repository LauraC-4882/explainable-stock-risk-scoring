import { ChartBar } from '@phosphor-icons/react'
import { useState } from 'react'
import { useLanguage } from '../i18n/LanguageContext'

// [G6] Collapsible panel for score.regime_technicals — the volatility regime,
// cyclical/defensive tilt, momentum-crash risk, trend state, and candlestick
// patterns.
//
// These signals carry weight 0 in risk_score (producers/regime_technicals.py:
// unvalidated signals must not move the headline number), and the panel says
// so in its intro rather than leaving a reader to assume the opposite from its
// prominence. Every block renders independently because each degrades
// independently — the VIX and sector legs need extra fetches and are US-only,
// while momentum/trend/patterns are pure price arithmetic and are always there.

const BAND_COLOR = {
  elevated: 'text-risk-extreme',
  moderate: 'text-risk-moderate',
  low: 'text-muted',
}

const TILT_COLOR = {
  cyclical: 'text-risk-high',
  defensive: 'text-emerald-400',
  balanced: 'text-muted',
}

function Row({ label, children }) {
  return (
    <div className="rounded-lg border border-border bg-surface2/50 p-3 transition-colors duration-150 hover:bg-surface2">
      <div className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">
        {label}
      </div>
      <div className="mt-1.5">{children}</div>
    </div>
  )
}

function Stat({ label, value, className = '' }) {
  return (
    <div className="flex flex-col">
      <span className="text-[0.65rem] text-muted">{label}</span>
      <span className={`font-mono text-sm font-semibold ${className}`}>{value}</span>
    </div>
  )
}

const signed = (n, digits = 1) =>
  n === null || n === undefined ? '—' : `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`

export default function RegimeSignalsPanel({ regimeTechnicals }) {
  const { t } = useLanguage()
  const [open, setOpen] = useState(false)

  const rt = regimeTechnicals
  if (!rt) return null
  const { regime, sector_tilt: tilt, trend, patterns, momentum } = rt
  // Nothing computed at all (e.g. every leg degraded) — render nothing rather
  // than an empty box promising information it doesn't have.
  if (!regime && !tilt && !trend && !patterns && !momentum) return null

  return (
    <div className="border-b border-border">
      <button
        onClick={() => setOpen((o) => !o)}
        className="group flex w-full items-center justify-between px-5 py-3 text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted transition-colors duration-150 hover:text-accent max-sm:text-[0.8rem]"
        aria-expanded={open}
      >
        <span className="inline-flex items-center gap-2">
          <span className="icon-badge h-7 w-7 transition-colors duration-150 group-hover:bg-accent/20">
            <ChartBar aria-hidden="true" size={16} />
          </span>
          {t('regimeSignals.toggle')}
        </span>
        <svg
          className={`h-3 w-3 flex-shrink-0 transition-transform duration-300 ease-out ${open ? 'rotate-180' : ''}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      <div
        className="grid transition-[grid-template-rows] duration-300 ease-in-out"
        style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
      >
        <div className="overflow-hidden">
          <div className="space-y-3 px-5 pb-4">
            <p className="text-sm leading-relaxed text-slate-300">{t('regimeSignals.intro')}</p>

            {regime && (
              <Row label={t('regimeSignals.regime.label')}>
                <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1.5">
                  <span
                    className={`font-mono text-sm font-bold ${
                      regime.state === 'risk_on' ? 'text-emerald-400' : 'text-risk-high'
                    }`}
                  >
                    {t(`regimeSignals.regime.${regime.state}`)}
                  </span>
                  <Stat
                    label={t('regimeSignals.regime.realized')}
                    value={`${regime.realized_vol_pct.toFixed(1)}%`}
                  />
                  <Stat
                    label={t('regimeSignals.regime.implied')}
                    value={`${regime.implied_vol_lagged_pct.toFixed(1)}%`}
                  />
                  {regime.persistence_21d !== null && (
                    <Stat
                      label={t('regimeSignals.regime.persistence')}
                      value={`${Math.round(regime.persistence_21d * 100)}%`}
                    />
                  )}
                </div>
              </Row>
            )}

            {momentum && (
              <Row label={t('regimeSignals.momentum.label')}>
                <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1.5">
                  <Stat label="1M" value={signed(momentum.momentum_1m_pct)} />
                  <Stat label="3M" value={signed(momentum.momentum_3m_pct)} />
                  <Stat label="12M" value={signed(momentum.momentum_12m_pct)} />
                  {momentum.crash_risk_band && (
                    <Stat
                      label={t('regimeSignals.momentum.crashRisk')}
                      value={t(`regimeSignals.momentum.band.${momentum.crash_risk_band}`)}
                      className={BAND_COLOR[momentum.crash_risk_band] || 'text-muted'}
                    />
                  )}
                  {momentum.vs_52w_high_pct !== null && (
                    <Stat
                      label={t('regimeSignals.momentum.vs52wHigh')}
                      value={signed(momentum.vs_52w_high_pct)}
                    />
                  )}
                </div>
              </Row>
            )}

            {tilt && (
              <Row label={t('regimeSignals.tilt.label')}>
                <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1.5">
                  <span
                    className={`font-mono text-sm font-bold ${TILT_COLOR[tilt.reading] || 'text-muted'}`}
                  >
                    {t(`regimeSignals.tilt.${tilt.reading}`)}
                  </span>
                  <Stat
                    label={t('regimeSignals.tilt.betaOn')}
                    value={tilt.beta_risk_on === null ? '—' : tilt.beta_risk_on.toFixed(2)}
                  />
                  <Stat
                    label={t('regimeSignals.tilt.betaOff')}
                    value={tilt.beta_risk_off === null ? '—' : tilt.beta_risk_off.toFixed(2)}
                  />
                </div>
              </Row>
            )}

            {trend && (
              <Row label={t('regimeSignals.trend.label')}>
                <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1.5">
                  <span
                    className={`font-mono text-sm font-bold ${
                      trend.state === 'above' ? 'text-emerald-400' : 'text-risk-moderate'
                    }`}
                  >
                    {t(`regimeSignals.trend.${trend.state}`)}
                  </span>
                  <Stat
                    label={t('regimeSignals.trend.window')}
                    value={`${trend.sma_window}d`}
                  />
                  <Stat
                    label={t('regimeSignals.trend.distance')}
                    value={signed(trend.distance_pct)}
                  />
                </div>
              </Row>
            )}

            {patterns && (
              <Row label={t('regimeSignals.patterns.label')}>
                {patterns.recent.length === 0 ? (
                  <p className="text-[0.7rem] text-muted">
                    {t('regimeSignals.patterns.none').replace(
                      '{days}',
                      patterns.lookback_days
                    )}
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {patterns.recent.map((p, i) => (
                      <span
                        key={`${p.name}-${p.date}-${i}`}
                        className="rounded-md border border-border bg-surface px-2 py-1 font-mono text-[0.65rem] text-slate-200"
                      >
                        {t(`regimeSignals.patterns.${p.name}`)}
                        <span className="ml-1.5 text-muted">{p.date}</span>
                      </span>
                    ))}
                  </div>
                )}
              </Row>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
