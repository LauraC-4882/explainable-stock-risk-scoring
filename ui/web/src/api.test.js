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

// The backend classifies every scoring failure into one of five codes
// (src/stock_risk/errors.py) and returns it as `error` in the body. apiScore
// turns that into an i18n key so the card shows translated copy instead of the
// backend's English sentence, plus a `retryable` flag the card uses to decide
// whether a retry button could possibly help.
describe('apiScore error classification', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  function failWith(status, body) {
    global.fetch = vi.fn(async () => ({
      ok: false,
      status,
      headers: { get: () => null },
      json: async () => body,
    }))
  }

  it.each([
    ['TICKER_NOT_FOUND', 404, 'errors.tickerNotFound'],
    ['INSUFFICIENT_DATA', 422, 'errors.insufficientData'],
    ['UPSTREAM_UNAVAILABLE', 503, 'errors.upstreamUnavailable'],
    ['CALCULATION_FAILED', 500, 'errors.calculationFailed'],
    ['DELISTED', 422, 'errors.delisted'],
  ])('maps %s to its own translation key', async (code, status, key) => {
    failWith(status, { error: code, message: 'english copy', status, ticker: 'AAPL' })

    const error = await apiScore('AAPL').catch((e) => e)
    expect(error.code).toBe(key)
    expect(error.errorCode).toBe(code)
    expect(error.status).toBe(status)
  })

  it('marks only the upstream outage retryable', async () => {
    // A misspelled symbol, a too-short history and a delisted name fail
    // identically on the second press — a retry button there would read as
    // "that was a fluke" and waste the user's time.
    for (const code of ['TICKER_NOT_FOUND', 'INSUFFICIENT_DATA', 'CALCULATION_FAILED', 'DELISTED']) {
      failWith(422, { error: code, message: 'x' })
      const error = await apiScore('AAPL').catch((e) => e)
      expect(error.retryable, code).toBe(false)
    }

    failWith(503, { error: 'UPSTREAM_UNAVAILABLE', message: 'x' })
    const outage = await apiScore('AAPL').catch((e) => e)
    expect(outage.retryable).toBe(true)
  })

  it('still recognises a 503 that carries no code', async () => {
    // A proxy or load balancer in front of this app answers with its own body;
    // the status alone still means the same thing, and this was the only
    // inference the pre-taxonomy client made.
    failWith(503, { detail: 'Service Unavailable' })

    const error = await apiScore('AAPL').catch((e) => e)
    expect(error.code).toBe('errors.upstreamUnavailable')
    expect(error.retryable).toBe(true)
  })

  it('falls back to the server message when there is no code to key off', async () => {
    failWith(404, { detail: 'Not Found' })

    const error = await apiScore('ZZZZ').catch((e) => e)
    expect(error.code).toBeNull()
    expect(error.message).toBe('Not Found')
  })
})
