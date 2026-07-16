import { useState } from 'react'
import { CATEGORY_ICONS, CATEGORY_ORDER } from '../data/categoryMeta'
import { useLanguage } from '../i18n/LanguageContext'
import InfoTooltip from './InfoTooltip'

const BAR_COLOR = (score) => {
  if (score >= 75) return '#f85149'
  if (score >= 50) return '#f0883e'
  if (score >= 25) return '#d29922'
  return '#3fb950'
}

// Beginner-friendly, expandable "what does this score mean" panel. Collapsed by
// default so it doesn't crowd the card for users who already know what they're doing.
export default function RiskExplainer({ riskLabel, breakdown }) {
  const { t } = useLanguage()
  const [open, setOpen] = useState(false)
  const categories = CATEGORY_ORDER.map((key) => [key, breakdown?.[key]]).filter(
    ([, cat]) => cat && cat.score != null
  )

  return (
    <div className="border-b border-border">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-5 py-3 text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted transition-colors duration-150 hover:text-accent"
        aria-expanded={open}
      >
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true">{'\u{1F393}'}</span> {t('explainer.toggle')}
        </span>
        <svg
          className={`h-3 w-3 flex-shrink-0 transition-transform duration-300 ease-out ${open ? 'rotate-180' : ''}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      <div
        className="grid transition-[grid-template-rows] duration-300 ease-in-out"
        style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
      >
        <div className="overflow-hidden">
          <div className="space-y-3.5 px-5 pb-4 text-sm">
            <p className="leading-relaxed text-slate-300">{t('explainer.intro')}</p>
            {riskLabel && (
              <p className="leading-relaxed text-slate-300">
                <span className="font-semibold text-slate-100">{t(`riskLabel.${riskLabel}`)}:</span>{' '}
                {t(`labelExplanation.${riskLabel}`)}
              </p>
            )}

            {categories.length > 0 && (
              <div className="space-y-3 pt-1">
                <div className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">
                  {t('explainer.makeup')}
                </div>
                {categories.map(([key, cat]) => (
                  <CategoryRow
                    key={key}
                    catKey={key}
                    score={cat.score}
                    weight={cat.weight}
                    open={open}
                    t={t}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function CategoryRow({ catKey, score, weight, open, t }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-xs">
        <span className="flex items-center gap-1.5 font-semibold text-slate-200">
          <span aria-hidden="true">{CATEGORY_ICONS[catKey]}</span>
          {t(`categories.${catKey}.label`)}
          <InfoTooltip text={t(`categories.${catKey}.plain`)} align="left" />
        </span>
        <span className="flex-shrink-0 font-mono text-[0.7rem] text-muted">
          {Math.round(score)}/100 · {Math.round(weight * 100)}% {t('explainer.weight')}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface2">
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{ width: open ? `${score}%` : '0%', backgroundColor: BAR_COLOR(score) }}
        />
      </div>
    </div>
  )
}
