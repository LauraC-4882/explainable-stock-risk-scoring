import { FlaskConical } from 'lucide-react'
import { useState } from 'react'
import { apiBacktest } from '../api'
import { useLanguage } from '../i18n/LanguageContext'

// VaR backtest, computed live for THIS ticker when the panel is expanded —
// Kupiec coverage, Christoffersen independence and conditional coverage from
// validation/tail_tests, on the same rolling 95% VaR the metric tile shows,
// shifted one day so no forecast is graded on data it had seen.
//
// There is deliberately no site-wide "our VaR is N% accurate" headline
// anywhere: a global average would hide exactly the per-name failures a
// backtest exists to expose. What renders here is this ticker's own breach
// count against its 5% target, and whether each test rejects at the 5% level
// — including when the answer is unflattering. A validation panel that only
// ever shows passes is marketing, not validation.

export default function BacktestPanel({ ticker }) {
  const { t } = useLanguage()
  const [open, setOpen] = useState(false)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function toggle() {
    const next = !open
    setOpen(next)
    if (next && !data && !busy) {
      setBusy(true)
      try {
        setData(await apiBacktest(ticker))
        setError(null)
      } catch (err) {
        setError(err.message)
      } finally {
        setBusy(false)
      }
    }
  }

  const rows = data
    ? [
        ['kupiec', data.kupiec],
        ['independence', data.independence],
        ['conditionalCoverage', data.conditional_coverage],
      ]
    : []

  return (
    <div className="border-b border-border">
      <button
        onClick={toggle}
        className="group flex w-full items-center justify-between px-5 py-3 text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted transition-colors duration-150 hover:text-accent max-sm:text-[0.8rem]"
        aria-expanded={open}
      >
        <span className="inline-flex items-center gap-2">
          <span className="icon-badge h-7 w-7 transition-colors duration-150 group-hover:bg-accent/20">
            <FlaskConical aria-hidden="true" size={16} />
          </span>
          {t('backtest.toggle')}
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
            <p className="text-[0.76rem] leading-relaxed text-muted">{t('backtest.intro')}</p>

            {busy && <div className="skeleton-shimmer animate-shimmer h-16 w-full rounded-lg" />}
            {error && (
              <p role="alert" className="text-xs text-down">
                {error}
              </p>
            )}

            {data && (
              <>
                <div className="rounded-lg border border-accent/20 bg-surface2/40 px-3.5 py-2.5 text-[0.8rem] text-slate-200">
                  {t('backtest.breachLine', {
                    days: data.days,
                    breaches: data.breaches,
                    rate: data.breach_rate_pct,
                    target: data.target_pct,
                  })}
                </div>

                <div className="space-y-1.5">
                  {rows.map(([key, test]) => (
                    <div
                      key={key}
                      className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2"
                    >
                      <div className="min-w-0">
                        <div className="text-[0.76rem] font-semibold text-slate-100">
                          {t(`backtest.tests.${key}`)}
                        </div>
                        <div className="font-mono text-[0.64rem] text-muted">
                          p = {test.p_value.toFixed(4)}
                        </div>
                      </div>
                      {/* Verdict is text + colour, never colour alone. */}
                      <span
                        className={`flex-shrink-0 rounded-full border px-2 py-0.5 text-[0.6rem] font-bold ${
                          test.reject
                            ? 'border-down/50 bg-down/10 text-down'
                            : 'border-up/50 bg-up/10 text-up'
                        }`}
                      >
                        {test.reject ? t('backtest.rejected') : t('backtest.consistent')}
                      </span>
                    </div>
                  ))}
                </div>

                <p className="text-[0.64rem] italic leading-relaxed text-muted">
                  {t('backtest.note')}
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
