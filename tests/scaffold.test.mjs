import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { promisify } from 'node:util'
import test from 'node:test'

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), 'utf8')
const execFileAsync = promisify(execFile)
const repositoryRoot = new URL('..', import.meta.url)
const stripLineComments = (source) => source.replace(/#.*$/gm, '')

const nginxLocation = (source, selector) => {
  const match = stripLineComments(source).match(new RegExp(`location\\s+${selector}\\s*\\{([\\s\\S]*?)\\n\\s*\\}`))
  assert.ok(match, `missing nginx location: ${selector}`)
  return match[1]
}

const fakeDocker = `#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_DOCKER_LOG"
if [ "$1" = "inspect" ]; then
  printf '%s\\n' "\${FAKE_CONFIG_USER:-101:101}"
  exit 0
fi
[ "$1" = "compose" ] || exit 2
shift
if [ "$1" = "--env-file" ]; then shift 2; fi
case "$1" in
  ps)
    if [ "$2" = "--status" ]; then
      printf '%s\\n' edge web admin api postgres
    elif [ "$2" = "-q" ]; then
      printf 'cid-%s\\n' "$3"
    else
      printf 'healthy\\n'
    fi
    ;;
  exec)
    if [ "$3" = "edge" ] && [ "\${FAKE_EDGE_ID_FAIL:-0}" = "1" ]; then exit 127; fi
    printf '10001\\n'
    ;;
  port) exit 1 ;;
  stop) : > "$FAKE_POSTGRES_STOPPED" ;;
  start) rm -f "$FAKE_POSTGRES_STOPPED" ;;
  *) exit 2 ;;
esac
`

const fakeCurl = `#!/bin/sh
output=/dev/null
headers=/dev/null
connect_timeout=
max_time=
url=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output) output=$2; shift 2 ;;
    --dump-header) headers=$2; shift 2 ;;
    --connect-timeout) connect_timeout=$2; shift 2 ;;
    --max-time) max_time=$2; shift 2 ;;
    --write-out) shift 2 ;;
    http://*) url=$1; shift ;;
    *) shift ;;
  esac
done
printf '%s connect=%s max=%s\\n' "$url" "$connect_timeout" "$max_time" >> "$FAKE_CURL_LOG"
if [ "\${FAKE_TIMEOUT_ONCE:-0}" = "1" ] && [ ! -e "$FAKE_TIMEOUT_MARKER" ]; then
  : > "$FAKE_TIMEOUT_MARKER"
  exit 28
fi
path=\${url#http://127.0.0.1:8080}
code=200
type=text/html
body=
location=
admin_index='<html><head><title>资料管理后台</title><link rel="stylesheet" href="/admin/assets/app.css"><script src="/admin/assets/app.js"></script></head><body>资料管理后台</body></html>'
case "$path" in
  /healthz) type=application/json; body='{"status":"ok"}' ;;
  /) body='<html><body>企业研究资料库</body></html>' ;;
  /admin) code=308; location=/admin/ ;;
  /admin/) body=$admin_index ;;
  /admin/assets/app.js) type=application/javascript; body='console.log("admin")' ;;
  /admin/assets/app.css) type=text/css; body='body{color:#111}' ;;
  /admin/review/example) body=$admin_index ;;
  /api/health/live) type=application/json; body='{"status":"live"}' ;;
  /api/health/ready)
    type=application/json
    if [ -e "$FAKE_POSTGRES_STOPPED" ]; then
      code=503
      if [ "\${FAKE_BAD_NOT_READY:-0}" = "1" ]; then body='{"status":"broken"}'; else body='{"status":"not_ready"}'; fi
    else
      body='{"status":"ready"}'
    fi
    ;;
  *) code=404; body='not found' ;;
esac
printf '%s' "$body" > "$output"
{
  printf 'HTTP/1.1 %s\\r\\n' "$code"
  printf 'Content-Type: %s\\r\\n' "$type"
  if [ -n "$location" ]; then printf 'Location: %s\\r\\n' "$location"; fi
  printf '\\r\\n'
} > "$headers"
printf '%s' "$code"
`

const runSmokeWithFakes = async (overrides = {}) => {
  const root = await mkdtemp(join(tmpdir(), 'company-smoke-test-'))
  const bin = join(root, 'bin')
  await mkdir(bin)
  await writeFile(join(bin, 'docker'), fakeDocker)
  await writeFile(join(bin, 'curl'), fakeCurl)
  await chmod(join(bin, 'docker'), 0o755)
  await chmod(join(bin, 'curl'), 0o755)
  const env = {
    ...process.env,
    PATH: `${bin}:${process.env.PATH}`,
    TMPDIR: root,
    FAKE_DOCKER_LOG: join(root, 'docker.log'),
    FAKE_CURL_LOG: join(root, 'curl.log'),
    FAKE_POSTGRES_STOPPED: join(root, 'postgres-stopped'),
    FAKE_TIMEOUT_MARKER: join(root, 'timeout-once'),
    ...overrides,
  }
  let result
  try {
    const output = await execFileAsync('bash', ['scripts/compose-smoke.sh'], {
      cwd: repositoryRoot,
      env,
      maxBuffer: 1024 * 1024,
    })
    result = { code: 0, ...output }
  } catch (error) {
    result = { code: error.code, stdout: error.stdout ?? '', stderr: error.stderr ?? '' }
  }
  const dockerLog = await readFile(env.FAKE_DOCKER_LOG, 'utf8').catch(() => '')
  const curlLog = await readFile(env.FAKE_CURL_LOG, 'utf8').catch(() => '')
  const postgresStopped = await readFile(env.FAKE_POSTGRES_STOPPED, 'utf8').then(() => true).catch(() => false)
  await rm(root, { recursive: true, force: true })
  return { ...result, dockerLog, curlLog, postgresStopped }
}

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
  const nginx = stripLineComments(await read('infra/nginx/default.conf'))

  assert.match(nginx, /listen\s+8080\s*;/)
  assert.match(nginx, /absolute_redirect\s+off\s*;/)
  assert.match(nginxLocation(nginx, '=\\s*\\/healthz'), /return\s+200\s+/)
  assert.match(nginxLocation(nginx, '=\\s*\\/admin'), /return\s+308\s+\/admin\/\s*;/)

  for (const [selector, upstream] of [
    ['\\/admin\\/', 'http:\\/\\/admin:8080\\/'],
    ['\\/api\\/', 'http:\\/\\/api:8000'],
    ['\\/', 'http:\\/\\/web:3000'],
  ]) {
    const location = nginxLocation(nginx, selector)
    assert.match(location, new RegExp(`proxy_pass\\s+${upstream}\\s*;`))
    for (const header of ['Host', 'X-Real-IP', 'X-Forwarded-For', 'X-Forwarded-Proto']) {
      assert.match(location, new RegExp(`proxy_set_header\\s+${header}\\s+`), `${selector} missing ${header}`)
    }
  }
})

test('uses bounded condition polling and restores postgres after smoke failures', async () => {
  const smoke = stripLineComments(await read('scripts/compose-smoke.sh'))

  assert.match(smoke, /^set -Eeuo pipefail$/m)
  assert.match(smoke, /request_http\(\)\s*{/)
  assert.match(smoke, /wait_for_http\(\)\s*{/)
  assert.match(smoke, /deadline=\$\(\(SECONDS \+ timeout\)\)/)
  assert.match(smoke, /while \(\( SECONDS < deadline \)\)/)
  assert.match(smoke, /remaining=\$\(\(deadline - SECONDS\)\)/)
  assert.doesNotMatch(smoke, /\bsleep\s+(?:10|30)\b/)
  const curlLines = smoke.match(/^\s*curl\b.*$/gm) ?? []
  assert.equal(curlLines.length, 1, 'all HTTP calls must use the single request helper')
  assert.match(curlLines[0], /--connect-timeout/)
  assert.match(curlLines[0], /--max-time/)
  assert.match(smoke, /trap\s+['"]?restore_postgres/)
  assert.match(smoke, /docker compose[^\n]*start postgres/)
  assert.match(smoke, /docker compose[^\n]*stop postgres/)
  assert.doesNotMatch(smoke, /down\s+-v/)
  assert.match(smoke, /configured_identity=\$\{configured_user%%:\*\}/)
  assert.match(smoke, /configured_identity[^\n]*!=\s*"0"/)
  assert.match(smoke, /configured_identity[^\n]*!=\s*"root"/)

  for (const route of ['/healthz', '/admin', '/admin/', '/api/health/live', '/api/health/ready']) {
    assert.ok(smoke.includes(route), `smoke must check ${route}`)
  }
  for (const [route, status] of [
    ['\\$BASE_URL/healthz', 200],
    ['\\$BASE_URL/', 200],
    ['\\$BASE_URL/admin', 308],
    ['\\$BASE_URL/admin/', 200],
    ['\\$BASE_URL/admin/review/example', 200],
    ['\\$BASE_URL/api/health/live', 200],
    ['\\$BASE_URL/api/health/ready', 200],
  ]) assert.match(smoke, new RegExp(`wait_for_http\\s+"${route}"\\s+${status}\\b`))
  assert.match(smoke, /stop postgres[^]*wait_for_http\s+"\$BASE_URL\/api\/health\/ready"\s+503\b/)
  assert.match(smoke, /start postgres[^]*wait_for_http\s+"\$BASE_URL\/api\/health\/ready"\s+200\b/)
  assert.ok(smoke.includes('/admin/review/example'), 'smoke must check a deep admin SPA route')
  assert.match(smoke, /\/admin\/assets\//)
  assert.match(smoke, /Content-Type/i)
  assert.match(smoke, /application\|text\)\/javascript/)
  assert.match(smoke, /text\/css/)
  for (const body of ['{"status":"live"}', '{"status":"ready"}', '{"status":"not_ready"}']) {
    assert.ok(smoke.includes(body), `smoke must assert exact body ${body}`)
  }
  assert.match(smoke, /for service in web admin api edge; do[^]*assert_non_root_uid\s+"\$service"[^]*done/)
})

test('smoke behavior uses bounded requests, one asset response, and a safe UID fallback', async () => {
  const result = await runSmokeWithFakes({ FAKE_EDGE_ID_FAIL: '1', FAKE_CONFIG_USER: '101:101', FAKE_TIMEOUT_ONCE: '1' })

  assert.equal(result.code, 0, result.stderr)
  assert.match(result.stdout, /compose smoke passed/)
  for (const request of result.curlLog.trim().split('\n')) {
    assert.match(request, /connect=[1-9][0-9]*/)
    assert.match(request, /max=[1-9][0-9]*/)
  }
  assert.equal(result.curlLog.match(/\/admin\/assets\/app\.js/g)?.length, 1)
  assert.equal(result.curlLog.match(/\/admin\/assets\/app\.css/g)?.length, 1)
  assert.match(result.dockerLog, /^inspect\b/m)
  assert.match(result.dockerLog, /stop postgres/)
  assert.match(result.dockerLog, /start postgres/)
  assert.equal(result.postgresStopped, false)
})

test('smoke rejects a root Config.User identity including group-qualified forms', async () => {
  for (const configuredUser of ['0:101', 'root:101']) {
    const result = await runSmokeWithFakes({ FAKE_EDGE_ID_FAIL: '1', FAKE_CONFIG_USER: configuredUser })
    assert.notEqual(result.code, 0)
    assert.match(result.stderr, /no verifiable non-root user/)
  }
})

test('smoke exit trap restores postgres when a post-stop assertion fails', async () => {
  const result = await runSmokeWithFakes({ FAKE_BAD_NOT_READY: '1' })

  assert.notEqual(result.code, 0)
  assert.match(result.stderr, /unexpected body/)
  assert.match(result.dockerLog, /stop postgres[^]*start postgres/)
  assert.equal(result.postgresStopped, false)
})
