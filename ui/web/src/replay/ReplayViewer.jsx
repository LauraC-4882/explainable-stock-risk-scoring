import { X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../i18n/LanguageContext'
import { SAMPLE_REPLAYS } from './sampleReplays'

// Viewer for simulated-user journey replays produced by the offline evaluation
// harness (`python -m stock_risk.simulation`). Deliberately backend-free: it
// renders the bundled samples or a replay JSON picked from disk, so it adds no
// endpoint and no coupling to the served API.
//
// The bundle ships five deterministic journeys, one per core surface of the
// site (score card, portfolio attribution, community misinformation, market
// crash, comprehension battery) — regenerated only via
// scripts/generate_sample_replays.py so they can never drift from real
// harness output.
//
// The permanent banner is not decoration. A journey replay reads like a real
// user session, and it must never be mistaken for one — every replay here is
// generated from developer-encoded behavioural assumptions.
//
// Step labels resolve through i18n (replay.stepLabels.*) with the raw event
// name as fallback — the first version hardcoded English labels, which leaked
// untranslated text into the Chinese modes, the exact defect class the
// harness's own language-parity scenario measures.

function isReplay(value) {
  return Boolean(value && Array.isArray(value.steps) && value.summary)
}

export default function ReplayViewer() {
  const { t } = useLanguage()
  const { replayPanelOpen, closeReplayPanel } = useAuth()
  const [sampleId, setSampleId] = useState(SAMPLE_REPLAYS[0].id)
  const [replay, setReplay] = useState(SAMPLE_REPLAYS[0].replay)
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

  const stepLabel = (event) => {
    const key = `replay.stepLabels.${event}`
    const resolved = t(key)
    return resolved === key ? event : resolved
  }

  function pickSample(sample) {
    setSampleId(sample.id)
    setReplay(sample.replay)
    setError('')
  }

  const onFile = (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result))
        if (!isReplay(parsed)) throw new Error('not a replay')
        setReplay(parsed)
        setSampleId(null)
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

          {/* One journey per core surface of the site. */}
          <div>
            <div className="mb-1.5 text-[0.66rem] font-semibold uppercase tracking-wide text-muted">
              {t('replay.samplesTitle')}
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {SAMPLE_REPLAYS.map((sample) => (
                <button
                  key={sample.id}
                  onClick={() => pickSample(sample)}
                  aria-pressed={sampleId === sample.id}
                  className={`rounded-full border px-3 py-1 text-[0.7rem] font-semibold transition ${
                    sampleId === sample.id
                      ? 'border-accent/50 bg-accent/10 text-accent'
                      : 'border-border text-muted hover:text-slate-200'
                  }`}
                >
                  {t(`replay.samples.${sample.id}`)}
                </button>
              ))}
              <label className="cursor-pointer rounded-full border border-border px-3 py-1 text-[0.7rem] font-semibold text-muted transition hover:text-slate-200">
                {t('replay.loadFile')}
                <input
                  type="file"
                  accept="application/json"
                  className="sr-only"
                  onChange={onFile}
                />
              </label>
            </div>
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
                      {stepLabel(step.event)}
                      {step.score != null ? ` — ${step.score}/100` : ''}
                    </span>
                    {step.event === 'comprehension_answered' && step.detail?.qid ? (
                      <span
                        className={`mt-0.5 block text-[0.76rem] ${
                          step.detail.correct ? 'text-up' : 'text-down'
                        }`}
                      >
                        {step.detail.qid} —{' '}
                        {step.detail.correct ? t('replay.correct') : t('replay.incorrect')}
                      </span>
                    ) : null}
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
