/** @type {import('tailwindcss').Config} */
// Riscore palette: deep violet base, purple->pink->rose accents, gold highlights.
// Risk-level colors stay semantically green->amber->orange->rose but are tuned
// to sit on the violet background (emerald/amber/orange/rose instead of the
// old GitHub-dark greens/reds).
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0d0814',
        surface: '#140d20',
        surface2: '#1d1230',
        border: '#2b1c45',
        accent: '#c084fc',
        accent2: '#e879f9',
        rose: '#f43f5e',
        gold: '#f59e0b',
        muted: '#9d7cb8',
        up: '#34d399',
        down: '#f43f5e',
        risk: {
          low: '#34d399',
          moderate: '#fbbf24',
          high: '#fb923c',
          extreme: '#f43f5e',
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
        brand: ['Georgia', '"Times New Roman"', 'serif'],
      },
      keyframes: {
        'fade-in': {
          from: { opacity: 0, transform: 'translateY(4px)' },
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
      },
      animation: {
        'fade-in': 'fade-in 0.25s ease-out',
        breathe: 'breathe 6s ease-in-out infinite',
        twinkle: 'twinkle 3s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
