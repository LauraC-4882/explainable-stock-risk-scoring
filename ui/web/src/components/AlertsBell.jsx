import { Bell } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { apiMarkAlertsSeen, apiWatchlistAlerts } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import { dateLocale, riskColor } from '../utils'

// Risk-movement bell for the signed-in user's watchlist.
//
// An alert isn't a stored/pushed record — it's a recent notable move derived
// from the same snapshot history the watchlist board reads, so there's no
// delivery job to run and nothing to fall out of sync. Opening the panel marks
// everything read (server-side watermark), which is what clears the badge.
//
// Colour follows the same market-independent rule as the board: risk up =
// warning, risk down = calmer. See WatchlistBoard's note for why.
export default function AlertsBell({ onOpen }) {
  const { t, lang } = useLanguage()
  const { token, watchlist } = useAuth()
  const [alerts, setAlerts] = useState([])
  const [unread, setUnread] = useState(0)
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    apiWatchlistAlerts(token)
      .then((res) => {
        if (cancelled) return
        setAlerts(res.items || [])
        setUnread(res.unread || 0)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [token, watchlist.length])

  useEffect(() => {
    function onClickOutside(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('click', onClickOutside)
    return () => document.removeEventListener('click', onClickOutside)
  }, [])

  if (!token) return null

  function toggle() {
    const next = !open
    setOpen(next)
    // Opening the panel is the "read" event — the list stays visible, only
    // the badge clears, so a user who opens it can still act on what's there.
    if (next && unread > 0) {
      setUnread(0)
      apiMarkAlertsSeen(token).catch(() => {})
    }
  }

  const fmtDate = (iso) =>
    iso
      ? new Date(`${iso}T00:00:00`).toLocaleDateString(dateLocale(lang), {
          month: 'short',
          day: 'numeric',
        })
      : null

  return (
    <div ref={wrapRef} className="relative">
      <button
        onClick={toggle}
        title={t('alerts.title')}
        aria-label={t('alerts.title')}
        aria-expanded={open}
        className="relative flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full border border-accent/20 bg-white/[0.04] text-sm transition-all duration-150 hover:border-accent/40 hover:bg-accent/[0.14] active:scale-95"
      >
        <Bell aria-hidden="true" size={16} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-risk-extreme px-1 text-[0.58rem] font-bold text-white">
            {unread}
          </span>
        )}
      </button>

      {open && (
        <div className="glass absolute right-0 top-[calc(100%+8px)] z-30 w-80 animate-fade-in overflow-hidden rounded-2xl border border-accent/28 shadow-[0_24px_60px_rgba(0,0,0,0.55)]">
          <div className="border-b border-border px-4 py-3">
            <div className="text-xs font-bold uppercase tracking-wide text-slate-100">
              {t('alerts.title')}
            </div>
            <div className="mt-0.5 text-[0.62rem] text-muted">{t('alerts.subtitle')}</div>
          </div>

          {alerts.length === 0 ? (
            <p className="px-4 py-6 text-center text-xs text-muted">{t('alerts.empty')}</p>
          ) : (
            <div className="max-h-80 divide-y divide-border overflow-y-auto">
              {alerts.map((a) => {
                const rose = a.delta > 0
                return (
                  <button
                    key={a.ticker}
                    onClick={() => {
                      setOpen(false)
                      onOpen(a.ticker)
                    }}
                    className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors duration-150 hover:bg-accent/[0.08]"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="font-display text-sm font-bold text-slate-100">
                        {a.ticker}
                      </div>
                      <div className="mt-0.5 text-[0.62rem] text-muted">
                        {a.previous_score} → {a.risk_score} · {fmtDate(a.as_of)}
                      </div>
                    </div>
                    {a.band_changed && (
                      <span
                        className="rounded-full px-2 py-0.5 text-[0.55rem] font-bold uppercase"
                        style={{
                          color: riskColor(a.risk_label),
                          background: `${riskColor(a.risk_label)}22`,
                        }}
                      >
                        {t(`riskLabel.${a.risk_label}`)}
                      </span>
                    )}
                    <span
                      className={`font-display text-sm font-bold tabular-nums ${
                        rose ? 'text-risk-extreme' : 'text-risk-low'
                      }`}
                    >
                      {rose ? '▲ +' : '▼ '}
                      {a.delta}
                    </span>
                  </button>
                )
              })}
            </div>
          )}

          <p className="border-t border-border px-4 py-2.5 text-[0.6rem] leading-relaxed text-muted">
            {t('alerts.note')}
          </p>
        </div>
      )}
    </div>
  )
}
