import { useEffect, useRef } from 'react'

// Purely decorative twinkling starfield + occasional shooting star, ported
// from the Riscore.dc design mockup. Canvas-based (cheap: a few hundred dots
// on one 2D context), fixed behind all content, and fully stilled under
// prefers-reduced-motion. No app state or data — it only paints.
export default function Starfield() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const cv = canvasRef.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    let stars = []
    let shoot = null
    let W = 0
    let H = 0
    let raf = 0
    const dpr = Math.min(2, window.devicePixelRatio || 1)

    const build = () => {
      W = cv.clientWidth
      H = cv.clientHeight
      cv.width = W * dpr
      cv.height = H * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const n = Math.round((W * H) / 9000)
      stars = []
      for (let i = 0; i < n; i++) {
        stars.push({
          x: Math.random() * W,
          y: Math.random() * H,
          r: Math.random() * 1.3 + 0.3,
          tw: Math.random() * Math.PI * 2,
          sp: Math.random() * 0.02 + 0.005,
          // hue: violet, rose, or plain white (weighted toward white)
          h: Math.random() < 0.15 ? 280 : Math.random() < 0.5 ? 330 : 0,
        })
      }
    }
    build()
    window.addEventListener('resize', build)

    const draw = () => {
      ctx.clearRect(0, 0, W, H)
      for (const s of stars) {
        if (!reduce) s.tw += s.sp
        const a = reduce ? 0.6 : 0.35 + 0.4 * (0.5 + 0.5 * Math.sin(s.tw))
        const col = s.h === 280 ? '167,139,250' : s.h === 330 ? '236,72,153' : '255,255,255'
        ctx.beginPath()
        ctx.arc(s.x, s.y, s.r, 0, 7)
        ctx.fillStyle = 'rgba(' + col + ',' + a + ')'
        ctx.fill()
      }
      if (!reduce) {
        if (!shoot && Math.random() < 0.004) {
          shoot = { x: Math.random() * W * 0.6, y: Math.random() * H * 0.4, l: 0 }
        }
        if (shoot) {
          shoot.l += 8
          const len = 90
          const g = ctx.createLinearGradient(
            shoot.x + shoot.l,
            shoot.y + shoot.l * 0.4,
            shoot.x + shoot.l + len,
            shoot.y + shoot.l * 0.4 + len * 0.4,
          )
          g.addColorStop(0, 'rgba(255,255,255,0.7)')
          g.addColorStop(1, 'rgba(255,255,255,0)')
          ctx.strokeStyle = g
          ctx.lineWidth = 1.6
          ctx.beginPath()
          ctx.moveTo(shoot.x + shoot.l, shoot.y + shoot.l * 0.4)
          ctx.lineTo(shoot.x + shoot.l + len, shoot.y + shoot.l * 0.4 + len * 0.4)
          ctx.stroke()
          if (shoot.l > W) shoot = null
        }
      }
      raf = requestAnimationFrame(draw)
    }
    draw()

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
