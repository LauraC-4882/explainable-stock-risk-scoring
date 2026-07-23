import { Cpu, ExternalLink, X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'

// The stack page lists what the product ACTUALLY runs — assembled from
// package.json and requirements.txt, not from aspiration. Metrics follow the
// same rule: the walk-forward AUC is the repo's published 0.671 (56 tickers x
// 5y), not a rounder number, and the "freshness" figures are the real cache
// TTLs from config.py. A stack page that flatters is worse than none.
const STACK = [
  { key: 'react', url: 'https://react.dev' },
  { key: 'tailwind', url: 'https://tailwindcss.com' },
  { key: 'recharts', url: 'https://recharts.org' },
  { key: 'framer', url: 'https://www.framer.com/motion/' },
  { key: 'i18next', url: 'https://www.i18next.com' },
  { key: 'fastapi', url: 'https://fastapi.tiangolo.com' },
  { key: 'sqlmodel', url: 'https://sqlmodel.tiangolo.com' },
  { key: 'xgboost', url: 'https://xgboost.readthedocs.io' },
  { key: 'shap', url: 'https://shap.readthedocs.io' },
  { key: 'arch', url: 'https://arch.readthedocs.io' },
  { key: 'data', url: 'https://twelvedata.com' },
  { key: 'render', url: 'https://render.com' },
]

const METRICS = ['auc', 'scoreCache', 'dataCache', 'tests']

const REPO_URL = 'https://github.com/LauraC-4882/explainable-stock-risk-scoring'

export default function TechStackPanel() {
  const { t } = useLanguage()
  const { techPanelOpen, closeTechPanel } = useAuth()
  const closeRef = useRef(null)

  useEffect(() => {
    if (!techPanelOpen) return undefined
    closeRef.current?.focus()
    const onKey = (e) => {
      if (e.key === 'Escape') closeTechPanel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [techPanelOpen, closeTechPanel])

  // No live GitHub stats widget: the app ships a strict connect-src CSP
  // (security/headers.py), and api.github.com is rightly not on it. Loosening
  // a security header to decorate a panel would invert the priorities — the
  // static link below is enough.
  if (!techPanelOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      style={{ animationDuration: '0.15s' }}
      onClick={closeTechPanel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="tech-title"
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[88vh] w-full max-w-3xl animate-fade-in flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-black/50"
        style={{ animationDuration: '0.2s' }}
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 id="tech-title" className="flex items-center gap-2 text-lg font-bold text-slate-100">
            <Cpu aria-hidden="true" size={18} />
            {t('tech.title')}
          </h2>
          <button
            ref={closeRef}
            onClick={closeTechPanel}
            aria-label={t('replay.close')}
            className="rounded-md px-1.5 py-0.5 text-base leading-none text-muted transition hover:bg-down/10 hover:text-down"
          >
            <X aria-hidden="true" size={14} color="currentColor" />
          </button>
        </div>

        <div className="flex-1 space-y-7 overflow-y-auto px-6 py-6 sm:px-8">
          <p className="text-[0.82rem] leading-relaxed text-muted">{t('tech.intro')}</p>

          {/* ── Honest performance metrics ── */}
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            {METRICS.map((key) => (
              <div key={key} className="panel-tile px-3 py-3 text-center">
                <div className="font-mono text-lg font-bold text-accent2">
                  {t(`tech.metrics.${key}.value`)}
                </div>
                <div className="mt-1 text-[0.66rem] leading-snug text-muted">
                  {t(`tech.metrics.${key}.label`)}
                </div>
              </div>
            ))}
          </div>

          {/* ── The stack ── */}
          <div className="grid gap-2.5 sm:grid-cols-2">
            {STACK.map(({ key, url }) => (
              <a
                key={key}
                href={url}
                target="_blank"
                rel="noreferrer"
                className="panel-tile group flex items-start justify-between gap-3 p-3.5 transition hover:border-accent/40"
              >
                <span>
                  <span className="block text-[0.85rem] font-semibold text-slate-100">
                    {t(`tech.stack.${key}.name`)}
                  </span>
                  <span className="mt-0.5 block text-[0.74rem] leading-relaxed text-muted">
                    {t(`tech.stack.${key}.why`)}
                  </span>
                </span>
                <ExternalLink
                  aria-hidden="true"
                  size={13}
                  className="mt-1 flex-shrink-0 text-muted transition group-hover:text-accent"
                />
              </a>
            ))}
          </div>

          {/* ── Repo ── */}
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className="panel-tile flex items-center justify-between gap-3 p-3.5 transition hover:border-accent/40"
          >
            <span className="text-[0.82rem] font-semibold text-slate-100">{t('tech.repo')}</span>
            <span className="font-mono text-[0.72rem] text-muted">GitHub →</span>
          </a>
        </div>
      </div>
    </div>
  )
}
