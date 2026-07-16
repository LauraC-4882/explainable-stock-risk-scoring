export default function Header() {
  return (
    <header className="relative overflow-hidden border-b border-border bg-gradient-to-br from-surface via-[#0d1117] to-[#111827] px-6 py-5 sm:px-8">
      <div className="pointer-events-none absolute -top-24 left-1/3 h-64 w-64 rounded-full bg-accent/10 blur-3xl" />
      <div className="relative flex items-center gap-4">
        <div className="text-3xl drop-shadow-[0_0_12px_rgba(88,166,255,0.35)]">📉</div>
        <div>
          <h1 className="bg-gradient-to-r from-accent to-[#bc8cff] bg-clip-text text-xl font-extrabold tracking-tight text-transparent sm:text-2xl">
            Stock Risk Analyzer
          </h1>
          <p className="mt-0.5 text-xs text-muted sm:text-sm">
            Real-time downside risk · direction signals · live data via yfinance
          </p>
        </div>
      </div>
    </header>
  )
}
