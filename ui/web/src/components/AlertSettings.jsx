import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import { dateLocale } from '../utils'

// Per-stock email alert triggers, rendered inside the watchlist panel.
//
// Two controls, each a checkbox plus a number, because they answer different
// questions: "tell me when this gets risky" (an absolute level) and "tell me
// when this moves fast" (a rate). A single combined control would have to pick
// one meaning and silently drop the other.
//
// Saved on blur and on Enter rather than behind a Save button: the two inputs
// are independent, there is nothing to review before committing, and a form
// with one button per row is more chrome than the setting is worth. Every save
// is echoed by the server and the row is replaced with what came back, so a
// value the backend rejects never lingers on screen looking accepted.

export const SPIKE_DEFAULT = 15

// The number inputs must accept "" while being typed — a controlled input that
// coerces "" to 0 makes the field impossible to clear. Empty means "unset",
// which is a different thing from 0, and only becomes a number on save.
export function parseSetting(raw, { min, max }) {
  if (raw === '' || raw == null) return null
  const n = Number(raw)
  if (!Number.isFinite(n)) return null
  return Math.min(max, Math.max(min, Math.round(n)))
}

export default function AlertSettings({ item }) {
  const { t, lang } = useLanguage()
  const { setAlertSettings, user, resubscribeAlerts } = useAuth()

  const [threshold, setThreshold] = useState(
    item.alert_threshold == null ? '' : String(item.alert_threshold)
  )
  const [spike, setSpike] = useState(
    item.alert_spike_points == null ? '' : String(item.alert_spike_points)
  )
  const [status, setStatus] = useState(null) // 'saved' | 'error' | null
  const [busy, setBusy] = useState(false)

  const thresholdOn = threshold !== ''
  const spikeOn = spike !== ''

  async function save(next) {
    setBusy(true)
    try {
      await setAlertSettings(item.ticker, {
        threshold: parseSetting(next.threshold, { min: 0, max: 100 }),
        spikePoints: parseSetting(next.spike, { min: 1, max: 100 }),
      })
      setStatus('saved')
    } catch {
      setStatus('error')
    } finally {
      setBusy(false)
    }
  }

  function toggleThreshold() {
    const next = thresholdOn ? '' : '70'
    setThreshold(next)
    save({ threshold: next, spike })
  }

  function toggleSpike() {
    const next = spikeOn ? '' : String(SPIKE_DEFAULT)
    setSpike(next)
    save({ threshold, spike: next })
  }

  const numberField = (value, onChange, onCommit, label, { min, max }) => (
    <input
      type="number"
      inputMode="numeric"
      min={min}
      max={max}
      value={value}
      aria-label={label}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onCommit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          e.currentTarget.blur() // blur fires onCommit — one save path, not two
        }
      }}
      className="w-14 rounded-md border border-border bg-surface2/60 px-1.5 py-0.5 text-center font-mono text-[0.7rem] text-slate-100 focus:border-accent focus:outline-none"
    />
  )

  const lastSent = item.alert_sent_at
    ? new Date(item.alert_sent_at).toLocaleDateString(dateLocale(lang), {
        month: 'short',
        day: 'numeric',
      })
    : null

  return (
    <div className="mt-2 space-y-1.5 border-t border-border/60 pt-2">
      {/* Account-level opt-out beats any per-stock setting, so say so here
          rather than letting someone configure a threshold that cannot fire. */}
      {user && user.email_alerts_enabled === false && (
        <p className="text-[0.66rem] leading-relaxed text-risk-extreme">
          {t('emailAlerts.unsubscribed')}{' '}
          <button
            onClick={resubscribeAlerts}
            className="underline underline-offset-2 hover:text-slate-100"
          >
            {t('emailAlerts.resubscribe')}
          </button>
        </p>
      )}

      <label className="flex items-center gap-2 text-[0.68rem] text-muted">
        <input
          type="checkbox"
          checked={thresholdOn}
          onChange={toggleThreshold}
          disabled={busy}
          className="h-3 w-3 flex-shrink-0 accent-accent"
        />
        <span>{t('emailAlerts.thresholdLabel')}</span>
        {thresholdOn &&
          numberField(
            threshold,
            setThreshold,
            () => save({ threshold, spike }),
            t('emailAlerts.thresholdAria', { ticker: item.ticker }),
            { min: 0, max: 100 }
          )}
      </label>

      <label className="flex items-center gap-2 text-[0.68rem] text-muted">
        <input
          type="checkbox"
          checked={spikeOn}
          onChange={toggleSpike}
          disabled={busy}
          className="h-3 w-3 flex-shrink-0 accent-accent"
        />
        <span>{t('emailAlerts.spikeLabel')}</span>
        {spikeOn &&
          numberField(
            spike,
            setSpike,
            () => save({ threshold, spike }),
            t('emailAlerts.spikeAria', { ticker: item.ticker }),
            { min: 1, max: 100 }
          )}
      </label>

      <p className="text-[0.62rem] text-muted">
        {status === 'error' ? (
          <span role="alert" className="text-down">
            {t('emailAlerts.saveFailed')}
          </span>
        ) : status === 'saved' ? (
          <span className="text-up">{t('emailAlerts.saved')}</span>
        ) : lastSent ? (
          t('emailAlerts.lastSent', { date: lastSent })
        ) : thresholdOn || spikeOn ? (
          t('emailAlerts.neverSent')
        ) : null}
      </p>
    </div>
  )
}
