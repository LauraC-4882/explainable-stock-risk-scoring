import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import LanguageSwitcher from './LanguageSwitcher'
import { RiscoreIcon, RiscoreWordmark } from './Logo'

export default function Header() {
  const { t } = useLanguage()
  const { user, watchlist, logout, openAuthModal, openWatchlistPanel } = useAuth()

  return (
    <header className="relative z-10 overflow-hidden border-b border-border bg-gradient-to-br from-surface via-[#140d20] to-[#1a1030] px-6 py-4 sm:px-8">
      <div className="pointer-events-none absolute -top-24 left-1/3 h-64 w-64 rounded-full bg-accent/10 blur-3xl" />
      <div className="relative flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="drop-shadow-[0_0_14px_rgba(192,132,252,0.35)]">
            <RiscoreIcon size={46} idPrefix="hdr" />
          </div>
          <div>
            <h1 className="leading-none">
              <RiscoreWordmark className="text-[1.55rem] sm:text-3xl" />
            </h1>
            <p className="mt-1 text-[0.7rem] tracking-wide text-muted sm:text-xs">
              {t('header.subtitle')}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {user ? (
            <>
              <button
                onClick={openWatchlistPanel}
                className="flex items-center gap-1.5 rounded-full border border-border px-3.5 py-1.5 text-xs font-semibold text-slate-200 transition-all duration-150 hover:border-accent hover:text-accent active:scale-95"
              >
                <span aria-hidden="true">★</span> {t('watchlist.button')}
                {watchlist.length > 0 && (
                  <span className="rounded-full bg-accent/20 px-1.5 py-0.5 text-[0.65rem] text-accent">
                    {watchlist.length}
                  </span>
                )}
              </button>
              <span className="hidden max-w-[10rem] truncate text-xs text-muted sm:inline" title={user.email}>
                {user.email}
              </span>
              <button
                onClick={logout}
                className="rounded-full border border-border px-3.5 py-1.5 text-xs font-semibold text-muted transition-all duration-150 hover:border-down hover:text-down active:scale-95"
              >
                {t('auth.signOut')}
              </button>
            </>
          ) : (
            <button
              onClick={openAuthModal}
              className="rounded-full bg-accent px-4 py-1.5 text-xs font-bold text-white shadow-lg shadow-accent/20 transition-all duration-150 hover:brightness-110 active:scale-95"
            >
              {t('auth.signIn')}
            </button>
          )}
          <LanguageSwitcher />
        </div>
      </div>
    </header>
  )
}
