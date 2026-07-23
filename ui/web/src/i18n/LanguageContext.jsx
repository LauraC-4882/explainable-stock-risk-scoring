import i18n from 'i18next'
import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { initReactI18next } from 'react-i18next'
import en from './locales/en.json'
import zhCN from './locales/zh-CN.json'
import zhTW from './locales/zh-TW.json'

// i18next backs the translations, but this module still exposes the original
// `useLanguage() -> { lang, setLang, t }` API. That is deliberate: 39
// components and ~400 call sites already use `t('a.b.c', vars)`, and swapping
// the engine underneath them is a far smaller change — and a far smaller
// regression surface — than rewriting every call site to useTranslation().
//
// Two i18next defaults have to be overridden to keep that contract:
//   * interpolation uses {{name}} by default; this codebase writes {name}.
//   * a key pointing at a subtree returns the key unless returnObjects is on,
//     and a few callers do read subtrees.
// Escaping is off because React already escapes rendered text; leaving it on
// would double-escape apostrophes, which appear throughout the English copy.

export const LOCALES = {
  en: { label: 'EN', resource: en },
  'zh-CN': { label: '简体', resource: zhCN },
  'zh-TW': { label: '繁體', resource: zhTW },
}

const STORAGE_KEY = 'stock-risk-lang'
const FALLBACK = 'en'

// 'zh' was the stored value before Simplified/Traditional were split apart.
// Anyone carrying it in localStorage should land on Simplified, not be reset
// to English.
const LEGACY_ALIASES = { zh: 'zh-CN', 'zh-Hans': 'zh-CN', 'zh-Hant': 'zh-TW' }

export function normaliseLang(code) {
  if (!code) return null
  if (LOCALES[code]) return code
  return LEGACY_ALIASES[code] ?? null
}

if (!i18n.isInitialized) {
  i18n.use(initReactI18next).init({
    resources: Object.fromEntries(
      Object.entries(LOCALES).map(([code, { resource }]) => [code, { translation: resource }])
    ),
    lng: FALLBACK,
    fallbackLng: FALLBACK,
    interpolation: { prefix: '{', suffix: '}', escapeValue: false },
    returnObjects: true,
    returnEmptyString: false,
    // A missing key should render its own path, matching the previous
    // behaviour that tests and the fallback chain rely on.
    parseMissingKeyHandler: (key) => key,
  })
}

const LanguageContext = createContext(null)

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(() => {
    const stored = normaliseLang(localStorage.getItem(STORAGE_KEY))
    return stored ?? FALLBACK
  })

  useEffect(() => {
    if (i18n.language !== lang) i18n.changeLanguage(lang)
  }, [lang])

  function setLang(next) {
    const resolved = normaliseLang(next)
    if (!resolved) return
    setLangState(resolved)
    localStorage.setItem(STORAGE_KEY, resolved)
  }

  const t = useMemo(() => {
    // `lang` is a dependency so the identity changes on switch and consumers
    // re-render; i18n.getFixedT pins the lookup to the active language.
    const fixed = i18n.getFixedT(lang)
    return (path, vars) => fixed(path, vars)
  }, [lang])

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>{children}</LanguageContext.Provider>
  )
}

export function useLanguage() {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useLanguage must be used within a LanguageProvider')
  return ctx
}
