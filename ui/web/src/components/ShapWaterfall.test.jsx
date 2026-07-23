import { describe, expect, it } from 'vitest'
import { buildWaterfallSteps } from './ShapWaterfall'

const logit = (p) => Math.log(p / (1 - p))

// Shaped like the committed TSLA fixture's ml_drawdown_explanation.
const explanation = {
  base_probability: 0.5969,
  predicted_probability: 0.7509,
  top_features: [
    { feature: 'volatility__max_drawdown_63d', raw_value: -0.239, shap_contribution: 0.7128 },
    { feature: 'volatility__vol_63d', raw_value: 0.4759, shap_contribution: 0.6524 },
    { feature: 'momentum__volume_ratio', raw_value: 0.509, shap_contribution: -0.375 },
  ],
}

describe('buildWaterfallSteps', () => {
  it('bridges base to predicted exactly, via an explicit "other" remainder', () => {
    // The additive identity the whole chart rests on: logit(base) plus every
    // bar (listed features AND the remainder) must land on logit(predicted).
    // Without the remainder bar the top-N list would silently imply it
    // explains everything.
    const { steps, start, end } = buildWaterfallSteps(explanation)
    const total = steps.reduce((acc, s) => acc + s.contribution, 0)
    expect(start + total).toBeCloseTo(end, 10)
    expect(start).toBeCloseTo(logit(0.5969), 10)
    expect(end).toBeCloseTo(logit(0.7509), 10)
    expect(steps.at(-1).isOther).toBe(true)
  })

  it('gives each bar floating geometry consistent with the running total', () => {
    const { steps, start } = buildWaterfallSteps(explanation)
    let cursor = start
    for (const s of steps) {
      const next = cursor + s.contribution
      expect(s.offset).toBeCloseTo(Math.min(cursor, next), 10)
      expect(s.delta).toBeCloseTo(Math.abs(s.contribution), 10)
      expect(s.positive).toBe(s.contribution >= 0)
      cursor = next
    }
  })

  it('omits the remainder bar when the listed features already sum exactly', () => {
    const start = logit(0.4)
    const contributions = [0.3, -0.1]
    const end = start + 0.2
    const exact = {
      base_probability: 0.4,
      predicted_probability: 1 / (1 + Math.exp(-end)),
      top_features: contributions.map((c, i) => ({
        feature: `f${i}`,
        raw_value: 0,
        shap_contribution: c,
      })),
    }
    const { steps } = buildWaterfallSteps(exact)
    expect(steps).toHaveLength(2)
    expect(steps.every((s) => !s.isOther)).toBe(true)
  })

  it('refuses degenerate probabilities instead of producing infinite bars', () => {
    expect(buildWaterfallSteps({ base_probability: 0, predicted_probability: 0.5 })).toBeNull()
    expect(buildWaterfallSteps({ base_probability: 0.5, predicted_probability: 1 })).toBeNull()
    expect(buildWaterfallSteps({ base_probability: null, predicted_probability: 0.5 })).toBeNull()
  })
})
