import { ClockCounterClockwise } from '@phosphor-icons/react'
import { useMemo, useState } from 'react'
import { apiHistoryEvents } from '../api'
import { useLanguage } from '../i18n/LanguageContext'

// [G8] Collapsible "historical events" panel: the named bull markets, bear
// markets, economic expansions, recessions and financial crises of the past
// century, with what THIS stock actually did inside each window it traded
// through — realised return, worst peak-to-trough drawdown, realised vol.
//
// Display-only, and unlike [G6]'s weight-0 block this one is not a producer at
// all: nothing here reaches risk_score. The payload says so
// (contributes_to_risk_score: false) and the intro copy repeats it in prose,
// because a panel this prominent would otherwise be read as an input. See
// market_history.py for the two reasons — the repo's no-weight-without-
// validation rule, and a survivorship-bias problem that rule alone misses.
//
// Data is fetched lazily on first expand: the endpoint pulls period="max"
// (every bar the ticker has), which is a heavier request than the card's 2y.
//
// The events are history, so colouring them is describing the past, not
// forecasting — the same licence OutcomePanel takes with its realised up/down
// percentages, and explicitly NOT the licence RegimeSignalsPanel withholds
// from its live chart-state reads.
const KIND_STYLE = {
  bull: 'text-up border-up/40 bg-up/10',
  bear: 'text-down border-down/40 bg-down/10',
  crisis: 'text-risk-extreme border-risk-extreme/40 bg-risk-extreme/10',
  expansion: 'text-accent border-accent/40 bg-accent/10',
  recession: 'text-risk-moderate border-risk-moderate/40 bg-risk-moderate/10',
}

const KIND_ORDER = ['bull', 'bear', 'expansion', 'recession', 'crisis']

const signed = (n, digits = 1) =>
  n === null || n === undefined ? '—' : `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`

const YEAR = (iso) => (iso ? iso.slice(0, 4) : null)

function KindBadge({ kind, label }) {
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide ${
        KIND_STYLE[kind] || 'text-muted border-border bg-surface2'
      }`}
    >
      {label}
    </span>
  )
}

function Stat({ label, value, className = '' }) {
  return (
    <div className="flex flex-col">
      <span className="text-[0.62rem] text-muted">{label}</span>
      <span className={`font-mono text-sm font-semibold ${className}`}>{value}</span>
    </div>
  )
}

// One event the stock actually traded through: the macro context on top, the
// stock's own realised numbers underneath.
function CoveredEvent({ event, name, summary, t }) {
  const span = event.ongoing
    ? `${YEAR(event.start)}–${t('history.ongoing')}`
    : `${YEAR(event.start)}–${YEAR(event.end)}`

  return (
    <div className="rounded-lg border border-border bg-surface2/50 p-3 transition-colors duration-150 hover:bg-surface2">
      <div className="flex flex-wrap items-center gap-2">
        <KindBadge kind={event.kind} label={t(`history.kind.${event.kind}`)} />
        <span className="text-sm font-semibold text-slate-100">{name}</span>
        <span className="font-mono text-[0.65rem] text-muted">{span}</span>
        {event.coverage === 'partial' && (
          <span className="rounded-full bg-surface px-2 py-0.5 text-[0.6rem] italic text-muted">
            {t('history.partial')}
          </span>
        )}
      </div>

      <p className="mt-1.5 text-[0.72rem] leading-relaxed text-slate-400">{summary}</p>

      <div className="mt-2.5 flex flex-wrap items-baseline gap-x-5 gap-y-1.5 border-t border-border/60 pt-2.5">
        <Stat
          label={t('history.stat.return')}
          value={signed(event.return_pct)}
          className={event.return_pct >= 0 ? 'text-up' : 'text-down'}
        />
        <Stat
          label={t('history.stat.drawdown')}
          value={signed(event.max_drawdown_pct)}
          className="text-down"
        />
        <Stat
          label={t('history.stat.vol')}
          value={
            event.annualized_vol_pct === null ? '—' : `${event.annualized_vol_pct.toFixed(1)}%`
          }
        />
        <Stat label={t('history.stat.days')} value={event.trading_days} />
      </div>
    </div>
  )
}

// Events entirely outside this ticker's price history. Compact by design —
// they carry no per-stock numbers, only the record that they happened.
function UncoveredEvent({ event, name, summary, t }) {
  const span = event.ongoing
    ? `${YEAR(event.start)}–${t('history.ongoing')}`
    : YEAR(event.start) === YEAR(event.end)
      ? YEAR(event.start)
      : `${YEAR(event.start)}–${YEAR(event.end)}`

  return (
    <div className="flex items-baseline gap-2 border-b border-border/40 py-1.5 last:border-b-0">
      <span className="w-20 flex-shrink-0 font-mono text-[0.65rem] text-muted">{span}</span>
      <KindBadge kind={event.kind} label={t(`history.kind.${event.kind}`)} />
      <span className="min-w-0 flex-1">
        <span className="text-[0.72rem] text-slate-300">{name}</span>
        <span className="ml-1.5 text-[0.68rem] leading-relaxed text-muted">{summary}</span>
      </span>
    </div>
  )
}

export default function HistoricalEventsPanel({ ticker }) {
  const { t, lang } = useLanguage()
  const [open, setOpen] = useState(false)
  const [showPrior, setShowPrior] = useState(false)
  const [kinds, setKinds] = useState(() => new Set(KIND_ORDER))
  const [data, setData] = useState(null)
  const [state, setState] = useState('idle') // 'idle' | 'loading' | 'ready' | 'error'

  function toggle() {
    const next = !open
    setOpen(next)
    if (next && state === 'idle') {
      setState('loading')
      apiHistoryEvents(ticker)
        .then((d) => {
          setData(d)
          setState('ready')
        })
        .catch(() => setState('error'))
    }
  }

  function toggleKind(kind) {
    setKinds((prev) => {
      const next = new Set(prev)
      // Never let the last filter be switched off — an empty panel reads as
      // "no such events exist" rather than "you filtered them all out".
      if (next.has(kind) && next.size > 1) next.delete(kind)
      else next.add(kind)
      return next
    })
  }

  // The backend serves both languages per event (they are data, not UI
  // chrome, so they can't live in the locale files without drifting from the
  // event ids they belong to). Pick the active one here.
  const localized = (event) => ({
    name: lang === 'zh' ? event.name_zh : event.name,
    summary: lang === 'zh' ? event.summary_zh : event.summary,
  })

  const { covered, prior } = useMemo(() => {
    if (!data) return { covered: [], prior: [] }
    const visible = data.events.filter((e) => kinds.has(e.kind))
    return {
      covered: visible.filter((e) => e.coverage !== 'none'),
      prior: visible.filter((e) => e.coverage === 'none'),
    }
  }, [data, kinds])

  return (
    <div className="border-b border-border">
      <button
        onClick={toggle}
        className="group flex w-full items-center justify-between px-5 py-3 text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted transition-colors duration-150 hover:text-accent max-sm:text-[0.8rem]"
        aria-expanded={open}
      >
        <span className="inline-flex items-center gap-2">
          <span className="icon-badge h-7 w-7 transition-colors duration-150 group-hover:bg-accent/20">
            <ClockCounterClockwise aria-hidden="true" size={16} />
          </span>
          {t('history.toggle')}
        </span>
        <svg
          className={`h-3 w-3 flex-shrink-0 transition-transform duration-300 ease-out ${open ? 'rotate-180' : ''}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      <div
        className="grid transition-[grid-template-rows] duration-300 ease-in-out"
        style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
      >
        <div className="overflow-hidden">
          <div className="space-y-3 px-5 pb-4">
            <p className="text-sm leading-relaxed text-slate-300">{t('history.intro')}</p>

            {state === 'loading' && (
              <div className="skeleton-shimmer animate-shimmer h-40 w-full rounded-lg" />
            )}
            {state === 'error' && <p className="text-xs text-muted">{t('history.error')}</p>}

            {state === 'ready' && data && (
              <>
                {/* Weight-0 statement first, not buried in a footnote: the
                    panel's prominence would otherwise imply the opposite. */}
                <p className="rounded-lg border border-border bg-surface2/40 p-2.5 text-[0.7rem] leading-relaxed text-muted">
                  {t('history.noScoreImpact')}
                </p>

                <div className="flex flex-wrap gap-1.5">
                  {KIND_ORDER.map((kind) => (
                    <button
                      key={kind}
                      onClick={() => toggleKind(kind)}
                      aria-pressed={kinds.has(kind)}
                      className={`rounded-full border px-2.5 py-1 text-[0.62rem] font-bold uppercase tracking-wide transition-all duration-150 active:scale-95 ${
                        kinds.has(kind)
                          ? KIND_STYLE[kind]
                          : 'border-border bg-transparent text-muted opacity-50 hover:opacity-80'
                      }`}
                    >
                      {t(`history.kind.${kind}`)}
                    </button>
                  ))}
                </div>

                <p className="font-mono text-[0.65rem] text-muted">
                  {t('history.coverage')
                    .replace('{ticker}', ticker)
                    .replace('{start}', data.price_history_start)
                    .replace('{covered}', data.events_covered)
                    .replace('{total}', data.events_total)}
                </p>

                {covered.length === 0 ? (
                  <p className="text-[0.7rem] text-muted">{t('history.noneCovered')}</p>
                ) : (
                  <div className="space-y-2">
                    {covered.map((event) => (
                      <CoveredEvent
                        key={event.id}
                        event={event}
                        {...localized(event)}
                        t={t}
                      />
                    ))}
                  </div>
                )}

                {prior.length > 0 && (
                  <div className="rounded-lg border border-border bg-surface2/30">
                    <button
                      onClick={() => setShowPrior((v) => !v)}
                      aria-expanded={showPrior}
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-[0.65rem] font-semibold uppercase tracking-wide text-muted transition-colors duration-150 hover:text-accent"
                    >
                      <span>
                        {t('history.priorToggle')
                          .replace('{ticker}', ticker)
                          .replace('{count}', prior.length)}
                      </span>
                      <svg
                        className={`h-3 w-3 flex-shrink-0 transition-transform duration-300 ease-out ${showPrior ? 'rotate-180' : ''}`}
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="3"
                      >
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                    </button>
                    {showPrior && (
                      <div className="px-3 pb-2">
                        {prior.map((event) => (
                          <UncoveredEvent
                            key={event.id}
                            event={event}
                            {...localized(event)}
                            t={t}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <p className="text-[0.68rem] leading-relaxed text-muted">
                  {t('history.takeaway')}
                </p>

                <div className="text-[0.62rem] leading-relaxed text-muted">
                  <span className="font-semibold">{t('history.sources')}</span>{' '}
                  {Object.entries(data.sources).map(([key, src], i) => (
                    <span key={key}>
                      {i > 0 && ' · '}
                      <a
                        href={src.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline decoration-dotted underline-offset-2 transition-colors duration-150 hover:text-accent"
                      >
                        {src.title}
                      </a>
                    </span>
                  ))}
                </div>

                <p className="text-[0.65rem] italic leading-relaxed text-muted">
                  {t('history.disclaimer')}
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
