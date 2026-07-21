import { useEffect, useState } from 'react'
import { apiLeaderboard } from '../api'
import { useLanguage } from '../i18n/LanguageContext'
import AccuracyBadge from './AccuracyBadge'

export default function Leaderboard() {
  const { t } = useLanguage()
  const [sort, setSort] = useState('accuracy')
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    apiLeaderboard({ sort })
      .then((rows) => {
        if (!cancelled) setEntries(rows)
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [sort])

  return (
    <div className="space-y-3">
      <div className="flex gap-1.5">
        {['accuracy', 'recent'].map((key) => (
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

      {loading ? (
        <div className="skeleton-shimmer animate-shimmer h-40 w-full rounded-lg" />
      ) : entries.length === 0 ? (
        <p className="px-2 py-8 text-center text-sm text-muted">{t('community.leaderboardEmpty')}</p>
      ) : (
        <div className="space-y-1.5">
          {entries.map((entry, i) => (
            <div
              key={entry.handle}
              className="panel-tile flex items-center justify-between gap-3 px-3 py-2.5"
            >
              <div className="flex min-w-0 items-center gap-2.5">
                <span className="w-5 flex-shrink-0 text-center text-xs font-black text-muted">
                  #{i + 1}
                </span>
                <span className="truncate font-mono text-sm font-semibold text-slate-200">
                  {entry.handle}
                </span>
              </div>
              <div className="flex flex-shrink-0 items-center gap-3">
                <span className="text-[0.65rem] text-muted">
                  {entry.post_count} {t('community.posts')}
                </span>
                <AccuracyBadge accuracy={entry.accuracy} size="md" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
