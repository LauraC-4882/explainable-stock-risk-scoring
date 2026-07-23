import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

// Hour-of-day request histogram (24 UTC bars). Data comes from
// /api/admin/analytics/summary's hourly_histogram (always 24 zero-filled
// entries, so bars render even for quiet hours).
export default function AdminAnalyticsChart({ hourly = [] }) {
  return (
    <div className="h-[160px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={hourly} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <XAxis
            dataKey="hour"
            tick={{ fill: '#9d7cb8', fontSize: 9 }}
            tickLine={false}
            axisLine={false}
            interval={0}
            tickFormatter={(v) => (v % 3 === 0 ? v : '')}
          />
          <YAxis
            width={30}
            allowDecimals={false}
            tick={{ fill: '#9d7cb8', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            cursor={{ fill: 'rgba(192,132,252,0.08)' }}
            contentStyle={{
              background: 'rgba(9,21,37,0.95)',
              border: '1px solid rgba(56,189,248,0.2)',
              borderRadius: 8,
              fontSize: 11,
            }}
            labelStyle={{ color: '#9d7cb8' }}
            itemStyle={{ color: '#c084fc' }}
            formatter={(value) => [`${value} requests`, null]}
            labelFormatter={(label) => `${label}:00 UTC`}
          />
          <Bar
            dataKey="count"
            fill="rgba(192, 132, 252, 0.55)"
            radius={[3, 3, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
