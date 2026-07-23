import { X } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import { SAMPLE_REPLAY } from './sampleReplay'

// Viewer for a simulated-user journey replay produced by the offline evaluation
// harness (`python -m stock_risk.simulation`). It is deliberately backend-free:
// it renders a bundled sample or a replay JSON the user picks from disk, so it
// adds no endpoint and no coupling to the served API.
//
// The permanent banner is not decoration. A journey replay reads like a real
// user session, and it must never be mistaken for one — every replay here is
// generated from developer-encoded behavioural assumptions.
//
// Accessibility: unlike the older panels, this dialog sets role/aria-modal,
// labels itself, closes on Escape, and moves focus to the close button on open —
// the gaps the evaluation itself flagged.

const STEP_LABEL = {
  user_simulation_started: 'Started',
  score_viewed: 'Viewed the risk score',
  component_viewed: 'Read a component breakdown',
  methodology_viewed: 'Read the plain-language meaning',
  uncertainty_viewed: 'Saw an uncertainty cue',
  data_warning_viewed: 'Saw a data-quality warning',
  disclaimer_viewed: 'Saw the disclaimer',
  misconception_detected: 'Formed a misconception',
  misconception_corrected: 'Corrected a misconception',
  stress_test_viewed: 'Reviewed a stress scenario',
  risk_contribution_viewed: 'Reviewed risk contribution',
  community_post_viewed: 'Read a community post',
  user_action_intent_recorded: 'Decided on an action',
  user_overreliance_detected: 'Over-relied on the score',
  professional_help_prompt_viewed: 'Considered professional advice',
  simulation_completed: 'Finished',
}

function isReplay(value) {
  return Boolean(value && Array.isArray(value.steps) && value.summary)
}

export default function ReplayViewer() {
  const { t } = useLanguage()
  const { replayPanelOpen, closeReplayPanel } = useAuth()
  const [replay, setReplay] = useState(SAMPLE_REPLAY)
  const [error, setError] = useState('')
  const closeRef = useRef(null)

  useEffect(() => {
    if (!replayPanelOpen) return undefined
    closeRef.current?.focus()
    const onKey = (e) => {
      if (e.key === 'Escape') closeReplayPanel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [replayPanelOpen, closeReplayPanel])

  if (!replayPanelOpen) return null

  const onFile = (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result))
        if (!isReplay(parsed)) throw new Error('not a replay')
        setReplay(parsed)
        setError('')
      } catch {
        setError(t('replay.invalidFile'))
      }
    }
    reader.readAsText(file)
  }

  const summary = replay.summary || {}
  const meta = [
    ['replay.archetype', replay.archetype],
    ['replay.language', replay.language],
    ['replay.variant', replay.experiment_variant],
    ['replay.accessibility', replay.accessibility_mode],
    ['replay.seed', String(replay.simulation_seed)],
  ]

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      style={{ animationDuration: '0.15s' }}
      onClick={closeReplayPanel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="replay-title"
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[88vh] w-full max-w-3xl animate-fade-in flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-black/50"
        style={{ animationDuration: '0.2s' }}
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 id="replay-title" className="text-lg font-bold text-slate-100">
            {t('replay.title')}
          </h2>
          <button
            ref={closeRef}
            onClick={closeReplayPanel}
            aria-label={t('replay.close')}
            className="rounded-md px-1.5 py-0.5 text-base leading-none text-muted transition hover:bg-down/10 hover:text-down"
          >
            <X aria-hidden="true" size={14} color="currentColor" />
          </button>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6 sm:px-8">
          {/* Permanent honesty banner — never dismissible. */}
          <p className="rounded-xl border border-gold/25 bg-gold/[0.06] px-4 py-3 text-[0.78rem] italic leading-relaxed text-slate-300">
            {t('replay.banner')}
          </p>

          <p className="text-[0.82rem] leading-relaxed text-muted">{t('replay.intro')}</p>

          <div className="flex flex-wrap items-center gap-3">
            <label className="cursor-pointer rounded-lg border border-border px-3 py-1.5 text-[0.78rem] text-slate-200 transition hover:border-accent hover:text-accent">
              {t('replay.loadFile')}
              <input type="file" accept="application/json" className="sr-only" onChange={onFile} />
            </label>
            <button
              onClick={() => {
                setReplay(SAMPLE_REPLAY)
                setError('')
              }}
              className="rounded-lg border border-border px-3 py-1.5 text-[0.78rem] text-slate-200 transition hover:border-accent hover:text-accent"
            >
              {t('replay.loadSample')}
            </button>
          </div>
          {error ? (
            <p role="alert" className="text-[0.78rem] text-down">
              {error}
            </p>
          ) : null}

          {/* Who this simulated user was */}
          <dl className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
            {meta.map(([key, value]) => (
              <div key={key} className="panel-tile px-3 py-2">
                <dt className="text-[0.66rem] uppercase tracking-wide text-muted">{t(key)}</dt>
                <dd className="mt-0.5 text-[0.8rem] font-semibold text-slate-100">{value}</dd>
              </div>
            ))}
          </dl>

          {/* The journey */}
          <section>
            <h3 className="heading-flourish mb-3 text-lg">{t('replay.steps')}</h3>
            <ol className="space-y-2">
              {replay.steps.map((step) => (
                <li key={step.step} className="panel-tile flex items-start gap-3 p-3">
                  <span className="icon-badge flex h-6 w-6 flex-shrink-0 items-center justify-center text-[0.7rem] font-bold">
                    {step.step + 1}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[0.82rem] font-semibold text-slate-100">
                      {STEP_LABEL[step.event] || step.event}
                      {step.score != null ? ` — ${step.score}/100` : ''}
                    </span>
                    {step.intended_financial_action ? (
                      <span className="mt-0.5 block text-[0.76rem] text-accent2">
                        {t('replay.intendedAction')}: {step.intended_financial_action}
                      </span>
                    ) : null}
                    {step.detail?.misconception ? (
                      <span className="mt-0.5 block text-[0.76rem] text-down">
                        {step.detail.misconception}
                      </span>
                    ) : null}
                    {step.detail?.product_surfaced_confidence === false &&
                    ['low', 'suppressed'].includes(step.detail?.intrinsic_confidence) ? (
                      <span className="mt-0.5 block text-[0.76rem] text-gold">
                        {t('replay.confidenceHidden')}
                      </span>
                    ) : null}
                    {step.detail?.reason ? (
                      <span className="mt-1 block break-words text-[0.72rem] italic leading-relaxed text-muted">
                        {step.detail.reason}
                      </span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ol>
          </section>

          {/* Outcome */}
          <section>
            <h3 className="heading-flourish mb-3 text-lg">{t('replay.outcome')}</h3>
            <dl className="space-y-1.5 text-[0.8rem]">
              <div className="flex gap-2">
                <dt className="text-muted">{t('replay.intendedAction')}:</dt>
                <dd className="font-semibold text-slate-100">
                  {summary.final_intended_action || t('replay.none')}
                </dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-muted">{t('replay.corrected')}:</dt>
                <dd className="text-slate-200">
                  {summary.corrected?.length ? summary.corrected.join(', ') : t('replay.none')}
                </dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-muted">{t('replay.remaining')}:</dt>
                <dd className="text-slate-200">
                  {summary.remaining?.length ? summary.remaining.join(', ') : t('replay.none')}
                </dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-muted">{t('replay.overreliance')}:</dt>
                <dd className="text-slate-200">
                  {summary.overreliance_detected ? t('replay.yes') : t('replay.no')}
                </dd>
              </div>
            </dl>
          </section>
        </div>
      </div>
    </div>
  )
}
