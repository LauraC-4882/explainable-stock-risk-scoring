// Icons and display order for the 5 risk categories — language-agnostic, so
// this stays separate from the translated label/plain-language text in
// src/i18n/locales/*.js.
export const CATEGORY_ORDER = ['volatility', 'tail', 'drawdown', 'sensitivity', 'liquidity']

export const CATEGORY_ICONS = {
  volatility: '\u{1F4CA}',
  tail: '⚠️',
  drawdown: '\u{1F4C9}',
  sensitivity: '\u{1F517}',
  liquidity: '\u{1F4A7}',
}
