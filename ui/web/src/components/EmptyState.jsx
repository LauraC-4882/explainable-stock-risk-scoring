const POPULAR = ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'NVDA', 'AMZN', 'META', 'JPM']

export default function EmptyState({ onAdd }) {
  return (
    <div className="flex flex-col items-center gap-3 px-8 py-20 text-center sm:py-24">
      <div className="text-5xl">📊</div>
      <h2 className="text-lg font-bold">Search any stock to see its risk</h2>
      <p className="max-w-sm text-sm leading-relaxed text-muted">
        Type a company name or ticker above. Scores update live using real market data.
      </p>
      <div className="mt-2 flex flex-wrap justify-center gap-2">
        {POPULAR.map((t) => (
          <button
            key={t}
            onClick={() => onAdd(t)}
            className="rounded-full border border-border bg-surface2 px-4 py-1.5 text-sm font-bold text-accent transition hover:-translate-y-0.5 hover:border-accent hover:bg-accent/10"
          >
            {t}
          </button>
        ))}
      </div>
    </div>
  )
}
