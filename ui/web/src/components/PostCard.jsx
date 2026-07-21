import { apiDeletePost } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import AccuracyBadge from './AccuracyBadge'
import VoteButtons from './VoteButtons'

export default function PostCard({ post, onVoted, onDeleted, showTicker = true }) {
  const { t, lang } = useLanguage()
  const { token } = useAuth()

  const timestamp = new Date(post.created_at).toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })

  async function handleDelete() {
    await apiDeletePost(token, post.id)
    onDeleted?.(post.id)
  }

  return (
    <div className="panel-tile animate-fade-in space-y-2 p-3.5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {showTicker && (
            <span className="rounded-full bg-accent/15 px-2 py-0.5 font-bold text-accent">
              {post.ticker}
            </span>
          )}
          <span className="font-mono text-muted">{post.author_handle}</span>
          <AccuracyBadge accuracy={post.author_accuracy} />
        </div>
        {post.can_delete && (
          <button
            onClick={handleDelete}
            title={post.is_own_post ? t('community.deletePost') : t('admin.deleteAsAdmin')}
            className="flex-shrink-0 rounded-md px-1.5 py-0.5 text-xs leading-none text-muted transition-colors duration-150 hover:bg-down/10 hover:text-down"
          >
            ✕
          </button>
        )}
      </div>

      <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">{post.body}</p>

      <div className="flex items-center justify-between gap-2 pt-0.5">
        <span className="text-[0.65rem] text-muted">{timestamp}</span>
        {post.is_own_post ? (
          <span className="text-[0.65rem] italic text-muted">{t('community.ownPost')}</span>
        ) : (
          <VoteButtons post={post} onVoted={onVoted} />
        )}
      </div>
    </div>
  )
}
