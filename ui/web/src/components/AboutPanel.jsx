import {
  Cpu,
  Database,
  FlaskConical,
  LockKeyhole,
  Scale,
  ShieldCheck,
  TrendingUp,
  X,
} from 'lucide-react'
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
    { key: 'lenses', icon: TrendingUp },
    { key: 'ml', icon: Cpu },
    { key: 'stress', icon: FlaskConical },
    { key: 'explain', icon: Scale },
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
                      <LockKeyhole aria-hidden="true" size={16} />
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

          {/* ── What actually runs here ──
              This project is larger than what a free instance serves, so the
              site states which capabilities are live, which degrade on the free
              tier, and which exist only in the repository. Without this, the
              page would imply the whole stack is running — see the "no claim
              the deployment can't back" rule in the README. Each list was
              checked against the live deployment, not assumed. */}
          <section>
            <h3 className="heading-flourish mb-1.5 text-xl">{t('capabilities.title')}</h3>
            <p className="mb-4 text-[0.8rem] leading-relaxed text-muted">
              {t('capabilities.intro')}
            </p>

            <div className="space-y-3">
              {[
                {
                  key: 'live',
                  items: [
                    'composite',
                    'metrics',
                    'ml',
                    'garch',
                    'har',
                    'stress',
                    'outcomes',
                    'options',
                  ],
                  tone: 'border-up/30 bg-up/[0.06]',
                  dot: 'bg-up',
                  mark: '●',
                },
                {
                  key: 'degraded',
                  items: ['vix', 'fundamentals', 'news'],
                  tone: 'border-gold/30 bg-gold/[0.06]',
                  dot: 'bg-gold',
                  mark: '◐',
                },
                {
                  key: 'repo',
                  items: ['portfolio', 'backtest', 'governance', 'drift', 'simulation'],
                  tone: 'border-border bg-white/[0.02]',
                  dot: 'bg-muted',
                  mark: '○',
                },
              ].map(({ key, items, tone, dot, mark }) => (
                <div key={key} className={`rounded-xl border px-4 py-3.5 ${tone}`}>
                  <div className="flex items-center gap-2">
                    {/* Status is never colour-only: a filled/half/hollow glyph
                        and the heading text both carry it. */}
                    <span aria-hidden="true" className={`h-2 w-2 rounded-full ${dot}`} />
                    <h4 className="text-[0.85rem] font-semibold text-slate-100">
                      {t(`capabilities.${key}Title`)}
                    </h4>
                  </div>
                  <p className="mt-1 text-[0.74rem] leading-relaxed text-muted">
                    {t(`capabilities.${key}Note`)}
                  </p>
                  <ul className="mt-2.5 space-y-1">
                    {items.map((id) => (
                      <li
                        key={id}
                        className="flex items-start gap-2 text-[0.78rem] leading-relaxed text-slate-300"
                      >
                        <span aria-hidden="true" className="mt-[0.15rem] text-[0.6rem] text-muted">
                          {mark}
                        </span>
                        <span>{t(`capabilities.items.${id}`)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>

            <p className="mt-3 text-[0.74rem] leading-relaxed text-muted">
              {t('capabilities.verifyHint')}
            </p>
            <pre className="mt-1.5 overflow-x-auto rounded-lg border border-border bg-black/30 px-3 py-2 font-mono text-[0.68rem] leading-relaxed text-slate-300">
              pytest tests/ -q{'\n'}
              python -m stock_risk.simulation run
            </pre>
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
