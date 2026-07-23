import { House, LayoutDashboard, Search, Star, User } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'

// Bottom navigation, mobile only (hidden from md up — the header pills cover
// everything there). Five fixed actions mapped onto what the app actually has:
// the app is panel-routed, so "Dashboard" scrolls to the cards and "Search"
// focuses the search box rather than navigating anywhere.
//
// Watchlist and Profile are auth-gated panels; signed out, both routes go to
// the sign-in modal — the same behaviour their header buttons have.
//
// A separate floating search FAB (spec) is deliberately NOT included on top of
// this: the nav already carries Search dead-centre, and stacking a second
// floating search control over a five-item bar would cover content to duplicate
// one tap.

function focusSearch() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
  // The search box is the page's only always-present text input.
  const input = document.querySelector('input[type="text"]')
  input?.focus()
}

export default function MobileNav({ onHome }) {
  const { t } = useLanguage()
  const { user, openWatchlistPanel, openProfilePanel, openAuthModal } = useAuth()

  const items = [
    { key: 'home', icon: House, onClick: onHome },
    {
      key: 'dashboard',
      icon: LayoutDashboard,
      onClick: () => window.scrollTo({ top: 0, behavior: 'smooth' }),
    },
    { key: 'search', icon: Search, onClick: focusSearch },
    {
      key: 'watchlist',
      icon: Star,
      onClick: () => (user ? openWatchlistPanel() : openAuthModal('signIn')),
    },
    {
      key: 'profile',
      icon: User,
      onClick: () => (user ? openProfilePanel() : openAuthModal('signIn')),
    },
  ]

  return (
    <nav
      aria-label={t('mobileNav.label')}
      className="fixed inset-x-0 bottom-0 z-40 flex items-stretch justify-around border-t border-border bg-[#091525]/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
    >
      {items.map(({ key, icon: Icon, onClick }) => (
        <button
          key={key}
          onClick={onClick}
          className="flex min-w-0 flex-1 flex-col items-center gap-0.5 px-1 py-2 text-muted transition active:scale-95 active:text-accent"
        >
          <Icon aria-hidden="true" size={18} />
          <span className="truncate text-[0.58rem] font-semibold">{t(`mobileNav.${key}`)}</span>
        </button>
      ))}
    </nav>
  )
}
