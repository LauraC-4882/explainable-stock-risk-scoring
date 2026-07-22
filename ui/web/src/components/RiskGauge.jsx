// 270° arc gauge (ported from the Riscore.dc design): a 3/4 ring opening
// downward with the score sitting inside it in Space Grotesk. The fill arc is
// the risk-band color with a soft outer glow; `score` is already count-up
// animated by the caller, and the stroke-dashoffset transition smooths it.
export default function RiskGauge({ score, color, size = 184 }) {
  const R = 82
  const cx = 115
  const cy = 108
  const circ = 2 * Math.PI * R
  const span = 0.75 * circ // 270° visible arc
  const frac = Math.min(Math.max(+score || 0, 0), 100) / 100
  const dash = `${span.toFixed(1)} ${circ.toFixed(1)}`
  const offset = (span * (1 - frac)).toFixed(1)

  return (
    <svg
      width={size}
      height={(size * 200) / 230}
      viewBox="0 0 230 200"
      style={{ overflow: 'visible' }}
      aria-hidden="true"
    >
      {/* rotate 135° so the 90° gap sits at the bottom, ends at 0 (bottom-left)
          and 100 (bottom-right) — a downward-opening speedometer sweep. */}
      <g transform="rotate(135 115 108)">
        <circle
          cx={cx}
          cy={cy}
          r={R}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth="16"
          strokeLinecap="round"
          strokeDasharray={dash}
        />
        <circle
          cx={cx}
          cy={cy}
          r={R}
          fill="none"
          stroke={color}
          strokeWidth="16"
          strokeLinecap="round"
          strokeDasharray={dash}
          strokeDashoffset={offset}
          style={{
            filter: `drop-shadow(0 0 10px ${color})`,
            transition: 'stroke-dashoffset 0.7s ease',
          }}
        />
      </g>
      <text
        x="115"
        y="104"
        textAnchor="middle"
        style={{ font: "700 56px 'Space Grotesk', system-ui, sans-serif", fill: color }}
      >
        {Math.round(+score || 0)}
      </text>
      <text
        x="115"
        y="132"
        textAnchor="middle"
        style={{
          font: '600 12px Manrope, system-ui, sans-serif',
          fill: '#8b83a6',
          letterSpacing: '2px',
        }}
      >
        / 100
      </text>
      <text
        x="42"
        y="188"
        textAnchor="middle"
        style={{ font: '600 11px Manrope, system-ui, sans-serif', fill: '#6f6890' }}
      >
        0
      </text>
      <text
        x="188"
        y="188"
        textAnchor="middle"
        style={{ font: '600 11px Manrope, system-ui, sans-serif', fill: '#6f6890' }}
      >
        100
      </text>
    </svg>
  )
}
