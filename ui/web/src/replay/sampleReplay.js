// A real replay produced by the simulated-user harness
// (`python -m stock_risk.simulation replay`), committed so the viewer has
// something to show with no backend call and no file upload.
export const SAMPLE_REPLAY = {
  user_id: 'first_time_retail-0000',
  archetype: 'first_time_retail',
  language: 'en',
  scenario_id: 'task1_single_stock',
  experiment_variant: 'as_is',
  accessibility_mode: 'none',
  simulation_seed: 7,
  config_hash: '4d3ea52979a9',
  steps: [
    {
      step: 0,
      event: 'user_simulation_started',
      score: null,
      confidence_status: 'unknown',
      intended_financial_action: null,
      misconceptions: ['score_is_advice', 'score_is_probability'],
      detail: {},
    },
    {
      step: 1,
      event: 'score_viewed',
      score: 66.5,
      confidence_status: 'unknown',
      intended_financial_action: null,
      misconceptions: [],
      detail: {
        intrinsic_confidence: 'normal',
        product_surfaced_confidence: false,
        noticed_score: false,
      },
    },
    {
      step: 2,
      event: 'component_viewed',
      score: 66.5,
      confidence_status: 'unknown',
      intended_financial_action: null,
      misconceptions: [],
      detail: {
        understood: false,
      },
    },
    {
      step: 3,
      event: 'user_action_intent_recorded',
      score: 66.5,
      confidence_status: 'unknown',
      intended_financial_action: 'research_more',
      misconceptions: ['score_is_advice', 'score_is_probability'],
      detail: {
        reason:
          'chose research_more: perceived_risk=0.90, understanding=0.00, community_sentiment=+0.00, warning_taken_in=0.00, live_misconceptions=[score_is_advice, score_is_probability]',
        perceived_risk: 0.8978,
        panic_sell: false,
        overconfident_buy: false,
        treats_score_as_advice: true,
      },
    },
    {
      step: 4,
      event: 'user_overreliance_detected',
      score: 66.5,
      confidence_status: 'unknown',
      intended_financial_action: null,
      misconceptions: [],
      detail: {
        confidence_after: 0.668,
        actual_understanding: 0.0,
      },
    },
    {
      step: 5,
      event: 'simulation_completed',
      score: 66.5,
      confidence_status: 'unknown',
      intended_financial_action: 'research_more',
      misconceptions: ['score_is_advice', 'score_is_probability'],
      detail: {},
    },
  ],
  summary: {
    final_intended_action: 'research_more',
    initial_misconceptions: ['score_is_advice', 'score_is_probability'],
    final_misconceptions: ['score_is_advice', 'score_is_probability'],
    corrected: [],
    remaining: ['score_is_advice', 'score_is_probability'],
    overreliance_detected: true,
  },
}
