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
    <div className="flex animate-fade-in flex-col items-center gap-4 px-8 py-14 text-center sm:py-20">
      <div className="relative animate-fade-in" style={{ animationDuration: '0.6s' }}>
        {/* Soft glow seated behind the icon — same purple/rose pair as the
            brand gradient, just diffused, so the mark reads as the light
            source of the whole hero instead of sitting flat on the backdrop. */}
        <div className="pointer-events-none absolute inset-0 -z-10 scale-150 rounded-full bg-accent/20 blur-3xl" />
        <RiscoreIcon size={128} idPrefix="hero" />
      </div>
      <div className="animate-fade-in" style={{ animationDuration: '0.7s' }}>
        <RiscoreWordmark className="text-6xl sm:text-7xl" />
      </div>

      {/* Slogan badge: a gradient-bordered pill with gradient text and two
          pulsing gold dots (echoing the header's twinkle motif) — a
          deliberately designed centerpiece rather than a plain caption line. */}
      <div
        className="my-1 inline-flex animate-fade-in items-center gap-3 rounded-full border border-accent2/30 bg-gradient-to-r from-accent/10 via-accent2/10 to-rose/10 px-6 py-2.5 shadow-lg shadow-accent/10"
        style={{ animationDuration: '0.75s' }}
      >
        <span className="h-1.5 w-1.5 flex-shrink-0 animate-glow-pulse rounded-full bg-gold" />
        <p className="bg-gradient-to-r from-accent2 via-accent to-rose bg-clip-text text-sm font-bold uppercase tracking-[0.35em] text-transparent sm:text-base">
          {t('emptyState.slogan')}
        </p>
        <span
          className="h-1.5 w-1.5 flex-shrink-0 animate-glow-pulse rounded-full bg-gold"
          style={{ animationDelay: '1.3s' }}
        />
      </div>

      <div className="relative my-2 animate-fade-in" style={{ animationDuration: '0.8s' }}>
        <div className="pointer-events-none absolute inset-0 -z-10 rounded-full bg-accent2/10 blur-2xl" />
        <SloganRing size={172} idPrefix="hero-sr" />
      </div>
      <h2 className="text-xl font-bold sm:text-2xl">{t('emptyState.heading')}</h2>
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
