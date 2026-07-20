import { useLanguage } from '../i18n/LanguageContext'
import { RiscoreIcon, RiscoreWordmark, SloganRing } from './Logo'

const POPULAR = {
  us: ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'NVDA', 'AMZN', 'META', 'JPM'],
  // A-shares and HK-listed names mixed together — the "China" bucket covers both.
  cn: ['600519.SS', '0700.HK', '000001.SZ', '9988.HK', '601318.SS', '3690.HK'],
}

// Hero lockup per the brand spec: shield icon on top, the Ri·score wordmark
// beneath it, the circular slogan ring beneath that, then the search prompt
// and quick-pick chips.
export default function EmptyState({ market, onAdd }) {
  const { t } = useLanguage()
  const popular = POPULAR[market] || POPULAR.us

  return (
    <div className="flex animate-fade-in flex-col items-center gap-3 px-8 py-12 text-center sm:py-16">
      <div className="animate-fade-in" style={{ animationDuration: '0.6s' }}>
        <RiscoreIcon size={110} idPrefix="hero" />
      </div>
      <div className="animate-fade-in" style={{ animationDuration: '0.7s' }}>
        <RiscoreWordmark className="text-5xl" />
      </div>
      <p className="text-[0.72rem] font-semibold uppercase tracking-[0.35em] text-accent2/80">
        {t('emptyState.slogan')}
      </p>
      <div className="my-2 animate-fade-in" style={{ animationDuration: '0.8s' }}>
        <SloganRing size={150} idPrefix="hero-sr" />
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
