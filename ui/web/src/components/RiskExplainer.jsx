import { GraduationCap } from '@phosphor-icons/react'
import { useState } from 'react'
import { CATEGORY_ORDER, NEUTRAL_COLOR, isFlooredOut } from '../data/categoryMeta'
import { useLanguage } from '../i18n/LanguageContext'
import InfoTooltip from './InfoTooltip'

const BAR_COLOR = (score) => {
  if (score >= 75) return '#f43f5e'
  if (score >= 50) return '#fb923c'
  if (score >= 25) return '#fbbf24'
  return '#34d399'
}

// Beginner-friendly, expandable "what does this score mean" panel. Collapsed by
// default so it doesn't crowd the card — except in the wide single-stock layout
// (defaultOpen), where the mockup shows it expanded and there's room for it.
export default function RiskExplainer({ riskLabel, breakdown, defaultOpen = false }) {
  const { t } = useLanguage()
  const [open, setOpen] = useState(defaultOpen)
  const categories = CATEGORY_ORDER.map((key) => [key, breakdown?.[key]]).filter(
    ([, cat]) => cat && cat.score != null
  )

  return (
    <div className="border-b border-border">
      <button
        onClick={() => setOpen((o) => !o)}
        className="group flex w-full items-center justify-between px-5 py-3 text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted transition-colors duration-150 hover:text-accent max-sm:text-[0.8rem]"
        aria-expanded={open}
      >
        <span className="inline-flex items-center gap-2">
          <span className="icon-badge h-7 w-7 transition-colors duration-150 group-hover:bg-accent/20">
            <GraduationCap aria-hidden="true" size={16} />
          </span>
          {t('explainer.toggle')}
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
                    contribution={cat.contribution}
                    flooredOut={isFlooredOut(cat)}
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

function CategoryRow({ catKey, score, contribution, flooredOut, weight, open, t }) {
  // This list is headed "what makes up the score", so the bar has to show what
  // the composite actually used — the floored contribution — not the raw
  // percentile. Both numbers are printed in the label so nothing is hidden:
  // showing only the raw 12/100 here drew a reassuring green bar for a
  // category that in fact contributed a neutral 50.
  const barValue = flooredOut && contribution != null ? contribution : score
  const barColor = flooredOut ? NEUTRAL_COLOR : BAR_COLOR(score)
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-xs">
        {/* Icon dropped on purpose — the tiles above already carry the
            category iconography; here plain text keeps the list clean. */}
        <span className="flex min-w-0 items-center gap-1.5 font-semibold text-slate-200">
          {t(`categories.${catKey}.label`)}
          {/* Plain-language gloss right next to the term, so the row reads
              even for someone who has never met the word "drawdown". */}
          <span className="truncate text-[0.68rem] font-normal text-muted">
            · {t(`categories.${catKey}.plainShort`)}
          </span>
          <InfoTooltip text={t(`categories.${catKey}.plain`)} align="left" />
        </span>
        <span className="flex-shrink-0 font-mono text-[0.7rem] text-muted">
          {Math.round(score)}/100
          {flooredOut && (
            <span className="text-accent2/80"> → {t('explainer.counted', { value: 50 })}</span>
          )}{' '}
          · {Math.round(weight * 100)}% {t('explainer.weight')}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface2">
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{ width: open ? `${barValue}%` : '0%', backgroundColor: barColor }}
        />
      </div>
    </div>
  )
}
