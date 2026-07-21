import { X } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { apiListPosts } from '../api'
import CommunityDisclaimer from '../components/CommunityDisclaimer'
import Leaderboard from '../components/Leaderboard'
import PostCard from '../components/PostCard'
import PostComposer from '../components/PostComposer'
import { useLanguage } from '../i18n/LanguageContext'
import { useAuth } from './AuthContext'

export default function CommunityPanel() {
  const { t } = useLanguage()
  const { token, communityPanelOpen, communityPanelTicker, closeCommunityPanel } = useAuth()
  const [tab, setTab] = useState('feed')
  const [tickerFilter, setTickerFilter] = useState(communityPanelTicker)
  const [sort, setSort] = useState('recent')
  const [posts, setPosts] = useState([])
  const [loading, setLoading] = useState(true)

  // Seed the filter from whatever ticker the panel was opened with (e.g. a
  // stock card's "view all analysis" link) — but only when the panel just
  // opened, so clearing the filter from inside the panel doesn't snap back.
  useEffect(() => {
    if (communityPanelOpen) {
      setTickerFilter(communityPanelTicker)
      setTab('feed')
    }
  }, [communityPanelOpen, communityPanelTicker])

  useEffect(() => {
    if (!communityPanelOpen) return
    let cancelled = false
    setLoading(true)
    apiListPosts(token, { ticker: tickerFilter, sort })
      .then((res) => {
        if (!cancelled) setPosts(res.items)
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [communityPanelOpen, tickerFilter, sort, token])

  if (!communityPanelOpen) return null

  function handlePosted(post) {
    setPosts((prev) => [post, ...prev])
  }

  function handleVoted(updated) {
    setPosts((prev) => prev.map((p) => (p.id === updated.id ? { ...p, ...updated } : p)))
  }

  function handleDeleted(postId) {
    setPosts((prev) => prev.filter((p) => p.id !== postId))
  }

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      style={{ animationDuration: '0.15s' }}
      onClick={closeCommunityPanel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[85vh] w-full max-w-2xl animate-fade-in flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-black/50"
        style={{ animationDuration: '0.2s' }}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-lg font-bold text-slate-100">{t('community.title')}</h2>
          <button
            onClick={closeCommunityPanel}
            className="rounded-md px-1.5 py-0.5 text-base leading-none text-muted transition hover:bg-down/10 hover:text-down"
          >
            <X aria-hidden="true" size={14} color="currentColor" />
          </button>
        </div>

        <CommunityDisclaimer />

        <div className="flex gap-1.5 border-b border-border px-5 py-3">
          {['feed', 'leaderboard'].map((key) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`rounded-full px-3.5 py-1.5 text-sm font-semibold transition-all duration-150 ${
                tab === key
                  ? 'bg-accent text-white shadow-lg shadow-accent/20'
                  : 'border border-border text-muted hover:border-accent hover:text-accent'
              }`}
            >
              {t(`community.tab.${key}`)}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {tab === 'feed' ? (
            <div className="space-y-3.5">
              <PostComposer initialTicker={tickerFilter} onPosted={handlePosted} />

              <div className="flex flex-wrap items-center gap-2">
                {tickerFilter && (
                  <button
                    onClick={() => setTickerFilter(null)}
                    className="flex items-center gap-1 rounded-full bg-accent/15 px-3 py-1 text-xs font-bold text-accent"
                  >
                    {tickerFilter} <X aria-hidden="true" size={12} color="currentColor" />
                  </button>
                )}
                <div className="ml-auto flex gap-1.5">
                  {['recent', 'top'].map((key) => (
                    <button
                      key={key}
                      onClick={() => setSort(key)}
                      className={`rounded-full px-3 py-1 text-xs font-semibold transition-all duration-150 ${
                        sort === key
                          ? 'bg-accent text-white shadow-lg shadow-accent/20'
                          : 'border border-border text-muted hover:border-accent hover:text-accent'
                      }`}
                    >
                      {t(`community.sort.${key}`)}
                    </button>
                  ))}
                </div>
              </div>

              {loading ? (
                <div className="space-y-2">
                  <div className="skeleton-shimmer animate-shimmer h-24 w-full rounded-lg" />
                  <div className="skeleton-shimmer animate-shimmer h-24 w-full rounded-lg" />
                </div>
              ) : posts.length === 0 ? (
                <p className="px-2 py-10 text-center text-sm leading-relaxed text-muted">
                  {t('community.feedEmpty')}
                </p>
              ) : (
                <div className="space-y-2.5">
                  {posts.map((post) => (
                    <PostCard
                      key={post.id}
                      post={post}
                      onVoted={handleVoted}
                      onDeleted={handleDeleted}
                      showTicker={!tickerFilter}
                    />
                  ))}
                </div>
              )}
            </div>
          ) : (
            <Leaderboard />
          )}
        </div>
      </div>
    </div>
  )
}
