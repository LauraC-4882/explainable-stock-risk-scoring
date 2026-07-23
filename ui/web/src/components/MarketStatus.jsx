import { useEffect, useState } from 'react'
import { useLanguage } from '../i18n/LanguageContext'

// US / CN session chips, derived purely from the clock via Intl time zones —
// no API call, and DST-correct because the browser's tz database does the
// conversion (a hand-rolled UTC offset would silently break every March and
// November).
//
// Deliberately coarse: exchange holidays are NOT modelled, so a chip can read
// "open" on Thanksgiving. Sessions only. Encoding the world's holiday
// calendars client-side would be its own maintenance liability; the chip's
// title says schedule-based so the limitation is stated, not hidden.

function minutesIn(timeZone, date) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hour: 'numeric',
    minute: 'numeric',
    weekday: 'short',
    hour12: false,
  }).formatToParts(date)
  const get = (type) => parts.find((p) => p.type === type)?.value
  const weekday = get('weekday')
  const minutes = Number(get('hour')) * 60 + Number(get('minute'))
  return { minutes, isWeekend: weekday === 'Sat' || weekday === 'Sun' }
}

export function usSession(date = new Date()) {
  const { minutes, isWeekend } = minutesIn('America/New_York', date)
  if (isWeekend) return 'closed'
  if (minutes >= 9 * 60 + 30 && minutes < 16 * 60) return 'open'
  if (minutes >= 4 * 60 && minutes < 9 * 60 + 30) return 'pre'
  return 'closed'
}

export function cnSession(date = new Date()) {
  const { minutes, isWeekend } = minutesIn('Asia/Shanghai', date)
  if (isWeekend) return 'closed'
  const am = minutes >= 9 * 60 + 30 && minutes < 11 * 60 + 30
  const pm = minutes >= 13 * 60 && minutes < 15 * 60
  if (am || pm) return 'open'
  if (minutes >= 11 * 60 + 30 && minutes < 13 * 60) return 'lunch'
  return 'closed'
}

const DOT = {
  open: 'bg-up',
  pre: 'bg-gold',
  lunch: 'bg-gold',
  closed: 'bg-muted/60',
}

export default function MarketStatus() {
  const { t } = useLanguage()
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000)
    return () => clearInterval(id)
  }, [])

  const chips = [
    { key: 'us', state: usSession(now) },
    { key: 'cn', state: cnSession(now) },
  ]

  return (
    <div className="flex items-center gap-2.5">
      {chips.map(({ key, state }) => (
        <span
          key={key}
          title={t('tickerBar.scheduleNote')}
          className="inline-flex items-center gap-1 whitespace-nowrap text-[0.62rem] font-bold uppercase tracking-wide text-slate-300"
        >
          {/* State is text + dot colour, never colour alone. */}
          <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${DOT[state]}`} />
          {t(`tickerBar.market.${key}`)} {t(`tickerBar.session.${state}`)}
        </span>
      ))}
    </div>
  )
}
