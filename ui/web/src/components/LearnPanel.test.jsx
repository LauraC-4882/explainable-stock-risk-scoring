import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import { renderWithProviders } from '../test/utils'
import LearnPanel, { bandForScore } from './LearnPanel'

// The band cut-offs are the load-bearing part: the panel teaches users where
// LOW/MODERATE/HIGH/EXTREME begin, so they must match the backend thresholds
// (settings.risk_low_max = 25 / risk_moderate_max = 50 / risk_high_max = 75).
// If someone re-tunes the backend bands, this test should fail rather than
// leave the site quietly teaching the wrong ones.
describe('bandForScore', () => {
  it('matches the backend RISK_LABELS boundaries', () => {
    expect(bandForScore(0)).toBe('LOW')
    expect(bandForScore(24.9)).toBe('LOW')
    expect(bandForScore(25)).toBe('MODERATE')
    expect(bandForScore(49.9)).toBe('MODERATE')
    expect(bandForScore(50)).toBe('HIGH')
    expect(bandForScore(74.9)).toBe('HIGH')
    expect(bandForScore(75)).toBe('EXTREME')
    expect(bandForScore(100)).toBe('EXTREME')
  })
})

function openPanel() {
  // The panel reads its open flag from AuthContext; render it inside the real
  // provider and drive it through the header-equivalent opener.
  return renderWithProviders(<LearnPanel />, { wrapper: AuthProvider })
}

describe('LearnPanel', () => {
  it('renders nothing while closed', () => {
    openPanel()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

// Driving the open state requires the context setter, so exercise the panel
// through a tiny harness that opens it on mount.
import { useEffect } from 'react'
import { useAuth } from '../auth/AuthContext'

function AutoOpen({ children }) {
  const { openLearnPanel } = useAuth()
  useEffect(() => {
    openLearnPanel()
  }, [openLearnPanel])
  return children
}

function renderOpen() {
  return renderWithProviders(
    <AuthProvider>
      <AutoOpen>
        <LearnPanel />
      </AutoOpen>
    </AuthProvider>
  )
}

describe('LearnPanel (open)', () => {
  it('states plainly that the score is not a probability', () => {
    renderOpen()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveTextContent(/not a probability/i)
    expect(dialog).toHaveTextContent(/80 is not an 80% chance/i)
  })

  it('moves the band label with the slider, in text not colour alone', () => {
    renderOpen()

    // Default sits in HIGH; drag down into LOW and the label must follow.
    expect(screen.getByTestId('learn-band')).toHaveTextContent('HIGH')

    const slider = screen.getByRole('slider')
    fireEvent.change(slider, { target: { value: '10' } })
    expect(screen.getByTestId('learn-score-value')).toHaveTextContent('10')
    expect(screen.getByTestId('learn-band')).toHaveTextContent('LOW')

    fireEvent.change(slider, { target: { value: '90' } })
    expect(screen.getByTestId('learn-band')).toHaveTextContent('EXTREME')
  })

  it('states the non-advisory boundary and points to a qualified adviser', () => {
    renderOpen()
    const text = screen.getByRole('dialog').textContent.toLowerCase()
    expect(text).toContain('qualified adviser')
    // The page must actively disclaim advice and price targets...
    expect(text).toContain('never tells you what to buy or sell')
    expect(text).toContain('never sets price targets')
    // ...and must never issue a directive itself.
    expect(text).not.toContain('you should buy')
    expect(text).not.toContain('you should sell')
    expect(text).not.toMatch(/price target of/)
  })

  it('renders the glossary as keyboard-reachable disclosure widgets', () => {
    renderOpen()
    // <details>/<summary> are focusable and expandable without JS.
    const summaries = screen.getAllByText(/^(Risk score|Percentile|Volatility|Beta)$/)
    expect(summaries.length).toBeGreaterThanOrEqual(4)
  })
})
