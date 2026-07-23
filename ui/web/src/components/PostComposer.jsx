import { CircleAlert } from 'lucide-react'
import { useState } from 'react'
import { apiCreatePost } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import { inferMarket } from '../utils'

// Mirrors the backend's POST_BODY_MAX_LEN. It was 1000 here while the server
// rejected at 500 — a user could type 500 characters past the real limit and
// only learn at submit, with a 422 for their trouble.
const BODY_MAX_LEN = 500

// Client-side echo of a few moderation.py trading-directive patterns. A HINT,
// not a gate: the server's filter stays authoritative and richer; this only
// warns while typing so a user can rephrase before losing the submit
// round-trip. Deliberately tiny — a full mirror would drift from the server.
const PRECHECK_PATTERNS = [
  /\b(strong\s+)?(buy|sell)\s+now\b/i,
  /\bguaranteed\b/i,
  /\bto\s+the\s+moon\b/i,
  /\ball[-\s]?in\b/i,
  /建议买入|建议卖出|必涨|必跌|梭哈|保证(收益|赚)/,
]

export function precheckWarns(text) {
  return PRECHECK_PATTERNS.some((re) => re.test(text))
}

export default function PostComposer({ initialTicker, onPosted }) {
  const { t } = useLanguage()
  const { token, user, openAuthModal } = useAuth()
  const [ticker, setTicker] = useState(initialTicker || '')
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [preview, setPreview] = useState(false)

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
      const post = await apiCreatePost(
        token,
        trimmedTicker,
        inferMarket(trimmedTicker),
        trimmedBody
      )
      setBody('')
      onPosted(post)
    } catch (err) {
      // Backend filter rejections arrive as "moderation:<category>" —
      // map them onto the localized explanation instead of the raw code.
      const match = /^moderation:(\w+)$/.exec(err.message)
      setError(match ? t(`community.moderation.${match[1]}`) : err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="panel space-y-2.5 px-4 py-3.5">
      <p className="text-[0.7rem] leading-relaxed text-muted">{t('community.scopeHint')}</p>
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
      {preview ? (
        <div className="min-h-[4.5rem] w-full whitespace-pre-wrap rounded-lg border border-accent/30 bg-surface2/40 px-3 py-2 text-sm text-slate-100">
          {body.trim() || t('community.previewEmpty')}
        </div>
      ) : (
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value.slice(0, BODY_MAX_LEN))}
          placeholder={t('community.bodyPlaceholder')}
          rows={3}
          className="w-full resize-none rounded-lg border border-border bg-surface2/60 px-3 py-2 text-sm text-slate-100 placeholder:text-muted focus:border-accent focus:outline-none"
        />
      )}
      {precheckWarns(body) && (
        <p className="flex items-start gap-1 text-[0.7rem] leading-relaxed text-gold">
          <CircleAlert aria-hidden="true" size={13} className="mt-0.5 flex-shrink-0" />
          {t('community.precheckWarn')}
        </p>
      )}
      {error && (
        <p className="flex items-center gap-1 text-xs text-down">
          <CircleAlert aria-hidden="true" size={13} color="currentColor" /> {error}
        </p>
      )}
      <div className="flex items-center justify-between gap-3">
        <p className="text-[0.65rem] leading-relaxed text-muted">{t('community.postDisclaimer')}</p>
        <button
          type="button"
          onClick={() => setPreview((v) => !v)}
          aria-pressed={preview}
          className="flex-shrink-0 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-muted transition hover:text-slate-200"
        >
          {preview ? t('community.previewOff') : t('community.previewOn')}
        </button>
        <button
          type="submit"
          disabled={busy || !ticker.trim() || !body.trim()}
          className="flex-shrink-0 rounded-full bg-accent px-4 py-1.5 text-xs font-bold text-white shadow-lg shadow-accent/20 transition-all duration-150 hover:brightness-110 active:scale-95 disabled:opacity-50"
        >
          {busy ? t('community.posting') : t('community.post')}
        </button>
      </div>
    </form>
  )
}
