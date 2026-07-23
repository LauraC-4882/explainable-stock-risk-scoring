import { BookOpen, Warning, X } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import { riskColor } from '../utils'

// Educational panel for newer investors.
//
// It exists because the platform's own simulated-user evaluation measured
// financial literacy as the dominant comprehension disparity (low-literacy
// users scored 0.24 against 0.70 for professionals), and found the raw factor
// attribution effectively unreadable for novices. The single most common
// misreading it surfaced — treating an 0-100 score as a probability of loss —
// is what section 1 is built to attack directly.
//
// Two deliberate constraints:
//
// * Bands mirror the BACKEND thresholds (25 / 50 / 75 -> LOW / MODERATE /
//   HIGH / EXTREME, see settings.risk_low_max and scorer.RISK_LABELS). A
//   teaching page that used different cut-offs from the product would be
//   teaching users something the app then contradicts.
// * Factor copy is READ from the shared `categories.*` i18n keys rather than
//   restated here, so Learn cannot drift away from what the card explains.
//
// Interactivity uses native <input type="range"> and <details>, which are
// keyboard-operable and screen-reader-announced for free — the accessibility
// gaps the same evaluation flagged in the older modals.

// Mirrors scoring/risk_categories.CATEGORY_WEIGHTS.
const FACTORS = [
  { key: 'volatility', weight: 25 },
  { key: 'tail', weight: 25 },
  { key: 'drawdown', weight: 20 },
  { key: 'sensitivity', weight: 15, twoSided: true },
  { key: 'liquidity', weight: 15, twoSided: true },
]

const GLOSSARY_TERMS = [
  'riskScore', 'percentile', 'volatility', 'downsideDeviation', 'var', 'cvar',
  'drawdown', 'maxDrawdown', 'beta', 'liquidity', 'amihud', 'skew', 'kurtosis',
  'garch', 'har', 'impliedVolatility', 'stressTest', 'shap', 'calibration',
  'breachRate', 'concentration', 'regime',
]

// Same cut-offs the backend applies; see module comment.
export function bandForScore(score) {
  if (score < 25) return 'LOW'
  if (score < 50) return 'MODERATE'
  if (score < 75) return 'HIGH'
  return 'EXTREME'
}

export default function LearnPanel() {
  const { t } = useLanguage()
  const { learnPanelOpen, closeLearnPanel } = useAuth()
  const [score, setScore] = useState(62)
  const closeRef = useRef(null)

  useEffect(() => {
    if (!learnPanelOpen) return undefined
    closeRef.current?.focus()
    const onKey = (e) => {
      if (e.key === 'Escape') closeLearnPanel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [learnPanelOpen, closeLearnPanel])

  if (!learnPanelOpen) return null

  const band = bandForScore(score)
  const color = riskColor(band)

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      style={{ animationDuration: '0.15s' }}
      onClick={closeLearnPanel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="learn-title"
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[88vh] w-full max-w-3xl animate-fade-in flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-black/50"
        style={{ animationDuration: '0.2s' }}
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 id="learn-title" className="flex items-center gap-2 text-lg font-bold text-slate-100">
            <BookOpen aria-hidden="true" size={18} />
            {t('learn.title')}
          </h2>
          <button
            ref={closeRef}
            onClick={closeLearnPanel}
            aria-label={t('replay.close')}
            className="rounded-md px-1.5 py-0.5 text-base leading-none text-muted transition hover:bg-down/10 hover:text-down"
          >
            <X aria-hidden="true" size={14} color="currentColor" />
          </button>
        </div>

        <div className="flex-1 space-y-8 overflow-y-auto px-6 py-6 sm:px-8">
          <p className="text-[0.82rem] leading-relaxed text-muted">{t('learn.intro')}</p>

          {/* ── 1. What is a risk score? ── */}
          <section>
            <h3 className="heading-flourish mb-1.5 text-xl">{t('learn.tryTitle')}</h3>
            <p className="mb-4 text-[0.8rem] leading-relaxed text-muted">{t('learn.tryBody')}</p>

            <div className="panel-tile px-4 py-4">
              <label htmlFor="learn-score" className="text-[0.7rem] uppercase tracking-wide text-muted">
                {t('learn.tryLabel')}
              </label>
              <div className="mt-2 flex items-baseline gap-3">
                <span
                  className="font-display text-4xl font-bold tabular-nums"
                  style={{ color }}
                  data-testid="learn-score-value"
                >
                  {score}
                </span>
                <span className="text-sm text-muted">/ 100</span>
                {/* Band is text + colour, never colour alone. */}
                <span
                  className="rounded px-2 py-0.5 text-[0.68rem] font-bold"
                  style={{ color, border: `1px solid ${color}55` }}
                  data-testid="learn-band"
                >
                  {t(`riskLabel.${band}`)}
                </span>
              </div>
              <input
                id="learn-score"
                type="range"
                min="0"
                max="100"
                value={score}
                onChange={(e) => setScore(Number(e.target.value))}
                aria-valuetext={`${score} — ${t(`riskLabel.${band}`)}`}
                className="mt-3 w-full accent-accent"
              />
              <p className="mt-2 text-[0.8rem] leading-relaxed text-slate-300">
                {t(`labelExplanation.${band}`)}
              </p>
            </div>

            <div className="mt-3 rounded-xl border border-down/30 bg-down/[0.07] px-4 py-3.5">
              <p className="flex items-start gap-2 text-[0.8rem] font-semibold text-slate-100">
                <Warning aria-hidden="true" size={16} className="mt-0.5 flex-shrink-0" />
                {t('learn.notProbTitle')}
              </p>
              <p className="mt-1 text-[0.78rem] leading-relaxed text-slate-300">
                {t('learn.notProb')}
              </p>
              <p className="mt-1.5 text-[0.78rem] leading-relaxed text-muted">
                {t('learn.notCompare')}
              </p>
            </div>
          </section>

          {/* ── 2. Each factor ── */}
          <section>
            <h3 className="heading-flourish mb-1.5 text-xl">{t('learn.factorsTitle')}</h3>
            <p className="mb-4 text-[0.8rem] leading-relaxed text-muted">
              {t('learn.factorsBody')}
            </p>
            <ul className="space-y-2.5">
              {FACTORS.map(({ key, weight, twoSided }) => (
                <li key={key} className="panel-tile p-3.5">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-[0.85rem] font-semibold text-slate-100">
                      {t(`categories.${key}.label`)}
                    </span>
                    <span className="font-mono text-[0.7rem] text-muted">
                      {weight}% {t('learn.weightLabel')}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[0.78rem] text-accent2">
                    {t(`categories.${key}.plainShort`)}
                  </p>
                  <p className="mt-1 text-[0.76rem] leading-relaxed text-muted">
                    {t(`categories.${key}.plain`)}
                  </p>
                  {twoSided ? (
                    <p className="mt-1.5 text-[0.72rem] italic leading-relaxed text-gold">
                      {t('learn.twoSidedNote')}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>

          {/* ── 3. Stress tests ── */}
          <section>
            <h3 className="heading-flourish mb-1.5 text-xl">{t('learn.stressTitle')}</h3>
            <p className="text-[0.8rem] leading-relaxed text-muted">{t('learn.stressBody')}</p>
          </section>

          {/* ── 4. Risk is not "bad" ── */}
          <section>
            <h3 className="heading-flourish mb-1.5 text-xl">{t('learn.riskReturnTitle')}</h3>
            <p className="text-[0.8rem] leading-relaxed text-muted">{t('learn.riskReturnBody')}</p>
            <p className="mt-3 rounded-xl border border-gold/25 bg-gold/[0.06] px-4 py-3 text-[0.8rem] italic leading-relaxed text-slate-300">
              {t('learn.riskReturnWarn')}
            </p>
          </section>

          {/* ── 5. Glossary ── */}
          <section>
            <h3 className="heading-flourish mb-1.5 text-xl">{t('learn.glossaryTitle')}</h3>
            <p className="mb-3 text-[0.8rem] leading-relaxed text-muted">
              {t('learn.glossaryBody')}
            </p>
            <div className="space-y-1.5">
              {GLOSSARY_TERMS.map((term) => (
                <details key={term} className="panel-tile px-3.5 py-2.5">
                  <summary className="cursor-pointer text-[0.8rem] font-semibold text-slate-100 marker:text-muted">
                    {t(`learn.terms.${term}`).split('—')[0].trim()}
                  </summary>
                  <p className="mt-1.5 text-[0.76rem] leading-relaxed text-muted">
                    {t(`learn.terms.${term}`)}
                  </p>
                </details>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
