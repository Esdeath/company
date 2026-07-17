import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), 'utf8')

test('locks the agreed toolchain versions', async () => {
  assert.equal((await read('.nvmrc')).trim(), '24.18.0')
  assert.equal((await read('.python-version')).trim(), '3.13')

  const rootPackage = JSON.parse(await read('package.json'))
  assert.equal(rootPackage.private, true)
  assert.equal(rootPackage.packageManager, 'pnpm@10.34.5')
  assert.equal(rootPackage.engines.node, '>=24.18.0 <25')
})

test('declares only the two JavaScript applications as workspace packages', async () => {
  const workspace = await read('pnpm-workspace.yaml')
  assert.match(workspace, /apps\/web/)
  assert.match(workspace, /apps\/admin/)
  assert.doesNotMatch(workspace, /apps\/api/)
})

test('serves the admin application from its reserved path', async () => {
  const adminViteConfig = await read('apps/admin/vite.config.ts')
  assert.match(adminViteConfig, /base:\s*['"]\/admin\/['"]/)
})

test('publishes a safe local environment template', async () => {
  const env = await read('.env.example')
  for (const key of [
    'POSTGRES_DB',
    'POSTGRES_USER',
    'POSTGRES_PASSWORD',
    'DATABASE_URL',
    'CORS_ORIGINS',
  ]) assert.match(env, new RegExp(`^${key}=`, 'm'))
  assert.doesNotMatch(env, /ayaseeri|buffett/i)
})

test('ignores local secrets and generated files while keeping the environment template', async () => {
  const rules = (await read('.gitignore')).split(/\r?\n/)
  for (const rule of [
    '.env',
    '.env.*',
    '!.env.example',
    '.superpowers/',
    'node_modules/',
    '.nuxt/',
    '.output/',
    'dist/',
    '__pycache__/',
    '.pytest_cache/',
    '.venv/',
    '*.pyc',
  ]) assert.ok(rules.includes(rule), `missing .gitignore rule: ${rule}`)
})

test('keeps local and generated files out of Docker build contexts', async () => {
  const rules = (await read('.dockerignore')).split(/\r?\n/)
  for (const rule of [
    '.git',
    '.env*',
    '!.env.example',
    '.superpowers',
    'node_modules',
    '.nuxt',
    '.output',
    'dist',
    '.venv',
    '__pycache__',
  ]) assert.ok(rules.includes(rule), `missing .dockerignore rule: ${rule}`)
})
