// Deterministic "what does this number mean" layer.
//
// Every reading below is a pure function of a value the backend already
// computed — no LLM call, no API cost, no latency, and (deliberately) no way
// to produce anything but the fixed, reviewed sentences these keys point at.
// That last property is the important one: an LLM asked to explain a risk
// metric can drift into "consider trimming this position", which is exactly
// the line this product does not cross. A threshold table cannot.
//
// Thresholds use conventional equity ranges and are stated here (rather than
// buried in a component) so the mapping from number -> wording stays
// auditable: the same value always yields the same reading.
//
// Every string these return is DESCRIPTIVE ONLY — it characterises the
// measurement, never suggests an action. See i18n `readings.*`.

/** Annualized 30-day volatility (decimal, e.g. 0.48 = 48%). */
export function volReading(v) {
  if (v == null || Number.isNaN(v)) return null
  if (v < 0.15) return 'low'
  if (v < 0.25) return 'normal'
  if (v < 0.4) return 'elevated'
  return 'high'
}

/** 95% Value at Risk (decimal, normally negative, e.g. -0.0596 = -5.96%). */
export function varReading(v) {
  if (v == null || Number.isNaN(v)) return null
  const mag = Math.abs(v)
  if (mag < 0.02) return 'mild'
  if (mag < 0.04) return 'moderate'
  if (mag < 0.06) return 'elevated'
  return 'severe'
}

/** Beta vs. the market benchmark. */
export function betaReading(v) {
  if (v == null || Number.isNaN(v)) return null
  if (v < 0) return 'negative'
  if (v < 0.8) return 'defensive'
  if (v <= 1.2) return 'inline'
  if (v <= 1.8) return 'amplified'
  return 'high'
}

/** RSI(14) momentum oscillator, 0-100. */
export function rsiReading(v) {
  if (v == null || Number.isNaN(v)) return null
  if (v < 30) return 'oversold'
  if (v < 45) return 'weak'
  if (v <= 55) return 'neutral'
  if (v <= 70) return 'firm'
  return 'overbought'
}

/** Percentile band shared by the five risk-category tiles (0-100). */
export function factorReading(score) {
  if (score == null || Number.isNaN(score)) return null
  if (score >= 75) return 'high'
  if (score >= 50) return 'elevated'
  if (score >= 25) return 'moderate'
  return 'low'
}

// Tailwind text color per reading level, so the chip's color agrees with the
// same green->amber->orange->rose semantics the rest of the card uses.
// "Higher" always means "more turbulent", never "better" or "worse".
export const LEVEL_TONE = {
  // volatility / VaR / factor bands
  low: 'text-risk-low',
  normal: 'text-risk-low',
  mild: 'text-risk-low',
  moderate: 'text-risk-moderate',
  elevated: 'text-risk-high',
  high: 'text-risk-extreme',
  severe: 'text-risk-extreme',
  // beta
  negative: 'text-risk-low',
  defensive: 'text-risk-low',
  inline: 'text-risk-moderate',
  amplified: 'text-risk-high',
  // rsi (momentum is descriptive, not a risk band — kept neutral-ish)
  oversold: 'text-risk-low',
  weak: 'text-risk-moderate',
  neutral: 'text-muted',
  firm: 'text-risk-moderate',
  overbought: 'text-risk-high',
}
