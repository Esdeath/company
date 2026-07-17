import tsParser from '@typescript-eslint/parser'
import pluginVue from 'eslint-plugin-vue'

export default [
  {
    ignores: ['dist/**'],
  },
  ...pluginVue.configs['flat/essential'],
  {
    files: ['**/*.ts'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
    },
  },
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        ecmaVersion: 'latest',
        parser: tsParser,
        sourceType: 'module',
      },
    },
  },
]
