import { useEffect, useState } from 'react'
import { useLanguage } from '../i18n/LanguageContext'
import { useAuth } from './AuthContext'

export default function AuthModal() {
  const { t } = useLanguage()
  const { authModalOpen, authModalMode, closeAuthModal, login, register } = useAuth()
  const [mode, setMode] = useState('signIn') // 'signIn' | 'signUp'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  // Adopt whichever mode the caller requested (e.g. Header's separate
  // Sign in / Sign up buttons) each time the modal opens.
  useEffect(() => {
    if (authModalOpen) setMode(authModalMode)
  }, [authModalOpen, authModalMode])

  if (!authModalOpen) return null

  function reset() {
    setEmail('')
    setPassword('')
    setError(null)
    setSubmitting(false)
  }

  function close() {
    reset()
    closeAuthModal()
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      if (mode === 'signIn') {
        await login(email, password)
      } else {
        await register(email, password)
      }
      close()
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/60 backdrop-blur-sm"
      style={{ animationDuration: '0.15s' }}
      onClick={close}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="w-full max-w-sm animate-fade-in rounded-2xl border border-border bg-surface p-6 shadow-2xl shadow-black/50"
        style={{ animationDuration: '0.2s' }}
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-100">
            {mode === 'signIn' ? t('auth.signIn') : t('auth.signUp')}
          </h2>
          <button
            type="button"
            onClick={close}
            className="rounded-md px-1.5 py-0.5 text-base leading-none text-muted transition hover:bg-down/10 hover:text-down"
          >
            ✕
          </button>
        </div>

        <label className="mb-3 block">
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
            {t('auth.email')}
          </span>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-xl border border-border bg-surface2 px-3.5 py-2.5 text-sm text-slate-100 outline-none transition focus:border-accent focus:ring-4 focus:ring-accent/10"
          />
        </label>

        <label className="mb-1.5 block">
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
            {t('auth.password')}
          </span>
          <input
            type="password"
            required
            minLength={8}
            autoComplete={mode === 'signIn' ? 'current-password' : 'new-password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-xl border border-border bg-surface2 px-3.5 py-2.5 text-sm text-slate-100 outline-none transition focus:border-accent focus:ring-4 focus:ring-accent/10"
          />
        </label>
        {mode === 'signUp' && <p className="mb-3 text-[0.7rem] text-muted">{t('auth.passwordHint')}</p>}

        {error && (
          <p className="mb-3 mt-3 rounded-lg bg-down/10 px-3 py-2 text-xs text-down">{error}</p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="mt-4 w-full rounded-xl bg-accent py-2.5 text-sm font-bold text-white shadow-lg shadow-accent/20 transition-all duration-150 hover:brightness-110 active:scale-[0.98] disabled:opacity-60"
        >
          {submitting ? t('auth.submitting') : t('auth.submit')}
        </button>

        <button
          type="button"
          onClick={() => {
            setMode((m) => (m === 'signIn' ? 'signUp' : 'signIn'))
            setError(null)
          }}
          className="mt-3 w-full text-center text-xs text-muted transition hover:text-accent"
        >
          {mode === 'signIn' ? t('auth.switchToSignUp') : t('auth.switchToSignIn')}
        </button>
      </form>
    </div>
  )
}
