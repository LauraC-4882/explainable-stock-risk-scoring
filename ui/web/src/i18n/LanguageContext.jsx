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
    return (path) => {
      const value = lookup(LOCALES[lang], path)
      if (value !== undefined) return value
      const fallback = lookup(LOCALES.en, path) // untranslated keys degrade to English, never a raw path string
      return fallback !== undefined ? fallback : path
    }
  }, [lang])

  return <LanguageContext.Provider value={{ lang, setLang, t }}>{children}</LanguageContext.Provider>
}

export function useLanguage() {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useLanguage must be used within a LanguageProvider')
  return ctx
}
