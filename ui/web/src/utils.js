const RISK_COLORS = {
  LOW: '#34d399',
  MODERATE: '#fbbf24',
  HIGH: '#fb923c',
  EXTREME: '#f43f5e',
}

export function riskColor(label) {
  return RISK_COLORS[label] || '#9d7cb8'
}

export function fmt(value, mul = 1, dp = 1, suffix = '') {
  if (value == null || Number.isNaN(value)) return '—'
  return (value * mul).toFixed(dp) + suffix
}

// Mirrors the frontend's market grouping (see MarketSwitcher.jsx) — "cn" is
// mainland A-shares (Shanghai/Shenzhen); Hong Kong listings are out of scope.
// Used only for watchlist labeling; actual scoring always infers the real
// exchange from the ticker suffix on the backend (scorer.market_for_ticker).
export function inferMarket(ticker) {
  const upper = ticker.toUpperCase()
  if (upper.endsWith('.SS') || upper.endsWith('.SZ')) return 'cn'
  return 'us'
}

// Summary of the selected timeframe, derived entirely from the timeseries the
// card already fetched — no extra request, and it updates the instant the
// timeframe changes. Every figure here is genuinely window-scoped, unlike the
// composite score and its 21d/63d metrics, which are ranked against a fixed
// ~2y baseline and so read the same at every timeframe by design.
export function windowStats(timeseries) {
  if (!Array.isArray(timeseries) || timeseries.length === 0) return null

  // Filter to priced rows FIRST, then take the endpoints from that same set.
  // Reading the dates off the raw array while computing the change off a
  // separately-filtered close array would caption the window with a date whose
  // price wasn't one of the two the change was measured between.
  const priced = timeseries.filter((d) => d.close != null)
  if (priced.length === 0) return null

  const first = priced[0]
  const last = priced[priced.length - 1]
  const closes = priced.map((d) => d.close)
  const risks = timeseries.map((d) => d.risk_score).filter((r) => r != null)

  // Max peak-to-trough decline *within the window*, walked in order — not the
  // backend's rolling 63-day max_drawdown, which ignores the window entirely.
  let peak = closes[0]
  let maxDrawdown = 0
  for (const c of closes) {
    if (c > peak) peak = c
    const dd = c / peak - 1
    if (dd < maxDrawdown) maxDrawdown = dd
  }

  return {
    start: first.date,
    end: last.date,
    sessions: priced.length,
    priceChange: closes[0] ? closes[closes.length - 1] / closes[0] - 1 : null,
    high: Math.max(...closes),
    low: Math.min(...closes),
    maxDrawdown,
    riskMin: risks.length ? Math.min(...risks) : null,
    riskMax: risks.length ? Math.max(...risks) : null,
    riskAvg: risks.length ? risks.reduce((a, b) => a + b, 0) / risks.length : null,
  }
}

export function debounce(fn, ms) {
  let timer
  return (...args) => {
    clearTimeout(timer)
    timer = setTimeout(() => fn(...args), ms)
  }
}
