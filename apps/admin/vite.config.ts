import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  base: '/admin/',
  plugins: [vue()],
  server: { host: '0.0.0.0', port: 5173 },
  test: { environment: 'happy-dom' },
})
