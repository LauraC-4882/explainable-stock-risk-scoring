import { useState } from 'react'
import { useLanguage } from '../i18n/LanguageContext'

// Collapsible SHAP feature-attribution panel for the secondary XGBoost
// downside-risk signal (models/explain.py). Rendered only when the backend
// actually has a fitted model and explanation for this request — a missing
// ml_drawdown_explanation means no model artefact was loaded, not an error.
export default function MLSignalPanel({ probability, explanation }) {
  const { t } = useLanguage()
  const [open, setOpen] = useState(false)

  if (probability == null || !explanation) return null

  const features = explanation.top_features || []
  const maxAbs = Math.max(...features.map((f) => Math.abs(f.shap_contribution)), 0.0001)
  // ml_drawdown_probability is already 0-100; calibrated_probability (when
  // present) is 0-1 — normalize both to the same 0-1 basis before display.
  const displayProb = explanation.calibrated_probability ?? probability / 100

  return (
    <div className="border-b border-border">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-5 py-3 text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted transition-colors duration-150 hover:text-accent"
        aria-expanded={open}
      >
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true">{'\u{1F916}'}</span> {t('mlSignal.toggle')}
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
            <p className="text-sm leading-relaxed text-slate-300">{t('mlSignal.intro')}</p>

            <div className="text-xs text-slate-200">
              {t('mlSignal.probability')}{' '}
              <span className="font-mono font-bold">{(displayProb * 100).toFixed(1)}%</span>
            </div>

            {features.length > 0 && (
              <div className="space-y-2.5 pt-1">
                <div className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">
                  {t('mlSignal.topFeatures')}
                </div>
                {features.map((f) => {
                  const positive = f.shap_contribution >= 0
                  return (
                    <div key={f.feature}>
                      <div className="mb-0.5 flex items-center justify-between gap-2 text-[0.7rem]">
                        <span className="truncate font-mono text-slate-300">{f.feature}</span>
                        <span
                          className={`flex-shrink-0 font-mono ${positive ? 'text-risk-high' : 'text-risk-low'}`}
                        >
                          {positive ? '+' : ''}
                          {f.shap_contribution.toFixed(3)}
                        </span>
                      </div>
                      <div className="h-1 overflow-hidden rounded-full bg-surface2">
                        <div
                          className={`h-full rounded-full ${positive ? 'bg-risk-high' : 'bg-risk-low'}`}
                          style={{
                            width: open
                              ? `${Math.min(100, (Math.abs(f.shap_contribution) / maxAbs) * 100)}%`
                              : '0%',
                          }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
