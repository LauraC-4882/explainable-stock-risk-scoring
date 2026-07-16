import { useLanguage } from '../i18n/LanguageContext'

const OPTIONS = [
  { code: 'en', label: 'EN' },
  { code: 'zh', label: '中文' },
]

export default function LanguageSwitcher() {
  const { lang, setLang } = useLanguage()

  return (
    <div className="flex items-center gap-1.5">
      {OPTIONS.map((o) => (
        <button
          key={o.code}
          onClick={() => setLang(o.code)}
          className={`rounded-full border px-3 py-1 text-xs font-semibold transition-all duration-200 ease-out active:scale-90 ${
            lang === o.code
              ? 'scale-105 border-accent bg-accent text-white shadow-lg shadow-accent/20'
              : 'border-border text-muted hover:-translate-y-px hover:border-accent hover:text-accent'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
