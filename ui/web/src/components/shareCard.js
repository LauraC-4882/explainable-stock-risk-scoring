import { riskColor } from '../utils'

// Draws a shareable PNG of a score summary onto a canvas — pure canvas 2D, no
// html2canvas dependency (nothing external to inline, nothing for the CSP to
// mind).
//
// The one non-negotiable design decision: THE DISCLAIMER IS PART OF THE
// PIXELS. The platform's own simulated-user evaluation ranked "screenshots
// stripped of disclaimers" among its harms — a share card is precisely that
// screenshot, manufactured on purpose. Baking the not-advice line into the
// image means the caveat travels wherever the image is reposted; there is no
// cropped variant of this card that looks complete without it, because the
// footer band is drawn inside the card's border.

export const CARD_W = 1200
export const CARD_H = 630

// Pure and exported for tests: everything textual on the card, in the
// caller's locale, assembled from the real scorecard.
export function buildShareText(score, t) {
  const metrics = []
  if (score.volatility_30d != null)
    metrics.push(`Vol ${(score.volatility_30d * 100).toFixed(1)}%`)
  if (score.var_95 != null) metrics.push(`VaR ${(score.var_95 * 100).toFixed(2)}%`)
  if (score.beta != null) metrics.push(`β ${score.beta.toFixed(2)}`)
  return {
    ticker: score.ticker,
    name: score.name && score.name !== score.ticker ? score.name : null,
    scoreLine: `${Math.round(score.risk_score)}`,
    band: t(`riskLabel.${score.risk_label}`),
    bandColor: riskColor(score.risk_label),
    meaning: t(`labelExplanation.${score.risk_label}`),
    metricsLine: metrics.join('   ·   '),
    asOf: (score.timestamp || '').slice(0, 10),
    disclaimer: t('share.imageDisclaimer'),
    brand: 'Riscore',
  }
}

export function shareFilename(ticker) {
  return `riscore-${ticker}-${new Date().toISOString().slice(0, 10)}.png`
}

function wrapText(ctx, text, maxWidth) {
  const words = text.split(' ')
  const lines = []
  let line = ''
  for (const word of words) {
    const probe = line ? `${line} ${word}` : word
    if (ctx.measureText(probe).width > maxWidth && line) {
      lines.push(line)
      line = word
    } else {
      line = probe
    }
  }
  if (line) lines.push(line)
  return lines
}

export function drawShareCard(canvas, content) {
  const ctx = canvas.getContext('2d')
  canvas.width = CARD_W
  canvas.height = CARD_H

  // Backdrop: the app's deep-navy gradient.
  const bg = ctx.createLinearGradient(0, 0, CARD_W, CARD_H)
  bg.addColorStop(0, '#060d1a')
  bg.addColorStop(0.55, '#091525')
  bg.addColorStop(1, '#0c1e35')
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, CARD_W, CARD_H)

  // Hairline border.
  ctx.strokeStyle = 'rgba(56,189,248,0.25)'
  ctx.lineWidth = 2
  ctx.strokeRect(1, 1, CARD_W - 2, CARD_H - 2)

  const sans = 'system-ui, -apple-system, "Segoe UI", "Noto Sans SC", sans-serif'

  // Brand + as-of.
  ctx.fillStyle = '#38bdf8'
  ctx.font = `700 34px ${sans}`
  ctx.fillText(content.brand, 56, 78)
  if (content.asOf) {
    ctx.fillStyle = '#7aa3c8'
    ctx.font = `400 22px ${sans}`
    ctx.textAlign = 'right'
    ctx.fillText(content.asOf, CARD_W - 56, 78)
    ctx.textAlign = 'left'
  }

  // Ticker + optional name.
  ctx.fillStyle = '#f0f8ff'
  ctx.font = `800 64px ${sans}`
  ctx.fillText(content.ticker, 56, 186)
  if (content.name) {
    ctx.fillStyle = '#7aa3c8'
    ctx.font = `400 26px ${sans}`
    ctx.fillText(content.name, 56, 226)
  }

  // Score hero.
  ctx.fillStyle = content.bandColor
  ctx.font = `800 150px ${sans}`
  ctx.fillText(content.scoreLine, 56, 400)
  const scoreWidth = ctx.measureText(content.scoreLine).width
  ctx.fillStyle = '#7aa3c8'
  ctx.font = `600 34px ${sans}`
  ctx.fillText('/ 100', 56 + scoreWidth + 18, 398)

  // Band chip: text + colour, never colour alone — same rule as the app.
  ctx.font = `800 34px ${sans}`
  const bandW = ctx.measureText(content.band).width + 44
  ctx.strokeStyle = content.bandColor
  ctx.lineWidth = 2.5
  ctx.strokeRect(56 + scoreWidth + 130, 356, bandW, 54)
  ctx.fillStyle = content.bandColor
  ctx.fillText(content.band, 56 + scoreWidth + 152, 396)

  // Plain-language meaning (wrapped).
  ctx.fillStyle = '#cbd5e1'
  ctx.font = `400 26px ${sans}`
  let y = 462
  for (const line of wrapText(ctx, content.meaning, CARD_W - 112).slice(0, 2)) {
    ctx.fillText(line, 56, y)
    y += 36
  }

  // Metric strip.
  if (content.metricsLine) {
    ctx.fillStyle = '#7aa3c8'
    ctx.font = `500 24px monospace`
    ctx.fillText(content.metricsLine, 56, y + 14)
  }

  // Disclaimer band — inside the border, part of the image by construction.
  ctx.fillStyle = 'rgba(56,189,248,0.08)'
  ctx.fillRect(2, CARD_H - 58, CARD_W - 4, 56)
  ctx.fillStyle = '#9db8d4'
  ctx.font = `400 21px ${sans}`
  ctx.fillText(content.disclaimer, 56, CARD_H - 22)

  return canvas
}
