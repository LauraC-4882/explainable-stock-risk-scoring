import { useEffect, useState } from 'react'
import { apiScore, apiTimeseries } from '../api'
import { riskColor } from '../utils'
import DirectionSignal from './DirectionSignal'
import MetricTiles from './MetricTiles'
import PriceChart from './PriceChart'
import RiskChart from './RiskChart'
import RiskGauge from './RiskGauge'

const BADGE_CLASS = {
  LOW: 'bg-risk-low/15 text-risk-low',
  MODERATE: 'bg-risk-moderate/15 text-risk-moderate',
  HIGH: 'bg-risk-high/15 text-risk-high',
  EXTREME: 'bg-risk-extreme/15 text-risk-extreme',
}

export default function StockCard({ ticker, period, onRemove }) {
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
      : score?.fundamentals?.sector || (loading ? 'Fetching…' : ticker)

  return (
    <div className="animate-fade-in overflow-hidden rounded-xl border border-border bg-surface transition hover:border-[#30363d] hover:shadow-2xl hover:shadow-black/40">
      <div className="flex items-start justify-between border-b border-border px-4 py-3.5">
        <div>
          <div className="text-xl font-extrabold tracking-tight">{ticker}</div>
          <div className="mt-0.5 text-xs text-muted">{subtitle}</div>
        </div>
        <button
          onClick={() => onRemove(ticker)}
          title="Remove"
          className="rounded-md px-1.5 py-0.5 text-base leading-none text-muted transition hover:bg-down/10 hover:text-down"
        >
          ✕
        </button>
      </div>

      {loading && (
        <div className="flex items-center justify-center gap-2.5 px-8 py-12 text-sm text-muted">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-accent" />
          Loading live data…
        </div>
      )}

      {error && !loading && (
        <div className="px-8 py-12 text-center text-sm text-down">⚠ {error}</div>
      )}

      {score && !loading && !error && (
        <>
          <div className="flex items-center gap-5 border-b border-border px-5 py-4">
            <RiskGauge score={score.risk_score} color={color} />
            <div>
              <div className="text-[2.6rem] font-black leading-none tracking-tighter" style={{ color }}>
                {score.risk_score}
              </div>
              <span
                className={`mt-1.5 inline-block rounded-full px-3 py-0.5 text-[0.72rem] font-bold uppercase tracking-wide ${
                  BADGE_CLASS[score.risk_label] || 'bg-muted/10 text-muted'
                }`}
              >
                {score.risk_label}
              </span>
              <div className="mt-1.5 text-[0.72rem] text-muted">risk score out of 100</div>
            </div>
          </div>

          <DirectionSignal upProb={upProb} downProb={downProb} />
          <MetricTiles score={score} />

          <div className="space-y-3.5 px-4 py-4">
            <div>
              <ChartLabel>Price History</ChartLabel>
              <PriceChart timeseries={timeseries} color={color} />
            </div>
            <div>
              <ChartLabel>Daily Risk Score (0–100)</ChartLabel>
              <RiskChart timeseries={timeseries} />
            </div>
          </div>
        </>
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
