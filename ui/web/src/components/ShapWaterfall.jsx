import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useLanguage } from '../i18n/LanguageContext'

// SHAP waterfall for the XGBoost drawdown leg.
//
// The axis is LOG-ODDS, not probability, because that is the only space in
// which SHAP contributions actually add: logit(base) + Σ contributions =
// logit(predicted). Converting each bar to a probability delta would show
// numbers that don't sum — a chart that lies politely. The two endpoints are
// annotated with their probabilities, which is what a reader can anchor to.
//
// The API returns only the top-N features, so the listed bars alone don't
// bridge base → predicted. The gap is drawn explicitly as an "other features"
// bar rather than silently absorbed — otherwise the chart would imply the
// shown features explain everything.

const logit = (p) => Math.log(p / (1 - p))

// Pure and exported for tests: turns an explanation payload into waterfall
// steps, each with the floating-bar geometry ([offset, delta]) Recharts needs.
export function buildWaterfallSteps(explanation) {
  const { base_probability: base, predicted_probability: pred } = explanation
  if (
    base == null ||
    pred == null ||
    base <= 0 ||
    base >= 1 ||
    pred <= 0 ||
    pred >= 1
  ) {
    return null
  }
  const start = logit(base)
  const end = logit(pred)
  const features = explanation.top_features || []
  const listedSum = features.reduce((acc, f) => acc + f.shap_contribution, 0)
  const other = end - start - listedSum

  const steps = []
  let cursor = start
  for (const f of features) {
    const next = cursor + f.shap_contribution
    steps.push({
      name: f.feature,
      contribution: f.shap_contribution,
      rawValue: f.raw_value,
      offset: Math.min(cursor, next),
      delta: Math.abs(f.shap_contribution),
      positive: f.shap_contribution >= 0,
      isOther: false,
    })
    cursor = next
  }
  // Only worth a bar if the remainder is visually meaningful.
  if (Math.abs(other) > 1e-6) {
    const next = cursor + other
    steps.push({
      name: '__other__',
      contribution: other,
      rawValue: null,
      offset: Math.min(cursor, next),
      delta: Math.abs(other),
      positive: other >= 0,
      isOther: true,
    })
  }
  return { steps, start, end, base, pred }
}

export default function ShapWaterfall({ explanation }) {
  const { t } = useLanguage()
  const model = buildWaterfallSteps(explanation)
  if (!model || model.steps.length === 0) return null

  const { steps, start, end, base, pred } = model
  const data = steps.map((s) => ({
    ...s,
    label: s.isOther ? t('mlSignal.waterfallOther') : s.name,
  }))

  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-[0.65rem] text-muted">
        <span>
          {t('mlSignal.waterfallBase')}{' '}
          <span className="font-mono text-slate-300">{(base * 100).toFixed(1)}%</span>
        </span>
        <span>
          {t('mlSignal.waterfallPredicted')}{' '}
          <span className="font-mono text-slate-300">{(pred * 100).toFixed(1)}%</span>
        </span>
      </div>
      <div style={{ height: 30 + data.length * 30 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
            <XAxis
              type="number"
              domain={['auto', 'auto']}
              tick={{ fill: '#9d7cb8', fontSize: 9 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => v.toFixed(1)}
            />
            <YAxis
              type="category"
              dataKey="label"
              width={186}
              tick={{ fill: '#9d7cb8', fontSize: 9, fontFamily: 'monospace' }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              cursor={{ fill: 'rgba(56,189,248,0.06)' }}
              contentStyle={{
                background: 'rgba(9,21,37,0.95)',
                border: '1px solid rgba(56,189,248,0.2)',
                borderRadius: 8,
                fontSize: 11,
              }}
              labelStyle={{ color: '#f0f8ff' }}
              formatter={(value, name, { payload }) => {
                if (name === 'offset') return null // invisible spacer
                const sign = payload.positive ? '+' : '−'
                const raw =
                  payload.rawValue != null
                    ? ` (raw ${Number(payload.rawValue).toFixed(3)})`
                    : ''
                return [`${sign}${Math.abs(payload.contribution).toFixed(3)} log-odds${raw}`, null]
              }}
            />
            {/* Floating bars: transparent offset + coloured delta. */}
            <Bar dataKey="offset" stackId="w" fill="transparent" isAnimationActive={false} />
            <Bar dataKey="delta" stackId="w" radius={[2, 2, 2, 2]} isAnimationActive={false}>
              {data.map((s) => (
                <Cell
                  key={s.name}
                  fill={s.isOther ? '#7aa3c8' : s.positive ? '#f43f5e' : '#34d399'}
                  fillOpacity={s.isOther ? 0.45 : 0.85}
                />
              ))}
            </Bar>
            <ReferenceLine x={start} stroke="#7aa3c8" strokeDasharray="4 3" />
            <ReferenceLine x={end} stroke="#38bdf8" strokeDasharray="4 3" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-[0.62rem] leading-relaxed text-muted">{t('mlSignal.waterfallNote')}</p>
    </div>
  )
}
