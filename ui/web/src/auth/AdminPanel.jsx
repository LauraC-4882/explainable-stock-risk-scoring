import { useEffect, useState } from 'react'
import { apiAdminAnalytics } from '../api'
import AdminAnalyticsChart from '../components/AdminAnalyticsChart'
import AdminUserTable from '../components/AdminUserTable'
import { useLanguage } from '../i18n/LanguageContext'
import { useAuth } from './AuthContext'

function StatTile({ label, value }) {
  return (
    <div className="panel-tile px-3 py-2.5">
      <div className="text-[0.62rem] font-semibold uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-0.5 text-lg font-black tabular-nums text-slate-100">{value}</div>
    </div>
  )
}

export default function AdminPanel() {
  const { t } = useLanguage()
  const { token, adminPanelOpen, closeAdminPanel } = useAuth()
  const [tab, setTab] = useState('overview')
  const [analytics, setAnalytics] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!adminPanelOpen) return
    let cancelled = false
    setLoading(true)
    setTab('overview')
    apiAdminAnalytics(token)
      .then((data) => {
        if (!cancelled) setAnalytics(data)
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [adminPanelOpen, token])

  if (!adminPanelOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      style={{ animationDuration: '0.15s' }}
      onClick={closeAdminPanel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[85vh] w-full max-w-2xl animate-fade-in flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-black/50"
        style={{ animationDuration: '0.2s' }}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="flex items-center gap-2 text-lg font-bold text-slate-100">
            <span aria-hidden="true">🛡️</span> {t('admin.title')}
          </h2>
          <button
            onClick={closeAdminPanel}
            className="rounded-md px-1.5 py-0.5 text-base leading-none text-muted transition hover:bg-down/10 hover:text-down"
          >
            ✕
          </button>
        </div>

        <div className="flex gap-1.5 border-b border-border px-5 py-3">
          {['overview', 'usage', 'users'].map((key) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`rounded-full px-3.5 py-1.5 text-sm font-semibold transition-all duration-150 ${
                tab === key
                  ? 'bg-accent text-white shadow-lg shadow-accent/20'
                  : 'border border-border text-muted hover:border-accent hover:text-accent'
              }`}
            >
              {t(`admin.tab.${key}`)}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="skeleton-shimmer animate-shimmer h-40 w-full rounded-lg" />
          ) : tab === 'overview' ? (
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
              <StatTile label={t('admin.totalRequests')} value={analytics?.total_requests ?? 0} />
              <StatTile label={t('admin.uniqueUsers')} value={analytics?.unique_users ?? 0} />
              <StatTile label={t('admin.last24h')} value={analytics?.requests_last_24h ?? 0} />
              <StatTile label={t('admin.last7d')} value={analytics?.requests_last_7d ?? 0} />
            </div>
          ) : tab === 'usage' ? (
            <div className="space-y-4">
              <div>
                <div className="mb-1.5 text-[0.67rem] font-semibold uppercase tracking-wide text-muted">
                  {t('admin.hourlyHistogram')}
                </div>
                {analytics && <AdminAnalyticsChart hourly={analytics.hourly_histogram} />}
              </div>
              <div>
                <div className="mb-1.5 text-[0.67rem] font-semibold uppercase tracking-wide text-muted">
                  {t('admin.topPaths')}
                </div>
                <div className="space-y-1">
                  {(analytics?.top_paths ?? []).map((p) => (
                    <div
                      key={`${p.method} ${p.path}`}
                      className="panel-tile flex items-center justify-between gap-3 px-3 py-1.5"
                    >
                      <span className="min-w-0 truncate font-mono text-xs text-slate-300">
                        <span className="text-muted">{p.method}</span> {p.path}
                      </span>
                      <span className="flex-shrink-0 font-mono text-xs font-bold text-accent">
                        {p.count}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <AdminUserTable />
          )}
        </div>
      </div>
    </div>
  )
}
