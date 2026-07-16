import { useLanguage } from '../i18n/LanguageContext'

const PERIODS = ['5d', '1mo', '3mo', '6mo', '1y', '2y']

export default function TimeframeSelector({ period, onChange }) {
  const { t } = useLanguage()
  return (
    <div className="flex flex-wrap gap-1.5">
      {PERIODS.map((p) => (
        <button
          key={p}
          onClick={() => onChange(p)}
          className={`rounded-full border px-4 py-1 text-xs font-semibold transition-all duration-200 ease-out active:scale-90 ${
            period === p
              ? 'scale-105 border-accent bg-accent text-white shadow-lg shadow-accent/20'
              : 'border-border text-muted hover:-translate-y-px hover:border-accent hover:text-accent'
          }`}
        >
          {t(`timeframe.${p}`)}
        </button>
      ))}
    </div>
  )
}
