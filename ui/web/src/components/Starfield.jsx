import { useEffect, useRef } from 'react'

// Decorative "deep network" backdrop matched to the user's background
// artwork: a drifting plexus constellation (nodes + distance-faded links),
// slow-sliding tech streak lines along the edges, and a breathing equalizer
// bar cluster bottom-center. Canvas-based on one 2D context, fixed behind
// all content. Everything moves continuously — nodes drift so the
// constellation lines connect/disconnect live — except under
// prefers-reduced-motion, where a single static frame is painted.
export default function Starfield() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const cv = canvasRef.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    let nodes = []
    let streaks = []
    let bars = []
    let W = 0
    let H = 0
    let raf = 0
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    const LINK_DIST = 130

    const build = () => {
      W = cv.clientWidth
      H = cv.clientHeight
      cv.width = W * dpr
      cv.height = H * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

      // Plexus nodes: mostly pale blue-white, some cyan, a few violet —
      // the dot mix in the artwork. Slow constant drift + gentle twinkle.
      const n = Math.round((W * H) / 26000)
      nodes = []
      for (let i = 0; i < n; i++) {
        const kind = Math.random()
        nodes.push({
          x: Math.random() * W,
          y: Math.random() * H,
          vx: (Math.random() - 0.5) * 0.22,
          vy: (Math.random() - 0.5) * 0.22,
          r: Math.random() * 1.6 + 1.0,
          tw: Math.random() * Math.PI * 2,
          sp: Math.random() * 0.02 + 0.006,
          col: kind < 0.14 ? '79,216,235' : kind < 0.22 ? '139,123,232' : '214,230,252',
        })
      }

      // Thin tech streaks hugging the edges (the artwork's fine light rules),
      // sliding slowly along their axis and wrapping around.
      streaks = []
      const sn = Math.max(6, Math.round(W / 320))
      for (let i = 0; i < sn; i++) {
        const vertical = Math.random() < 0.5
        streaks.push({
          vertical,
          // cluster near the left/right (vertical) or top/bottom (horizontal) edges
          edge: Math.random() < 0.5,
          off: Math.random() * (vertical ? W * 0.16 : H * 0.14),
          pos: Math.random() * (vertical ? H : W),
          len: 60 + Math.random() * 180,
          v: 0.2 + Math.random() * 0.5,
          a: 0.1 + Math.random() * 0.16,
        })
      }

      // Equalizer bars bottom-center, breathing at individual rates.
      bars = []
      const bn = 36
      for (let i = 0; i < bn; i++) {
        bars.push({
          base: 18 + Math.random() * 60,
          ph: Math.random() * Math.PI * 2,
          sp: 0.008 + Math.random() * 0.02,
        })
      }
    }
    build()
    window.addEventListener('resize', build)

    const drawFrame = () => {
      ctx.clearRect(0, 0, W, H)

      // Links first so nodes render on top of their own lines.
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i]
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const d2 = dx * dx + dy * dy
          if (d2 < LINK_DIST * LINK_DIST) {
            const alpha = 0.14 * (1 - Math.sqrt(d2) / LINK_DIST)
            ctx.strokeStyle = `rgba(168,198,240,${alpha})`
            ctx.lineWidth = 0.7
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(b.x, b.y)
            ctx.stroke()
          }
        }
      }

      for (const s of nodes) {
        const tw = reduce ? 0.65 : 0.4 + 0.4 * (0.5 + 0.5 * Math.sin(s.tw))
        ctx.beginPath()
        ctx.arc(s.x, s.y, s.r, 0, 7)
        ctx.fillStyle = `rgba(${s.col},${tw})`
        ctx.fill()
      }

      for (const s of streaks) {
        const coord = s.edge ? s.off : (s.vertical ? W : H) - s.off
        ctx.strokeStyle = `rgba(110,168,232,${s.a})`
        ctx.lineWidth = 1
        ctx.beginPath()
        if (s.vertical) {
          ctx.moveTo(coord, s.pos)
          ctx.lineTo(coord, s.pos + s.len)
        } else {
          ctx.moveTo(s.pos, coord)
          ctx.lineTo(s.pos + s.len, coord)
        }
        ctx.stroke()
      }

      // Equalizer cluster: centered, rounded-top bars fading upward.
      const bw = 5
      const gap = 9
      const total = bars.length * gap
      const x0 = W / 2 - total / 2
      for (let i = 0; i < bars.length; i++) {
        const b = bars[i]
        const h = reduce ? b.base : b.base * (0.7 + 0.3 * Math.sin(b.ph))
        const x = x0 + i * gap
        const g = ctx.createLinearGradient(0, H, 0, H - h)
        g.addColorStop(0, 'rgba(157,184,232,0.34)')
        g.addColorStop(1, 'rgba(157,184,232,0.06)')
        ctx.fillStyle = g
        ctx.beginPath()
        ctx.roundRect(x, H - h, bw, h, [3, 3, 0, 0])
        ctx.fill()
      }
    }

    const tick = () => {
      for (const s of nodes) {
        s.x += s.vx
        s.y += s.vy
        s.tw += s.sp
        // wrap with a small margin so links don't visibly pop at the border
        if (s.x < -20) s.x = W + 20
        if (s.x > W + 20) s.x = -20
        if (s.y < -20) s.y = H + 20
        if (s.y > H + 20) s.y = -20
      }
      for (const s of streaks) {
        s.pos += s.v
        const limit = s.vertical ? H : W
        if (s.pos > limit) s.pos = -s.len
      }
      for (const b of bars) b.ph += b.sp
      drawFrame()
      raf = requestAnimationFrame(tick)
    }

    if (reduce) {
      drawFrame() // one static frame, nothing moves
    } else {
      tick()
    }

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', build)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0 h-full w-full"
    />
  )
}
