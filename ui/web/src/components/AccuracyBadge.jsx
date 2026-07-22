import { useLanguage } from '../i18n/LanguageContext'

// Reused on post bylines and the leaderboard: null accuracy (below the
// backend's minimum-vote threshold, or zero votes) renders as a neutral
// "not enough votes yet" state — never as "0%", which would misleadingly
// read as "always wrong" rather than "no data yet."
export default function AccuracyBadge({ accuracy, size = 'sm' }) {
  const { t } = useLanguage()
  const sizeClass = size === 'sm' ? 'px-1.5 py-0.5 text-[0.62rem]' : 'px-2 py-1 text-xs'

  if (accuracy == null) {
    return (
      <span
        className={`inline-block rounded-full bg-muted/10 font-bold uppercase tracking-wide text-muted ${sizeClass}`}
      >
        {t('community.accuracyPending')}
      </span>
    )
  }

  const pct = Math.round(accuracy * 100)
  const color = pct >= 70 ? '#34d399' : pct >= 40 ? '#fbbf24' : '#f43f5e'

  return (
    <span
      className={`inline-block rounded-full font-bold tabular-nums ${sizeClass}`}
      style={{ color, backgroundColor: `${color}22` }}
    >
      {pct}% {t('community.accuracy')}
    </span>
  )
}
