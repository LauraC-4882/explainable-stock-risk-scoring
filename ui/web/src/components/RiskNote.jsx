import { useLanguage } from '../i18n/LanguageContext'

// The per-card disclaimer under the community rail. The backend ships
// `risk_note` as a pre-formatted English sentence (scorer.py's _risk_note),
// but everything that sentence interpolates is already in the response as
// structured data — market_regime.benchmark, and the ml_drawdown share in
// risk_score_composition — so the sentence is rebuilt here from locale
// templates, same treatment as StressTestPanel's narrative. The backend
// string stays in the API (other consumers read it) and is the fallback
// whenever the structured fields are missing (e.g. an older cached response
// without market_regime).
export default function RiskNote({ score }) {
  const { t } = useLanguage()
  if (!score?.risk_note) return null

  const benchmark = score.market_regime?.benchmark
  const mlShare =
    (score.risk_score_composition || []).find((c) => c.producer === 'ml_drawdown')?.weight ?? 0

  const note = !benchmark
    ? score.risk_note
    : mlShare > 0
      ? t('riskNote.fused', {
          pct: Math.round((1 - mlShare) * 100),
          ml: Math.round(mlShare * 100),
          benchmark,
        })
      : t('riskNote.percentile', { benchmark })

  return (
    <p
      className="animate-rise-in px-1 text-[0.7rem] leading-relaxed text-muted"
      style={{ animationDelay: '360ms', animationFillMode: 'backwards' }}
    >
      {note}
    </p>
  )
}
