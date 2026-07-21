import { Star, WarningCircle, X } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { apiScore, apiTimeseries } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useCountUp } from '../hooks/useCountUp'
import { useLanguage } from '../i18n/LanguageContext'
import { inferMarket, riskColor } from '../utils'
import CardSkeleton from './CardSkeleton'
import KeyFactorTiles from './KeyFactorTiles'
import MetricTiles from './MetricTiles'
import MLSignalPanel from './MLSignalPanel'
import OutcomePanel from './OutcomePanel'
import PriceChart from './PriceChart'
import RegimeSignalsPanel from './RegimeSignalsPanel'
import RiskChart from './RiskChart'
import RiskExplainer from './RiskExplainer'
import RiskGauge from './RiskGauge'
import RiskRadar from './RiskRadar'
import StressTestPanel from './StressTestPanel'
import TopAnalysisWidget from './TopAnalysisWidget'

// Every tracked stock renders as the full two-column bento dashboard
// (Riscore.dc mockup): score hero + factor tiles on the left, metrics/
// explainers/community rail on the right, charts side by side across the
// bottom. Comparing stocks stacks these dashboards vertically (see
// App.jsx) instead of shrinking them into cramped side-by-side cards.
export default function StockCard({ ticker, period, onRemove, index = 0 }) {
  const { t } = useLanguage()
  const { isFavorited, toggleFavorite, openCommunityPanel } = useAuth()
  const [favBusy, setFavBusy] = useState(false)
  const [score, setScore] = useState(null)
  const [timeseries, setTimeseries] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  // Initial load — fires once per ticker.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([apiScore(ticker), apiTimeseries(ticker, period)])
      .then(([sc, ts]) => {
        if (cancelled) return
        setScore(sc)
        setTimeseries(ts)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker])

  // Timeframe change — refresh the timeseries only, without a full reload.
  useEffect(() => {
    if (!score) return
    let cancelled = false
    apiTimeseries(ticker, period)
      .then((ts) => {
        if (!cancelled) setTimeseries(ts)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period])

  const color = score ? riskColor(score.risk_label) : '#9d7cb8'
  const subtitle =
    score?.name && score.name !== ticker
      ? score.name + (score.fundamentals?.sector ? ` · ${score.fundamentals.sector}` : '')
      : score?.fundamentals?.sector || (loading ? t('card.fetching') : ticker)
  const animatedScore = useCountUp(score?.risk_score)
  const favorited = isFavorited(ticker)

  async function handleToggleFavorite() {
    if (favBusy) return
    setFavBusy(true)
    try {
      await toggleFavorite(ticker, inferMarket(ticker))
    } finally {
      setFavBusy(false)
    }
  }

  const headerButtons = (
    <div className="flex items-center gap-1">
      <button
        onClick={handleToggleFavorite}
        disabled={favBusy}
        title={favorited ? t('watchlist.unfavorite') : t('watchlist.favorite')}
        className="flex h-8 w-8 items-center justify-center rounded-lg border border-border transition-all duration-150 hover:scale-110 hover:bg-surface2 active:scale-90 disabled:opacity-50"
      >
        <Star
          size={16}
          weight={favorited ? 'fill' : 'thin'}
          color={favorited ? '#fbbf24' : undefined}
        />
      </button>
      <button
        onClick={() => onRemove(ticker)}
        title={t('card.remove')}
        className="flex h-8 w-8 items-center justify-center rounded-lg border border-border transition-all duration-150 hover:bg-down/10 active:scale-90"
      >
        <X size={14} />
      </button>
    </div>
  )

  // Loading / error keep the same floating-panel shell so the swap into
  // the full bento grid doesn't visually jump.
  if (loading || error || !score) {
    return (
      <div
        className="animate-fade-in"
        style={{ animationDelay: `${Math.min(index, 4) * 90}ms`, animationFillMode: 'backwards' }}
      >
        <div className="panel overflow-hidden">
          <div className="flex items-start justify-between px-6 pb-0 pt-5">
            <div>
              <div className="font-display text-2xl font-bold tracking-tight">{ticker}</div>
              <div className="mt-0.5 text-xs text-muted">{subtitle}</div>
            </div>
            {headerButtons}
          </div>
          {loading && <CardSkeleton />}
          {error && !loading && (
            <div className="animate-fade-in flex items-center justify-center gap-1.5 px-8 py-12 text-sm text-down">
              <WarningCircle aria-hidden="true" size={16} color="currentColor" /> {error}
            </div>
          )}
        </div>
      </div>
    )
  }

  // In the hero the company name carries the heading (the mockup's
  // "Apple Inc." treatment) with ticker · sector as the eyebrow line.
  const heroTitle = score.name && score.name !== ticker ? score.name : ticker
  const heroSub =
    score.name && score.name !== ticker
      ? `${ticker}${score.fundamentals?.sector ? ` · ${score.fundamentals.sector}` : ''}`
      : score.fundamentals?.sector || ticker

  return (
    <div
      className="animate-fade-in"
      style={{ animationDelay: `${Math.min(index, 4) * 90}ms`, animationFillMode: 'backwards' }}
    >
      <div className="grid items-start gap-5 lg:grid-cols-[13fr_11fr]">
        {/* ── Left column ─────────────────────────────────────────── */}
        <div className="space-y-5">
          {/* Hero keeps overflow-hidden: its nebula wash + sweeping accent
              bar must clip to the rounded corners, and it hosts no floating
              tooltips that clipping could truncate. */}
          <Panel delay={0} className="relative overflow-hidden">
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 transition-all duration-700"
              style={{
                background: `radial-gradient(560px 300px at 18% 0%, ${color}1f, transparent 70%)`,
              }}
            />
            <div
              className="pointer-events-none absolute inset-x-0 top-0 h-[3px] overflow-hidden"
              style={{ background: color, boxShadow: `0 0 18px ${color}` }}
            >
              <div className="animate-sweep absolute inset-y-0 left-0 w-1/3 bg-gradient-to-r from-transparent via-white/90 to-transparent" />
            </div>

            <div className="relative px-6 pb-6 pt-6">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="font-display text-3xl font-bold tracking-tight text-slate-100 max-sm:text-2xl sm:truncate">
                    {heroTitle}
                  </h2>
                  <div className="mt-1 text-sm uppercase tracking-widest text-muted max-sm:text-[0.8rem] max-sm:tracking-wide">{heroSub}</div>
                </div>
                {headerButtons}
              </div>

              <div className="mt-5 flex flex-wrap items-center gap-6 sm:gap-9">
                <div className="animate-floaty flex-shrink-0">
                  <RiskGauge score={animatedScore} color={color} size={210} />
                </div>
                <div className="min-w-0 max-w-md">
                  <span
                    className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-bold uppercase tracking-wide transition-colors duration-500"
                    style={{ color, background: `${color}22`, border: `1px solid ${color}55` }}
                  >
                    <span
                      className="animate-glow-pulse h-2 w-2 flex-shrink-0 rounded-full"
                      style={{ background: color, boxShadow: `0 0 10px ${color}` }}
                    />
                    {t(`riskLabel.${score.risk_label}`)}
                  </span>
                  <div className="mt-3 text-sm text-muted">{t('card.riskScoreLabel')}</div>
                  <p className="mt-3 text-sm leading-relaxed text-slate-300">
                    {t(`labelExplanation.${score.risk_label}`)}
                  </p>
                </div>
                {/* Radar re-visualizes the five category scores in the hero's
                    spare width; on narrow layouts it wraps below the text. */}
                <div className="animate-fade-in flex-shrink-0 sm:ml-auto">
                  <RiskRadar breakdown={score.risk_breakdown} color={color} />
                </div>
              </div>
            </div>
          </Panel>

          <Panel delay={1} hover className="[&>div]:border-b-0">
            <KeyFactorTiles breakdown={score.risk_breakdown} />
          </Panel>
        </div>

        {/* ── Right column ────────────────────────────────────────── */}
        <div className="space-y-4">
          {/* MetricTiles keeps overflow-hidden (its bg fill must clip to the
              rounded corners; its readings expand inline, nothing floats).
              The explainer panels don't: RiskExplainer hosts hover
              tooltips that must be free to float past the panel edge
              instead of being truncated at it. */}
          <Panel delay={1} hover className="overflow-hidden [&>div]:border-b-0">
            <MetricTiles score={score} />
          </Panel>

          <Panel delay={2} hover className="[&>div]:border-b-0">
            <RiskExplainer
              riskLabel={score.risk_label}
              breakdown={score.risk_breakdown}
              defaultOpen
            />
          </Panel>

          <Panel delay={3} hover className="[&>div]:border-b-0">
            <StressTestPanel stressTest={score.stress_test} />
          </Panel>

          <Panel delay={4} hover className="[&>div]:border-b-0">
            <OutcomePanel ticker={ticker} />
          </Panel>

          <Panel delay={5} hover className="[&>div]:border-b-0">
            <MLSignalPanel
              probability={score.ml_drawdown_probability}
              explanation={score.ml_drawdown_explanation}
            />
          </Panel>

          {/* [G6] Regime/technical context. Sits directly after the ML signal
              because both are secondary, weight-0 reads — everything above
              this point feeds the headline score, nothing from here down
              does. Shares delay 5 so the two secondary panels animate in
              together rather than stretching the stagger by another beat. */}
          <Panel delay={5} hover className="[&>div]:border-b-0">
            <RegimeSignalsPanel regimeTechnicals={score.regime_technicals} />
          </Panel>

          <Panel delay={6} hover>
            <div className="[&>div]:border-b-0">
              <TopAnalysisWidget ticker={ticker} />
            </div>
            <div className="px-4 pb-4 sm:px-5">
              <button
                onClick={() => openCommunityPanel(ticker)}
                className="btn-cta w-full rounded-xl py-2.5 text-sm font-bold transition-all duration-200 active:scale-[0.98]"
              >
                {t('community.shareCta')}
              </button>
            </div>
          </Panel>

          {score.risk_note && (
            <p
              className="animate-rise-in px-1 text-[0.7rem] leading-relaxed text-muted"
              style={{ animationDelay: '360ms', animationFillMode: 'backwards' }}
            >
              {score.risk_note}
            </p>
          )}
        </div>
      </div>

      {/* ── Charts row, full width ──────────────────────────────────── */}
      <div className="mt-5 grid gap-5 md:grid-cols-2">
        <Panel delay={6} hover className="px-3 pb-2.5 pt-2.5">
          <ChartLabel>{t('charts.price')}</ChartLabel>
          <PriceChart timeseries={timeseries} color={color} />
        </Panel>
        <Panel delay={7} hover className="px-3 pb-2.5 pt-2.5">
          <ChartLabel>{t('charts.riskScore')}</ChartLabel>
          <RiskChart timeseries={timeseries} />
        </Panel>
      </div>
    </div>
  )
}

// Glass panel with a staggered entrance and (optionally) a hover lift —
// the bento layout's shared section chrome.
function Panel({ children, className = '', delay = 0, hover = false }) {
  return (
    <div
      className={`panel animate-rise-in ${
        hover
          ? 'transition-all duration-300 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-panel'
          : ''
      } ${className}`}
      style={{ animationDelay: `${delay * 60}ms`, animationFillMode: 'backwards' }}
    >
      {children}
    </div>
  )
}

// Icon-free on purpose: the serif-gradient flourish type IS the ornament.
function ChartLabel({ children }) {
  return <div className="heading-flourish mb-1.5 px-1 pt-1 text-base">{children}</div>
}
