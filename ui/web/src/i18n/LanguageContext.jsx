import { createContext, useContext, useMemo, useState } from 'react'
import en from './locales/en'
import zh from './locales/zh'

const LOCALES = { en, zh }
const STORAGE_KEY = 'stock-risk-lang'

const LanguageContext = createContext(null)

function lookup(dict, path) {
  return path.split('.').reduce((acc, key) => (acc && acc[key] != null ? acc[key] : undefined), dict)
}

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored && LOCALES[stored] ? stored : 'en'
  })

  function setLang(next) {
    if (!LOCALES[next]) return
    setLangState(next)
    localStorage.setItem(STORAGE_KEY, next)
  }

  const t = useMemo(() => {
    // Optional `vars` fills {name} placeholders. Substitution happens after
    // the English fallback below, so a key that exists only in en.js still
    // interpolates rather than rendering literal braces. Callers that pass no
    // vars are unaffected — a string with no placeholders is returned as-is.
    return (path, vars) => {
      const value = lookup(LOCALES[lang], path)
      const resolved =
        value !== undefined
          ? value
          : // untranslated keys degrade to English, never a raw path string
            (lookup(LOCALES.en, path) ?? path)
      if (!vars || typeof resolved !== 'string') return resolved
      return resolved.replace(/\{(\w+)\}/g, (match, key) =>
        vars[key] != null ? String(vars[key]) : match
      )
    }
  }, [lang])

  return <LanguageContext.Provider value={{ lang, setLang, t }}>{children}</LanguageContext.Provider>
}

export function useLanguage() {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useLanguage must be used within a LanguageProvider')
  return ctx
}
