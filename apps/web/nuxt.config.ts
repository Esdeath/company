export default defineNuxtConfig({
  compatibilityDate: '2026-07-17',
  css: ['~/assets/css/main.css'],
  devtools: { enabled: false },
  modules: ['@nuxt/eslint'],
  typescript: { strict: true, typeCheck: true },
})
