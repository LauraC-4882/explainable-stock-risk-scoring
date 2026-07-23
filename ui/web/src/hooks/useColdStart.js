import { useEffect, useState } from 'react'
import { apiHealth } from '../api'

// Render's free tier spins the instance down when idle, and the next request
// pays the full boot cost — measured at ~101s against this deployment's
// /health, versus ~1s warm. Without this the app just sits blank for a minute
// and a half, which reads as "broken site", not "sleeping instance".
//
// The probe hits /health (excluded from rate limiting and from PageView
// tracking, and it touches neither yfinance nor the model) so waking the dyno
// costs nothing and pollutes no analytics.
//
// GRACE_MS exists so a warm instance never flashes the banner: warm /health
// answers in well under a second, so nothing renders in the common case.
const GRACE_MS = 3000
const TICK_MS = 1000

export default function useColdStart() {
  const [waking, setWaking] = useState(false)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    let cancelled = false
    const startedAt = Date.now()

    const graceTimer = setTimeout(() => {
      if (!cancelled) setWaking(true)
    }, GRACE_MS)

    const tick = setInterval(() => {
      if (!cancelled) setElapsed(Math.round((Date.now() - startedAt) / 1000))
    }, TICK_MS)

    const done = () => {
      if (cancelled) return
      clearTimeout(graceTimer)
      setWaking(false)
    }

    // No timeout/abort on purpose: a cold boot legitimately takes ~100s, and
    // aborting early would hide exactly the case this exists to explain. A
    // failed probe also resolves the banner — the app's own requests will
    // surface a real error, and a stuck "waking…" banner would be its own lie.
    apiHealth().then(done).catch(done)

    return () => {
      cancelled = true
      clearTimeout(graceTimer)
      clearInterval(tick)
    }
  }, [])

  return { waking, elapsed }
}
