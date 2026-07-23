import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '../test/utils'
import StressTestPanel from './StressTestPanel'

// Exactly the shape scoring/stress_test.py returns, including its
// pre-formatted English `label`/`narrative` (see tests/fixtures/mock_api/).
const scenario = (over = {}) => ({
  label: '2008 Global Financial Crisis',
  baseline_score: 68.2,
  stressed_score: 93,
  delta: 24.8,
  narrative:
    "If 2008 Global Financial Crisis conditions recurred, this stock's risk score " +
    'would move from 68.2 to 93.0 (+24.8).',
  stressed_categories: {},
  ...over,
})

const stressTest = (scenarios) => ({ live_score: 66.5, scenarios })

const inChinese = (code) => localStorage.setItem('stock-risk-lang', code)

describe('StressTestPanel', () => {
  it('reproduces the backend narrative verbatim in English', () => {
    // The panel re-renders the sentence from the scenario key instead of
    // printing score.narrative, so the English copy is now ours — this pins it
    // to the string the API already produced (note 93 renders as "93.0").
    const s = scenario()
    renderWithProviders(<StressTestPanel stressTest={stressTest({ '2008_financial_crisis': s })} />)

    expect(screen.getByText('2008 Global Financial Crisis')).toBeInTheDocument()
    expect(screen.getByText(s.narrative)).toBeInTheDocument()
  })

  it.each(['zh-CN', 'zh-TW'])('leaves no English scenario text on a %s screen', (code) => {
    inChinese(code)
    renderWithProviders(
      <StressTestPanel
        stressTest={stressTest({
          '2008_financial_crisis': scenario(),
          '2020_covid_crash': scenario({ label: '2020 COVID-19 Crash', narrative: 'ignored' }),
          '2022_rate_hike_selloff': scenario({
            label: '2022 Rate Hike Bear Market',
            narrative: 'ignored',
          }),
        })}
      />
    )

    // The scenario card was the last English island inside an otherwise
    // translated card: an English title plus a full English sentence under it.
    expect(screen.queryByText(/Global Financial Crisis/)).not.toBeInTheDocument()
    expect(screen.queryByText(/conditions recurred/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Rate Hike Bear Market/)).not.toBeInTheDocument()
    expect(screen.getAllByText(/風險分數|风险分数/)).toHaveLength(3)
    // Numbers stay verbatim — only the words around them are translated.
    expect(screen.getAllByText(/68\.2.*93\.0.*\+24\.8/)).toHaveLength(3)
  })

  it('falls back to the backend strings for a scenario the locale does not know', () => {
    // Adding a scenario to stress_test.py without touching the locale files
    // must degrade to untranslated English, not render a raw i18n key path.
    inChinese('zh-CN')
    const s = scenario({ label: '1987 Black Monday', narrative: 'A brand new backend sentence.' })
    renderWithProviders(<StressTestPanel stressTest={stressTest({ '1987_black_monday': s })} />)

    expect(screen.getByText('1987 Black Monday')).toBeInTheDocument()
    expect(screen.getByText(s.narrative)).toBeInTheDocument()
    expect(screen.queryByText(/stressTest\.scenario/)).not.toBeInTheDocument()
  })
})
