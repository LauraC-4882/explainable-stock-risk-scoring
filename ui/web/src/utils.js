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

// Mirrors the frontend's market grouping (see MarketSwitcher.jsx) — "cn"
// covers both A-shares and HK-listed tickers. Used only for watchlist
// labeling; actual scoring always infers the real exchange from the ticker
// suffix on the backend (scorer.market_for_ticker).
export function inferMarket(ticker) {
  const upper = ticker.toUpperCase()
  if (upper.endsWith('.HK') || upper.endsWith('.SS') || upper.endsWith('.SZ')) return 'cn'
  return 'us'
}

export function debounce(fn, ms) {
  let timer
  return (...args) => {
    clearTimeout(timer)
    timer = setTimeout(() => fn(...args), ms)
  }
}
