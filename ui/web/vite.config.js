import react from '@vitejs/plugin-react'
// defineConfig comes from vitest/config rather than vite so the `test` block
// below is type-checked and the dev/build config stays in ONE file — a
// separate vitest.config.js would shadow this one entirely and silently drop
// the react plugin, so JSX in tests would fail to transform.
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/metrics': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    css: false,
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      reportsDirectory: './coverage',
      include: ['src/**/*.{js,jsx}'],
      exclude: ['src/test/**', 'src/main.jsx', 'src/chartSetup.js'],
    },
  },
})
