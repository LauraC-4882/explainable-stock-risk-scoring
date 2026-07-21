import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import { RiscoreIcon, RiscoreWordmark } from './Logo'

// Small self-contained popup used by all three footer links below — same
// center-modal chrome as AuthModal/CommunityPanel so it reads as one system,
// but plain-text content only (no form, no fetch).
function FooterModal({ title, onClose, children }) {
  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      style={{ animationDuration: '0.15s' }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="max-h-[80vh] w-full max-w-md animate-fade-in overflow-y-auto rounded-2xl border border-border bg-surface p-6 shadow-2xl shadow-black/50"
        style={{ animationDuration: '0.2s' }}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-100">{title}</h2>
          <button
            onClick={onClose}
            className="rounded-md px-1.5 py-0.5 text-base leading-none text-muted transition hover:bg-down/10 hover:text-down"
          >
            ✕
          </button>
        </div>
        <div className="space-y-3 text-sm leading-relaxed text-slate-300">{children}</div>
      </div>
    </div>
  )
}

export default function Footer() {
  const { t } = useLanguage()
  const { openCommunityPanel } = useAuth()
  const [modal, setModal] = useState(null) // 'privacy' | 'license' | 'contact' | null

  return (
    <footer className="relative z-10 mt-12 px-6 py-9 sm:px-8">
      {/* Gradient hairline instead of a flat border — the one accent that
          reads "deliberate surface" against the cosmic backdrop. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/40 to-transparent" />
      <div className="mx-auto flex w-full max-w-[1360px] flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-2.5">
          <RiscoreIcon size={28} idPrefix="ftr" />
          <div>
            <RiscoreWordmark className="text-base" />
            <p className="mt-0.5 text-[0.68rem] text-muted">
              © {new Date().getFullYear()} Riscore · {t('footer.tagline')}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-x-10 gap-y-4 text-xs">
          <div className="flex flex-col gap-1.5">
            <span className="font-semibold uppercase tracking-wide text-slate-300">
              {t('footer.legal')}
            </span>
            <button
              onClick={() => setModal('privacy')}
              className="text-left text-muted transition hover:text-accent"
            >
              {t('footer.privacy')}
            </button>
            <button
              onClick={() => setModal('license')}
              className="text-left text-muted transition hover:text-accent"
            >
              {t('footer.license')}
            </button>
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="font-semibold uppercase tracking-wide text-slate-300">
              {t('footer.support')}
            </span>
            <button
              onClick={() => setModal('contact')}
              className="text-left text-muted transition hover:text-accent"
            >
              {t('footer.contact')}
            </button>
          </div>
        </div>
      </div>

      {modal === 'privacy' && (
        <FooterModal title={t('footer.privacyTitle')} onClose={() => setModal(null)}>
          <p>{t('footer.privacyBody1')}</p>
          <p>{t('footer.privacyBody2')}</p>
        </FooterModal>
      )}

      {modal === 'license' && (
        <FooterModal title={t('footer.licenseTitle')} onClose={() => setModal(null)}>
          <p>{t('footer.licenseBody1')}</p>
          <p>{t('footer.licenseBody2')}</p>
        </FooterModal>
      )}

      {modal === 'contact' && (
        <FooterModal title={t('footer.contactTitle')} onClose={() => setModal(null)}>
          <p>{t('footer.contactBody')}</p>
          <button
            onClick={() => {
              setModal(null)
              openCommunityPanel()
            }}
            className="mt-2 w-full rounded-xl bg-accent py-2.5 text-sm font-bold text-white shadow-lg shadow-accent/20 transition-all duration-150 hover:brightness-110 active:scale-[0.98]"
          >
            {t('footer.openCommunity')}
          </button>
        </FooterModal>
      )}
    </footer>
  )
}
