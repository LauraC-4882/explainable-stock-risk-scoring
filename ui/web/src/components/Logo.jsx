// Riscore brand assets, ported from the approved logo mockup
// (riscore_logo_v3): shield-in-ring icon with a candlestick mini-chart and
// gold trend line, the "Ri·score" two-gradient wordmark, and the circular
// slogan ring. Brand copy inside the SVGs is intentionally not translated.
// Animation classes live in index.css (logo-ring-spin / logo-chart-line /
// logo-dot-pulse / slogan-*) and are disabled under prefers-reduced-motion.

export function RiscoreIcon({ size = 110, idPrefix = 'ri' }) {
  const grad = `${idPrefix}-iconGrad`
  const gold = `${idPrefix}-goldGrad`
  return (
    <svg width={size} height={size} viewBox="0 0 110 110" aria-label="Riscore logo">
      <defs>
        <linearGradient id={grad} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#7dd3fc" />
          <stop offset="100%" stopColor="#2563eb" />
        </linearGradient>
        <linearGradient id={gold} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#f59e0b" />
          <stop offset="100%" stopColor="#fbbf24" />
        </linearGradient>
      </defs>

      <circle cx="55" cy="55" r="50" fill="none" stroke="rgba(125,211,252,0.16)" strokeWidth="1" />
      <circle
        cx="55" cy="55" r="44" fill="none" stroke="rgba(79,216,235,0.22)"
        strokeWidth="0.8" strokeDasharray="5 7" className="logo-ring-spin"
      />

      <path
        d="M55,18 L82,30 L82,58 Q82,76 55,88 Q28,76 28,58 L28,30 Z"
        fill="rgba(30,90,200,0.2)" stroke={`url(#${grad})`} strokeWidth="1.5"
      />

      <rect x="38" y="64" width="5" height="10" rx="1" fill="#f43f5e" opacity="0.9" />
      <line x1="40.5" y1="61" x2="40.5" y2="75" stroke="#f43f5e" strokeWidth="1" opacity="0.7" />
      <rect x="47" y="58" width="5" height="14" rx="1" fill="#86efac" opacity="0.9" />
      <line x1="49.5" y1="54" x2="49.5" y2="73" stroke="#86efac" strokeWidth="1" opacity="0.7" />
      <rect x="56" y="52" width="5" height="16" rx="1" fill="#86efac" opacity="0.9" />
      <line x1="58.5" y1="48" x2="58.5" y2="69" stroke="#86efac" strokeWidth="1" opacity="0.7" />
      <rect x="65" y="46" width="5" height="18" rx="1" fill="#86efac" opacity="0.9" />
      <line x1="67.5" y1="42" x2="67.5" y2="65" stroke="#86efac" strokeWidth="1" opacity="0.7" />

      <path
        d="M39,70 L49,62 L58,55 L67,47" fill="none" stroke={`url(#${gold})`}
        strokeWidth="1.8" strokeLinecap="round" className="logo-chart-line"
      />
      <circle cx="67" cy="47" r="4" fill="#f59e0b" className="logo-dot-pulse" />
      <circle
        cx="67" cy="47" r="7" fill="none" stroke="#f59e0b"
        strokeWidth="0.8" strokeOpacity="0.4" className="logo-dot-pulse"
      />
    </svg>
  )
}

export function RiscoreWordmark({ className = 'text-2xl' }) {
  return (
    <span className={`inline-flex items-center gap-[0.18em] font-brand font-bold leading-none tracking-wide ${className}`}>
      <span className="text-gradient-purple">Ri</span>
      <span
        aria-hidden="true"
        className="mb-[0.08em] inline-block h-[0.18em] w-[0.18em] rounded-full bg-[#38bdf8]"
      />
      <span className="text-gradient-rose">score</span>
    </span>
  )
}

export function SloganRing({ size = 160, idPrefix = 'sr' }) {
  const grad = `${idPrefix}-sloganGrad`
  return (
    <svg width={size} height={size} viewBox="0 0 160 160" aria-label="Know your risk — invest with clarity">
      <defs>
        <linearGradient id={grad} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#7dd3fc" />
          <stop offset="50%" stopColor="#38bdf8" />
          <stop offset="100%" stopColor="#fbbf24" />
        </linearGradient>
      </defs>

      <circle cx="80" cy="80" r="72" fill="none" stroke="rgba(125,211,252,0.16)" strokeWidth="1" />
      <circle
        cx="80" cy="80" r="64" fill="none" stroke="rgba(79,216,235,0.22)" strokeWidth="0.5"
        strokeDasharray="4 6" className="slogan-ring-spin-reverse"
      />
      <circle
        cx="80" cy="80" r="72" fill="none" stroke={`url(#${grad})`} strokeWidth="2"
        strokeLinecap="round" className="slogan-arc-draw" transform="rotate(-90 80 80)"
      />

      <rect x="77" y="4" width="6" height="6" rx="1" fill="#f59e0b" transform="rotate(45 80 7)" opacity="0.8" />
      <rect x="77" y="147" width="6" height="6" rx="1" fill="#f59e0b" transform="rotate(45 80 150)" opacity="0.8" />
      <rect x="4" y="77" width="6" height="6" rx="1" fill="#7dd3fc" transform="rotate(45 7 80)" opacity="0.6" />
      <rect x="148" y="77" width="6" height="6" rx="1" fill="#38bdf8" transform="rotate(45 151 80)" opacity="0.6" />

      <text x="80" y="72" textAnchor="middle" fontSize="13" fontWeight="700" fill="#bfe6ff" letterSpacing="0.5">
        Know your
      </text>
      <text x="80" y="88" textAnchor="middle" fontSize="13" fontWeight="700" fill="#bfe6ff" letterSpacing="0.5">
        risk.
      </text>
      <text x="80" y="106" textAnchor="middle" fontSize="10" fill="#8ba3c9" letterSpacing="1">
        INVEST WITH CLARITY
      </text>
    </svg>
  )
}
