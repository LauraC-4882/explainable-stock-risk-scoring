import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from 'recharts'

// See PriceChart: missing data must render an empty frame, never throw.
//
// Chart.js coloured each line segment by its value via a per-segment callback.
// Recharts has no per-segment stroke, so the band colouring is a value-mapped
// vertical gradient instead: gradientUnits="userSpaceOnUse" pins the gradient
// to the y-axis value range (0-100), so green sits at low scores and rose at
// high ones regardless of what the series does — same risk-band semantics,
// rendered as one continuous ramp. Band colours match utils.RISK_COLORS and
// the backend thresholds (25/50/75).
export default function RiskChart({ timeseries = [] }) {
  return (
    <div className="h-[110px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={timeseries} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <defs>
            {/* y1/y2 in value space: 110 is the chart's pixel height, and the
                offsets below are (1 - threshold/100) because SVG gradients run
                top-down while the score axis runs bottom-up. */}
            <linearGradient
              id="risk-stroke"
              x1="0"
              y1="110"
              x2="0"
              y2="0"
              gradientUnits="userSpaceOnUse"
            >
              <stop offset="0%" stopColor="#34d399" />
              <stop offset="25%" stopColor="#34d399" />
              <stop offset="25%" stopColor="#fbbf24" />
              <stop offset="50%" stopColor="#fbbf24" />
              <stop offset="50%" stopColor="#fb923c" />
              <stop offset="75%" stopColor="#fb923c" />
              <stop offset="75%" stopColor="#f43f5e" />
              <stop offset="100%" stopColor="#f43f5e" />
            </linearGradient>
            <linearGradient id="risk-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f43f5e" stopOpacity={0.35} />
              <stop offset="50%" stopColor="#fb923c" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#34d399" stopOpacity={0} />
            </linearGradient>
          </defs>
          <YAxis
            width={30}
            domain={[0, 100]}
            ticks={[0, 25, 50, 75, 100]}
            tick={{ fill: '#9d7cb8', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            cursor={{ stroke: '#9d7cb8', strokeDasharray: '3 3' }}
            contentStyle={{
              background: 'rgba(9,21,37,0.95)',
              border: '1px solid rgba(56,189,248,0.2)',
              borderRadius: 8,
              fontSize: 11,
            }}
            labelStyle={{ color: '#9d7cb8' }}
            itemStyle={{ color: '#f0f8ff' }}
            formatter={(value) => [Number(value).toFixed(1), null]}
            labelFormatter={(label, payload) => payload?.[0]?.payload?.date ?? ''}
          />
          <Area
            type="monotone"
            dataKey="risk_score"
            stroke="url(#risk-stroke)"
            strokeWidth={1.5}
            fill="url(#risk-fill)"
            dot={false}
            activeDot={{ r: 4 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
