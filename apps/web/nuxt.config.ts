export default defineNuxtConfig({
  compatibilityDate: '2026-07-17',
  app: {
    head: {
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/icon.svg' },
        { rel: 'icon', type: 'image/x-icon', href: '/favicon.ico' },
        { rel: 'icon', type: 'image/png', sizes: '16x16', href: '/favicon-16x16.png' },
        { rel: 'icon', type: 'image/png', sizes: '32x32', href: '/favicon-32x32.png' },
        { rel: 'apple-touch-icon', sizes: '180x180', href: '/apple-touch-icon.png' },
        { rel: 'manifest', href: '/site.webmanifest' },
      ],
      meta: [{ name: 'theme-color', content: '#285541' }],
    },
  },
  css: ['~/assets/css/main.css'],
  devtools: { enabled: false },
  modules: ['@nuxt/eslint'],
  typescript: { strict: true, typeCheck: true },
  routeRules: {
    '/api/**': { proxy: 'http://127.0.0.1:8000/api/**' },
  },
})
