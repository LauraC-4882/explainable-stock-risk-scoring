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

// ── Auth / watchlist ─────────────────────────────────────────────────────────

async function parseErrorOr(res, fallback) {
  if (res.ok) return res.json()
  const err = await res.json().catch(() => ({}))
  throw new Error(err.detail || fallback)
}

export async function apiRegister(email, password) {
  const res = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  return parseErrorOr(res, 'Registration failed')
}

export async function apiLogin(email, password) {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  return parseErrorOr(res, 'Login failed')
}

export async function apiMe(token) {
  const res = await fetch('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } })
  return parseErrorOr(res, 'Failed to fetch user')
}

export async function apiGetWatchlist(token) {
  const res = await fetch('/api/watchlist', { headers: { Authorization: `Bearer ${token}` } })
  return parseErrorOr(res, 'Failed to fetch watchlist')
}

export async function apiAddWatchlist(token, ticker, market, notes) {
  const res = await fetch('/api/watchlist', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ ticker, market, notes }),
  })
  return parseErrorOr(res, 'Failed to add to watchlist')
}

export async function apiRemoveWatchlist(token, itemId) {
  const res = await fetch(`/api/watchlist/${itemId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error('Failed to remove from watchlist')
}
