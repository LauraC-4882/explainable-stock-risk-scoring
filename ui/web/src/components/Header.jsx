import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import { useOnboarding } from '../onboarding/OnboardingContext'
import AlertsBell from './AlertsBell'
import Avatar from './Avatar'
import LanguageSwitcher from './LanguageSwitcher'
import { RiscoreIcon, RiscoreWordmark } from './Logo'

export default function Header({ onHome, onOpenTicker }) {
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

  // Shared pill styling for the "glass" nav buttons (Community, Watchlist,
  // Sign up, ?) — matches the Riscore.dc design: faint white fill, violet
  // hairline, violet-tint hover.
  const pill =
    'flex items-center gap-1.5 rounded-full border border-accent/20 bg-white/[0.04] px-3.5 py-2 text-xs font-semibold text-slate-200 transition-all duration-150 hover:border-accent/40 hover:bg-accent/[0.14] hover:text-white active:scale-95'

  return (
    <header className="relative z-10 px-1 pb-3 pt-6 sm:px-2">
      <div className="mx-auto flex w-full max-w-[1360px] flex-wrap items-center justify-between gap-4 px-4 sm:px-6">
        <button
          type="button"
          onClick={onHome}
          title={t('header.homeTitle')}
          aria-label={t('header.homeTitle')}
          className="group flex items-center gap-3.5 rounded-xl text-left transition-transform duration-150 hover:scale-[1.02] active:scale-95"
        >
          <div className="animate-floaty rounded-2xl border border-accent/35 bg-gradient-to-br from-accent/25 to-accent2/[0.14] p-1.5 shadow-[0_8px_30px_rgba(37,99,235,0.3)] transition-shadow duration-200 group-hover:shadow-[0_10px_36px_rgba(37,99,235,0.45)]">
            <RiscoreIcon size={40} idPrefix="hdr" />
          </div>
          <div>
            <h1 className="leading-none">
              <RiscoreWordmark className="text-[1.55rem] sm:text-[2rem]" />
            </h1>
            <p className="mt-1.5 max-w-[520px] text-[0.7rem] tracking-wide text-muted sm:text-[0.8rem]">
              {t('header.subtitle')}
            </p>
          </div>
        </button>

        <div className="flex flex-wrap items-center justify-end gap-2 sm:gap-2.5">
          <button onClick={() => openCommunityPanel()} className={pill}>
            <span aria-hidden="true">💬</span> {t('community.navButton')}
          </button>
          {user?.is_admin && (
            <button
              onClick={openAdminPanel}
              className="flex items-center gap-1.5 rounded-full border border-gold/40 bg-gold/[0.06] px-3.5 py-2 text-xs font-semibold text-gold transition-all duration-150 hover:bg-gold/15 active:scale-95"
            >
              <span aria-hidden="true">🛡️</span> {t('admin.navButton')}
            </button>
          )}

          {user ? (
            <>
              <button onClick={openWatchlistPanel} className={pill}>
                <span aria-hidden="true">★</span> {t('watchlist.button')}
                {watchlist.length > 0 && (
                  <span className="rounded-full bg-accent/20 px-1.5 py-0.5 text-[0.65rem] text-accent">
                    {watchlist.length}
                  </span>
                )}
              </button>
              <AlertsBell onOpen={onOpenTicker} />
              <button
                onClick={openProfilePanel}
                title={user.email}
                className="rounded-full ring-2 ring-transparent transition-all duration-150 hover:scale-110 hover:ring-accent/40 active:scale-95"
              >
                <Avatar email={user.email} size={38} />
              </button>
            </>
          ) : (
            <>
              <button onClick={() => openAuthModal('signUp')} className={`${pill} hidden sm:flex`}>
                {t('auth.signUpShort')}
              </button>
              <button
                onClick={() => openAuthModal('signIn')}
                className="btn-cta rounded-full px-5 py-2 text-xs font-bold transition-all duration-150 active:scale-95"
              >
                {t('auth.signIn')}
              </button>
            </>
          )}

          <button
            onClick={openTour}
            title={t('onboarding.replayTitle')}
            aria-label={t('onboarding.replayTitle')}
            className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full border border-accent/20 bg-white/[0.04] text-sm font-bold text-muted transition-all duration-150 hover:border-accent/40 hover:bg-accent/[0.14] hover:text-white active:scale-95"
          >
            ?
          </button>
          <LanguageSwitcher />
        </div>
      </div>
    </header>
  )
}
