import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // One shared .env at the repository root serves both backend and frontend.
  const envDir = '..'
  const env = loadEnv(mode, envDir, '')
  return {
    envDir,
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      // In development the browser calls /api on the Vite server, which forwards to FastAPI.
      proxy: { '/api': env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8000' },
    },
  }
})
