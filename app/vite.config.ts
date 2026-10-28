/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base './' so the built bundle (and the ./data/*.json fetches) work when served under any sub-path
export default defineConfig({
  base: './',
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/lib/**', 'src/data/**'],
      thresholds: { lines: 85, functions: 85, branches: 75 },
    },
  },
})
