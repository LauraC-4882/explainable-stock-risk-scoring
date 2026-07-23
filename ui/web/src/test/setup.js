import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
  localStorage.clear()
})

// Recharts' ResponsiveContainer sizes itself off ResizeObserver, which jsdom
// doesn't implement.
global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// useCountUp animates via rAF; jsdom has it, but running frames on a real
// clock makes assertions flaky. Resolve immediately so the final value lands
// in the first tick.
global.requestAnimationFrame = (cb) => setTimeout(() => cb(performance.now() + 1000), 0)
global.cancelAnimationFrame = (id) => clearTimeout(id)

// Vite injects __APP_VERSION__ at build time; tests get a stand-in.
globalThis.__APP_VERSION__ = '0.0.0-test'
