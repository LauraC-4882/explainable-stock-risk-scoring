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

export async function apiRegister(email, password, nickname, consent) {
  const res = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, nickname, consent }),
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

// ── Community platform ───────────────────────────────────────────────────────

function authHeader(token) {
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function apiListPosts(token, { ticker, sort = 'recent', limit = 20, offset = 0 } = {}) {
  const params = new URLSearchParams({ sort, limit: String(limit), offset: String(offset) })
  if (ticker) params.set('ticker', ticker)
  const res = await fetch(`/api/community/posts?${params}`, { headers: authHeader(token) })
  return parseErrorOr(res, 'Failed to load community posts')
}

export async function apiCreatePost(token, ticker, market, body) {
  const res = await fetch('/api/community/posts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader(token) },
    body: JSON.stringify({ ticker, market, body }),
  })
  return parseErrorOr(res, 'Failed to create post')
}

export async function apiDeletePost(token, postId) {
  const res = await fetch(`/api/community/posts/${postId}`, {
    method: 'DELETE',
    headers: authHeader(token),
  })
  if (!res.ok) throw new Error('Failed to delete post')
}

export async function apiVote(token, postId, value) {
  const res = await fetch(`/api/community/posts/${postId}/vote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader(token) },
    body: JSON.stringify({ value }),
  })
  return parseErrorOr(res, 'Failed to vote')
}

export async function apiRemoveVote(token, postId) {
  const res = await fetch(`/api/community/posts/${postId}/vote`, {
    method: 'DELETE',
    headers: authHeader(token),
  })
  if (!res.ok) throw new Error('Failed to remove vote')
}

export async function apiReportPost(token, postId, reason) {
  const res = await fetch(`/api/community/posts/${postId}/report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader(token) },
    body: JSON.stringify({ reason }),
  })
  return parseErrorOr(res, 'Failed to report post')
}

export async function apiLeaderboard({ sort = 'accuracy', limit = 25 } = {}) {
  const params = new URLSearchParams({ sort, limit: String(limit) })
  const res = await fetch(`/api/community/leaderboard?${params}`)
  return parseErrorOr(res, 'Failed to load leaderboard')
}

export async function apiMyPosts(token) {
  const res = await fetch('/api/community/me/posts', { headers: authHeader(token) })
  return parseErrorOr(res, 'Failed to load your posts')
}

export async function apiMyVotes(token) {
  const res = await fetch('/api/community/me/votes', { headers: authHeader(token) })
  return parseErrorOr(res, 'Failed to load your votes')
}

// ── Admin ─────────────────────────────────────────────────────────────────────

export async function apiAdminAnalytics(token) {
  const res = await fetch('/api/admin/analytics/summary', { headers: authHeader(token) })
  return parseErrorOr(res, 'Failed to load analytics')
}

export async function apiAdminListUsers(token, { q, bannedOnly, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (q) params.set('q', q)
  if (bannedOnly) params.set('banned_only', 'true')
  const res = await fetch(`/api/admin/users?${params}`, { headers: authHeader(token) })
  return parseErrorOr(res, 'Failed to load users')
}

export async function apiAdminBanUser(token, userId) {
  const res = await fetch(`/api/admin/users/${userId}/ban`, {
    method: 'POST',
    headers: authHeader(token),
  })
  return parseErrorOr(res, 'Failed to ban user')
}

export async function apiAdminUnbanUser(token, userId) {
  const res = await fetch(`/api/admin/users/${userId}/unban`, {
    method: 'POST',
    headers: authHeader(token),
  })
  return parseErrorOr(res, 'Failed to unban user')
}

export async function apiAdminListReports(token, { status = 'pending' } = {}) {
  const res = await fetch(`/api/admin/reports?status=${status}`, { headers: authHeader(token) })
  return parseErrorOr(res, 'Failed to load reports')
}

export async function apiAdminDismissReport(token, reportId) {
  const res = await fetch(`/api/admin/reports/${reportId}/dismiss`, {
    method: 'POST',
    headers: authHeader(token),
  })
  if (!res.ok) throw new Error('Failed to dismiss report')
}
