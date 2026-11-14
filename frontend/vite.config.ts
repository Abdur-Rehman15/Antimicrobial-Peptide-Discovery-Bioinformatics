import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// In development the browser talks to this server and /api is forwarded to the FastAPI backend
// (uvicorn amp_triage.api.main:app --port 8000), so there is no CORS to configure.
const backend = process.env.AMP_BACKEND ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': backend, '/health': backend },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
