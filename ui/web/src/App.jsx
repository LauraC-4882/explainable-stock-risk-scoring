import { useState } from 'react'
import AdminPanel from './auth/AdminPanel'
import { AuthProvider } from './auth/AuthContext'
import AuthModal from './auth/AuthModal'
import CommunityPanel from './auth/CommunityPanel'
import ProfilePanel from './auth/ProfilePanel'
import WatchlistPanel from './auth/WatchlistPanel'
import EmptyState from './components/EmptyState'
import Footer from './components/Footer'
import Header from './components/Header'
import MarketSwitcher from './components/MarketSwitcher'
import SearchBar from './components/SearchBar'
import StockCard from './components/StockCard'
import TimeframeSelector from './components/TimeframeSelector'
import { LanguageProvider } from './i18n/LanguageContext'
import { OnboardingProvider } from './onboarding/OnboardingContext'
import OnboardingTour from './onboarding/OnboardingTour'

export default function App() {
  const [tickers, setTickers] = useState([])
  const [period, setPeriod] = useState('1mo')
  const [market, setMarket] = useState('us')

  function addStock(rawTicker) {
    const ticker = rawTicker.toUpperCase().trim()
    if (!ticker) return
    setTickers((prev) => (prev.includes(ticker) ? prev : [...prev, ticker]))
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
          <div className="relative flex min-h-screen flex-col text-slate-100">
            {/* Ambient sci-fi/fintech backdrop: two slow breathing orbs and a
                few twinkle dots on top of the fixed gradient+grid from
                index.css — deliberately sparse, animated via transform/opacity
                only, and stilled under prefers-reduced-motion. */}
            <div aria-hidden="true">
              <div className="bg-orb animate-breathe" style={{ width: 260, height: 260, top: -70, left: -70, background: '#7c3aed', opacity: 0.15 }} />
              <div className="bg-orb animate-breathe" style={{ width: 220, height: 220, bottom: -50, right: -50, background: '#db2777', opacity: 0.13, animationDelay: '2s' }} />
              <span className="animate-twinkle fixed left-[3%] top-[40%] h-1 w-1 rounded-full bg-accent" />
              <span className="animate-twinkle fixed right-[4%] top-[26%] h-[3px] w-[3px] rounded-full bg-rose" style={{ animationDelay: '0.6s' }} />
              <span className="animate-twinkle fixed bottom-[14%] left-[4%] h-[5px] w-[5px] rounded-full bg-gold" style={{ animationDelay: '1.1s' }} />
              <span className="animate-twinkle fixed bottom-[30%] right-[3%] h-[3px] w-[3px] rounded-full bg-accent2" style={{ animationDelay: '1.6s' }} />
            </div>

            <div className="relative z-10 flex flex-1 flex-col">
              <Header onHome={goHome} />

              {/* Side gutters at every breakpoint (wider as the viewport
                  grows) keep the page from stretching edge-to-edge, and the
                  bordered/blurred panel below reads as a distinct surface
                  "popped" up from the center of the page rather than raw
                  content sitting directly on the ambient backdrop. */}
              <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-4 pb-16 pt-6 sm:px-8 lg:px-12 xl:px-20">
                <div
                  className="animate-fade-in rounded-3xl border border-border/60 bg-surface/40 p-4 shadow-2xl shadow-black/30 backdrop-blur-sm sm:p-6"
                  style={{ animationDuration: '0.35s' }}
                >
                  <div className="mx-auto flex max-w-2xl flex-col gap-3.5">
                    <MarketSwitcher market={market} onChange={setMarket} />
                    <SearchBar market={market} onAdd={addStock} />
                    <TimeframeSelector period={period} onChange={setPeriod} />
                  </div>

                  {tickers.length === 0 ? (
                    <EmptyState market={market} onAdd={addStock} />
                  ) : (
                    // Capped at 2 columns (never 3+) so any pair of cards
                    // placed side by side stays legible for comparison —
                    // more than two get their own new row instead of
                    // squeezing a third card into the same row.
                    <div className="grid grid-cols-1 gap-5 pt-7 sm:grid-cols-2">
                      {tickers.map((t, i) => (
                        <StockCard key={t} ticker={t} period={period} onRemove={removeStock} index={i} />
                      ))}
                    </div>
                  )}
                </div>
              </main>

              <Footer />

              <AuthModal />
              <WatchlistPanel onAdd={addStock} />
              <ProfilePanel />
              <CommunityPanel />
              <AdminPanel />
              <OnboardingTour />
            </div>
          </div>
        </OnboardingProvider>
      </AuthProvider>
    </LanguageProvider>
  )
}
