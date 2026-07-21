import { useState } from 'react'

// Small "(?)" affordance that reveals a plain-language explanation on hover/tap.
// Used throughout the UI to define jargon (RSI, beta, VaR, ...) for users new to finance.
export default function InfoTooltip({ text, align = 'center' }) {
  const [open, setOpen] = useState(false)
  const alignClass =
    align === 'left' ? 'left-0 translate-x-0' : align === 'right' ? 'right-0 left-auto translate-x-0' : 'left-1/2 -translate-x-1/2'

  return (
    <span className="relative inline-flex normal-case">
      <button
        type="button"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(e) => {
          e.stopPropagation()
          setOpen((o) => !o)
        }}
        className="flex h-3.5 w-3.5 items-center justify-center rounded-full border border-muted/40 text-[9px] font-bold leading-none text-muted transition-all duration-150 hover:scale-110 hover:border-accent hover:text-accent active:scale-95"
        aria-label="More info"
      >
        ?
      </button>
      <span
        role="tooltip"
        // whitespace-normal + text-left are load-bearing, not cosmetic: this
        // span inherits white-space/text-align from wherever the (?) sits,
        // and inside a whitespace-nowrap label row the explanation would
        // otherwise render as one long unwrapped line shooting out of the
        // panel (seen live with the VaR glossary tooltip).
        className={`pointer-events-none absolute bottom-full z-30 mb-2 w-56 whitespace-normal rounded-lg border border-border bg-surface2 px-3 py-2 text-left text-[11px] font-normal normal-case leading-relaxed text-slate-200 shadow-xl shadow-black/40 transition-all duration-150 ease-out ${alignClass} ${
          open ? 'translate-y-0 scale-100 opacity-100' : 'translate-y-1 scale-95 opacity-0'
        }`}
      >
        {text}
      </span>
    </span>
  )
}
