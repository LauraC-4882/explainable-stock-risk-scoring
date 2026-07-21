import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import {
  apiAddWatchlist,
  apiGetWatchlist,
  apiLogin,
  apiMe,
  apiRegister,
  apiRemoveWatchlist,
} from '../api'

const TOKEN_KEY = 'stock-risk-token'
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY))
  const [user, setUser] = useState(null)
  const [watchlist, setWatchlist] = useState([])
  const [ready, setReady] = useState(false) // whether the initial session restore finished
  const [authModalOpen, setAuthModalOpen] = useState(false)
  const [authModalMode, setAuthModalMode] = useState('signIn') // 'signIn' | 'signUp'
  const [watchlistPanelOpen, setWatchlistPanelOpen] = useState(false)
  const [profilePanelOpen, setProfilePanelOpen] = useState(false)
  const [communityPanelOpen, setCommunityPanelOpen] = useState(false)
  // Doubles as "open pre-filtered to this ticker" and "pre-fill the
  // composer with this ticker" — one param, one reasonable meaning, no
  // router to carry it as a URL param instead (see TopAnalysisWidget).
  const [communityPanelTicker, setCommunityPanelTicker] = useState(null)
  const [adminPanelOpen, setAdminPanelOpen] = useState(false)

  // Restore the session on load (and whenever the token changes) by re-fetching
  // the user + watchlist — a stale/expired token is dropped rather than surfaced
  // as an error, since the user just sees themselves logged out.
  useEffect(() => {
    if (!token) {
      setReady(true)
      return
    }
    let cancelled = false
    Promise.all([apiMe(token), apiGetWatchlist(token)])
      .then(([u, wl]) => {
        if (cancelled) return
        setUser(u)
        setWatchlist(wl)
      })
      .catch(() => {
        if (cancelled) return
        localStorage.removeItem(TOKEN_KEY)
        setToken(null)
      })
      .finally(() => {
        if (!cancelled) setReady(true)
      })
    return () => {
      cancelled = true
    }
  }, [token])

  async function login(email, password) {
    const { access_token } = await apiLogin(email, password)
    localStorage.setItem(TOKEN_KEY, access_token)
    setToken(access_token)
  }

  async function register(email, password) {
    const { access_token } = await apiRegister(email, password)
    localStorage.setItem(TOKEN_KEY, access_token)
    setToken(access_token)
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
    setWatchlist([])
  }

  const isFavorited = useCallback(
    (ticker) => watchlist.some((w) => w.ticker === ticker),
    [watchlist],
  )

  async function toggleFavorite(ticker, market) {
    if (!token) {
      setAuthModalOpen(true)
      return
    }
    const existing = watchlist.find((w) => w.ticker === ticker)
    if (existing) {
      await apiRemoveWatchlist(token, existing.id)
      setWatchlist((prev) => prev.filter((w) => w.id !== existing.id))
    } else {
      const item = await apiAddWatchlist(token, ticker, market)
      setWatchlist((prev) => [...prev, item])
    }
  }

  async function removeFromWatchlist(itemId) {
    await apiRemoveWatchlist(token, itemId)
    setWatchlist((prev) => prev.filter((w) => w.id !== itemId))
  }

  return (
    <AuthContext.Provider
      value={{
        token,
        user,
        watchlist,
        ready,
        login,
        register,
        logout,
        isFavorited,
        toggleFavorite,
        removeFromWatchlist,
        authModalOpen,
        authModalMode,
        openAuthModal: (mode = 'signIn') => {
          setAuthModalMode(mode)
          setAuthModalOpen(true)
        },
        closeAuthModal: () => setAuthModalOpen(false),
        watchlistPanelOpen,
        openWatchlistPanel: () => setWatchlistPanelOpen(true),
        closeWatchlistPanel: () => setWatchlistPanelOpen(false),
        profilePanelOpen,
        openProfilePanel: () => setProfilePanelOpen(true),
        closeProfilePanel: () => setProfilePanelOpen(false),
        communityPanelOpen,
        communityPanelTicker,
        openCommunityPanel: (ticker = null) => {
          setCommunityPanelTicker(ticker)
          setCommunityPanelOpen(true)
        },
        closeCommunityPanel: () => setCommunityPanelOpen(false),
        adminPanelOpen,
        openAdminPanel: () => setAdminPanelOpen(true),
        closeAdminPanel: () => setAdminPanelOpen(false),
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
