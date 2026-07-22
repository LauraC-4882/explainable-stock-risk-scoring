import { Flag, X } from '@phosphor-icons/react'
import { useState } from 'react'
import { apiDeletePost, apiReportPost } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import AccuracyBadge from './AccuracyBadge'
import VoteButtons from './VoteButtons'

const REPORT_REASONS = [
  'investment_advice',
  'political',
  'misinformation',
  'solicitation',
  'abuse',
  'off_topic',
]

export default function PostCard({ post, onVoted, onDeleted, showTicker = true }) {
  const { t, lang } = useLanguage()
  const { token, user } = useAuth()
  const [reportOpen, setReportOpen] = useState(false)
  const [reported, setReported] = useState(false)

  async function handleReport(reason) {
    setReportOpen(false)
    try {
      await apiReportPost(token, post.id, reason)
    } catch {
      // 409 = already reported by this user — either way the end state the
      // user cares about is "flagged for the admin", so show it as done.
    }
    setReported(true)
  }

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
            <X aria-hidden="true" size={14} color="currentColor" />
          </button>
        )}
      </div>

      <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">{post.body}</p>

      <div className="flex items-center justify-between gap-2 pt-0.5">
        <span className="text-[0.65rem] text-muted">{timestamp}</span>
        <div className="flex items-center gap-2">
          {user &&
            !post.is_own_post &&
            (reported ? (
              <span className="text-[0.65rem] italic text-muted">{t('community.report.done')}</span>
            ) : (
              <button
                onClick={() => setReportOpen((o) => !o)}
                title={t('community.report.button')}
                aria-label={t('community.report.button')}
                className="rounded-md px-1 py-0.5 text-[0.7rem] leading-none text-muted opacity-60 transition hover:bg-down/10 hover:opacity-100"
              >
                <Flag aria-hidden="true" size={13} color="currentColor" />
              </button>
            ))}
          {post.is_own_post ? (
            <span className="text-[0.65rem] italic text-muted">{t('community.ownPost')}</span>
          ) : (
            <VoteButtons post={post} onVoted={onVoted} />
          )}
        </div>
      </div>

      {reportOpen && !reported && (
        <div className="animate-fade-in space-y-1.5 rounded-lg border border-border bg-surface2/50 px-2.5 py-2">
          <p className="text-[0.65rem] font-semibold text-slate-300">
            {t('community.report.prompt')}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {REPORT_REASONS.map((reason) => (
              <button
                key={reason}
                onClick={() => handleReport(reason)}
                className="rounded-full border border-border px-2 py-0.5 text-[0.65rem] text-muted transition hover:border-down hover:text-down"
              >
                {t(`community.report.reasons.${reason}`)}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
