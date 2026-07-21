import { useEffect, useState } from 'react'
import { apiAdminBanUser, apiAdminListUsers, apiAdminUnbanUser } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'

export default function AdminUserTable() {
  const { t, lang } = useLanguage()
  const { token, user: currentUser } = useAuth()
  const [query, setQuery] = useState('')
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)

  // Debounced search: wait out typing before hitting the API, and drop a
  // stale response if the query changed again before it landed.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const timer = setTimeout(() => {
      apiAdminListUsers(token, { q: query })
        .then((res) => {
          if (!cancelled) setUsers(res.items)
        })
        .catch(() => {})
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }, 250)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query, token])

  async function toggleBan(u) {
    if (busyId) return
    setBusyId(u.id)
    try {
      const updated = u.is_banned
        ? await apiAdminUnbanUser(token, u.id)
        : await apiAdminBanUser(token, u.id)
      setUsers((prev) => prev.map((x) => (x.id === updated.id ? updated : x)))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-3">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t('admin.searchUsers')}
        className="w-full rounded-lg border border-border bg-surface2/60 px-3 py-2 text-sm text-slate-100 placeholder:text-muted focus:border-accent focus:outline-none"
      />

      {loading ? (
        <div className="skeleton-shimmer animate-shimmer h-40 w-full rounded-lg" />
      ) : users.length === 0 ? (
        <p className="px-2 py-8 text-center text-sm text-muted">{t('admin.noUsers')}</p>
      ) : (
        <div className="space-y-1.5">
          {users.map((u) => {
            const isSelf = currentUser?.id === u.id
            return (
              <div
                key={u.id}
                className="panel-tile flex items-center justify-between gap-3 px-3 py-2.5"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-sm font-semibold text-slate-200">{u.email}</span>
                    {u.is_admin && (
                      <span className="flex-shrink-0 rounded-full bg-accent/15 px-1.5 py-0.5 text-[0.58rem] font-bold uppercase text-accent">
                        {t('admin.adminBadge')}
                      </span>
                    )}
                    {u.is_banned && (
                      <span className="flex-shrink-0 rounded-full bg-risk-extreme/15 px-1.5 py-0.5 text-[0.58rem] font-bold uppercase text-risk-extreme">
                        {t('admin.bannedBadge')}
                      </span>
                    )}
                  </div>
                  <div className="text-[0.62rem] text-muted">
                    {new Date(u.created_at).toLocaleDateString(lang === 'zh' ? 'zh-CN' : 'en-US')}
                  </div>
                </div>
                {/* No ban control on your own row or on another admin —
                    mirrors the backend guardrails so the button never
                    appears where it would 403; the backend stays the
                    actual authority. */}
                {!isSelf && !u.is_admin && (
                  <button
                    onClick={() => toggleBan(u)}
                    disabled={busyId === u.id}
                    className={`flex-shrink-0 rounded-full border px-3 py-1 text-xs font-semibold transition-all duration-150 active:scale-95 disabled:opacity-50 ${
                      u.is_banned
                        ? 'border-border text-muted hover:border-risk-low hover:text-risk-low'
                        : 'border-risk-extreme/60 text-risk-extreme hover:bg-risk-extreme/10'
                    }`}
                  >
                    {u.is_banned ? t('admin.unban') : t('admin.ban')}
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
