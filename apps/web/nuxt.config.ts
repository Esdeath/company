export default defineNuxtConfig({
  compatibilityDate: '2026-07-17',
  css: ['~/assets/css/main.css'],
  devtools: { enabled: false },
  modules: ['@nuxt/eslint'],
  typescript: { strict: true, typeCheck: true },
  routeRules: {
    '/api/**': { proxy: 'http://127.0.0.1:8000/api/**' },
  },
})
