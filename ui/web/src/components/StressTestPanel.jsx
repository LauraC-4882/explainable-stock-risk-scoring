import { FlaskConical } from 'lucide-react'
import { useState } from 'react'
import { useLanguage } from '../i18n/LanguageContext'

const DELTA_COLOR = (delta) => {
  if (delta >= 20) return 'text-risk-extreme'
  if (delta >= 10) return 'text-risk-high'
  if (delta > 0) return 'text-risk-moderate'
  return 'text-muted'
}

const DELTA_BORDER = (delta) => {
  if (delta >= 20) return '#f43f5e'
  if (delta >= 10) return '#fb923c'
  if (delta > 0) return '#fbbf24'
  return '#2b1c45'
}

// Collapsible "what if a historical crisis recurred" panel, driven by
// score.stress_test (scoring/stress_test.py). The backend ships an English
// `label` and a pre-formatted English `narrative` per scenario; both are
// re-rendered here from the scenario *key* so a Chinese screen doesn't show
// two English sentences inside an otherwise translated card. The backend
// strings stay in the API response (other consumers read them) and are used
// as the fallback if the backend adds a scenario this locale file doesn't
// know yet — a missing i18next key resolves to its own path (see
// parseMissingKeyHandler in LanguageContext), which is what MISSING checks.
const MISSING = (value, key) => value === key

// Backend narrative formats the scores with Python float repr (93.0, not 93);
// keeping toFixed(1) here means the English sentence is byte-identical to what
// the API already produced.
const fmt = (n) => Number(n).toFixed(1)

export default function StressTestPanel({ stressTest }) {
  const { t } = useLanguage()
  const [open, setOpen] = useState(false)
  const scenarios = stressTest?.scenarios ? Object.entries(stressTest.scenarios) : []

  if (scenarios.length === 0) return null

  return (
    <div className="border-b border-border">
      <button
        onClick={() => setOpen((o) => !o)}
        className="group flex w-full items-center justify-between px-5 py-3 text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted transition-colors duration-150 hover:text-accent max-sm:text-[0.8rem]"
        aria-expanded={open}
      >
        <span className="inline-flex items-center gap-2">
          <span className="icon-badge h-7 w-7 transition-colors duration-150 group-hover:bg-accent/20">
            <FlaskConical aria-hidden="true" size={16} />
          </span>
          {t('stressTest.toggle')}
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
          <div className="space-y-3 px-5 pb-4">
            <p className="text-sm leading-relaxed text-slate-300">{t('stressTest.intro')}</p>
            <div className="space-y-2.5">
              {scenarios.map(([key, s]) => {
                const labelKey = `stressTest.scenario.${key}`
                const translated = t(labelKey)
                const label = MISSING(translated, labelKey) ? s.label : translated
                const narrative = MISSING(translated, labelKey)
                  ? s.narrative
                  : t('stressTest.narrative', {
                      label,
                      baseline: fmt(s.baseline_score),
                      stressed: fmt(s.stressed_score),
                      delta: `${s.delta >= 0 ? '+' : ''}${fmt(s.delta)}`,
                    })
                return (
                  <div
                    key={key}
                    className="rounded-lg border border-border border-l-2 bg-surface2/50 p-3 transition-colors duration-150 hover:bg-surface2"
                    style={{ borderLeftColor: DELTA_BORDER(s.delta) }}
                  >
                    <div className="text-xs font-semibold text-slate-200">{label}</div>
                    <div className="mt-1.5 flex items-baseline gap-1.5">
                      <span className="font-mono text-[0.7rem] text-muted">
                        {t('stressTest.baseline')} {s.baseline_score} →
                      </span>
                      <span className={`font-mono text-sm font-bold ${DELTA_COLOR(s.delta)}`}>
                        {s.stressed_score}
                      </span>
                      <span className={`font-mono text-[0.7rem] ${DELTA_COLOR(s.delta)}`}>
                        ({s.delta >= 0 ? '+' : ''}
                        {s.delta})
                      </span>
                    </div>
                    <p className="mt-1.5 text-[0.7rem] leading-relaxed text-muted">{narrative}</p>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
