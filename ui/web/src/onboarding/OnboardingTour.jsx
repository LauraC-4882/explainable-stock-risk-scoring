import { ChartLineUp, Compass, Cpu, Flask, Gauge, HandWaving, Star } from '@phosphor-icons/react'
import { useState } from 'react'
import LanguageSwitcher from '../components/LanguageSwitcher'
import { useLanguage } from '../i18n/LanguageContext'
import { useOnboarding } from './OnboardingContext'

// Each step names what a section of the card tells you and, explicitly, how
// to use it when deciding what to do about a position — not just what the
// number is. Content lives in i18n so it's translated, not hardcoded here.
const STEPS = [
  { id: 'welcome', icon: HandWaving },
  { id: 'score', icon: Gauge },
  { id: 'breakdown', icon: Compass },
  { id: 'mlSignal', icon: Cpu },
  { id: 'stressTest', icon: Flask },
  { id: 'metrics', icon: ChartLineUp },
  { id: 'watchlist', icon: Star },
]

export default function OnboardingTour() {
  const { t } = useLanguage()
  const { open, closeTour } = useOnboarding()
  const [step, setStep] = useState(0)

  if (!open) return null

  const isLast = step === STEPS.length - 1
  const current = STEPS[step]

  function close() {
    setStep(0)
    closeTour()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/60 backdrop-blur-sm"
      style={{ animationDuration: '0.15s' }}
      onClick={close}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md animate-fade-in overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-black/50"
        style={{ animationDuration: '0.2s' }}
      >
        <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">
            {t('onboarding.title')}
          </span>
          {/* Language selector lives inside the tour too: it auto-opens on
              first visit, dimming the header (and its own switcher) behind
              this overlay — so a first-time visitor who wants 中文 can pick
              it right here without closing the tutorial first. Shares the
              same setLang, so switching here switches the whole app. */}
          <div className="flex items-center gap-2">
            <LanguageSwitcher />
            <button
              onClick={close}
              className="rounded-md px-1.5 py-0.5 text-base leading-none text-muted transition hover:bg-down/10 hover:text-down"
            >
              {t('onboarding.skip')}
            </button>
          </div>
        </div>

        <div
          key={current.id}
          className="animate-fade-in px-6 py-7"
          style={{ animationDuration: '0.25s' }}
        >
          <div className="icon-badge mb-4 h-12 w-12" aria-hidden="true">
            <current.icon size={28} />
          </div>
          <h3 className="mb-2.5 text-lg font-bold text-slate-100">
            {t(`onboarding.steps.${current.id}.title`)}
          </h3>
          <p className="text-sm leading-relaxed text-slate-300">
            {t(`onboarding.steps.${current.id}.body`)}
          </p>
        </div>

        <div className="flex items-center justify-between border-t border-border px-5 py-4">
          <div className="flex gap-1.5">
            {STEPS.map((s, i) => (
              <span
                key={s.id}
                className={`h-1.5 rounded-full transition-all duration-300 ${
                  i === step ? 'w-4 bg-accent' : 'w-1.5 bg-border'
                }`}
              />
            ))}
          </div>
          <div className="flex gap-2">
            {step > 0 && (
              <button
                onClick={() => setStep((s) => s - 1)}
                className="rounded-full border border-border px-4 py-1.5 text-xs font-semibold text-slate-200 transition-all duration-150 hover:border-accent hover:text-accent active:scale-95"
              >
                {t('onboarding.back')}
              </button>
            )}
            <button
              onClick={() => (isLast ? close() : setStep((s) => s + 1))}
              className="rounded-full bg-accent px-4 py-1.5 text-xs font-bold text-white shadow-lg shadow-accent/20 transition-all duration-150 hover:brightness-110 active:scale-95"
            >
              {isLast ? t('onboarding.done') : t('onboarding.next')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
