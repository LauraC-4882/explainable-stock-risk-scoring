import { CATEGORY_ICONS, CATEGORY_ORDER, NEUTRAL_COLOR, isFlooredOut } from '../data/categoryMeta'
import { factorReading } from '../explain/readings'
import { useLanguage } from '../i18n/LanguageContext'
import InfoTooltip from './InfoTooltip'

const SEVERITY_COLOR = (score) => {
  if (score >= 75) return '#f43f5e'
  if (score >= 50) return '#fb923c'
  if (score >= 25) return '#fbbf24'
  return '#34d399'
}

// A floored-out two-sided category never renders green. Green is this card's
// "reassuringly safe" colour, and a low reading here is not that: a near-zero
// beta means the stock sits out rallies as well as selloffs, and very low
// illiquidity just means it trades cheaply. Grey-blue reads as "nothing to
// flag" rather than "good", and the tile says so in words too rather than
// leaving the colour to carry it.
const tileColor = (cat) => (isFlooredOut(cat) ? NEUTRAL_COLOR : SEVERITY_COLOR(cat.score))

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
      {/* Flourish serif title carries the design here — no icon needed. */}
      <div className="heading-flourish mb-2.5 text-base">{t('keyFactors.title')}</div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {categories.map(([key, cat]) => {
          const twoSided = Boolean(cat.two_sided)
          // Below-neutral two-sided readings are floored out of the composite
          // by the backend, so the tile says the score was left unchanged
          // instead of letting a low number look like it earned a discount.
          const flooredOut = isFlooredOut(cat)
          const color = tileColor(cat)
          const Icon = CATEGORY_ICONS[key]
          return (
            <div
              key={key}
              title={t(`categories.${key}.label`)}
              className="panel-tile group px-2.5 py-2.5 transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/40"
            >
              <div className="icon-badge h-7 w-7 transition-transform duration-200 group-hover:scale-110">
                <Icon aria-hidden="true" size={16} />
              </div>
              {/* max-sm: bumps — the root font-size lift (index.css) isn't
                  enough for these micro-labels; phones get a full size up. */}
              <div className="mt-1.5 flex items-center gap-1 text-[0.68rem] font-semibold text-slate-200 max-sm:text-[0.8rem]">
                <span className="truncate">{t(`categories.${key}.short`)}</span>
                {/* Second tier: the technical definition (actual inputs and
                    windows) for anyone who wants it, without pushing jargon
                    at users who don't. */}
                <InfoTooltip text={t(`categories.${key}.plain`)} align="left" />
              </div>
              {/* The everyday question this factor answers, always visible —
                  the finance term alone ("drawdown", "tail risk") told users
                  nothing, and most never hover to find out. */}
              <div className="mt-0.5 text-[0.6rem] leading-snug text-muted max-sm:text-[0.72rem]">
                {t(`categories.${key}.plainShort`)}
              </div>
              <div className="mt-1 flex items-baseline gap-1">
                <span
                  className="font-mono text-sm font-extrabold tabular-nums max-sm:text-base"
                  style={{ color }}
                >
                  {Math.round(cat.score)}
                </span>
                <span className="text-[0.62rem] text-muted">/100</span>
              </div>
              <div
                className="mt-1 inline-block rounded-full px-1.5 py-0.5 text-[0.58rem] font-bold uppercase tracking-wide"
                style={{ color, backgroundColor: `${color}22` }}
              >
                {flooredOut
                  ? t('keyFactors.impact.none')
                  : t(`keyFactors.impact.${SEVERITY_KEY(cat.score)}`)}
              </div>
              {/* Deterministic one-line reading of where this percentile sits
                  in the stock's own history — see explain/readings.js.
                  Two-sided categories get their own wording: the generic
                  "quieter than normal, one of the things keeping the score
                  down" copy is actively wrong for them. */}
              <p className="mt-2 text-[0.68rem] leading-relaxed text-muted max-sm:text-[0.78rem]">
                {t(
                  twoSided
                    ? `readings.twoSided.${key}.${factorReading(cat.score)}`
                    : `readings.factor.${factorReading(cat.score)}`
                )}
              </p>
              {flooredOut && (
                <p className="mt-1.5 text-[0.62rem] leading-relaxed text-accent2/80 max-sm:text-[0.74rem]">
                  {t('keyFactors.flooredNote')}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
