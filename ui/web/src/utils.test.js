import { describe, expect, it } from 'vitest'
import { fmt, inferMarket, riskColor, windowStats } from './utils'

const row = (date, close, risk_score = null) => ({ date, close, risk_score })

describe('windowStats', () => {
  it('returns null for input that cannot describe a window', () => {
    expect(windowStats([])).toBeNull()
    expect(windowStats(null)).toBeNull()
    expect(windowStats(undefined)).toBeNull()
    // Rows exist but none carries a price: there is no start/end/change to
    // report, and returning zeros here would render a flat, confident window.
    expect(windowStats([row('2026-01-02', null), row('2026-01-03', null)])).toBeNull()
  })

  it('reports the window from priced rows only, endpoints included', () => {
    const stats = windowStats([
      row('2026-01-01', null),
      row('2026-01-02', 100),
      row('2026-01-03', 120),
      row('2026-01-04', 90),
      row('2026-01-05', 110),
      row('2026-01-06', null),
    ])

    // Dates come from the priced rows, not the raw array — otherwise the
    // header would caption the window with a session whose price was excluded.
    expect(stats.start).toBe('2026-01-02')
    expect(stats.end).toBe('2026-01-05')
    expect(stats.sessions).toBe(4)
    expect(stats.priceChange).toBeCloseTo(0.1, 10)
    expect(stats.high).toBe(120)
    expect(stats.low).toBe(90)
    // Peak 120 -> trough 90 inside the window: -25%. The last close being
    // above the first must not hide the decline that happened between them.
    expect(stats.maxDrawdown).toBeCloseTo(-0.25, 10)
  })

  it('reports no drawdown for a monotonically rising window', () => {
    const stats = windowStats([row('2026-01-02', 10), row('2026-01-03', 12), row('2026-01-04', 15)])
    expect(stats.maxDrawdown).toBe(0)
    expect(stats.priceChange).toBeCloseTo(0.5, 10)
  })

  it('leaves risk fields null when no row carries a risk score', () => {
    // Regression: risks were previously reduced unguarded, so an all-warmup
    // (or degraded) window rendered a confident "0–0" risk range and an
    // average of 0 — the safest possible reading — for missing data.
    const stats = windowStats([row('2026-01-02', 100), row('2026-01-03', 105)])
    expect(stats.riskMin).toBeNull()
    expect(stats.riskMax).toBeNull()
    expect(stats.riskAvg).toBeNull()
  })

  it('summarises risk over the rows that do carry a score', () => {
    const stats = windowStats([
      row('2026-01-02', 100, 40),
      row('2026-01-03', 105, null),
      row('2026-01-04', 102, 60),
    ])
    expect(stats.riskMin).toBe(40)
    expect(stats.riskMax).toBe(60)
    expect(stats.riskAvg).toBe(50)
  })
})

describe('fmt', () => {
  it('renders an em dash for missing numbers rather than NaN', () => {
    expect(fmt(null)).toBe('—')
    expect(fmt(undefined)).toBe('—')
    expect(fmt(NaN)).toBe('—')
  })

  it('scales, rounds and suffixes', () => {
    expect(fmt(0.1234, 100, 2, '%')).toBe('12.34%')
    expect(fmt(0, 100, 2, '%')).toBe('0.00%')
  })
})

describe('riskColor', () => {
  it('gives each band its own colour and falls back for unknown labels', () => {
    const bands = ['LOW', 'MODERATE', 'HIGH', 'EXTREME'].map(riskColor)
    expect(new Set(bands).size).toBe(4)
    expect(riskColor(undefined)).toBe(riskColor('NOT_A_LABEL'))
  })
})

describe('inferMarket', () => {
  it('routes A-share suffixes to cn and everything else to us', () => {
    expect(inferMarket('600519.SS')).toBe('cn')
    expect(inferMarket('000001.SZ')).toBe('cn')
    expect(inferMarket('TSLA')).toBe('us')
  })
})
