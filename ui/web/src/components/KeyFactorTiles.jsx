import { CATEGORY_ICONS, CATEGORY_ORDER } from '../data/categoryMeta'
import { factorReading } from '../explain/readings'
import { useLanguage } from '../i18n/LanguageContext'

const SEVERITY_COLOR = (score) => {
  if (score >= 75) return '#f43f5e'
  if (score >= 50) return '#fb923c'
  if (score >= 25) return '#fbbf24'
  return '#34d399'
}

const SEVERITY_KEY = (score) => {
  if (score >= 75) return 'high'
  if (score >= 50) return 'elevated'
  if (score >= 25) return 'moderate'
  return 'low'
}

// Always-visible glanceable summary of the same score.risk_breakdown data
// RiskExplainer covers in depth — a row of icon tiles so the five
// contributing categories are readable at a glance without opening the
// collapsible explainer below it.
export default function KeyFactorTiles({ breakdown }) {
  const { t } = useLanguage()
  const categories = CATEGORY_ORDER.map((key) => [key, breakdown?.[key]]).filter(
    ([, cat]) => cat && cat.score != null
  )

  if (categories.length === 0) return null

  return (
    <div className="border-b border-border px-4 py-4 sm:px-5">
      <div className="mb-2.5 text-[0.67rem] font-semibold uppercase tracking-wide text-muted">
        {t('keyFactors.title')}
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {categories.map(([key, cat]) => {
          const color = SEVERITY_COLOR(cat.score)
          return (
            <div
              key={key}
              title={t(`categories.${key}.label`)}
              className="panel-tile group px-2.5 py-2.5 transition-all duration-200 hover:-translate-y-0.5 hover:border-[#3b2a5e]"
            >
              <div className="icon-badge h-6 w-6 text-[0.72rem] transition-transform duration-200 group-hover:scale-110">
                <span aria-hidden="true">{CATEGORY_ICONS[key]}</span>
              </div>
              <div className="mt-1.5 truncate text-[0.68rem] font-semibold text-slate-200">
                {t(`categories.${key}.short`)}
              </div>
              <div className="mt-0.5 flex items-baseline gap-1">
                <span className="font-mono text-sm font-extrabold tabular-nums" style={{ color }}>
                  {Math.round(cat.score)}
                </span>
                <span className="text-[0.62rem] text-muted">/100</span>
              </div>
              <div
                className="mt-1 inline-block rounded-full px-1.5 py-0.5 text-[0.58rem] font-bold uppercase tracking-wide"
                style={{ color, backgroundColor: `${color}22` }}
              >
                {t(`keyFactors.impact.${SEVERITY_KEY(cat.score)}`)}
              </div>
              {/* Deterministic one-line reading of where this percentile sits
                  in the stock's own history — see explain/readings.js. */}
              <p className="mt-2 text-[0.68rem] leading-relaxed text-muted">
                {t(`readings.factor.${factorReading(cat.score)}`)}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
