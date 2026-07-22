// Icons and display order for the 5 risk categories — language-agnostic, so
// this stays separate from the translated label/plain-language text in
// src/i18n/locales/*.js. Icons are Phosphor components (phosphoricons.com,
// thin weight via the app-level IconContext), not emoji — render as
// <Icon /> where Icon = CATEGORY_ICONS[key].
import { ChartLineUp, Drop, LinkSimple, TrendDown, Warning } from '@phosphor-icons/react'

export const CATEGORY_ORDER = ['volatility', 'tail', 'drawdown', 'sensitivity', 'liquidity']

export const CATEGORY_ICONS = {
  volatility: ChartLineUp,
  tail: Warning,
  drawdown: TrendDown,
  sensitivity: LinkSimple,
  liquidity: Drop,
}

// Two-sided categories (backend flags them via `two_sided` — see
// scoring/risk_categories.TWO_SIDED_CATEGORIES) reading below neutral were
// floored out of the composite: they contributed nothing rather than earning
// the stock a discount. Both the tiles and the explainer bars have to agree
// on that, so the rule and its colour live here instead of being reimplemented
// in each — they disagreed on the first pass, with the tile showing "no
// effect" in grey right beside a reassuring green bar for the same category.
export const NEUTRAL_COLOR = '#8fa8c4'

export function isFlooredOut(cat) {
  return Boolean(cat?.two_sided) && cat?.score != null && cat.score < 50
}
