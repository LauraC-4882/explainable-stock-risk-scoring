import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { createContext, useCallback, useContext, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

// App-wide toast notifications: short confirmations for actions whose result
// isn't otherwise visible at the point of click (added to watchlist, removed,
// copied, …). Deliberately minimal — no queue cap games, no action buttons,
// auto-dismiss only — because anything that demands interaction belongs in a
// dialog, not a toast.
//
// Accessibility: the container is aria-live="polite", so screen readers
// announce each toast without it stealing focus; timing is generous (4s) and
// the reduced-motion path swaps the slide for a plain fade.

const ToastContext = createContext(null)

let nextId = 1

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timers = useRef(new Map())

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
  }, [])

  const toast = useCallback(
    (message, { tone = 'info' } = {}) => {
      const id = nextId++
      setToasts((prev) => [...prev.slice(-3), { id, message, tone }]) // keep at most 4
      timers.current.set(
        id,
        setTimeout(() => dismiss(id), 4000)
      )
      return id
    },
    [dismiss]
  )

  return (
    <ToastContext.Provider value={{ toast, dismiss }}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  )
}

const TONE_STYLES = {
  info: 'border-accent/40',
  success: 'border-up/50',
  error: 'border-down/50',
}

function ToastContainer({ toasts, onDismiss }) {
  const reduced = useReducedMotion()
  // Portalled to <body>: toasts overlay the whole app, and mounting the
  // container inside the provider's subtree also broke every
  // "renders nothing" toBeEmptyDOMElement() test the moment the provider
  // wrapped it. The overlay belongs to the document, not the component tree.
  return createPortal(
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-20 z-[60] flex flex-col items-center gap-2 px-4 md:bottom-6"
    >
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            initial={reduced ? { opacity: 0 } : { opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, transition: { duration: 0.15 } }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className={`pointer-events-auto max-w-sm rounded-xl border bg-[#091525]/95 px-4 py-2.5 text-[0.8rem] text-slate-100 shadow-lg shadow-black/40 backdrop-blur ${
              TONE_STYLES[t.tone] || TONE_STYLES.info
            }`}
            onClick={() => onDismiss(t.id)}
            role="status"
          >
            {t.message}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>,
    document.body
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within a ToastProvider')
  return ctx
}
