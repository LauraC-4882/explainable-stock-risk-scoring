import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiGetWatchlist, apiScore, onTokenRefreshed } from './api'

// [R2] The backend cut JWT lifetime to 12 hours and re-issues a token in
// X-Refreshed-Token as expiry nears. If the frontend ignores that header, an
// active user is silently logged out mid-session — the exact regression these
// cover, and one that would otherwise only show up 12 hours into real use.

function jsonResponse(body, headers = {}) {
  return {
    ok: true,
    headers: { get: (name) => headers[name] ?? null },
    json: async () => body,
  }
}

describe('token refresh plumbing', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('notifies subscribers when the response carries a refreshed token', async () => {
    global.fetch = vi.fn(async () => jsonResponse([], { 'X-Refreshed-Token': 'new-token-abc' }))
    const seen = []
    const unsubscribe = onTokenRefreshed((t) => seen.push(t))

    await apiGetWatchlist('old-token')

    expect(seen).toEqual(['new-token-abc'])
    unsubscribe()
  })

  it('does not notify when the header is absent', async () => {
    global.fetch = vi.fn(async () => jsonResponse([]))
    const seen = []
    const unsubscribe = onTokenRefreshed((t) => seen.push(t))

    await apiGetWatchlist('old-token')

    expect(seen).toEqual([])
    unsubscribe()
  })

  it('still notifies on an error response', async () => {
    // A 4xx carries the header too, and still means the session is alive —
    // dropping the refresh here would expire an active session on the first
    // validation error the user happened to hit.
    global.fetch = vi.fn(async () => ({
      ok: false,
      headers: { get: (n) => (n === 'X-Refreshed-Token' ? 'refreshed-on-error' : null) },
      json: async () => ({ detail: 'nope' }),
    }))
    const seen = []
    const unsubscribe = onTokenRefreshed((t) => seen.push(t))

    await expect(apiGetWatchlist('old-token')).rejects.toThrow('nope')

    expect(seen).toEqual(['refreshed-on-error'])
    unsubscribe()
  })

  it('stops notifying after unsubscribe', async () => {
    global.fetch = vi.fn(async () => jsonResponse([], { 'X-Refreshed-Token': 'tok' }))
    const seen = []
    onTokenRefreshed((t) => seen.push(t))()

    await apiGetWatchlist('old-token')

    expect(seen).toEqual([])
  })
})

// A 503 from /api/score means the upstream market-data provider is throttling
// this server (app.py: UPSTREAM_UNAVAILABLE_DETAIL) — a known, retryable cause
// rather than a bug here. The card needs to know that to show translated copy
// instead of the backend's English sentence.
describe('apiScore error classification', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('tags a 503 with a translation key', async () => {
    global.fetch = vi.fn(async () => ({
      ok: false,
      status: 503,
      headers: { get: () => null },
      json: async () => ({ detail: 'Market data is temporarily unavailable — …' }),
    }))

    await expect(apiScore('AAPL')).rejects.toMatchObject({
      code: 'errors.upstreamUnavailable',
    })
  })

  it('leaves other failures untagged so their detail still surfaces verbatim', async () => {
    global.fetch = vi.fn(async () => ({
      ok: false,
      status: 404,
      headers: { get: () => null },
      json: async () => ({ detail: "No data returned for ticker 'ZZZZ'" }),
    }))

    const error = await apiScore('ZZZZ').catch((e) => e)
    expect(error.code).toBeUndefined()
    expect(error.message).toBe("No data returned for ticker 'ZZZZ'")
  })
})
