import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { NEUTRAL_COLOR } from '../data/categoryMeta'
import { hexToRgb, renderWithProviders } from '../test/utils'
import KeyFactorTiles from './KeyFactorTiles'

const GREEN = '#34d399' // the "reassuringly safe" colour a floored tile must never use

const cat = (score, extra = {}) => ({
  score,
  weight: 0.2,
  two_sided: false,
  contribution: score,
  metrics: {},
  ...extra,
})

// The rendered score number is the only element carrying the tile's colour,
// and it's unique per tile because each category gets a distinct score here.
const scoreNode = (score) => screen.getByText(String(score))

describe('KeyFactorTiles', () => {
  it('renders nothing when the breakdown is missing or empty', () => {
    expect(
      renderWithProviders(<KeyFactorTiles breakdown={undefined} />).container
    ).toBeEmptyDOMElement()
    expect(renderWithProviders(<KeyFactorTiles breakdown={{}} />).container).toBeEmptyDOMElement()
    // A category present but unscored is not a tile either — an empty
    // "Key Factor Contributions" heading over nothing is worse than no panel.
    expect(
      renderWithProviders(<KeyFactorTiles breakdown={{ tail: { score: null } }} />).container
    ).toBeEmptyDOMElement()
  })

  it('marks a floored-out two-sided category as having no effect, not as safe', () => {
    renderWithProviders(
      <KeyFactorTiles breakdown={{ liquidity: cat(12, { two_sided: true, contribution: 50 }) }} />
    )

    // A user reading this tile must not conclude the stock is safe on
    // liquidity: the low reading was floored out of the composite entirely.
    expect(screen.getByText('No effect')).toBeInTheDocument()
    expect(screen.getByText(/Left the score unchanged/)).toBeInTheDocument()
    expect(screen.queryByText('Low')).not.toBeInTheDocument()

    const color = scoreNode(12).style.color
    expect(color).toBe(hexToRgb(NEUTRAL_COLOR))
    expect(color).not.toBe(hexToRgb(GREEN))
  })

  it('scores a two-sided category above neutral normally', () => {
    renderWithProviders(
      <KeyFactorTiles breakdown={{ sensitivity: cat(69.7, { two_sided: true }) }} />
    )
    expect(screen.queryByText('No effect')).not.toBeInTheDocument()
    expect(screen.getByText('Elevated')).toBeInTheDocument()
    expect(scoreNode(70).style.color).not.toBe(hexToRgb(NEUTRAL_COLOR))
  })

  it('still renders a low one-sided category as green/low risk', () => {
    renderWithProviders(<KeyFactorTiles breakdown={{ volatility: cat(12) }} />)
    // One-sided low readings DO earn a discount, so the reassuring colour and
    // wording are correct here — the floor rule must not spill onto them.
    expect(screen.getByText('Low')).toBeInTheDocument()
    expect(screen.queryByText('No effect')).not.toBeInTheDocument()
    expect(scoreNode(12).style.color).toBe(hexToRgb(GREEN))
  })

  it('skips categories with no score but keeps the rest', () => {
    renderWithProviders(
      <KeyFactorTiles
        breakdown={{ volatility: cat(54.7), tail: { score: null, two_sided: false } }}
      />
    )
    expect(screen.getByText('55')).toBeInTheDocument()
    expect(screen.getAllByRole('tooltip')).toHaveLength(1)
  })

  it('a two-sided category exactly at neutral is not floored', () => {
    // The backend floors strictly below 50; a tile at exactly 50 contributed
    // to the composite and must say so.
    renderWithProviders(
      <KeyFactorTiles breakdown={{ sensitivity: cat(50, { two_sided: true }) }} />
    )
    expect(screen.queryByText('No effect')).not.toBeInTheDocument()
  })
})
