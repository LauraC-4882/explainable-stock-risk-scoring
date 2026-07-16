export async function apiSearch(query) {
  const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`)
  return res.ok ? res.json() : []
}

export async function apiScore(ticker) {
  const res = await fetch(`/api/score/${ticker}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to fetch score')
  }
  return res.json()
}

export async function apiTimeseries(ticker, period) {
  const res = await fetch(`/api/score/${ticker}/timeseries?period=${period}`)
  if (!res.ok) throw new Error('Failed to fetch timeseries')
  return res.json()
}
