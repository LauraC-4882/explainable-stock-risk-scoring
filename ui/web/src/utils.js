const RISK_COLORS = {
  LOW: '#3fb950',
  MODERATE: '#d29922',
  HIGH: '#f0883e',
  EXTREME: '#f85149',
}

export function riskColor(label) {
  return RISK_COLORS[label] || '#8b949e'
}

export function fmt(value, mul = 1, dp = 1, suffix = '') {
  if (value == null || Number.isNaN(value)) return '—'
  return (value * mul).toFixed(dp) + suffix
}

export function debounce(fn, ms) {
  let timer
  return (...args) => {
    clearTimeout(timer)
    timer = setTimeout(() => fn(...args), ms)
  }
}
