import { renderWithProviders as render } from '../test/utils'
import { describe, expect, it } from 'vitest'
import { timeseriesTsla } from '../test/fixtures/timeseries'
import AdminAnalyticsChart from './AdminAnalyticsChart'
import PriceChart from './PriceChart'
import RiskChart from './RiskChart'

// The charts sit inside the card, not behind an error boundary, so anything
// that throws here blanks the whole dashboard — including the score hero,
// which is still perfectly valid data. Degraded/absent series must render an
// empty frame instead.
describe('chart components tolerate missing data', () => {
  const cases = [
    ['undefined series', undefined],
    ['empty series', []],
    ['rows with null values', [{ date: '2026-01-02', close: null, risk_score: null }]],
    ['rows missing fields entirely', [{ date: '2026-01-02' }]],
  ]

  it.each(cases)('PriceChart: %s', (_name, timeseries) => {
    expect(() => render(<PriceChart timeseries={timeseries} color="#34d399" />)).not.toThrow()
  })

  it.each(cases)('RiskChart: %s', (_name, timeseries) => {
    expect(() => render(<RiskChart timeseries={timeseries} />)).not.toThrow()
  })

  it('AdminAnalyticsChart: missing histogram', () => {
    expect(() => render(<AdminAnalyticsChart hourly={undefined} />)).not.toThrow()
    expect(() => render(<AdminAnalyticsChart hourly={[]} />)).not.toThrow()
  })
})

describe('chart components render real data', () => {
  // Recharts renders SVG (Chart.js drew to a canvas). ResponsiveContainer
  // measures its parent, which jsdom reports as 0x0, so the chart surface is
  // asserted via the container class rather than a laid-out <svg> — the
  // ui_shot harness covers the actually-painted pixels.
  it('mounts a responsive chart surface for each series', () => {
    const { container } = render(<PriceChart timeseries={timeseriesTsla} color="#f43f5e" />)
    expect(container.querySelector('.recharts-responsive-container')).toBeInTheDocument()

    const risk = render(<RiskChart timeseries={timeseriesTsla} />)
    expect(risk.container.querySelector('.recharts-responsive-container')).toBeInTheDocument()
  })
})
