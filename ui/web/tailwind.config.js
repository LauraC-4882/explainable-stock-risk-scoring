/** @type {import('tailwindcss').Config} */
// Riscore "Cosmic Trust" palette (ported from the Riscore.dc design mockup):
// deep space-navy base, violet structural chrome, a sky->indigo primary accent
// for CTAs, and an orange/rose family for the "score" wordmark, price line and
// high-risk bands. Risk-level colors stay semantically green->amber->orange->
// rose. Token NAMES are unchanged from before so the whole app re-skins by
// retuning values rather than rewriting every className.
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#070510',
        surface: '#140d26',
        surface2: '#1d1438',
        border: '#2e2350',
        accent: '#a78bfa', // violet-400 — structural (links, hovers, icon tints)
        accent2: '#c4b5fd', // lighter violet (link hover / gradient partner)
        sky: '#38bdf8', // primary CTA start
        indigo: '#6366f1', // primary CTA end
        rose: '#fb7185',
        gold: '#fb923c', // design "orange" — score wordmark + price line
        amber: '#fbbf24',
        muted: '#8b83a6',
        up: '#34d399',
        down: '#fb7185',
        risk: {
          low: '#34d399',
          moderate: '#fbbf24',
          high: '#fb923c',
          extreme: '#fb7185',
        },
      },
      fontFamily: {
        sans: ['Manrope', 'system-ui', '-apple-system', 'sans-serif'],
        brand: ['"DM Serif Display"', 'Georgia', 'serif'],
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif'], // numbers, tickers, scores
      },
      keyframes: {
        'fade-in': {
          from: { opacity: 0, transform: 'translateY(4px)' },
          to: { opacity: 1, transform: 'translateY(0)' },
        },
        'rise-in': {
          from: { opacity: 0, transform: 'translateY(14px)' },
          to: { opacity: 1, transform: 'translateY(0)' },
        },
        breathe: {
          '0%, 100%': { transform: 'scale(1)' },
          '50%': { transform: 'scale(1.12)' },
        },
        twinkle: {
          '0%, 100%': { opacity: 0.3, transform: 'scale(1)' },
          '50%': { opacity: 1, transform: 'scale(1.6)' },
        },
        'glow-pulse': {
          '0%, 100%': { opacity: 0.55 },
          '50%': { opacity: 1 },
        },
        floaty: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-8px)' },
        },
        shimmer: {
          from: { backgroundPosition: '200% 0' },
          to: { backgroundPosition: '-200% 0' },
        },
        // Signature "cosmic" ambient drift for the three aurora blobs.
        aurora1: {
          '0%, 100%': { transform: 'translate(0,0) scale(1)' },
          '33%': { transform: 'translate(7vw,5vh) scale(1.18)' },
          '66%': { transform: 'translate(-5vw,3vh) scale(.92)' },
        },
        aurora2: {
          '0%, 100%': { transform: 'translate(0,0) scale(1)' },
          '50%': { transform: 'translate(-8vw,-4vh) scale(1.22)' },
        },
        aurora3: {
          '0%, 100%': { transform: 'translate(0,0) scale(1)' },
          '50%': { transform: 'translate(6vw,-6vh) scale(1.1)' },
        },
        // Light sweep across the score-hero top accent bar.
        sweep: {
          '0%': { transform: 'translateX(-120%)' },
          '60%, 100%': { transform: 'translateX(320%)' },
        },
        // Perspective grid-floor scroll.
        'grid-scroll': {
          to: { backgroundPosition: '0 64px' },
        },
        'spin-slow': { to: { transform: 'rotate(360deg)' } },
        'spin-reverse': { to: { transform: 'rotate(-360deg)' } },
      },
      animation: {
        'fade-in': 'fade-in 0.25s ease-out',
        'rise-in': 'rise-in 0.55s ease both',
        breathe: 'breathe 6s ease-in-out infinite',
        twinkle: 'twinkle 3s ease-in-out infinite',
        'glow-pulse': 'glow-pulse 2.6s ease-in-out infinite',
        floaty: 'floaty 6s ease-in-out infinite',
        shimmer: 'shimmer 2.2s linear infinite',
        aurora1: 'aurora1 26s ease-in-out infinite',
        aurora2: 'aurora2 32s ease-in-out infinite',
        aurora3: 'aurora3 38s ease-in-out infinite',
        sweep: 'sweep 3.2s ease-in-out infinite',
        'grid-scroll': 'grid-scroll 4.5s linear infinite',
        'spin-slow': 'spin-slow 26s linear infinite',
        'spin-reverse': 'spin-reverse 20s linear infinite',
      },
      boxShadow: {
        panel: '0 1px 0 0 rgba(255,255,255,0.03) inset, 0 12px 30px -18px rgba(0,0,0,0.6)',
        cta: '0 8px 26px rgba(56,189,248,0.32)',
      },
      backgroundImage: {
        'cta-grad': 'linear-gradient(90deg,#38bdf8,#6366f1)',
      },
    },
  },
  plugins: [],
}
