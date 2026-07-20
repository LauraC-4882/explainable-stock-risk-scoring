import { createContext, useContext, useEffect, useState } from 'react'

const STORAGE_KEY = 'stock-risk-onboarding-seen'
const OnboardingContext = createContext(null)

export function OnboardingProvider({ children }) {
  const [open, setOpen] = useState(false)

  // First-visit auto-open, once — a short delay so it appears after the
  // page's own entrance animations settle instead of flashing in mid-layout.
  useEffect(() => {
    if (localStorage.getItem(STORAGE_KEY)) return
    const timer = setTimeout(() => {
      setOpen(true)
      localStorage.setItem(STORAGE_KEY, '1')
    }, 600)
    return () => clearTimeout(timer)
  }, [])

  return (
    <OnboardingContext.Provider
      value={{
        open,
        openTour: () => setOpen(true),
        closeTour: () => setOpen(false),
      }}
    >
      {children}
    </OnboardingContext.Provider>
  )
}

export function useOnboarding() {
  const ctx = useContext(OnboardingContext)
  if (!ctx) throw new Error('useOnboarding must be used within an OnboardingProvider')
  return ctx
}
