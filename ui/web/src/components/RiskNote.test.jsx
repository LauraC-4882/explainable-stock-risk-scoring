import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '../test/utils'
import RiskNote from './RiskNote'

// Exactly what scorer.py's _risk_note produces — the English locale template
// must reproduce these byte-for-byte, since the component now renders from the
// template instead of printing score.risk_note.
const PERCENTILE_NOTE =
  "Score reflects this stock's risk relative to its own historical distribution " +
  '(and market sensitivity vs. SPY) — it is not a probability of loss, ' +
  'default probability, or investment recommendation.'
const FUSED_NOTE =
  "Score blends this stock's risk percentile relative to its own history (85%) " +
  'with a walk-forward-validated ML estimate of its 20-day severe-drawdown ' +
  'probability (15%), plus market sensitivity vs. SPY — it is ' +
  'not a probability of loss, default probability, or investment recommendation.'

const percentileScore = () => ({
  risk_note: PERCENTILE_NOTE,
  risk_score_composition: null, // ML leg unavailable — renormalised to pure percentile
  market_regime: { vix: 17.8, regime: 'calm', market: 'us', benchmark: 'SPY' },
})

const fusedScore = () => ({
  risk_note: FUSED_NOTE,
  risk_score_composition: [
    { producer: 'percentile_composite', score: 62.7, weight: 0.85 },
    { producer: 'ml_drawdown', score: 14.3, weight: 0.15 },
  ],
  market_regime: { vix: 17.8, regime: 'calm', market: 'us', benchmark: 'SPY' },
})

const inChinese = (code) => localStorage.setItem('stock-risk-lang', code)

describe('RiskNote', () => {
  it('renders nothing without a risk_note', () => {
    expect(renderWithProviders(<RiskNote score={null} />).container).toBeEmptyDOMElement()
    expect(renderWithProviders(<RiskNote score={{}} />).container).toBeEmptyDOMElement()
  })

  it('reproduces the backend percentile note verbatim in English', () => {
    renderWithProviders(<RiskNote score={percentileScore()} />)
    expect(screen.getByText(PERCENTILE_NOTE)).toBeInTheDocument()
  })

  it('reproduces the backend fused note verbatim in English', () => {
    renderWithProviders(<RiskNote score={fusedScore()} />)
    expect(screen.getByText(FUSED_NOTE)).toBeInTheDocument()
  })

  it.each(['zh-CN', 'zh-TW'])('translates both variants on a %s screen', (code) => {
    inChinese(code)
    const { unmount } = renderWithProviders(<RiskNote score={percentileScore()} />)
    expect(screen.queryByText(/Score reflects/)).not.toBeInTheDocument()
    expect(screen.getByText(/SPY/)).toHaveTextContent(/投资建议|投資建議/)
    unmount()

    renderWithProviders(<RiskNote score={fusedScore()} />)
    expect(screen.queryByText(/Score blends/)).not.toBeInTheDocument()
    // The fused shares survive translation: 85% / 15% from the composition.
    expect(screen.getByText(/85%/)).toHaveTextContent(/15%/)
  })

  it('falls back to the backend string when the structured fields are missing', () => {
    // An older cached response without market_regime must degrade to the
    // backend's English sentence, not render a template with a hole in it.
    inChinese('zh-CN')
    renderWithProviders(<RiskNote score={{ risk_note: PERCENTILE_NOTE }} />)
    expect(screen.getByText(PERCENTILE_NOTE)).toBeInTheDocument()
  })
})
