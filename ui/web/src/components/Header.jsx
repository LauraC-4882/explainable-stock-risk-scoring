import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import { useOnboarding } from '../onboarding/OnboardingContext'
import Avatar from './Avatar'
import LanguageSwitcher from './LanguageSwitcher'
import { RiscoreIcon, RiscoreWordmark } from './Logo'

export default function Header() {
  const { t } = useLanguage()
  const {
    user,
    watchlist,
    openAuthModal,
    openWatchlistPanel,
    openProfilePanel,
    openCommunityPanel,
    openAdminPanel,
  } = useAuth()
  const { openTour } = useOnboarding()

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
          <button
            onClick={() => openCommunityPanel()}
            className="flex items-center gap-1.5 rounded-full border border-border px-3.5 py-1.5 text-xs font-semibold text-slate-200 transition-all duration-150 hover:border-accent hover:text-accent active:scale-95"
          >
            <span aria-hidden="true">💬</span> {t('community.navButton')}
          </button>
          {user?.is_admin && (
            <button
              onClick={openAdminPanel}
              className="flex items-center gap-1.5 rounded-full border border-gold/40 px-3.5 py-1.5 text-xs font-semibold text-gold transition-all duration-150 hover:bg-gold/10 active:scale-95"
            >
              <span aria-hidden="true">🛡️</span> {t('admin.navButton')}
            </button>
          )}
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
              <button
                onClick={openProfilePanel}
                title={user.email}
                className="rounded-full transition-transform duration-150 hover:scale-110 active:scale-95"
              >
                <Avatar email={user.email} size={34} />
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => openAuthModal('signUp')}
                className="hidden rounded-full border border-border px-3.5 py-1.5 text-xs font-semibold text-slate-200 transition-all duration-150 hover:border-accent hover:text-accent active:scale-95 sm:inline-block"
              >
                {t('auth.signUpShort')}
              </button>
              <button
                onClick={() => openAuthModal('signIn')}
                className="rounded-full bg-accent px-4 py-1.5 text-xs font-bold text-white shadow-lg shadow-accent/20 transition-all duration-150 hover:brightness-110 active:scale-95"
              >
                {t('auth.signIn')}
              </button>
            </>
          )}
          <button
            onClick={openTour}
            title={t('onboarding.replayTitle')}
            aria-label={t('onboarding.replayTitle')}
            className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full border border-border text-xs font-bold text-muted transition-all duration-150 hover:border-accent hover:text-accent active:scale-95"
          >
            ?
          </button>
          <LanguageSwitcher />
        </div>
      </div>
    </header>
  )
}
