import { Cpu } from 'lucide-react'
import { useState } from 'react'
import { useLanguage } from '../i18n/LanguageContext'
import ShapWaterfall from './ShapWaterfall'

// Collapsible SHAP feature-attribution panel for the secondary XGBoost
// downside-risk signal (models/explain.py). Rendered only when the backend
// actually has a fitted model and explanation for this request — a missing
// ml_drawdown_explanation means no model artefact was loaded, not an error.
export default function MLSignalPanel({ probability, explanation }) {
  const { t } = useLanguage()
  const [open, setOpen] = useState(false)

  if (probability == null || !explanation) return null

  const features = explanation.top_features || []
  // ml_drawdown_probability is already 0-100; calibrated_probability (when
  // present) is 0-1 — normalize both to the same 0-1 basis before display.
  const displayProb = explanation.calibrated_probability ?? probability / 100

  return (
    <div className="border-b border-border">
      <button
        onClick={() => setOpen((o) => !o)}
        className="group flex w-full items-center justify-between px-5 py-3 text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted transition-colors duration-150 hover:text-accent max-sm:text-[0.8rem]"
        aria-expanded={open}
      >
        <span className="inline-flex items-center gap-2">
          <span className="icon-badge h-7 w-7 transition-colors duration-150 group-hover:bg-accent/20">
            <Cpu aria-hidden="true" size={16} />
          </span>
          {t('mlSignal.toggle')}
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
            <div className="rounded-lg border border-accent/20 bg-gradient-to-br from-accent/10 via-surface2/40 to-rose/10 p-3">
              <p className="text-sm leading-relaxed text-slate-300">{t('mlSignal.intro')}</p>
              <div className="mt-2 text-xs text-slate-200">
                {t('mlSignal.probability')}{' '}
                <span className="font-mono font-bold text-accent">
                  {(displayProb * 100).toFixed(1)}%
                </span>
              </div>
            </div>

            {features.length > 0 && (
              <div className="pt-1">
                <div className="mb-2 text-[0.65rem] font-semibold uppercase tracking-wide text-muted">
                  {t('mlSignal.topFeatures')}
                </div>
                {/* Waterfall replaces the old magnitude bars: same features,
                    but now the DIRECTION and the running total are visible,
                    and an explicit "other features" bar closes the gap the
                    top-N list leaves. Only rendered while open so Recharts
                    doesn't measure a 0-height container. */}
                {open && <ShapWaterfall explanation={explanation} />}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
