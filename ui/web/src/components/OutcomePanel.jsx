import { ChartBar } from '@phosphor-icons/react'
import { useState } from 'react'
import { apiOutcomes } from '../api'
import { useLanguage } from '../i18n/LanguageContext'
import { riskColor } from '../utils'

// Collapsible "historical outcome distribution" panel: when this stock
// previously sat in each risk band, what happened over the next 20 trading
// days — up/down frequency, the interquartile range of forward returns, and
// 10%+ drawdown/rally frequencies. Descriptive statistics about the past
// (same epistemic category as the stress test), deliberately NOT a forecast:
// the point it makes visually is that a higher band widens outcomes in BOTH
// directions rather than predicting a fall. Data is fetched lazily on first
// expand — it needs a full 2y timeseries computation server-side.
export default function OutcomePanel({ ticker }) {
  const { t } = useLanguage()
  const [open, setOpen] = useState(false)
  const [data, setData] = useState(null)
  const [state, setState] = useState('idle') // 'idle' | 'loading' | 'ready' | 'error'

  function toggle() {
    const next = !open
    setOpen(next)
    if (next && state === 'idle') {
      setState('loading')
      apiOutcomes(ticker)
        .then((d) => {
          setData(d)
          setState('ready')
        })
        .catch(() => setState('error'))
    }
  }

  return (
    <div className="border-b border-border">
      <button
        onClick={toggle}
        className="group flex w-full items-center justify-between px-5 py-3 text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted transition-colors duration-150 hover:text-accent"
        aria-expanded={open}
      >
        <span className="inline-flex items-center gap-2">
          <span className="icon-badge h-7 w-7 transition-colors duration-150 group-hover:bg-accent/20">
            <ChartBar aria-hidden="true" size={16} />
          </span>
          {t('outcomes.toggle')}
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
            <p className="text-sm leading-relaxed text-slate-300">{t('outcomes.intro')}</p>

            {state === 'loading' && (
              <div className="skeleton-shimmer animate-shimmer h-32 w-full rounded-lg" />
            )}
            {state === 'error' && <p className="text-xs text-muted">{t('outcomes.error')}</p>}

            {state === 'ready' && data && (
              <>
                <div className="space-y-2">
                  {data.bands.map((band) => {
                    const isCurrent = band.label === data.current_label
                    const empty = band.days === 0
                    const dim = empty || !band.sufficient
                    return (
                      <div
                        key={band.label}
                        className={`rounded-lg border p-3 transition-colors duration-150 ${
                          isCurrent
                            ? 'border-accent/60 bg-accent/[0.07]'
                            : 'border-border bg-surface2/40'
                        } ${dim ? 'opacity-60' : ''}`}
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className="rounded-full px-2 py-0.5 text-[0.65rem] font-bold"
                            style={{
                              color: riskColor(band.label),
                              background: `${riskColor(band.label)}22`,
                            }}
                          >
                            {t(`riskLabel.${band.label}`)}
                          </span>
                          <span className="text-[0.65rem] text-muted">
                            {band.days} {t('outcomes.samples')}
                          </span>
                          {isCurrent && (
                            <span className="rounded-full bg-accent/20 px-2 py-0.5 text-[0.62rem] font-semibold text-accent">
                              {t('outcomes.currentBand')}
                            </span>
                          )}
                          {!empty && !band.sufficient && (
                            <span className="text-[0.62rem] italic text-muted">
                              {t('outcomes.insufficient')}
                            </span>
                          )}
                        </div>

                        {empty ? (
                          <p className="mt-2 text-[0.7rem] text-muted">{t('outcomes.noData')}</p>
                        ) : (
                          <>
                            {/* Up/down frequency split bar */}
                            <div className="mt-2.5 flex items-center gap-2 font-mono text-[0.7rem]">
                              <span className="w-16 flex-shrink-0 text-up">↑ {band.up_pct}%</span>
                              <div className="flex h-1.5 flex-1 overflow-hidden rounded-full bg-surface2">
                                <div className="bg-up/70" style={{ width: `${band.up_pct}%` }} />
                                <div
                                  className="bg-down/70"
                                  style={{ width: `${band.down_pct}%` }}
                                />
                              </div>
                              <span className="w-16 flex-shrink-0 text-right text-down">
                                ↓ {band.down_pct}%
                              </span>
                            </div>

                            <div className="mt-2 grid grid-cols-3 gap-2 text-[0.68rem]">
                              <div>
                                <div className="text-muted">{t('outcomes.range')}</div>
                                <div className="font-mono text-slate-200">
                                  {band.p25}% ~ {band.p75}%
                                </div>
                              </div>
                              <div>
                                <div className="text-muted">{t('outcomes.drawdown10')}</div>
                                <div className="font-mono text-down">{band.drawdown10_pct}%</div>
                              </div>
                              <div>
                                <div className="text-muted">{t('outcomes.rally10')}</div>
                                <div className="font-mono text-up">{band.rally10_pct}%</div>
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    )
                  })}
                </div>

                <p className="text-[0.68rem] leading-relaxed text-muted">
                  {t('outcomes.takeaway')}
                </p>
                <p className="text-[0.65rem] italic leading-relaxed text-muted">
                  {t('outcomes.disclaimer')}
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
