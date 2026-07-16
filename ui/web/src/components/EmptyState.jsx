import { useLanguage } from '../i18n/LanguageContext'

const POPULAR = {
  us: ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'NVDA', 'AMZN', 'META', 'JPM'],
  // A-shares and HK-listed names mixed together — the "China" bucket covers both.
  cn: ['600519.SS', '0700.HK', '000001.SZ', '9988.HK', '601318.SS', '3690.HK'],
}

export default function EmptyState({ market, onAdd }) {
  const { t } = useLanguage()
  const popular = POPULAR[market] || POPULAR.us

  return (
    <div className="flex animate-fade-in flex-col items-center gap-3 px-8 py-20 text-center sm:py-24">
      <div className="animate-fade-in text-5xl" style={{ animationDuration: '0.5s' }}>
        📊
      </div>
      <h2 className="text-lg font-bold">{t('emptyState.heading')}</h2>
      <p className="max-w-sm text-sm leading-relaxed text-muted">{t('emptyState.body')}</p>
      <div className="mt-2 flex flex-wrap justify-center gap-2">
        {popular.map((ticker, i) => (
          <button
            key={ticker}
            onClick={() => onAdd(ticker)}
            style={{ animationDelay: `${i * 40}ms`, animationFillMode: 'backwards' }}
            className="animate-fade-in rounded-full border border-border bg-surface2 px-4 py-1.5 text-sm font-bold text-accent transition-all duration-200 ease-out hover:-translate-y-0.5 hover:border-accent hover:bg-accent/10 hover:shadow-lg hover:shadow-accent/10 active:scale-90"
          >
            {ticker}
          </button>
        ))}
      </div>
    </div>
  )
}
