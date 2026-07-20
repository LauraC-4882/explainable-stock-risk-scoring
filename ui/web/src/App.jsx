import { useState } from 'react'
import { AuthProvider } from './auth/AuthContext'
import AuthModal from './auth/AuthModal'
import ProfilePanel from './auth/ProfilePanel'
import WatchlistPanel from './auth/WatchlistPanel'
import EmptyState from './components/EmptyState'
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

  return (
    <LanguageProvider>
      <AuthProvider>
        <OnboardingProvider>
          <div className="relative min-h-screen text-slate-100">
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

            <div className="relative z-10">
              <Header />

              <div className="flex max-w-2xl flex-col gap-3.5 px-6 pt-6 sm:px-8">
                <MarketSwitcher market={market} onChange={setMarket} />
                <SearchBar market={market} onAdd={addStock} />
                <TimeframeSelector period={period} onChange={setPeriod} />
              </div>

              {tickers.length === 0 ? (
                <EmptyState market={market} onAdd={addStock} />
              ) : (
                <div className="grid grid-cols-1 gap-5 px-6 pb-16 pt-7 sm:px-8 md:grid-cols-2 xl:grid-cols-3">
                  {tickers.map((t, i) => (
                    <StockCard key={t} ticker={t} period={period} onRemove={removeStock} index={i} />
                  ))}
                </div>
              )}

              <AuthModal />
              <WatchlistPanel onAdd={addStock} />
              <ProfilePanel />
              <OnboardingTour />
            </div>
          </div>
        </OnboardingProvider>
      </AuthProvider>
    </LanguageProvider>
  )
}
