import { describe, expect, it } from 'vitest'
import { dateLocale } from '../utils'
import { buildCsv, sortRows } from './WatchlistBoard'

const rows = [
  { ticker: 'TSLA', risk_score: 67, risk_label: 'HIGH', delta: 3, as_of: '2026-07-22' },
  { ticker: 'AAPL', risk_score: 48, risk_label: 'MODERATE', delta: -2, as_of: '2026-07-22' },
  { ticker: 'NEWCO', risk_score: null, risk_label: null, delta: null, as_of: null },
  { ticker: 'MSFT', risk_score: 51, risk_label: 'HIGH', delta: 0, as_of: '2026-07-21' },
]

describe('sortRows', () => {
  it('preserves server order for "added"', () => {
    expect(sortRows(rows, 'added').map((r) => r.ticker)).toEqual([
      'TSLA', 'AAPL', 'NEWCO', 'MSFT',
    ])
  })

  it('sorts by risk descending with unreadable rows sinking to the bottom', () => {
    expect(sortRows(rows, 'risk').map((r) => r.ticker)).toEqual([
      'TSLA', 'MSFT', 'AAPL', 'NEWCO',
    ])
  })

  it('sorts by delta descending', () => {
    expect(sortRows(rows, 'delta').map((r) => r.ticker)).toEqual([
      'TSLA', 'MSFT', 'AAPL', 'NEWCO',
    ])
  })

  it('sorts alphabetically for ticker mode and never mutates its input', () => {
    const before = rows.map((r) => r.ticker)
    expect(sortRows(rows, 'ticker').map((r) => r.ticker)).toEqual([
      'AAPL', 'MSFT', 'NEWCO', 'TSLA',
    ])
    expect(rows.map((r) => r.ticker)).toEqual(before)
  })
})

describe('buildCsv', () => {
  it('leads with the caveat comment so the disclaimer travels with the file', () => {
    const csv = buildCsv(rows, 'Descriptive statistics, not advice.')
    const lines = csv.split('\n')
    expect(lines[0]).toBe('# Descriptive statistics, not advice.')
    expect(lines[1]).toBe('ticker,risk_score,risk_label,delta,as_of')
    expect(lines[2]).toBe('TSLA,67,HIGH,3,2026-07-22')
    // Nulls become empty cells, not the string "null".
    expect(lines[4]).toBe('NEWCO,,,,')
    expect(lines).toHaveLength(2 + rows.length)
  })
})

describe('dateLocale', () => {
  it('maps both Chinese variants and defaults everything else to en-US', () => {
    // Regression guard: after the i18next split, five components still
    // compared lang === 'zh' and silently gave Chinese users en-US dates.
    expect(dateLocale('zh-CN')).toBe('zh-CN')
    expect(dateLocale('zh-TW')).toBe('zh-TW')
    expect(dateLocale('en')).toBe('en-US')
    expect(dateLocale(undefined)).toBe('en-US')
  })
})
