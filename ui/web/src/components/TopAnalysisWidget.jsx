import { useEffect, useState } from 'react'
import { apiListPosts } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import AccuracyBadge from './AccuracyBadge'

// Compact "top community take" slot for one ticker. Fetches independently
// of the card's main score/timeseries load (own effect, own loading state)
// so it never blocks or delays the primary reason a user opened this card.
export default function TopAnalysisWidget({ ticker }) {
  const { t } = useLanguage()
  const { openCommunityPanel } = useAuth()
  const [post, setPost] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    apiListPosts(null, { ticker, sort: 'top', limit: 1 })
      .then((res) => {
        if (!cancelled) setPost(res.items[0] || null)
      })
      .catch(() => {
        if (!cancelled) setPost(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [ticker])

  if (loading) {
    return (
      <div className="border-b border-border px-4 py-3.5 sm:px-5">
        <div className="skeleton-shimmer animate-shimmer h-14 w-full rounded-lg" />
      </div>
    )
  }

  return (
    <div className="border-b border-border px-4 py-3.5 sm:px-5">
      <div className="mb-1.5 flex items-center gap-1.5 text-[0.67rem] font-semibold uppercase tracking-wide text-muted">
        <span className="icon-badge h-6 w-6 text-[0.72rem]">
          <span aria-hidden="true">💬</span>
        </span>
        {t('community.topAnalysis')}
      </div>

      {post ? (
        <button
          onClick={() => openCommunityPanel(ticker)}
          className="panel-tile w-full px-3 py-2.5 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-[#3b2a5e]"
        >
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-semibold text-slate-200">{post.author_handle}</span>
            <AccuracyBadge accuracy={post.author_accuracy} />
          </div>
          <p className="mt-1 truncate text-sm text-slate-300">{post.body}</p>
        </button>
      ) : (
        <button
          onClick={() => openCommunityPanel(ticker)}
          className="panel-tile w-full px-3 py-2.5 text-left text-sm text-muted transition-all duration-200 hover:-translate-y-0.5 hover:border-[#3b2a5e] hover:text-accent"
        >
          {t('community.beFirst')}
        </button>
      )}
    </div>
  )
}
