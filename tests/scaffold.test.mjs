import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { promisify } from 'node:util'
import test from 'node:test'

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), 'utf8')
const execFileAsync = promisify(execFile)
const repositoryRoot = new URL('..', import.meta.url)

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
  assert.match(adminViteConfig, /^(?!\s*\/\/)\s*base:\s*['"]\/admin\/['"]\s*,?\s*$/m)
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

test('declares the five-service local runtime with only intended host ports', async () => {
  const { stdout } = await execFileAsync(
    'docker',
    ['compose', '--env-file', '.env.example', 'config', '--format', 'json'],
    { cwd: repositoryRoot, maxBuffer: 1024 * 1024 },
  )
  const compose = JSON.parse(stdout)

  assert.equal(compose.name, 'company-research-library')
  assert.deepEqual(Object.keys(compose.services).sort(), ['admin', 'api', 'edge', 'postgres', 'web'])
  assert.equal(compose.services.postgres.image, 'postgres:18.4-alpine')
  assert.equal(compose.services.edge.image, 'nginxinc/nginx-unprivileged:1.30.4-alpine')
  assert.doesNotMatch(stdout, /:latest(?:\s|"|$)/)

  assert.deepEqual(compose.services.edge.ports, [
    { mode: 'ingress', target: 8080, published: '8080', protocol: 'tcp', host_ip: '127.0.0.1' },
  ])
  assert.deepEqual(compose.services.postgres.ports, [
    { mode: 'ingress', target: 5432, published: '5432', protocol: 'tcp', host_ip: '127.0.0.1' },
  ])
  for (const [service, port] of [['web', '3000'], ['admin', '8080'], ['api', '8000']]) {
    assert.equal(compose.services[service].ports, undefined, `${service} must not publish a host port`)
    assert.ok(compose.services[service].expose.includes(port), `${service} must expose ${port}`)
  }
})

test('wires health-gated dependencies, durable postgres, and container-safe database settings', async () => {
  const { stdout } = await execFileAsync(
    'docker',
    ['compose', '--env-file', '.env.example', 'config', '--format', 'json'],
    { cwd: repositoryRoot, maxBuffer: 1024 * 1024 },
  )
  const compose = JSON.parse(stdout)

  for (const service of ['edge', 'web', 'admin', 'api', 'postgres']) {
    assert.equal(compose.services[service].restart, 'unless-stopped')
    assert.ok(compose.services[service].healthcheck, `${service} must declare a healthcheck`)
  }
  assert.equal(compose.services.api.depends_on.postgres.condition, 'service_healthy')
  for (const upstream of ['web', 'admin', 'api']) {
    assert.equal(compose.services.edge.depends_on[upstream].condition, 'service_healthy')
  }
  assert.match(compose.services.api.environment.DATABASE_URL, /@postgres:5432\//)
  assert.ok(Object.values(compose.services.api.environment).every((value) => value !== ''))
  const postgresData = compose.services.postgres.volumes.find((mount) => mount.type === 'volume' && mount.source === 'postgres_data')
  assert.ok(postgresData)
  assert.equal(postgresData.target, '/var/lib/postgresql')
  assert.ok(compose.volumes.postgres_data)
})

test('routes edge traffic with deliberate admin prefix stripping and API path preservation', async () => {
  const nginx = await read('infra/nginx/default.conf')

  assert.match(nginx, /listen\s+8080\s*;/)
  assert.match(nginx, /location\s*=\s*\/healthz\s*{[^}]*return\s+200\s+/s)
  assert.match(nginx, /location\s*=\s*\/admin\s*{[^}]*return\s+308\s+\/admin\/\s*;/s)
  assert.match(nginx, /location\s+\/admin\/\s*{[^}]*proxy_pass\s+http:\/\/admin:8080\/\s*;/s)
  assert.match(nginx, /location\s+\/api\/\s*{[^}]*proxy_pass\s+http:\/\/api:8000\s*;/s)
  assert.match(nginx, /location\s+\/\s*{[^}]*proxy_pass\s+http:\/\/web:3000\s*;/s)
  for (const header of ['Host', 'X-Real-IP', 'X-Forwarded-For', 'X-Forwarded-Proto']) {
    assert.match(nginx, new RegExp(`proxy_set_header\\s+${header}\\s+`))
  }
})

test('uses bounded condition polling and restores postgres after smoke failures', async () => {
  const smoke = await read('scripts/compose-smoke.sh')

  assert.match(smoke, /^set -Eeuo pipefail$/m)
  assert.match(smoke, /wait_for_http\(\)\s*{/)
  assert.match(smoke, /deadline=\$\(\(SECONDS \+ timeout\)\)/)
  assert.match(smoke, /while \(\( SECONDS < deadline \)\)/)
  assert.doesNotMatch(smoke, /\bsleep\s+(?:10|30)\b/)
  assert.match(smoke, /trap\s+['"]?restore_postgres/)
  assert.match(smoke, /docker compose[^\n]*start postgres/)
  assert.match(smoke, /docker compose[^\n]*stop postgres/)
  assert.doesNotMatch(smoke, /down\s+-v/)

  for (const route of ['/healthz', '/admin', '/admin/', '/api/health/live', '/api/health/ready']) {
    assert.ok(smoke.includes(route), `smoke must check ${route}`)
  }
  assert.ok(smoke.includes('/admin/review/example'), 'smoke must check a deep admin SPA route')
  assert.match(smoke, /\/admin\/assets\//)
  assert.match(smoke, /Content-Type/i)
  assert.match(smoke, /application\|text\)\/javascript/)
  assert.match(smoke, /text\/css/)
  assert.match(smoke, /for service in web admin api edge; do[^]*assert_non_root_uid\s+"\$service"[^]*done/)
})
