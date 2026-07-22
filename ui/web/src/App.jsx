import { IconContext } from '@phosphor-icons/react'
import { useState } from 'react'
import AdminPanel from './auth/AdminPanel'
import AboutPanel from './components/AboutPanel'
import { AuthProvider } from './auth/AuthContext'
import AuthModal from './auth/AuthModal'
import CommunityPanel from './auth/CommunityPanel'
import ProfilePanel from './auth/ProfilePanel'
import WatchlistPanel from './auth/WatchlistPanel'
import CompareView from './components/CompareView'
import EmptyState from './components/EmptyState'
import Footer from './components/Footer'
import Header from './components/Header'
import MarketSwitcher from './components/MarketSwitcher'
import SearchBar from './components/SearchBar'
import Starfield from './components/Starfield'
import StockCard from './components/StockCard'
import TimeframeSelector from './components/TimeframeSelector'
import WatchlistBoard from './components/WatchlistBoard'
import { LanguageProvider, useLanguage } from './i18n/LanguageContext'
import { OnboardingProvider } from './onboarding/OnboardingContext'
import OnboardingTour from './onboarding/OnboardingTour'

export default function App() {
  const [tickers, setTickers] = useState([])
  const [period, setPeriod] = useState('1mo')
  const [market, setMarket] = useState('us')
  // 'cards' = full dashboard per stock (default); 'compare' = one
  // aligned row per measure across every added stock.
  const [view, setView] = useState('cards')

  function addStock(rawTicker) {
    const ticker = rawTicker.toUpperCase().trim()
    if (!ticker) return
    // Newest first: a freshly searched stock lands at the top of the stack
    // rather than below however many dashboards are already open, which on a
    // full-height bento card meant scrolling past everything to reach the one
    // you just asked for.
    setTickers((prev) => (prev.includes(ticker) ? prev : [ticker, ...prev]))
  }

  function removeStock(ticker) {
    setTickers((prev) => prev.filter((t) => t !== ticker))
  }

  // Header logo doubles as "go home": drops every added stock and resets
  // market/timeframe back to their defaults, landing back on the same
  // EmptyState a fresh visit would show — the only "back to homepage"
  // affordance this single-page app needs since there's no router/URL.
  function goHome() {
    setTickers([])
    setMarket('us')
    setPeriod('1mo')
  }

  return (
    <LanguageProvider>
      <AuthProvider>
        <OnboardingProvider>
          {/* Phosphor icon defaults (phosphoricons.com, thin @ #71b8e5) —
              every icon inherits these unless it explicitly overrides. */}
          <IconContext.Provider value={{ size: 18, weight: 'thin', color: '#71b8e5' }}>
          <div className="relative flex min-h-screen flex-col text-slate-100">
            {/* Ambient "Deep Network" backdrop matched to the user's
                background artwork: three drifting glow orbs (blue top-left,
                teal center-right, faint violet bottom), the animated plexus
                canvas, and a perspective grid-floor — all fixed behind the
                content, animated via transform/opacity only, and stilled
                under prefers-reduced-motion. */}
            <div aria-hidden="true">
              <div
                className="bg-orb animate-aurora1"
                style={{ top: '-18%', left: '-8%', width: '48vw', height: '48vw', opacity: 0.3, filter: 'blur(70px)', background: 'radial-gradient(circle,rgba(64,144,255,0.55),transparent 68%)' }}
              />
              <div
                className="bg-orb animate-aurora2"
                style={{ top: '18%', right: '-14%', width: '50vw', height: '50vw', opacity: 0.28, filter: 'blur(85px)', background: 'radial-gradient(circle,rgba(20,170,180,0.5),transparent 66%)' }}
              />
              <div
                className="bg-orb animate-aurora3"
                style={{ bottom: '-24%', left: '22%', width: '52vw', height: '52vw', opacity: 0.16, filter: 'blur(90px)', background: 'radial-gradient(circle,rgba(120,80,220,0.4),transparent 68%)' }}
              />
              <Starfield />
              <div className="grid-floor">
                <div className="grid-floor-inner animate-grid-scroll" />
              </div>
            </div>

            <div className="relative z-10 flex flex-1 flex-col">
              <Header onHome={goHome} onOpenTicker={addStock} />

              {/* The design floats its controls and cards directly on the
                  cosmic backdrop (no competing wrapper box) inside a wide,
                  centered column. Controls sit in a left-aligned stack; the
                  search bar spans the column while the market/timeframe
                  pill-groups size to their content. */}
              <main className="mx-auto flex w-full max-w-[1360px] flex-1 flex-col px-5 pb-16 pt-5 sm:px-8">
                <div className="flex flex-col gap-4">
                  <MarketSwitcher market={market} onChange={setMarket} />
                  <SearchBar market={market} onAdd={addStock} />
                  <TimeframeSelector period={period} onChange={setPeriod} />
                </div>

                {tickers.length === 0 ? (
                  // Signed-in users land on their watchlist board (renders
                  // nothing when signed out or empty), so returning users see
                  // what moved instead of an empty search box every visit.
                  <>
                    <WatchlistBoard onOpen={addStock} />
                    <EmptyState market={market} onAdd={addStock} />
                  </>
                ) : (
                  <>
                    {tickers.length > 1 && <ViewToggle view={view} onChange={setView} />}
                    {view === 'compare' && tickers.length > 1 ? (
                      <CompareView tickers={tickers} onRemove={removeStock} />
                    ) : (
                      // Every stock gets the full wide bento layout; comparing
                      // means stacking those full dashboards vertically rather
                      // than shrinking each into a cramped side-by-side card —
                      // scroll between them, every section keeps its room.
                      <div className="mx-auto grid w-full max-w-[1240px] grid-cols-1 gap-10 pt-7">
                        {tickers.map((t, i) => (
                          <StockCard
                            key={t}
                            ticker={t}
                            period={period}
                            onRemove={removeStock}
                            index={i}
                          />
                        ))}
                      </div>
                    )}
                  </>
                )}
              </main>

              <Footer />

              <AuthModal />
              <WatchlistPanel onAdd={addStock} />
              <ProfilePanel />
              <CommunityPanel />
              <AdminPanel />
              <AboutPanel />
              <OnboardingTour />
            </div>
          </div>
          </IconContext.Provider>
        </OnboardingProvider>
      </AuthProvider>
    </LanguageProvider>
  )
}

// Cards vs. compare switch — only meaningful once there are two stocks to
// line up, so App renders it conditionally.
function ViewToggle({ view, onChange }) {
  const { t } = useLanguage()
  const opts = [
    ['cards', t('compare.viewCards')],
    ['compare', t('compare.viewCompare')],
  ]
  return (
    <div className="mx-auto mt-7 flex w-fit items-center gap-1.5 rounded-full border border-accent/20 bg-white/[0.03] p-1.5">
      {opts.map(([key, label]) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={`rounded-full px-4 py-1.5 text-xs font-bold transition-all duration-200 active:scale-95 ${
            view === key ? 'btn-cta' : 'text-muted hover:text-white'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
