import { useState } from 'react'
import EmptyState from './components/EmptyState'
import Header from './components/Header'
import MarketSwitcher from './components/MarketSwitcher'
import SearchBar from './components/SearchBar'
import StockCard from './components/StockCard'
import TimeframeSelector from './components/TimeframeSelector'
import { LanguageProvider } from './i18n/LanguageContext'

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
      <div className="min-h-screen bg-bg text-slate-100">
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
      </div>
    </LanguageProvider>
  )
}
