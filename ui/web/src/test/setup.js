import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
  localStorage.clear()
})

// jsdom ships no canvas backend, so Chart.js would throw on construction and
// every chart-rendering test would pass or fail for that reason rather than
// for the behaviour under test. A no-op 2D context lets the real Chart.js run
// its data pipeline — which is where the crashes we care about (mapping over
// undefined series) actually happen.
const noopContext = () =>
  new Proxy(
    {
      canvas: null,
      createLinearGradient: () => ({ addColorStop: () => {} }),
      createPattern: () => ({}),
      measureText: () => ({ width: 0 }),
      getImageData: () => ({ data: [] }),
      save: () => {},
      restore: () => {},
    },
    { get: (target, prop) => (prop in target ? target[prop] : () => {}) }
  )

HTMLCanvasElement.prototype.getContext = vi.fn(noopContext)

// Chart.js sizes itself off ResizeObserver, which jsdom doesn't implement.
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
