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
import PriceChart from './PriceChart'
import RiskChart from './RiskChart'
import RiskExplainer from './RiskExplainer'
import RiskGauge from './RiskGauge'
import StressTestPanel from './StressTestPanel'
import TopAnalysisWidget from './TopAnalysisWidget'

export default function StockCard({ ticker, period, onRemove, index = 0 }) {
  const { t } = useLanguage()
  const { isFavorited, toggleFavorite } = useAuth()
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

  return (
    <div
      className="animate-fade-in relative overflow-hidden rounded-xl border border-border bg-surface transition-all duration-300 ease-out hover:-translate-y-0.5 hover:border-[#3b2a5e] hover:shadow-2xl hover:shadow-black/40"
      style={{ animationDelay: `${Math.min(index, 8) * 60}ms`, animationFillMode: 'backwards' }}
    >
      {/* Risk-colored top accent — a quiet "at a glance" signal before any
          number is even read, echoing the colored status rail on dashboard
          summary cards. */}
      <div
        className="h-[3px] w-full transition-colors duration-500"
        style={{ background: `linear-gradient(90deg, ${color}, ${color}00 130%)` }}
      />

      <div className="flex items-start justify-between border-b border-border px-4 py-3.5">
        <div>
          <div className="text-xl font-extrabold tracking-tight">{ticker}</div>
          <div className="mt-0.5 text-xs text-muted">{subtitle}</div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleToggleFavorite}
            disabled={favBusy}
            title={favorited ? t('watchlist.unfavorite') : t('watchlist.favorite')}
            className={`flex h-7 w-7 items-center justify-center rounded-full text-lg leading-none transition-all duration-150 hover:scale-110 hover:bg-surface2 active:scale-90 disabled:opacity-50 ${
              favorited ? 'text-yellow-400' : 'text-muted hover:text-yellow-400'
            }`}
          >
            {favorited ? '★' : '☆'}
          </button>
          <button
            onClick={() => onRemove(ticker)}
            title={t('card.remove')}
            className="flex h-7 w-7 items-center justify-center rounded-full text-base leading-none text-muted transition-all duration-150 hover:bg-down/10 hover:text-down active:scale-90"
          >
            ✕
          </button>
        </div>
      </div>

      {loading && <CardSkeleton />}

      {error && !loading && (
        <div className="animate-fade-in px-8 py-12 text-center text-sm text-down">⚠ {error}</div>
      )}

      {score && !loading && !error && (
        <div className="animate-fade-in">
          {/* Score hero (Riscore.dc): the 270° arc gauge carries the number
              itself, with the band pill + score caption beside it. A thin
              risk-colored top accent bar with a periodic light-sweep crowns
              the card. */}
          <div className="relative flex flex-wrap items-center gap-4 border-b border-border px-5 py-5 sm:gap-6">
            <div
              className="pointer-events-none absolute inset-x-0 top-0 h-[3px] overflow-hidden"
              style={{ background: color, boxShadow: `0 0 18px ${color}` }}
            >
              <div className="animate-sweep absolute inset-y-0 left-0 w-1/3 bg-gradient-to-r from-transparent via-white/90 to-transparent" />
            </div>
            <div className="flex-shrink-0">
              <RiskGauge score={animatedScore} color={color} size={180} />
            </div>
            <div className="min-w-0">
              <span
                className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-bold uppercase tracking-wide transition-colors duration-500"
                style={{ color, background: `${color}22`, border: `1px solid ${color}55` }}
              >
                <span
                  className="h-2 w-2 flex-shrink-0 rounded-full"
                  style={{ background: color, boxShadow: `0 0 10px ${color}` }}
                />
                {t(`riskLabel.${score.risk_label}`)}
              </span>
              <div className="mt-3.5 text-sm text-muted">{t('card.riskScoreLabel')}</div>
            </div>
          </div>

          <KeyFactorTiles breakdown={score.risk_breakdown} />

          <RiskExplainer riskLabel={score.risk_label} breakdown={score.risk_breakdown} />

          <StressTestPanel stressTest={score.stress_test} />

          <MLSignalPanel
            probability={score.ml_drawdown_probability}
            explanation={score.ml_drawdown_explanation}
          />

          <MetricTiles score={score} />

          <TopAnalysisWidget ticker={ticker} />

          <div className="space-y-3.5 px-4 py-4">
            <ChartPanel icon="📈" title={t('charts.price')}>
              <PriceChart timeseries={timeseries} color={color} />
            </ChartPanel>
            <ChartPanel icon="🩺" title={t('charts.riskScore')}>
              <RiskChart timeseries={timeseries} />
            </ChartPanel>
          </div>

          {score.risk_note && (
            <div className="border-t border-border px-4 py-2.5 text-[0.65rem] leading-relaxed text-muted">
              {score.risk_note}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ChartPanel({ icon, title, children }) {
  return (
    <div className="panel px-3 pb-2.5 pt-2.5">
      <div className="mb-1.5 flex items-center gap-1.5 text-[0.67rem] font-semibold uppercase tracking-wide text-muted">
        <span aria-hidden="true" className="text-[0.75rem] leading-none">
          {icon}
        </span>
        {title}
      </div>
      {children}
    </div>
  )
}
