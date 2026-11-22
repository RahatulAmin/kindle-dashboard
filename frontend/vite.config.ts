import tailwindcss from '@tailwindcss/vite'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, '..', 'APP_'), ...process.env }
  const host = env.APP_HOST || '127.0.0.1'
  const backendHost = host === '0.0.0.0' ? '127.0.0.1' : host
  const target = 'http://' + backendHost + ':' + (env.APP_PORT || '8765')
  return {
    plugins: [tailwindcss()],
    server: {
      host: '127.0.0.1',
      proxy: { '/api': target, '/kindle': target },
    },
  }
})
