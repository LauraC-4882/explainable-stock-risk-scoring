import { useEffect, useState } from 'react'
import { apiScore, apiTimeseries } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useCountUp } from '../hooks/useCountUp'
import { useLanguage } from '../i18n/LanguageContext'
import { inferMarket, riskColor } from '../utils'
import CardSkeleton from './CardSkeleton'
import DirectionSignal from './DirectionSignal'
import MetricTiles from './MetricTiles'
import PriceChart from './PriceChart'
import RiskChart from './RiskChart'
import RiskExplainer from './RiskExplainer'
import RiskGauge from './RiskGauge'

const BADGE_CLASS = {
  LOW: 'bg-risk-low/15 text-risk-low',
  MODERATE: 'bg-risk-moderate/15 text-risk-moderate',
  HIGH: 'bg-risk-high/15 text-risk-high',
  EXTREME: 'bg-risk-extreme/15 text-risk-extreme',
}

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

  const last = timeseries.length ? timeseries[timeseries.length - 1] : null
  const upProb = last?.up_prob ?? 0.5
  const downProb = last?.down_prob ?? 0.5
  const color = score ? riskColor(score.risk_label) : '#8b949e'
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
      className="animate-fade-in overflow-hidden rounded-xl border border-border bg-surface transition-all duration-300 ease-out hover:-translate-y-0.5 hover:border-[#30363d] hover:shadow-2xl hover:shadow-black/40"
      style={{ animationDelay: `${Math.min(index, 8) * 60}ms`, animationFillMode: 'backwards' }}
    >
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
            className={`rounded-md px-1.5 py-0.5 text-lg leading-none transition-all duration-150 hover:scale-110 active:scale-90 disabled:opacity-50 ${
              favorited ? 'text-yellow-400' : 'text-muted hover:text-yellow-400'
            }`}
          >
            {favorited ? '★' : '☆'}
          </button>
          <button
            onClick={() => onRemove(ticker)}
            title={t('card.remove')}
            className="rounded-md px-1.5 py-0.5 text-base leading-none text-muted transition-all duration-150 hover:bg-down/10 hover:text-down active:scale-90"
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
          <div className="flex items-center gap-5 border-b border-border px-5 py-4">
            <RiskGauge score={animatedScore} color={color} />
            <div>
              <div className="text-[2.6rem] font-black leading-none tracking-tighter tabular-nums" style={{ color }}>
                {Math.round(animatedScore)}
              </div>
              <span
                className={`mt-1.5 inline-block rounded-full px-3 py-0.5 text-[0.72rem] font-bold uppercase tracking-wide transition-colors duration-500 ${
                  BADGE_CLASS[score.risk_label] || 'bg-muted/10 text-muted'
                }`}
              >
                {t(`riskLabel.${score.risk_label}`)}
              </span>
              <div className="mt-1.5 text-[0.72rem] text-muted">{t('card.riskScoreLabel')}</div>
            </div>
          </div>

          <RiskExplainer riskLabel={score.risk_label} breakdown={score.risk_breakdown} />

          <DirectionSignal upProb={upProb} downProb={downProb} />
          <MetricTiles score={score} />

          <div className="space-y-3.5 px-4 py-4">
            <div>
              <ChartLabel>{t('charts.price')}</ChartLabel>
              <PriceChart timeseries={timeseries} color={color} />
            </div>
            <div>
              <ChartLabel>{t('charts.riskScore')}</ChartLabel>
              <RiskChart timeseries={timeseries} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ChartLabel({ children }) {
  return (
    <div className="mb-1.5 text-[0.67rem] font-semibold uppercase tracking-wide text-muted">
      {children}
    </div>
  )
}
