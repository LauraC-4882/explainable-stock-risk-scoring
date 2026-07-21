import {
  ChartLineUp,
  Cpu,
  Database,
  Flask,
  LockKey,
  Scales,
  ShieldCheck,
  X,
} from '@phosphor-icons/react'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import { RiscoreIcon, RiscoreWordmark } from './Logo'

// "About / How it works" — the site's trust page. Everything here describes
// what the product already does (pipeline, validation numbers, security
// practices, limitations); it must never claim more than the README/model
// docs can back up. Copy lives in i18n (about.*) in both languages.
export default function AboutPanel() {
  const { t } = useLanguage()
  const { aboutPanelOpen, closeAboutPanel } = useAuth()

  if (!aboutPanelOpen) return null

  const PIPELINE = [
    { key: 'data', icon: Database },
    { key: 'lenses', icon: ChartLineUp },
    { key: 'ml', icon: Cpu },
    { key: 'stress', icon: Flask },
    { key: 'explain', icon: Scales },
  ]

  const STATS = ['stocks', 'years', 'auc', 'weight']

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      style={{ animationDuration: '0.15s' }}
      onClick={closeAboutPanel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[88vh] w-full max-w-3xl animate-fade-in flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-black/50"
        style={{ animationDuration: '0.2s' }}
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-lg font-bold text-slate-100">{t('about.title')}</h2>
          <button
            onClick={closeAboutPanel}
            className="rounded-md px-1.5 py-0.5 text-base leading-none text-muted transition hover:bg-down/10 hover:text-down"
          >
            <X aria-hidden="true" size={14} color="currentColor" />
          </button>
        </div>

        <div className="flex-1 space-y-8 overflow-y-auto px-6 py-6 sm:px-8">
          {/* ── What is Riscore ── */}
          <section className="flex flex-col items-center gap-3 text-center">
            <RiscoreIcon size={64} idPrefix="about" />
            <RiscoreWordmark className="text-3xl" />
            <p className="max-w-xl text-sm leading-relaxed text-slate-300">{t('about.intro')}</p>
          </section>

          {/* ── How the score is built ── */}
          <section>
            <h3 className="heading-flourish mb-4 text-xl">{t('about.pipelineTitle')}</h3>
            <ol className="space-y-3">
              {PIPELINE.map(({ key, icon: Icon }, i) => (
                <li key={key} className="panel-tile flex items-start gap-3.5 p-3.5">
                  <span className="icon-badge relative h-9 w-9 flex-shrink-0">
                    <Icon aria-hidden="true" size={18} />
                    <span className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-accent text-[0.6rem] font-bold text-white">
                      {i + 1}
                    </span>
                  </span>
                  <span>
                    <span className="block text-sm font-semibold text-slate-100">
                      {t(`about.pipeline.${key}.title`)}
                    </span>
                    <span className="mt-0.5 block text-[0.8rem] leading-relaxed text-muted">
                      {t(`about.pipeline.${key}.body`)}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          </section>

          {/* ── Validation, in numbers ── */}
          <section>
            <h3 className="heading-flourish mb-1.5 text-xl">{t('about.validationTitle')}</h3>
            <p className="mb-4 text-[0.8rem] leading-relaxed text-muted">
              {t('about.validationIntro')}
            </p>
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
              {STATS.map((key) => (
                <div key={key} className="panel-tile px-3 py-3 text-center">
                  <div className="font-display text-2xl font-bold text-accent2">
                    {t(`about.stats.${key}.value`)}
                  </div>
                  <div className="mt-1 text-[0.68rem] leading-snug text-muted">
                    {t(`about.stats.${key}.label`)}
                  </div>
                </div>
              ))}
            </div>
            <ul className="mt-4 list-disc space-y-1.5 pl-5 text-[0.8rem] leading-relaxed text-slate-300">
              <li>{t('about.honesty1')}</li>
              <li>{t('about.honesty2')}</li>
              <li>{t('about.honesty3')}</li>
            </ul>
          </section>

          {/* ── Security & privacy ── */}
          <section>
            <h3 className="heading-flourish mb-4 text-xl">{t('about.securityTitle')}</h3>
            <div className="grid gap-2.5 sm:grid-cols-2">
              {['accounts', 'data', 'community', 'transparency'].map((key) => (
                <div key={key} className="panel-tile flex items-start gap-3 p-3.5">
                  <span className="icon-badge h-8 w-8 flex-shrink-0">
                    {key === 'accounts' || key === 'data' ? (
                      <LockKey aria-hidden="true" size={16} />
                    ) : (
                      <ShieldCheck aria-hidden="true" size={16} />
                    )}
                  </span>
                  <span>
                    <span className="block text-[0.83rem] font-semibold text-slate-100">
                      {t(`about.security.${key}.title`)}
                    </span>
                    <span className="mt-0.5 block text-[0.76rem] leading-relaxed text-muted">
                      {t(`about.security.${key}.body`)}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </section>

          {/* ── Responsible use ── */}
          <section className="rounded-xl border border-gold/25 bg-gold/[0.06] px-4 py-3.5">
            <p className="text-[0.8rem] italic leading-relaxed text-slate-300">
              {t('about.responsible')}
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
