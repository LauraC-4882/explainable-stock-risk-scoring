import { useLanguage } from '../i18n/LanguageContext'

// Two supported markets: US equities and mainland China A-shares. Hong Kong
// listings are out of scope. The backend still infers the actual exchange
// from each ticker's own suffix (market_for_ticker) and picks the matching
// benchmark (SPY / CSI 300), so this switcher only scopes the search and
// quick-pick chips — it isn't something the backend needs from the frontend.
const OPTIONS = [
  { code: 'us', flag: '🇺🇸' },
  { code: 'cn', flag: '🇨🇳' },
]

export default function MarketSwitcher({ market, onChange }) {
  const { t } = useLanguage()

  // Segmented control (per the design): one rounded pill-group container with
  // the two markets as inner segments — active gets the sky→indigo CTA fill.
  return (
    <div className="flex w-fit items-center gap-1.5 rounded-full border border-accent/16 bg-white/[0.03] p-1.5">
      {OPTIONS.map((o) => {
        const active = market === o.code
        return (
          <button
            key={o.code}
            onClick={() => onChange(o.code)}
            // Selection lived only in the `btn-cta` fill, which a screen reader
            // cannot see — so the control announced two identical buttons with
            // no indication of which market was live. That matters more since
            // App.addStock moves this on its own when a CN symbol is opened:
            // the one user who cannot see the fill change is also the one
            // getting no other signal that the market just changed under them.
            aria-pressed={active}
            className={`flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-bold transition-all duration-200 ease-out active:scale-95 ${
              active ? 'btn-cta' : 'text-muted hover:text-white'
            }`}
          >
            <span aria-hidden="true">{o.flag}</span> {t(`market.${o.code}`)}
          </button>
        )
      })}
    </div>
  )
}
