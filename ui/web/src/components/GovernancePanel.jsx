import { GitCommitHorizontal, ScrollText, ShieldCheck, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { apiGovernance } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'

// [R4] Model governance, read-only. The registry, the lifecycle it enforces,
// and the artefact that is actually answering requests — surfaced from
// /api/governance/model, which reads the real files rather than restating them.
//
// The design constraint that shapes this whole component: it must render the
// UNPOPULATED state as informatively as the populated one. The committed
// champion predates the registry, so `registry_present` is false in a fresh
// clone, and the honest rendering of that is a card that names what is missing
// and the command that fills it — not a blank space, and emphatically not a
// green tick standing in for a record nobody wrote. Same rule as BacktestPanel:
// a governance page that always looks healthy is marketing.
//
// Everything below is therefore either a value from the API or a locale string
// describing a value from the API. No metric is hardcoded here.

// Order matters — this is the route a model normally travels, and the panel
// renders it as a path so the two missing edges are visible as gaps.
const LIFECYCLE_ORDER = [
  'development',
  'validated',
  'approved',
  'shadow',
  'active',
  'degraded',
  'retired',
]

const STATUS_TONE = {
  active: 'border-up/50 bg-up/10 text-up',
  degraded: 'border-down/50 bg-down/10 text-down',
  retired: 'border-border bg-surface2/60 text-muted',
}

export function statusTone(status) {
  return STATUS_TONE[status] || 'border-accent/40 bg-accent/10 text-accent'
}

// Importance bars are scaled against the TOP feature, not against 1.0. XGBoost
// gain importances sum to 1 across ~19 features, so the leader sits near 0.13
// and an absolute scale renders every bar as a barely-visible sliver — the
// ranking, which is the point, becomes unreadable. The printed number stays
// absolute so the scaling can't mislead about magnitude.
export function barWidth(value, max) {
  if (!max || !Number.isFinite(value)) return 0
  return Math.max(2, Math.round((value / max) * 100))
}

// Label-left / value-right only from 640px up. At 375px the value column is
// ~150px, which is narrower than a single mono token like
// `learning_rate=0.05` — so the row broke it mid-number ("learning_rate=0.0 /
// 5"). Stacking gives the value the full width and the tokens wrap at their
// separators instead.
function Row({ label, children, mono = false }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-border/60 py-1.5 last:border-0 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
      <span className="flex-shrink-0 text-[0.72rem] text-muted">{label}</span>
      <span
        // break-words, not break-all: break-all splits mid-token even when
        // there is a space to wrap at, which rendered the hyperparameter row as
        // "colsample_byt / ree=0.8". This still breaks the one genuinely
        // unbreakable token (the SHA-256) because it has nowhere else to go.
        className={`min-w-0 break-words text-[0.76rem] text-slate-200 sm:text-right ${mono ? 'font-mono text-[0.68rem]' : ''}`}
      >
        {children}
      </span>
    </div>
  )
}

export default function GovernancePanel() {
  const { t, lang } = useLanguage()
  const { governancePanelOpen, closeGovernancePanel } = useAuth()
  const closeRef = useRef(null)
  const [data, setData] = useState(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (!governancePanelOpen) return undefined
    closeRef.current?.focus()
    const onKey = (e) => {
      if (e.key === 'Escape') closeGovernancePanel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [governancePanelOpen, closeGovernancePanel])

  useEffect(() => {
    if (!governancePanelOpen || loaded) return undefined
    let cancelled = false
    apiGovernance().then((d) => {
      if (cancelled) return
      setData(d)
      setLoaded(true)
    })
    return () => {
      cancelled = true
    }
  }, [governancePanelOpen, loaded])

  if (!governancePanelOpen) return null

  const artefact = data?.artefact
  const champion = data?.champion
  const features = artefact?.top_features || []
  const maxImportance = features.length ? features[0].importance : 0
  const committedAt = artefact?.provenance?.committed_at
  // Locale-aware and timezone-honest: the backend sends an ISO string with its
  // offset, so this renders the commit's own moment rather than re-anchoring it
  // to the viewer's midnight.
  const committedLabel = committedAt
    ? new Date(committedAt).toLocaleDateString(lang, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    : null

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      style={{ animationDuration: '0.15s' }}
      onClick={closeGovernancePanel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={t('governance.title')}
        className="flex max-h-[88vh] w-full max-w-3xl animate-fade-in flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-black/50"
        style={{ animationDuration: '0.2s' }}
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="flex items-center gap-2.5 text-lg font-bold text-slate-100">
            <span className="icon-badge h-8 w-8">
              <ShieldCheck aria-hidden="true" size={17} />
            </span>
            {t('governance.title')}
          </h2>
          <button
            ref={closeRef}
            onClick={closeGovernancePanel}
            aria-label={t('replay.close')}
            className="rounded-md px-1.5 py-0.5 text-base leading-none text-muted transition hover:bg-down/10 hover:text-down"
          >
            <X aria-hidden="true" size={14} color="currentColor" />
          </button>
        </div>

        <div className="flex-1 space-y-7 overflow-y-auto px-6 py-6 sm:px-8">
          <p className="text-[0.82rem] leading-relaxed text-slate-300">{t('governance.intro')}</p>

          {!loaded && <div className="skeleton-shimmer animate-shimmer h-40 w-full rounded-xl" />}

          {loaded && !data && (
            <p role="alert" className="text-sm text-down">
              {t('governance.unavailable')}
            </p>
          )}

          {data && (
            <>
              {/* ── Champion, or the honest absence of one ── */}
              <section>
                <h3 className="heading-flourish mb-3 text-lg">{t('governance.championTitle')}</h3>

                {champion ? (
                  <div className="panel-tile space-y-1 p-4">
                    <div className="mb-2 flex items-center gap-2">
                      <span className="font-mono text-sm font-bold text-slate-100">
                        {champion.name} v{champion.version}
                      </span>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[0.6rem] font-bold uppercase ${statusTone(
                          champion.status
                        )}`}
                      >
                        {t(`governance.status.${champion.status}`)}
                      </span>
                    </div>
                    {Object.entries(champion.metrics || {}).map(([key, value]) => (
                      <Row key={key} label={key} mono>
                        {typeof value === 'number' ? value.toFixed(4) : String(value)}
                      </Row>
                    ))}
                    <Row label={t('governance.thresholdVerdict')}>
                      <span className={champion.thresholds_pass ? 'text-up' : 'text-down'}>
                        {champion.thresholds_pass
                          ? t('governance.thresholdsPass')
                          : champion.threshold_failures.join('; ')}
                      </span>
                    </Row>
                    {champion.dataset_hash && (
                      <Row label={t('governance.datasetHash')} mono>
                        {champion.dataset_hash.slice(0, 16)}…
                      </Row>
                    )}
                  </div>
                ) : (
                  /* The unpopulated state, rendered as a finding rather than as
                     empty space. It says which file is absent and what produces
                     it, so the page is actionable instead of merely blank. */
                  <div className="panel-tile space-y-2 border-gold/30 bg-gold/[0.05] p-4">
                    <p className="text-[0.82rem] font-semibold text-gold">
                      {t('governance.noRecordTitle')}
                    </p>
                    <p className="text-[0.78rem] leading-relaxed text-slate-300">
                      {t('governance.noRecordBody', { path: data.registry_path })}
                    </p>
                    <code className="block rounded-md border border-border bg-surface2/60 px-2.5 py-1.5 font-mono text-[0.68rem] text-slate-200">
                      python scripts/train.py --version 1.0.0
                    </code>
                  </div>
                )}

                {data.artefact_matches_record === false && (
                  <p role="alert" className="mt-2 text-[0.76rem] font-semibold text-down">
                    {t('governance.artefactMismatch')}
                  </p>
                )}
              </section>

              {/* ── The binary actually answering requests ── */}
              <section>
                <h3 className="heading-flourish mb-3 text-lg">{t('governance.artefactTitle')}</h3>
                <div className="panel-tile p-4">
                  <Row label={t('governance.artefactPath')} mono>
                    {artefact.path}
                  </Row>
                  <Row label={t('governance.lastCommit')} mono>
                    {artefact.provenance.commit ? (
                      <span className="inline-flex items-center gap-1.5">
                        <GitCommitHorizontal aria-hidden="true" size={13} />
                        {artefact.provenance.commit.slice(0, 10)}
                        {committedLabel ? ` · ${committedLabel}` : ''}
                      </span>
                    ) : (
                      t('governance.notInCheckout')
                    )}
                  </Row>
                  <Row label={t('governance.sha')} mono>
                    {artefact.sha256 ? `${artefact.sha256.slice(0, 24)}…` : '—'}
                  </Row>
                  <Row label={t('governance.calibrated')}>
                    {artefact.calibrated ? t('governance.yesIsotonic') : t('governance.no')}
                  </Row>
                  <Row label={t('governance.served')}>
                    <span className={artefact.loaded ? 'text-up' : 'text-down'}>
                      {artefact.loaded ? t('governance.loadedYes') : t('governance.loadedNo')}
                    </span>
                  </Row>
                  <Row label={t('governance.schemaVersion')} mono>
                    {artefact.feature_schema_version}
                  </Row>
                  <Row label={t('governance.hyperparameters')} mono>
                    {Object.entries(artefact.hyperparameters || {})
                      .map(([k, v]) => `${k}=${v}`)
                      .join(' · ') || '—'}
                  </Row>
                </div>
                <p className="mt-2 text-[0.68rem] italic leading-relaxed text-muted">
                  {t('governance.provenanceNote')}
                </p>
              </section>

              {/* ── Feature importance ── */}
              {features.length > 0 && (
                <section>
                  <h3 className="heading-flourish mb-1 text-lg">{t('governance.featuresTitle')}</h3>
                  <p className="mb-3 text-[0.74rem] text-muted">
                    {t('governance.featuresSub', {
                      shown: features.length,
                      total: artefact.feature_count,
                    })}
                  </p>
                  <ol className="space-y-1.5">
                    {features.map((f, i) => (
                      <li key={f.feature} className="flex items-center gap-3">
                        <span className="w-5 flex-shrink-0 text-right font-mono text-[0.64rem] text-muted">
                          {i + 1}
                        </span>
                        {/* Wider on mobile at the bar's expense: the feature
                            NAME is the finding, and at 42% a 375px screen
                            truncated every one of them to "volatility__vol_6…",
                            which ranks nothing. title= keeps the full name
                            reachable when it still has to truncate. */}
                        <span
                          title={f.feature}
                          className="w-[60%] flex-shrink-0 truncate font-mono text-[0.68rem] text-slate-200 sm:w-[42%]"
                        >
                          {f.feature}
                        </span>
                        {/* Hidden below 640px. Once the name column takes the
                            width it needs, the bar is left with ~8px and
                            renders as a sliver that reads as a broken element
                            rather than as a magnitude. The rank and the printed
                            importance still carry the ranking. */}
                        <span className="hidden h-2 flex-1 overflow-hidden rounded-full bg-surface2 sm:block">
                          <span
                            className="block h-full rounded-full bg-accent/70"
                            style={{ width: `${barWidth(f.importance, maxImportance)}%` }}
                          />
                        </span>
                        <span className="w-12 flex-shrink-0 text-right font-mono text-[0.64rem] text-muted">
                          {f.importance.toFixed(3)}
                        </span>
                      </li>
                    ))}
                  </ol>
                  <p className="mt-2 text-[0.68rem] italic leading-relaxed text-muted">
                    {t('governance.featuresNote')}
                  </p>
                </section>
              )}

              {/* ── The enforced lifecycle ── */}
              <section>
                <h3 className="heading-flourish mb-1 text-lg">{t('governance.lifecycleTitle')}</h3>
                <p className="mb-3 text-[0.74rem] leading-relaxed text-muted">
                  {t('governance.lifecycleSub')}
                </p>
                <div className="space-y-1.5">
                  {LIFECYCLE_ORDER.filter((state) =>
                    data.lifecycle.states.some((s) => s.state === state)
                  ).map((state) => {
                    const node = data.lifecycle.states.find((s) => s.state === state)
                    return (
                      <div
                        key={state}
                        // Addressable per state: the localized badge text and
                        // the untranslated transition chips both render the
                        // same words, so a test asserting "development cannot
                        // reach active" needs to name the row, not the text.
                        data-testid={`lifecycle-${state}`}
                        className="flex flex-wrap items-center gap-2 rounded-lg border border-border px-3 py-2"
                      >
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[0.6rem] font-bold uppercase ${statusTone(state)}`}
                        >
                          {t(`governance.status.${state}`)}
                        </span>
                        <span className="text-[0.68rem] text-muted">→</span>
                        {node.to.length ? (
                          node.to.map((to) => (
                            <span
                              key={to}
                              className="rounded-md border border-border bg-surface2/50 px-1.5 py-0.5 font-mono text-[0.62rem] text-slate-300"
                            >
                              {to}
                            </span>
                          ))
                        ) : (
                          <span className="text-[0.66rem] italic text-muted">
                            {t('governance.terminal')}
                          </span>
                        )}
                      </div>
                    )
                  })}
                </div>
                <p className="mt-2 text-[0.7rem] leading-relaxed text-muted">
                  {t('governance.lifecycleNote')}
                </p>
              </section>

              {/* ── The gate ── */}
              <section>
                <h3 className="heading-flourish mb-3 text-lg">{t('governance.gateTitle')}</h3>
                <div className="panel-tile p-4">
                  <Row label={t('governance.minAuc')} mono>
                    ≥ {data.default_thresholds.min_roc_auc}
                  </Row>
                  <Row label={t('governance.maxBrier')} mono>
                    ≤ {data.default_thresholds.max_brier}
                  </Row>
                  <Row label={t('governance.maxPsi')} mono>
                    ≤ {data.default_thresholds.max_drift_psi}
                  </Row>
                  <Row label={t('governance.calibrationRule')}>
                    {data.default_thresholds.require_calibration_improves_brier
                      ? t('governance.enforced')
                      : t('governance.notEnforced')}
                  </Row>
                </div>
                <p className="mt-2 flex items-start gap-2 text-[0.7rem] leading-relaxed text-muted">
                  <ScrollText aria-hidden="true" size={14} className="mt-0.5 flex-shrink-0" />
                  {t('governance.gateNote')}
                </p>
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
