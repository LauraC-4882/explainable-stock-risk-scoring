import { useLanguage } from '../i18n/LanguageContext'

const PERIODS = ['5d', '1mo', '3mo', '6mo', '1y', '2y']

export default function TimeframeSelector({ period, onChange }) {
  const { t } = useLanguage()
  return (
    <div className="flex flex-wrap gap-2">
      {PERIODS.map((p) => {
        const active = period === p
        return (
          <button
            key={p}
            onClick={() => onChange(p)}
            className={`rounded-full border px-[18px] py-2 text-xs font-semibold transition-all duration-200 ease-out active:scale-95 ${
              active
                ? 'border-accent/50 bg-sky/[0.14] text-accent2 shadow-[0_0_16px_rgba(56,189,248,0.3)]'
                : 'border-accent/[0.14] bg-white/[0.02] text-muted hover:-translate-y-px hover:border-accent/40 hover:text-white'
            }`}
          >
            {t(`timeframe.${p}`)}
          </button>
        )
      })}
    </div>
  )
}
