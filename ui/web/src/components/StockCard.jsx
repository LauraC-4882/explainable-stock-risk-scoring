import { CircleAlert, Star, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { apiScore, apiTimeseries } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useCountUp } from '../hooks/useCountUp'
import { useLanguage } from '../i18n/LanguageContext'
import { fmt, inferMarket, riskColor, windowStats } from '../utils'
import CardSkeleton from './CardSkeleton'
import KeyFactorTiles from './KeyFactorTiles'
import MetricTiles from './MetricTiles'
import MLSignalPanel from './MLSignalPanel'
import OutcomePanel from './OutcomePanel'
import PriceChart from './PriceChart'
import RiskChart from './RiskChart'
import RiskExplainer from './RiskExplainer'
import RiskGauge from './RiskGauge'
import RiskNote from './RiskNote'
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
  // Separate from `loading`: a timeframe switch refreshes only the
  // window-scoped sections, so the card must not fall back to the full
  // skeleton and throw away the score hero that isn't changing.
  const [tsLoading, setTsLoading] = useState(false)

  // Score — fires once per ticker. Deliberately NOT keyed on `period`: it
  // ranks against a fixed ~2y baseline, so it would come back identical for
  // every timeframe (see api.js: apiScore) at the cost of a full re-score.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    apiScore(ticker)
      .then((sc) => {
        if (!cancelled) setScore(sc)
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
  }, [ticker])

  // Timeseries — keyed on BOTH ticker and period, and with no early-out. An
  // earlier version fetched it alongside the score on mount and then bailed
  // (`if (!score) return`) on the period effect, which meant switching
  // timeframe while the first load was still in flight left the card showing
  // the mount-time window forever: the in-flight request had already closed
  // over the old period, and the period effect had declined to run. Harmless
  // when only the charts depended on the window; now that the section header
  // states the actual date range, it rendered a header that disagreed with
  // the data underneath it. One effect, both deps, no early-out.
  useEffect(() => {
    let cancelled = false
    setTsLoading(true)
    apiTimeseries(ticker, period)
      .then((ts) => {
        if (!cancelled) setTimeseries(ts)
      })
      .catch(() => {
        // Leave the previous window's data on screen rather than blanking the
        // section: the score hero above is still valid, and the header keeps
        // naming the range that's actually displayed.
      })
      .finally(() => {
        if (!cancelled) setTsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [ticker, period])

  const stats = useMemo(() => windowStats(timeseries), [timeseries])

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
              <CircleAlert aria-hidden="true" size={16} color="currentColor" /> {error}
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
                  <div className="mt-1 text-sm uppercase tracking-widest text-muted max-sm:text-[0.8rem] max-sm:tracking-wide">
                    {heroSub}
                  </div>
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

          <RiskNote score={score} />
        </div>
      </div>

      {/* ── Selected-timeframe section ──────────────────────────────────
          Everything from here down is scoped to the timeframe selector, and
          re-renders as a unit whenever it changes. The heading names the
          actual first and last session in the data below it — not just the
          "1M" label — because the real span depends on trading days,
          holidays and how much history the provider returned, so "1M" alone
          was never a reliable statement of what the charts covered. */}
      <div
        className={`mt-7 transition-opacity duration-200 ${tsLoading ? 'opacity-50' : 'opacity-100'}`}
      >
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-t border-border pt-4">
          <div className="heading-flourish text-base">
            {t('window.title', { ticker, period: t(`timeframe.${period}`) })}
          </div>
          <div className="font-mono text-[0.7rem] tabular-nums text-muted max-sm:text-[0.8rem]">
            {stats
              ? t('window.range', {
                  start: stats.start,
                  end: stats.end,
                  sessions: stats.sessions,
                })
              : t('card.fetching')}
          </div>
        </div>

        {stats && (
          <Panel delay={6} hover className="[&>div]:border-b-0">
            <WindowStats stats={stats} />
          </Panel>
        )}

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

// The figures that genuinely change with the timeframe. Kept visually and
// textually distinct from the score hero above: those numbers are ranked
// against a fixed ~2y baseline and read the same at every timeframe, so
// putting window-scoped figures beside them without saying so would imply the
// score itself moved when the user clicked "1M".
function WindowStats({ stats }) {
  const { t } = useLanguage()
  const up = stats.priceChange != null && stats.priceChange >= 0

  const items = [
    {
      key: 'priceChange',
      value: stats.priceChange == null ? '—' : fmt(stats.priceChange, 100, 2, '%'),
      tone: stats.priceChange == null ? 'text-slate-200' : up ? 'text-up' : 'text-down',
    },
    { key: 'high', value: fmt(stats.high, 1, 2) },
    { key: 'low', value: fmt(stats.low, 1, 2) },
    {
      key: 'maxDrawdown',
      value: fmt(stats.maxDrawdown, 100, 2, '%'),
      // Only tone it as a loss when there actually was one — a flat window
      // reads 0.00%, which isn't a decline and shouldn't render in red.
      tone: stats.maxDrawdown < 0 ? 'text-down' : undefined,
    },
    // riskMin/riskMax/riskAvg are null when no row in the window carried a
    // score (all-warmup rows, or a degraded response). Math.round(null) is 0,
    // so rendering these unguarded showed a confident "0–0" — the lowest
    // possible risk — for what is actually missing data.
    {
      key: 'riskRange',
      value:
        stats.riskMin == null || stats.riskMax == null
          ? '—'
          : `${Math.round(stats.riskMin)}–${Math.round(stats.riskMax)}`,
    },
    { key: 'riskAvg', value: stats.riskAvg == null ? '—' : Math.round(stats.riskAvg) },
  ]

  return (
    <div className="px-4 py-4 sm:px-5">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {items.map(({ key, value, tone }) => (
          <div key={key} className="panel-tile px-2.5 py-2">
            <div className="text-[0.62rem] uppercase tracking-wide text-muted max-sm:text-[0.74rem]">
              {t(`window.stat.${key}`)}
            </div>
            <div
              className={`mt-1 font-mono text-sm font-extrabold tabular-nums max-sm:text-base ${
                tone || 'text-slate-200'
              }`}
            >
              {value}
            </div>
          </div>
        ))}
      </div>
      <p className="mt-2.5 text-[0.68rem] leading-relaxed text-muted max-sm:text-[0.78rem]">
        {t('window.note')}
      </p>
    </div>
  )
}

// Icon-free on purpose: the serif-gradient flourish type IS the ornament.
function ChartLabel({ children }) {
  return <div className="heading-flourish mb-1.5 px-1 pt-1 text-base">{children}</div>
}
