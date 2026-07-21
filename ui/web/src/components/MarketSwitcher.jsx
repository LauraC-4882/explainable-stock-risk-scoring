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
