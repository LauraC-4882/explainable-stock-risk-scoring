export default function DirectionSignal({ upProb, downProb }) {
  const verdict = upProb > 0.55 ? 'bull' : upProb < 0.45 ? 'bear' : 'flat'
  const verdictText = {
    bull: '↑ Likely to INCREASE',
    bear: '↓ Likely to DECREASE',
    flat: '→ Neutral — unclear direction',
  }[verdict]
  const verdictClass = {
    bull: 'bg-up/10 text-up',
    bear: 'bg-down/10 text-down',
    flat: 'bg-muted/10 text-muted',
  }[verdict]

  return (
    <div className="border-b border-border px-5 py-3.5">
      <div className="mb-2.5 text-[0.68rem] font-semibold uppercase tracking-wide text-muted">
        Today&apos;s Direction Signal
      </div>
      <Bar label="↑ Upside" pct={upProb} colorClass="text-up" barClass="from-[#1a7f37] to-up" />
      <Bar label="↓ Downside" pct={downProb} colorClass="text-down" barClass="from-[#b91c1c] to-down" />
      <div
        className={`mt-2.5 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${verdictClass}`}
      >
        {verdictText}
      </div>
    </div>
  )
}

function Bar({ label, pct, colorClass, barClass }) {
  return (
    <div className="mb-2 flex items-center gap-2 last:mb-0">
      <span className={`w-20 flex-shrink-0 text-sm font-bold ${colorClass}`}>{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface2">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${barClass} transition-all duration-700 ease-out`}
          style={{ width: `${(pct * 100).toFixed(1)}%` }}
        />
      </div>
      <span className={`w-9 flex-shrink-0 text-right text-sm font-bold ${colorClass}`}>
        {(pct * 100).toFixed(0)}%
      </span>
    </div>
  )
}
