const OPTIONS = [
  { p: '5d', label: '5D' },
  { p: '1mo', label: '1M' },
  { p: '3mo', label: '3M' },
  { p: '6mo', label: '6M' },
  { p: '1y', label: '1Y' },
  { p: '2y', label: '2Y' },
]

export default function TimeframeSelector({ period, onChange }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {OPTIONS.map((o) => (
        <button
          key={o.p}
          onClick={() => onChange(o.p)}
          className={`rounded-full border px-4 py-1 text-xs font-semibold transition ${
            period === o.p
              ? 'border-accent bg-accent text-white shadow-lg shadow-accent/20'
              : 'border-border text-muted hover:border-accent hover:text-accent'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
