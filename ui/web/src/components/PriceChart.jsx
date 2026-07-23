import { useState } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useLanguage } from '../i18n/LanguageContext'

// timeseries defaults to [] so a card that hasn't loaded (or whose timeseries
// request failed) renders an empty chart frame instead of throwing on .map and
// taking the whole card down with it — the score hero above is still valid.
//
// Two modes: the classic close line, and candlesticks over the OHLC the
// timeseries endpoint now ships. The toggle only renders when every row
// actually has OHLC — a source without it falls back to the line silently
// rather than drawing invented candles.
//
// Candle colours are the app's own emerald/rose, market-independent — the
// US-green-up vs CN-red-up convention is deliberately NOT inherited here,
// same reasoning as the watchlist board's delta colours.

const UP = '#34d399'
const DOWN = '#f43f5e'

function hasOhlc(rows) {
  return (
    rows.length > 0 &&
    rows.every((r) => r.open != null && r.high != null && r.low != null && r.close != null)
  )
}

// Custom Bar shape: the Bar's dataKey is the [low, high] range, so x/y/width/
// height describe the wick extent in pixels; the body is interpolated inside
// it from open/close. Everything derives from the payload — no extra scales.
function Candle({ x, y, width, height, payload }) {
  const { open, close, high, low } = payload
  const span = high - low
  const up = close >= open
  const color = up ? UP : DOWN
  const bodyTop = span === 0 ? y : y + ((high - Math.max(open, close)) / span) * height
  const bodyH =
    span === 0 ? 1 : Math.max(1, (Math.abs(close - open) / span) * height)
  const cx = x + width / 2
  const bodyW = Math.max(2, width * 0.6)
  return (
    <g>
      <line x1={cx} y1={y} x2={cx} y2={y + height} stroke={color} strokeWidth={1} />
      <rect
        x={cx - bodyW / 2}
        y={bodyTop}
        width={bodyW}
        height={bodyH}
        fill={color}
        fillOpacity={up ? 0.85 : 1}
        rx={0.5}
      />
    </g>
  )
}

const TOOLTIP_STYLE = {
  contentStyle: {
    background: 'rgba(9,21,37,0.95)',
    border: '1px solid rgba(56,189,248,0.2)',
    borderRadius: 8,
    fontSize: 11,
  },
  labelStyle: { color: '#9d7cb8' },
}

export default function PriceChart({ timeseries = [], color }) {
  const { t } = useLanguage()
  const [mode, setMode] = useState('line')
  const gradientId = `price-fill-${(color || '').replace('#', '')}`
  const candlesAvailable = hasOhlc(timeseries)
  const showCandles = mode === 'candles' && candlesAvailable

  return (
    <div>
      {candlesAvailable && (
        <div className="mb-1 flex justify-end gap-1">
          {['line', 'candles'].map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              aria-pressed={mode === m}
              className={`rounded-full border px-2 py-0.5 text-[0.58rem] font-semibold transition ${
                mode === m
                  ? 'border-accent/50 bg-accent/10 text-accent'
                  : 'border-border text-muted hover:text-slate-200'
              }`}
            >
              {t(`chart.${m}`)}
            </button>
          ))}
        </div>
      )}
      <div className="h-[110px]">
        <ResponsiveContainer width="100%" height="100%">
          {showCandles ? (
            <ComposedChart
              data={timeseries.map((r) => ({ ...r, hl: [r.low, r.high] }))}
              margin={{ top: 4, right: 0, bottom: 0, left: 0 }}
            >
              <XAxis dataKey="date" hide />
              <YAxis
                width={38}
                domain={['auto', 'auto']}
                tick={{ fill: '#9d7cb8', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                {...TOOLTIP_STYLE}
                formatter={(value, name, { payload }) => {
                  if (name !== 'hl') return null
                  return [
                    `O ${payload.open}  H ${payload.high}  L ${payload.low}  C ${payload.close}`,
                    null,
                  ]
                }}
                labelFormatter={(label, payload) => payload?.[0]?.payload?.date ?? ''}
              />
              <Bar dataKey="hl" shape={<Candle />} isAnimationActive={false} />
            </ComposedChart>
          ) : (
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
                {...TOOLTIP_STYLE}
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
          )}
        </ResponsiveContainer>
      </div>
    </div>
  )
}
