import { CloudUpload } from 'lucide-react'
import { useLanguage } from '../i18n/LanguageContext'
import useColdStart from '../hooks/useColdStart'

// Shown only while a sleeping free-tier instance is booting (~60-100s measured).
// A warm instance answers /health in under a second, so this never renders in
// the normal case — see hooks/useColdStart for the grace period.
//
// role="status" + aria-live="polite" so a screen-reader user is told the page
// is waiting on a boot rather than being left in silence; the elapsed counter
// is aria-hidden so it doesn't re-announce every second.
export default function ColdStartBanner() {
  const { t } = useLanguage()
  const { waking, elapsed } = useColdStart()

  if (!waking) return null

  return (
    <div
      role="status"
      aria-live="polite"
      className="mx-auto mb-4 flex max-w-3xl items-start gap-3 rounded-xl border border-gold/30 bg-gold/[0.07] px-4 py-3"
    >
      <span className="icon-badge mt-0.5 h-8 w-8 flex-shrink-0">
        <CloudUpload aria-hidden="true" size={16} />
      </span>
      <span className="min-w-0">
        <span className="block text-[0.85rem] font-semibold text-slate-100">
          {t('coldStart.title')}
        </span>
        <span className="mt-0.5 block text-[0.78rem] leading-relaxed text-muted">
          {t('coldStart.body')}
        </span>
        {/* Progress against the measured ~100s boot, capped at 95% so the bar
            never claims completion the probe hasn't confirmed. Purely
            presentational — the app's own requests resume by themselves the
            moment the dyno answers, since fetch() just keeps waiting. */}
        <span className="mt-2 block h-1 overflow-hidden rounded-full bg-surface2">
          <span
            aria-hidden="true"
            className="block h-full rounded-full bg-gold transition-[width] duration-1000 ease-linear"
            style={{ width: `${Math.min(95, (elapsed / 100) * 100)}%` }}
          />
        </span>
        <span aria-hidden="true" className="mt-1 block font-mono text-[0.72rem] text-gold">
          {t('coldStart.elapsed', { seconds: elapsed })} · {t('coldStart.eta')}
        </span>
      </span>
    </div>
  )
}
