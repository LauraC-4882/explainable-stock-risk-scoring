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
