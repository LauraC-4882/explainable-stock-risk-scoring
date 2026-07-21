import { useState } from 'react'
import { apiCreatePost } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import { inferMarket } from '../utils'

const BODY_MAX_LEN = 1000

export default function PostComposer({ initialTicker, onPosted }) {
  const { t } = useLanguage()
  const { token, user, openAuthModal } = useAuth()
  const [ticker, setTicker] = useState(initialTicker || '')
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  if (!user) {
    return (
      <div className="panel flex items-center justify-between gap-3 px-4 py-3.5">
        <span className="text-sm text-slate-300">{t('community.signInToPost')}</span>
        <button
          onClick={() => openAuthModal('signIn')}
          className="flex-shrink-0 rounded-full bg-accent px-4 py-1.5 text-xs font-bold text-white shadow-lg shadow-accent/20 transition-all duration-150 hover:brightness-110 active:scale-95"
        >
          {t('auth.signIn')}
        </button>
      </div>
    )
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const trimmedTicker = ticker.toUpperCase().trim()
    const trimmedBody = body.trim()
    if (!trimmedTicker || !trimmedBody || busy) return
    setBusy(true)
    setError(null)
    try {
      const post = await apiCreatePost(token, trimmedTicker, inferMarket(trimmedTicker), trimmedBody)
      setBody('')
      onPosted(post)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="panel space-y-2.5 px-4 py-3.5">
      <div className="flex items-center gap-2">
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          placeholder={t('community.tickerPlaceholder')}
          maxLength={12}
          className="w-28 flex-shrink-0 rounded-lg border border-border bg-surface2/60 px-2.5 py-1.5 text-sm font-bold uppercase text-slate-100 placeholder:text-muted placeholder:normal-case focus:border-accent focus:outline-none"
        />
        <span className="text-[0.65rem] text-muted">
          {body.length}/{BODY_MAX_LEN}
        </span>
      </div>
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value.slice(0, BODY_MAX_LEN))}
        placeholder={t('community.bodyPlaceholder')}
        rows={3}
        className="w-full resize-none rounded-lg border border-border bg-surface2/60 px-3 py-2 text-sm text-slate-100 placeholder:text-muted focus:border-accent focus:outline-none"
      />
      {error && <p className="text-xs text-down">⚠ {error}</p>}
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={busy || !ticker.trim() || !body.trim()}
          className="rounded-full bg-accent px-4 py-1.5 text-xs font-bold text-white shadow-lg shadow-accent/20 transition-all duration-150 hover:brightness-110 active:scale-95 disabled:opacity-50"
        >
          {busy ? t('community.posting') : t('community.post')}
        </button>
      </div>
    </form>
  )
}
