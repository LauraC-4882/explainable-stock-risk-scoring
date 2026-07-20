import { useLanguage } from '../i18n/LanguageContext'
import { useOnboarding } from '../onboarding/OnboardingContext'
import Avatar from '../components/Avatar'
import { useAuth } from './AuthContext'

export default function ProfilePanel() {
  const { t, lang } = useLanguage()
  const { profilePanelOpen, closeProfilePanel, user, watchlist, logout } = useAuth()
  const { openTour } = useOnboarding()

  if (!profilePanelOpen || !user) return null

  const memberSince = user.created_at
    ? new Date(user.created_at).toLocaleDateString(lang === 'zh' ? 'zh-CN' : 'en-US', {
        year: 'numeric',
        month: 'long',
      })
    : null

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/60 backdrop-blur-sm"
      style={{ animationDuration: '0.15s' }}
      onClick={closeProfilePanel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm animate-fade-in overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-black/50"
        style={{ animationDuration: '0.2s' }}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-lg font-bold text-slate-100">{t('profile.title')}</h2>
          <button
            onClick={closeProfilePanel}
            className="rounded-md px-1.5 py-0.5 text-base leading-none text-muted transition hover:bg-down/10 hover:text-down"
          >
            ✕
          </button>
        </div>

        <div className="space-y-5 px-5 py-5">
          <div className="flex items-center gap-3.5">
            <Avatar email={user.email} size={54} />
            <div className="min-w-0">
              <div className="truncate text-sm font-bold text-slate-100">{user.email}</div>
              {memberSince && (
                <div className="mt-0.5 text-xs text-muted">
                  {t('profile.memberSince')} {memberSince}
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between rounded-xl border border-border bg-surface2/50 px-4 py-3">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">
              {t('profile.watchlistCount')}
            </span>
            <span className="text-sm font-bold text-slate-100">{watchlist.length}</span>
          </div>

          <button
            onClick={() => {
              closeProfilePanel()
              openTour()
            }}
            className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-border py-2.5 text-sm font-semibold text-slate-200 transition-all duration-150 hover:border-accent hover:text-accent active:scale-[0.98]"
          >
            <span aria-hidden="true">🎓</span> {t('profile.replayTour')}
          </button>

          <button
            onClick={() => {
              logout()
              closeProfilePanel()
            }}
            className="w-full rounded-xl border border-border py-2.5 text-sm font-semibold text-muted transition-all duration-150 hover:border-down hover:text-down active:scale-[0.98]"
          >
            {t('auth.signOut')}
          </button>
        </div>
      </div>
    </div>
  )
}
