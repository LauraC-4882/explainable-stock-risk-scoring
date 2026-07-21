import { ThumbsDown, ThumbsUp } from '@phosphor-icons/react'
import { useState } from 'react'
import { apiVote } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'

// Thumbs pair for one community post. Optimistic update on click, reconciled
// with the server's fresh tally in the response; auth-gates by opening the
// sign-in modal instead of voting when logged out. Hidden entirely by the
// caller (not here) when post.is_own_post — self-votes are rejected
// server-side regardless, but the button shouldn't even be clickable.
export default function VoteButtons({ post, onVoted }) {
  const { t } = useLanguage()
  const { token, openAuthModal } = useAuth()
  const [busy, setBusy] = useState(false)

  async function cast(value) {
    if (!token) {
      openAuthModal('signIn')
      return
    }
    if (busy) return
    setBusy(true)
    try {
      const updated = await apiVote(token, post.id, value)
      onVoted(updated)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => cast(1)}
        disabled={busy}
        title={t('community.voteUp')}
        className={`flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-bold transition-all duration-150 hover:scale-105 active:scale-95 disabled:opacity-50 ${
          post.my_vote === 1
            ? 'border-risk-low bg-risk-low/15 text-risk-low'
            : 'border-border text-muted hover:border-risk-low hover:text-risk-low'
        }`}
      >
        <ThumbsUp
          aria-hidden="true"
          size={14}
          weight={post.my_vote === 1 ? 'fill' : 'thin'}
          color="currentColor"
        />
        {post.upvotes}
      </button>
      <button
        onClick={() => cast(-1)}
        disabled={busy}
        title={t('community.voteDown')}
        className={`flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-bold transition-all duration-150 hover:scale-105 active:scale-95 disabled:opacity-50 ${
          post.my_vote === -1
            ? 'border-risk-extreme bg-risk-extreme/15 text-risk-extreme'
            : 'border-border text-muted hover:border-risk-extreme hover:text-risk-extreme'
        }`}
      >
        <ThumbsDown
          aria-hidden="true"
          size={14}
          weight={post.my_vote === -1 ? 'fill' : 'thin'}
          color="currentColor"
        />
        {post.downvotes}
      </button>
    </div>
  )
}
