import { fmt } from '../utils'

export default function MetricTiles({ score }) {
  const rsi = score.indicators?.rsi_14
  const rsiClass = rsi > 70 ? 'text-down' : rsi < 30 ? 'text-up' : 'text-slate-100'

  return (
    <div className="grid grid-cols-4 divide-x divide-border border-b border-border">
      <Tile label="30d Vol" value={fmt(score.volatility_30d, 100, 1, '%')} />
      <Tile label="VaR 95%" value={fmt(score.var_95, 100, 2, '%')} valueClass="text-down" />
      <Tile label="Beta" value={score.beta != null ? (+score.beta).toFixed(2) : '—'} />
      <Tile label="RSI 14" value={fmt(rsi, 1, 1)} valueClass={rsiClass} />
    </div>
  )
}

function Tile({ label, value, valueClass = '' }) {
  return (
    <div className="px-3.5 py-2.5">
      <div className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-0.5 text-sm font-bold ${valueClass}`}>{value}</div>
    </div>
  )
}
