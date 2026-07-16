/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#07090f',
        surface: '#0d1117',
        surface2: '#161b22',
        border: '#21262d',
        accent: '#58a6ff',
        muted: '#8b949e',
        up: '#3fb950',
        down: '#f85149',
        risk: {
          low: '#3fb950',
          moderate: '#d29922',
          high: '#f0883e',
          extreme: '#f85149',
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
      },
      keyframes: {
        'fade-in': {
          from: { opacity: 0, transform: 'translateY(4px)' },
          to: { opacity: 1, transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.25s ease-out',
      },
    },
  },
  plugins: [],
}
