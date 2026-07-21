import { useEffect, useState } from 'react'
import { apiListPosts } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import PostCard from './PostCard'

// How many recent takes the in-card rail shows before "view all".
const RECENT_LIMIT = 5

// Recent community takes for one ticker, inline in the card. Fetches
// independently of the card's score/timeseries load (own effect, own loading
// state) so it never blocks the primary reason the card was opened.
//
// Shows the most RECENT posts rather than the single highest-voted one: a
// "top" post needs MIN_VOTES_FOR_TOP_POST votes to qualify, so a freshly
// discussed ticker showed an empty placeholder even when people had just
// posted. Recency has no such cold-start.
//
// Reuses PostCard (same component the full feed uses) so voting, reporting
// and deleting behave identically here — one vote code path, not two.
export default function TopAnalysisWidget({ ticker }) {
  const { t } = useLanguage()
  const { token, openCommunityPanel, communityPanelOpen } = useAuth()
  const [posts, setPosts] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)

  // Refetch when the ticker changes and whenever the community panel closes —
  // the user may have just posted or voted in there, and the card behind it
  // should reflect that instead of going stale until reload.
  useEffect(() => {
    if (communityPanelOpen) return
    let cancelled = false
    setLoading(true)
    apiListPosts(token, { ticker, sort: 'recent', limit: RECENT_LIMIT })
      .then((res) => {
        if (cancelled) return
        setPosts(res.items || [])
        setTotal(res.total ?? (res.items || []).length)
      })
      .catch(() => {
        if (!cancelled) setPosts([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [ticker, token, communityPanelOpen])

  function handleVoted(updated) {
    setPosts((prev) => prev.map((p) => (p.id === updated.id ? { ...p, ...updated } : p)))
  }

  function handleDeleted(postId) {
    setPosts((prev) => prev.filter((p) => p.id !== postId))
    setTotal((n) => Math.max(0, n - 1))
  }

  return (
    <div className="border-b border-border px-4 py-3.5 sm:px-5">
      <div className="mb-2 flex items-center justify-between gap-2">
        {/* Flourish type instead of an icon badge — cleaner section head. */}
        <div className="flex items-center gap-1.5">
          <span className="heading-flourish text-base">{t('community.recentTakes')}</span>
          {total > 0 && (
            <span className="rounded-full bg-accent/15 px-1.5 py-0.5 text-[0.6rem] text-accent">
              {total}
            </span>
          )}
        </div>
        <button
          onClick={() => openCommunityPanel(ticker)}
          className="flex-shrink-0 text-[0.68rem] font-semibold text-accent transition hover:text-accent2"
        >
          {total > RECENT_LIMIT ? t('community.viewAll') : t('community.shareCta')} →
        </button>
      </div>

      {loading ? (
        <div className="skeleton-shimmer animate-shimmer h-14 w-full rounded-lg" />
      ) : posts.length > 0 ? (
        <>
          <div className="max-h-72 space-y-2 overflow-y-auto pr-0.5">
            {posts.map((post) => (
              <PostCard
                key={post.id}
                post={post}
                onVoted={handleVoted}
                onDeleted={handleDeleted}
                showTicker={false}
              />
            ))}
          </div>
          {/* Standing reminder that this block is opinion, not the model's
              output — the score above it is computed, these are not. */}
          <p className="mt-2 text-[0.62rem] leading-relaxed text-muted">
            {t('community.opinionNote')}
          </p>
        </>
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
