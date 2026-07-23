import { X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useLanguage } from '../i18n/LanguageContext'
import { useAuth } from './AuthContext'

export default function AuthModal() {
  const { t } = useLanguage()
  const { authModalOpen, authModalMode, closeAuthModal, login, register } = useAuth()
  const [mode, setMode] = useState('signIn') // 'signIn' | 'signUp'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [nickname, setNickname] = useState('')
  // Three separate agreements rather than one blanket checkbox — each is
  // its own affirmative click so a user can't later claim they didn't know
  // posts aren't investment advice or that off-topic/political content
  // isn't allowed. All three gate the submit button; the backend still only
  // takes a single `consent: bool`, so this is a frontend-only distinction.
  const [agreeAdvice, setAgreeAdvice] = useState(false)
  const [agreeRules, setAgreeRules] = useState(false)
  const [agreePrivacy, setAgreePrivacy] = useState(false)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const consent = agreeAdvice && agreeRules && agreePrivacy

  // Adopt whichever mode the caller requested (e.g. Header's separate
  // Sign in / Sign up buttons) each time the modal opens.
  useEffect(() => {
    if (authModalOpen) setMode(authModalMode)
  }, [authModalOpen, authModalMode])

  if (!authModalOpen) return null

  function reset() {
    setEmail('')
    setPassword('')
    setNickname('')
    setAgreeAdvice(false)
    setAgreeRules(false)
    setAgreePrivacy(false)
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
        await register(email, password, nickname.trim(), consent)
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
            <X aria-hidden="true" size={14} color="currentColor" />
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

        {mode === 'signUp' && (
          <label className="mb-3 block">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
              {t('auth.nickname')}
            </span>
            <input
              type="text"
              required
              minLength={2}
              maxLength={30}
              autoComplete="nickname"
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              className="w-full rounded-xl border border-border bg-surface2 px-3.5 py-2.5 text-sm text-slate-100 outline-none transition focus:border-accent focus:ring-4 focus:ring-accent/10"
            />
            <p className="mt-1.5 text-[0.7rem] text-muted">{t('auth.nicknameHint')}</p>
          </label>
        )}

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
        {mode === 'signUp' && (
          <p className="mb-3 text-[0.7rem] text-muted">{t('auth.passwordHint')}</p>
        )}

        {mode === 'signUp' && (
          <div className="mb-3 space-y-2 rounded-lg border border-border bg-surface2/50 px-3 py-2.5">
            <label className="flex cursor-pointer items-start gap-2.5">
              <input
                type="checkbox"
                required
                checked={agreeAdvice}
                onChange={(e) => setAgreeAdvice(e.target.checked)}
                className="mt-0.5 h-4 w-4 flex-shrink-0 rounded border-border bg-surface2 accent-accent"
              />
              <span className="text-xs leading-relaxed text-slate-300">
                {t('auth.agreeNotAdvice')}
              </span>
            </label>
            <label className="flex cursor-pointer items-start gap-2.5">
              <input
                type="checkbox"
                required
                checked={agreeRules}
                onChange={(e) => setAgreeRules(e.target.checked)}
                className="mt-0.5 h-4 w-4 flex-shrink-0 rounded border-border bg-surface2 accent-accent"
              />
              <span className="text-xs leading-relaxed text-slate-300">
                {t('auth.agreeCommunityRules')}
              </span>
            </label>
            <label className="flex cursor-pointer items-start gap-2.5">
              <input
                type="checkbox"
                required
                checked={agreePrivacy}
                onChange={(e) => setAgreePrivacy(e.target.checked)}
                className="mt-0.5 h-4 w-4 flex-shrink-0 rounded border-border bg-surface2 accent-accent"
              />
              <span className="text-xs leading-relaxed text-slate-300">
                {t('auth.consentLabel')}
                <span className="block text-muted">{t('auth.consentNotice')}</span>
              </span>
            </label>
          </div>
        )}

        {error && (
          <p className="mb-3 mt-3 rounded-lg bg-down/10 px-3 py-2 text-xs text-down">{error}</p>
        )}

        <button
          type="submit"
          disabled={submitting || (mode === 'signUp' && !consent)}
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
