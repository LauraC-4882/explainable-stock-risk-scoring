import { useLanguage } from '../i18n/LanguageContext'

// Pentagon radar of the five risk categories that already make up the
// headline score (each 0–100 = this stock's percentile vs. its own ~2y
// history). A re-visualization of risk_breakdown — the same numbers the
// factor tiles show — not a new signal: descriptive only, and deliberately
// NOT a cross-stock "beats N% of stocks" diagnostic (scores are only
// comparable to this stock's own past). Pure SVG, no chart library.
const AXES = ['volatility', 'tail', 'drawdown', 'sensitivity', 'liquidity']

export default function RiskRadar({ breakdown, color, size = 220 }) {
  const { t } = useLanguage()
  const values = AXES.map((k) => breakdown?.[k]?.score)
  if (values.some((v) => v == null)) return null

  const c = size / 2
  const R = c - 34 // leave margin for labels outside the outer ring

  const point = (i, frac) => {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / AXES.length
    return [c + R * frac * Math.cos(angle), c + R * frac * Math.sin(angle)]
  }
  const ring = (frac) =>
    AXES.map((_, i) => point(i, frac).map((n) => n.toFixed(1)).join(',')).join(' ')

  const dataPoints = AXES.map((_, i) => point(i, values[i] / 100))
  const dataPolygon = dataPoints.map((p) => p.map((n) => n.toFixed(1)).join(',')).join(' ')

  return (
    <div className="flex flex-col items-center px-9">
      {/* overflow-visible: side axis labels render past the square viewport
          (text-anchor start/end extends outward); the px-9 wrapper reserves
          the real estate so they don't collide with siblings. */}
      <svg
        width={size}
        height={size}
        aria-label={t('radar.title')}
        role="img"
        className="overflow-visible"
      >
        {/* grid rings at 25/50/75/100 + spokes */}
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <polygon
            key={f}
            points={ring(f)}
            fill="none"
            stroke="rgba(139,163,201,0.18)"
            strokeWidth={f === 1 ? 1 : 0.6}
          />
        ))}
        {AXES.map((_, i) => {
          const [x, y] = point(i, 1)
          return (
            <line
              key={i}
              x1={c}
              y1={c}
              x2={x}
              y2={y}
              stroke="rgba(139,163,201,0.12)"
              strokeWidth="0.6"
            />
          )
        })}

        {/* data polygon */}
        <polygon
          points={dataPolygon}
          fill={`${color}2e`}
          stroke={color}
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
        {dataPoints.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="2.6" fill={color} />
        ))}

        {/* axis labels + values just outside each vertex */}
        {AXES.map((key, i) => {
          const [x, y] = point(i, 1.16)
          const anchor = Math.abs(x - c) < 8 ? 'middle' : x > c ? 'start' : 'end'
          return (
            <text key={key} x={x} y={y} textAnchor={anchor} fontSize="10">
              <tspan fill="#8ba3c9">{t(`categories.${key}.short`)} </tspan>
              <tspan fill={color} fontWeight="700">
                {Math.round(values[i])}
              </tspan>
            </text>
          )
        })}
      </svg>
      <p className="max-w-[220px] text-center text-[0.62rem] leading-snug text-muted">
        {t('radar.hint')}
      </p>
    </div>
  )
}
