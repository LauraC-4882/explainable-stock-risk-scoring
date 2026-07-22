import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import { LanguageProvider } from '../i18n/LanguageContext'
import { scoreTsla } from '../test/fixtures/score'
import { timeseriesTsla } from '../test/fixtures/timeseries'
import StockCard from './StockCard'

// Charts are covered by charts.test.jsx; here they'd only add Chart.js noise
// to assertions about the card's own load/error/populated states.
vi.mock('react-chartjs-2', () => ({
  Line: () => <div data-testid="chart" />,
  Bar: () => <div data-testid="chart" />,
}))

vi.mock('../api', () => ({
  apiScore: vi.fn(),
  apiTimeseries: vi.fn(),
  apiOutcomes: vi.fn(),
  apiListPosts: vi.fn(),
  // AuthProvider imports these at module scope; with no stored token none of
  // them is called, but the module still has to export them.
  apiMe: vi.fn(),
  apiLogin: vi.fn(),
  apiRegister: vi.fn(),
  apiGetWatchlist: vi.fn(),
  apiAddWatchlist: vi.fn(),
  apiRemoveWatchlist: vi.fn(),
  apiVote: vi.fn(),
  apiRemoveVote: vi.fn(),
  apiDeletePost: vi.fn(),
  apiReportPost: vi.fn(),
  // [R2] token-refresh subscription. AuthProvider calls this in an effect and
  // uses the return value as the cleanup function, so the mock must return a
  // callable — returning undefined makes React throw on unmount.
  onTokenRefreshed: vi.fn(() => () => {}),
}))

import { apiListPosts, apiScore, apiTimeseries } from '../api'

// Never resolves — holds the card in its loading state for as long as the
// assertion needs.
const pending = () => new Promise(() => {})

function renderCard(props = {}) {
  return render(
    <LanguageProvider>
      <AuthProvider>
        <StockCard ticker="TSLA" period="1mo" onRemove={() => {}} {...props} />
      </AuthProvider>
    </LanguageProvider>
  )
}

beforeEach(() => {
  apiScore.mockReset()
  apiTimeseries.mockReset()
  apiListPosts.mockReset()
  apiListPosts.mockResolvedValue({ items: [], total: 0 })
})

describe('StockCard', () => {
  it('shows the skeleton, not a score, while the score request is in flight', () => {
    apiScore.mockImplementation(pending)
    apiTimeseries.mockImplementation(pending)

    const { container } = renderCard()

    expect(screen.getByText('TSLA')).toBeInTheDocument()
    expect(screen.getByText('Fetching…')).toBeInTheDocument()
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
    // A half-rendered hero would be worse than the skeleton: no risk band
    // may be claimed before the score arrives.
    expect(screen.queryByText('HIGH')).not.toBeInTheDocument()
  })

  it('surfaces the backend error message instead of an empty card', async () => {
    apiScore.mockRejectedValue(new Error('No data for TSLA'))
    apiTimeseries.mockResolvedValue([])

    const { container } = renderCard()

    expect(await screen.findByText('No data for TSLA')).toBeInTheDocument()
    expect(container.querySelector('.animate-pulse')).not.toBeInTheDocument()
  })

  it('renders the populated dashboard once both requests resolve', async () => {
    apiScore.mockResolvedValue(scoreTsla)
    apiTimeseries.mockResolvedValue(timeseriesTsla)

    renderCard()

    // Hero: company name leads, ticker · sector is the eyebrow.
    expect(await screen.findByRole('heading', { name: /Tesla/i })).toBeInTheDocument()
    expect(screen.getByText(/TSLA · Consumer Cyclical/)).toBeInTheDocument()
    expect(screen.getAllByText('HIGH').length).toBeGreaterThan(0)

    // Window section is captioned with the real first/last session in the
    // data, not just the "1M" label.
    const first = timeseriesTsla[0].date
    const last = timeseriesTsla[timeseriesTsla.length - 1].date
    await waitFor(() =>
      expect(screen.getByText(new RegExp(`${first}.*${last}`))).toBeInTheDocument()
    )
    expect(screen.getByText('Key Factor Contributions')).toBeInTheDocument()
  })

  it('shows an em dash for the risk range when no session carried a score', async () => {
    apiScore.mockResolvedValue(scoreTsla)
    // Regression: Math.round(null) is 0, so this window used to advertise a
    // confident "0–0" — the safest possible reading — for missing data.
    apiTimeseries.mockResolvedValue(
      timeseriesTsla.map((d) => ({ ...d, risk_score: null, risk_label: null }))
    )

    renderCard()

    await screen.findByText('Risk range')
    const rangeTile = screen.getByText('Risk range').parentElement
    expect(rangeTile).toHaveTextContent('—')
    expect(rangeTile).not.toHaveTextContent('0–0')
  })

  it('refetches the timeseries but not the score when the period changes', async () => {
    apiScore.mockResolvedValue(scoreTsla)
    apiTimeseries.mockResolvedValue(timeseriesTsla)

    const { rerender } = renderCard()
    await screen.findByRole('heading', { name: /Tesla/i })

    expect(apiScore).toHaveBeenCalledTimes(1)
    expect(apiTimeseries).toHaveBeenCalledTimes(1)
    expect(apiTimeseries).toHaveBeenLastCalledWith('TSLA', '1mo')

    rerender(
      <LanguageProvider>
        <AuthProvider>
          <StockCard ticker="TSLA" period="1y" onRemove={() => {}} />
        </AuthProvider>
      </LanguageProvider>
    )

    // The composite ranks against a fixed ~2y baseline, so re-scoring on a
    // timeframe click would be a full upstream fetch for an identical number.
    await waitFor(() => expect(apiTimeseries).toHaveBeenCalledTimes(2))
    expect(apiTimeseries).toHaveBeenLastCalledWith('TSLA', '1y')
    expect(apiScore).toHaveBeenCalledTimes(1)
  })

  it('refetches both when the ticker changes', async () => {
    apiScore.mockResolvedValue(scoreTsla)
    apiTimeseries.mockResolvedValue(timeseriesTsla)

    const { rerender } = renderCard()
    await screen.findByRole('heading', { name: /Tesla/i })

    rerender(
      <LanguageProvider>
        <AuthProvider>
          <StockCard ticker="NVDA" period="1mo" onRemove={() => {}} />
        </AuthProvider>
      </LanguageProvider>
    )

    await waitFor(() => expect(apiScore).toHaveBeenCalledTimes(2))
    expect(apiScore).toHaveBeenLastCalledWith('NVDA')
    expect(apiTimeseries).toHaveBeenLastCalledWith('NVDA', '1mo')
  })

  it('keeps the score hero when only the timeseries request fails', async () => {
    apiScore.mockResolvedValue(scoreTsla)
    apiTimeseries.mockRejectedValue(new Error('Failed to fetch timeseries'))

    renderCard()

    expect(await screen.findByRole('heading', { name: /Tesla/i })).toBeInTheDocument()
    expect(screen.getAllByText('HIGH').length).toBeGreaterThan(0)
    // The window section has nothing to show, but the card must not error out.
    expect(screen.queryByText('Failed to fetch timeseries')).not.toBeInTheDocument()
  })
})
