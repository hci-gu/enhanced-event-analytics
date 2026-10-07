import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'API_URL')
  const apiUrl = process.env.API_URL?.trim() || env.API_URL?.trim() || 'http://127.0.0.1:8000'
  const proxy = {
    '/api': {
      target: apiUrl.replace(/\/+$/, ''),
      changeOrigin: true,
      rewrite: (path: string) => path.replace(/^\/api(?=\/|$)/, ''),
    },
  }

  return {
    plugins: [
      react(),
      babel({ presets: [reactCompilerPreset()] })
    ],
    server: { proxy },
    preview: { proxy },
  }
})
