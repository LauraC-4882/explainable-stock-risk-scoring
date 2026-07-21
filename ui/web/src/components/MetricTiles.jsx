import { useState } from 'react'
import { betaReading, LEVEL_TONE, rsiReading, varReading, volReading } from '../explain/readings'
import { useLanguage } from '../i18n/LanguageContext'
import { fmt } from '../utils'

// Each tile is clickable: it shows the value plus a one-word reading of that
// value, and expands into "what this measures" + "what this particular number
// means". Both sentences come from the deterministic threshold table in
// explain/readings.js — no model call, so the copy is fixed, reviewable and
// strictly descriptive (never an action suggestion).
export default function MetricTiles({ score }) {
  const { t } = useLanguage()
  const [open, setOpen] = useState(null)

  const rsi = score.indicators?.rsi_14
  const beta = score.beta != null ? +score.beta : null
  const rsiClass = rsi > 70 ? 'text-down' : rsi < 30 ? 'text-up' : 'text-slate-100'

  const metrics = [
    {
      key: 'vol30d',
      label: t('metrics.vol30d'),
      value: fmt(score.volatility_30d, 100, 1, '%'),
      level: volReading(score.volatility_30d),
      group: 'vol',
      glossary: t('glossary.volatility'),
    },
    {
      key: 'var95',
      label: t('metrics.var95'),
      value: fmt(score.var_95, 100, 2, '%'),
      valueClass: 'text-down',
      level: varReading(score.var_95),
      group: 'var95',
      glossary: t('glossary.var95'),
    },
    {
      key: 'beta',
      label: t('metrics.beta'),
      value: beta != null ? beta.toFixed(2) : '—',
      level: betaReading(beta),
      group: 'beta',
      glossary: t('glossary.beta'),
    },
    {
      key: 'rsi',
      label: t('metrics.rsi'),
      value: fmt(rsi, 1, 1),
      valueClass: rsiClass,
      level: rsiReading(rsi),
      group: 'rsi',
      glossary: t('glossary.rsi'),
    },
  ]

  const active = metrics.find((m) => m.key === open)

  return (
    <div className="border-b border-border bg-surface2/20">
      {/* Phones get a roomier 2×2 grid (with bigger type) instead of four
          cramped columns; the divide-x rules only make sense on one row, so
          they apply from sm: up. */}
      <div className="grid grid-cols-2 gap-y-1 py-1 sm:grid-cols-4 sm:gap-y-0 sm:divide-x sm:divide-border sm:py-0">
        {metrics.map((m) => (
          <button
            key={m.key}
            onClick={() => setOpen((o) => (o === m.key ? null : m.key))}
            aria-expanded={open === m.key}
            className={`px-3 py-2.5 text-left transition-colors duration-150 hover:bg-surface2/60 sm:px-3.5 ${
              open === m.key ? 'bg-accent/[0.08]' : ''
            }`}
          >
            <div className="flex items-center gap-1 whitespace-nowrap text-[0.62rem] font-semibold uppercase tracking-wide text-muted max-sm:text-[0.72rem] sm:text-[0.65rem]">
              {m.label}
              <span
                aria-hidden="true"
                className={`flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center rounded-full border text-[9px] font-bold leading-none transition-colors ${
                  open === m.key ? 'border-accent text-accent' : 'border-muted/40 text-muted'
                }`}
              >
                ?
              </span>
            </div>
            <div
              className={`mt-0.5 text-sm font-bold tabular-nums max-sm:text-lg ${m.valueClass || ''}`}
            >
              {m.value}
            </div>
            {m.level && (
              <div
                className={`mt-1 text-[0.55rem] font-bold uppercase tracking-wide max-sm:text-[0.66rem] sm:text-[0.58rem] ${
                  LEVEL_TONE[m.level] || 'text-muted'
                }`}
              >
                {t(`readings.chip.${m.level}`)}
              </div>
            )}
          </button>
        ))}
      </div>

      {active && (
        <div className="animate-fade-in border-t border-border px-5 py-4">
          <div className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">
            {active.label} · {t('readings.title')}
          </div>
          <p className="mt-2 text-sm leading-relaxed text-slate-300">{active.glossary}</p>
          {active.level && (
            <p className="mt-2 text-sm leading-relaxed text-slate-200">
              {t(`readings.${active.group}.${active.level}`)}
            </p>
          )}
          <p className="mt-2.5 text-[0.68rem] leading-relaxed text-muted">
            {t('readings.disclaimer')}
          </p>
        </div>
      )}
    </div>
  )
}
