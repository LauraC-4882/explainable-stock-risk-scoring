import { describe, expect, it } from 'vitest'
import { buildShareText, shareFilename } from './shareCard'

const t = (key) =>
  ({
    'riskLabel.HIGH': 'HIGH',
    'labelExplanation.HIGH': 'Bumpier than this stock’s own normal.',
    'share.imageDisclaimer': 'Not a probability of loss and not investment advice · riscore',
  })[key] || key

const score = {
  ticker: 'TSLA',
  name: 'Tesla, Inc.',
  risk_score: 66.5,
  risk_label: 'HIGH',
  volatility_30d: 0.4759,
  var_95: -0.0596,
  beta: 1.802,
  timestamp: '2026-07-17T17:47:57Z',
}

describe('buildShareText', () => {
  it('assembles every band of the card from the real scorecard', () => {
    const c = buildShareText(score, t)
    expect(c.ticker).toBe('TSLA')
    expect(c.name).toBe('Tesla, Inc.')
    expect(c.scoreLine).toBe('67')
    expect(c.band).toBe('HIGH')
    expect(c.metricsLine).toContain('Vol 47.6%')
    expect(c.metricsLine).toContain('VaR -5.96%')
    expect(c.metricsLine).toContain('β 1.80')
    expect(c.asOf).toBe('2026-07-17')
  })

  it('always carries the disclaimer — the card exists to keep it attached', () => {
    const c = buildShareText(score, t)
    expect(c.disclaimer).toContain('not investment advice')
  })

  it('drops a name that merely repeats the ticker, and missing metrics', () => {
    const c = buildShareText(
      { ...score, name: 'TSLA', volatility_30d: null, var_95: null, beta: null },
      t
    )
    expect(c.name).toBeNull()
    expect(c.metricsLine).toBe('')
  })
})

describe('shareFilename', () => {
  it('stamps ticker and date', () => {
    expect(shareFilename('TSLA')).toMatch(/^riscore-TSLA-\d{4}-\d{2}-\d{2}\.png$/)
  })
})
