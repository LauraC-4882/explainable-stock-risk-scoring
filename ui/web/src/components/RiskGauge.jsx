export default function RiskGauge({ score, color }) {
  const pct = Math.min(+score, 100) / 100
  const R = 50
  const cx = 58
  const cy = 58
  const pt = (a) => [cx + R * Math.cos(a), cy + R * Math.sin(a)]
  const [sx, sy] = pt(Math.PI)
  const [ex, ey] = pt(2 * Math.PI)
  const angle = Math.PI + pct * Math.PI
  const [vx, vy] = pt(angle)
  const large = pct > 0.5 ? 1 : 0
  const track = `M ${sx} ${sy} A ${R} ${R} 0 0 1 ${ex} ${ey}`
  const fill = pct > 0.005 ? `M ${sx} ${sy} A ${R} ${R} 0 ${large} 1 ${vx} ${vy}` : ''

  const ticks = [0.25, 0.5, 0.75].map((p) => {
    const a = Math.PI + p * Math.PI
    const [x1, y1] = pt(a)
    const x2 = cx + (R + 5) * Math.cos(a)
    const y2 = cy + (R + 5) * Math.sin(a)
    return { x1, y1, x2, y2 }
  })

  return (
    <svg width="116" height="68" viewBox="0 0 116 68" style={{ overflow: 'visible' }}>
      {ticks.map((t, i) => (
        <line
          key={i}
          x1={t.x1.toFixed(1)}
          y1={t.y1.toFixed(1)}
          x2={t.x2.toFixed(1)}
          y2={t.y2.toFixed(1)}
          stroke="#2b1c45"
          strokeWidth="2"
        />
      ))}
      <path d={track} fill="none" stroke="#2b1c45" strokeWidth="9" strokeLinecap="round" />
      {fill && (
        <path
          d={fill}
          fill="none"
          stroke={color}
          strokeWidth="9"
          strokeLinecap="round"
          className="transition-all duration-700 ease-out"
        />
      )}
      <text x={cx} y="56" textAnchor="middle" fill={color} fontSize="14" fontWeight="900">
        {Math.round(score)}
      </text>
      <text x="8" y="66" fill="#9d7cb8" fontSize="8.5">
        0
      </text>
      <text x={cx - 6} y="10" fill="#9d7cb8" fontSize="8.5">
        50
      </text>
      <text x="98" y="66" fill="#9d7cb8" fontSize="8.5">
        100
      </text>
    </svg>
  )
}
