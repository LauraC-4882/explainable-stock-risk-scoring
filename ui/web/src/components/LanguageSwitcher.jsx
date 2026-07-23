import { LOCALES, useLanguage } from '../i18n/LanguageContext'

// Options are derived from the registered locales rather than hard-coded, so
// adding a language is a one-line change in LanguageContext.
const OPTIONS = Object.entries(LOCALES).map(([code, { label }]) => ({ code, label }))

export default function LanguageSwitcher() {
  const { lang, setLang } = useLanguage()

  return (
    <div className="flex items-center gap-1.5">
      {OPTIONS.map((o) => (
        <button
          key={o.code}
          onClick={() => setLang(o.code)}
          aria-pressed={lang === o.code}
          className={`rounded-full border px-3 py-2 text-xs font-bold transition-all duration-200 ease-out active:scale-90 ${
            lang === o.code
              ? 'border-accent/40 bg-sky/15 text-white'
              : 'border-transparent text-muted hover:text-white'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
