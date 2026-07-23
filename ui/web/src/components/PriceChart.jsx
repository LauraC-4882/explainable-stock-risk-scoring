import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from 'recharts'

// timeseries defaults to [] so a card that hasn't loaded (or whose timeseries
// request failed) renders an empty chart frame instead of throwing on .map and
// taking the whole card down with it — the score hero above is still valid.
//
// Recharts (SVG) replaced Chart.js (canvas). The gradient fill that needed a
// canvas createLinearGradient callback is now a plain SVG <linearGradient>;
// the id carries the colour so two cards with different accent colours on one
// page can't collide on a shared gradient definition.
export default function PriceChart({ timeseries = [], color }) {
  const gradientId = `price-fill-${(color || '').replace('#', '')}`

  return (
    <div className="h-[110px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={timeseries} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.27} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <YAxis
            width={38}
            domain={['auto', 'auto']}
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
            itemStyle={{ color }}
            formatter={(value) => [`$${Number(value).toFixed(2)}`, null]}
            labelFormatter={(label, payload) => payload?.[0]?.payload?.date ?? ''}
          />
          <Area
            type="monotone"
            dataKey="close"
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#${gradientId})`}
            dot={false}
            activeDot={{ r: 4 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
