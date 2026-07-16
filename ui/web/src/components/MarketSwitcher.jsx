import { useLanguage } from '../i18n/LanguageContext'

// "cn" covers both A-shares and HK-listed stocks — they route through the
// same backend regardless (market_for_ticker infers the actual exchange from
// each ticker's own suffix and picks the right benchmark/HSI vs CSI300 per
// stock), so splitting them in the switcher was UI overhead, not a real
// distinction the backend needs from the frontend.
const OPTIONS = [
  { code: 'us', flag: '🇺🇸' },
  { code: 'cn', flag: '🇨🇳' },
]

export default function MarketSwitcher({ market, onChange }) {
  const { t } = useLanguage()

  return (
    <div className="flex items-center gap-1.5">
      {OPTIONS.map((o) => (
        <button
          key={o.code}
          onClick={() => onChange(o.code)}
          className={`flex items-center gap-1.5 rounded-full border px-3.5 py-1 text-xs font-semibold transition-all duration-200 ease-out active:scale-90 ${
            market === o.code
              ? 'scale-105 border-accent bg-accent text-white shadow-lg shadow-accent/20'
              : 'border-border text-muted hover:-translate-y-px hover:border-accent hover:text-accent'
          }`}
        >
          <span aria-hidden="true">{o.flag}</span> {t(`market.${o.code}`)}
        </button>
      ))}
    </div>
  )
}
