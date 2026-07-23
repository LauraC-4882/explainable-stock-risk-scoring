export { useReducedMotion } from 'framer-motion'

// Shared Framer Motion variants — one vocabulary for the whole app, so pages
// and panels move the same way everywhere.
//
// Durations are deliberately short (0.28s entrance, 0.08s stagger): the spec's
// own constraint is "no gratuitous animations that slow performance", and
// anything longer makes a data tool feel slower, not richer. Everything
// animates transform/opacity only — the two GPU-composited properties — never
// layout.
//
// Reduced motion: pass `initial={reduced ? false : 'hidden'}` (from
// useReducedMotion) so elements mount directly in their final state — the same
// contract the CSS backdrop already honours via prefers-reduced-motion.

export const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.28, ease: 'easeOut' } },
}

export const stagger = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08 } },
}

// For AnimatePresence swaps (cards <-> compare view): the leaving view fades
// straight out (no slide) so the entering one doesn't appear to chase it.
export const viewSwap = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.28, ease: 'easeOut' } },
  exit: { opacity: 0, transition: { duration: 0.15 } },
}
