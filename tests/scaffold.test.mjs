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
const stripJavaScriptComments = (source) => source
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/\/\/.*$/gm, '')

const markdownSection = (source, title) => {
  const lines = source.split(/\r?\n/)
  const start = lines.findIndex((line) => line.trim() === `## ${title}`)
  assert.notEqual(start, -1, `missing README section: ${title}`)
  const end = lines.findIndex((line, index) => index > start && line.startsWith('## '))
  return lines.slice(start + 1, end === -1 ? undefined : end).join('\n')
}

const markdownTableRow = (section, firstCell) => {
  const row = section.split(/\r?\n/).find((line) => line.startsWith(`| \`${firstCell}\` |`))
  assert.ok(row, `missing Markdown table row: ${firstCell}`)
  return row
}

const makeTarget = (source, name) => {
  const lines = source.split(/\r?\n/)
  const start = lines.findIndex((line) => line.startsWith(`${name}:`))
  assert.notEqual(start, -1, `Makefile must provide ${name}`)
  const prerequisites = lines[start].slice(name.length + 1).trim().split(/\s+/).filter(Boolean)
  const recipe = []
  for (let index = start + 1; index < lines.length && lines[index].startsWith('\t'); index += 1) {
    recipe.push(lines[index].slice(1))
  }
  return { prerequisites, recipe }
}

const nginxLocation = (source, selector) => {
  const match = stripLineComments(source).match(new RegExp(`location\\s+${selector}\\s*\\{([\\s\\S]*?)\\n\\s*\\}`))
  assert.ok(match, `missing nginx location: ${selector}`)
  return match[1]
}

const fakeDocker = `#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_DOCKER_LOG"
if [ "$1" = "inspect" ]; then
  case "$*" in
    *NetworkSettings.Ports*) printf '%s\\n' "\${FAKE_PORT_BINDINGS:-null}" ;;
    *) printf '%s\\n' "\${FAKE_CONFIG_USER:-101:101}" ;;
  esac
  exit 0
fi
[ "$1" = "compose" ] || exit 2
shift
if [ "$1" = "--env-file" ]; then shift 2; fi
case "$1" in
  ps)
    if [ "$2" = "--status" ]; then
      if [ "\${FAKE_SERVICE_STATE:-running}" = "exited" ]; then
        printf '%s\\n' web admin api postgres
      else
        printf '%s\\n' edge web admin api postgres
      fi
    elif [ "$2" = "-q" ]; then
      printf 'cid-%s\\n' "$3"
    else
      case "$*" in
        *State*)
          if [ "\${FAKE_SERVICE_STATE:-running}" = "exited" ] && ! printf '%s' "$*" | grep -Fq -- '--all'; then
            :
          else
            printf '%s\\n' "\${FAKE_SERVICE_STATE:-running}"
          fi
          ;;
        *Health*)
          if [ "\${FAKE_SERVICE_STATE:-running}" = "exited" ] && ! printf '%s' "$*" | grep -Fq -- '--all'; then
            :
          elif [ "\${FAKE_HEALTH_UNHEALTHY:-0}" = "1" ]; then
            printf 'unhealthy\\n'
          elif [ "\${FAKE_HEALTH_STARTING_ONCE:-0}" = "1" ] && [ ! -e "$FAKE_HEALTH_MARKER" ]; then
            : > "$FAKE_HEALTH_MARKER"
            printf 'starting\\n'
          else
            printf 'healthy\\n'
          fi
          ;;
        *) exit 2 ;;
      esac
    fi
    ;;
  exec)
    if [ "$3" = "edge" ] && [ "\${FAKE_EDGE_ID_FAIL:-0}" = "1" ]; then exit 127; fi
    if [ "$3" = "api" ] && [ "$4" = "python" ]; then
      printf 'fake-verification-token\\n'
    else
      printf '10001\\n'
    fi
    ;;
  port) printf ':0\\n' ;;
  stop) : > "$FAKE_POSTGRES_STOPPED" ;;
  start) rm -f "$FAKE_POSTGRES_STOPPED" ;;
  up) ;;
  *) exit 2 ;;
esac
`

const fakeCurl = `#!/bin/sh
output=/dev/null
headers=/dev/null
connect_timeout=
max_time=
url=
method=GET
request_data=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output) output=$2; shift 2 ;;
    --dump-header) headers=$2; shift 2 ;;
    --connect-timeout) connect_timeout=$2; shift 2 ;;
    --max-time) max_time=$2; shift 2 ;;
    --write-out) shift 2 ;;
    --request|-X) method=$2; shift 2 ;;
    --data) request_data=$2; shift 2 ;;
    --header|-H|--form|-F|--cookie|--cookie-jar) shift 2 ;;
    http://*) url=$1; shift ;;
    *) shift ;;
  esac
done
printf '%s %s connect=%s max=%s\\n' "$method" "$url" "$connect_timeout" "$max_time" >> "$FAKE_CURL_LOG"
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
case "$method:$path" in
  GET:/api/v1/auth/session)
    type=application/json
    body='{"authenticated":false,"username":null,"csrf_token":"login-csrf","expires_at":null}'
    ;;
  POST:/api/v1/auth/login)
    type=application/json
    body='{"authenticated":true,"username":"admin","csrf_token":"session-csrf","expires_at":"2026-07-21T20:00:00Z"}'
    ;;
  POST:/api/v1/companies)
    company_name=$(printf '%s' "$request_data" | sed -n 's/.*"name":"\\([^"]*\\)".*/\\1/p')
    printf '%s' "$company_name" > "$FAKE_COMPANY_NAME_FILE"
    if [ "\${FAKE_COMPANY_POST_TIMEOUT:-0}" = "1" ]; then exit 28; fi
    type=application/json
    code=201
    if [ "\${FAKE_COMPANY_RESPONSE_MALFORMED:-0}" = "1" ]; then
      body='{malformed'
    else
      response_id='"11111111-1111-4111-8111-111111111111"'
      response_name=$company_name
      case "\${FAKE_COMPANY_RESPONSE_ID_KIND:-uuid}" in
        null) response_id=null ;;
        number) response_id=42 ;;
        invalid) response_id='"not-a-uuid"' ;;
        noncanonical) response_id='"AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"' ;;
      esac
      if [ "\${FAKE_COMPANY_RESPONSE_NAME_MISMATCH:-0}" = "1" ]; then
        response_id='"55555555-5555-4555-8555-555555555555"'
        response_name=another-company
      fi
      body='{"id":'"$response_id"',"name":"'"$response_name"'","ticker":null,"market":null,"created_at":"2026-07-20T00:00:00Z"}'
    fi
    ;;
  POST:/api/v1/companies/11111111-1111-4111-8111-111111111111/documents)
    type=application/json
    second_format=html
    second_url=/api/v1/documents/33333333-3333-4333-8333-333333333333/content
    if [ "\${FAKE_DUPLICATE_UPLOAD_FORMAT:-0}" = "1" ]; then second_format=markdown; fi
    if [ "\${FAKE_MISMATCHED_CONTENT_URL:-0}" = "1" ]; then second_url=/api/v1/documents/22222222-2222-4222-8222-222222222222/content; fi
    body='{"items":[{"id":"22222222-2222-4222-8222-222222222222","title":"CEO interview","format":"markdown","content_url":"/api/v1/documents/22222222-2222-4222-8222-222222222222/content"},{"id":"33333333-3333-4333-8333-333333333333","title":"Showcase","format":"'"$second_format"'","content_url":"'"$second_url"'"}],"errors":[]}'
    ;;
  GET:/api/v1/user-auth/session)
    type=application/json
    body='{"authenticated":false,"csrf_token":"user-challenge","registration_enabled":true}'
    ;;
  POST:/api/v1/user-auth/register)
    type=application/json
    code=202
    body='{"message":"verification queued"}'
    ;;
  POST:/api/v1/user-auth/verify-email)
    type=application/json
    body='{"authenticated":true,"csrf_token":"user-csrf","registration_enabled":true,"user":{"id":"99999999-9999-4999-8999-999999999999","email":"reader@example.com","username":"reader","email_verified_at":"2026-07-20T00:00:00Z","first_comment_approved_at":null,"reply_email_enabled":true}}'
    ;;
  POST:/api/v1/documents/22222222-2222-4222-8222-222222222222/comments)
    type=application/json
    code=201
    if printf '%s' "$request_data" | grep -Fq 'parent_id'; then
      body='{"id":"77777777-7777-4777-8777-777777777777","document_id":"22222222-2222-4222-8222-222222222222","parent_id":"66666666-6666-4666-8666-666666666666","body":"Compose smoke reply","status":"pending","author":{"id":"99999999-9999-4999-8999-999999999999","username":"reader"},"created_at":"2026-07-20T00:00:00Z","edited_at":null,"replies":[],"can_edit":true,"can_delete":true,"can_report":false}'
    else
      body='{"id":"66666666-6666-4666-8666-666666666666","document_id":"22222222-2222-4222-8222-222222222222","parent_id":null,"body":"Compose smoke pending comment","status":"pending","author":{"id":"99999999-9999-4999-8999-999999999999","username":"reader"},"created_at":"2026-07-20T00:00:00Z","edited_at":null,"replies":[],"can_edit":true,"can_delete":true,"can_report":false}'
    fi
    ;;
  POST:/api/v1/admin/comments/*/approve)
    type=application/json
    body='{"status":"published"}'
    ;;
  GET:/api/v1/users/me/notifications)
    type=application/json
    body='{"items":[{"id":"88888888-8888-4888-8888-888888888888","type":"reply","company_id":"11111111-1111-4111-8111-111111111111","document_id":"22222222-2222-4222-8222-222222222222","comment_id":"77777777-7777-4777-8777-777777777777","actor_username":"reader","excerpt":"reply","message":"reply","created_at":"2026-07-20T00:00:00Z","read_at":null}],"unread_count":1}'
    ;;
  PATCH:/api/v1/users/me/notifications/88888888-8888-4888-8888-888888888888)
    type=application/json
    body='{"id":"88888888-8888-4888-8888-888888888888","read_at":"2026-07-20T00:01:00Z"}'
    ;;
  DELETE:/api/v1/users/me) code=204; body= ;;
  GET:/api/v1/companies)
    type=application/json
    company_name=$(cat "$FAKE_COMPANY_NAME_FILE" 2>/dev/null || true)
    if [ "\${FAKE_COMPANY_RESPONSE_NAME_MISMATCH:-0}" = "1" ]; then
      body='[{"id":"11111111-1111-4111-8111-111111111111","name":"'"$company_name"'"},{"id":"55555555-5555-4555-8555-555555555555","name":"another-company"}]'
    elif [ "\${FAKE_DUPLICATE_COMPANY_NAME:-0}" = "1" ]; then
      body='[{"id":"11111111-1111-4111-8111-111111111111","name":"'"$company_name"'"},{"id":"44444444-4444-4444-8444-444444444444","name":"'"$company_name"'"}]'
    else
      body='[{"id":"11111111-1111-4111-8111-111111111111","name":"'"$company_name"'"}]'
    fi
    ;;
  GET:/api/v1/companies/11111111-1111-4111-8111-111111111111/documents)
    type=application/json
    body='[{"id":"22222222-2222-4222-8222-222222222222"},{"id":"33333333-3333-4333-8333-333333333333"}]'
    ;;
  GET:/api/v1/documents/22222222-2222-4222-8222-222222222222/content)
    if [ "\${FAKE_BAD_MARKDOWN:-0}" = "1" ]; then body='<html>bad markdown</html>'; else body='<main class="research-document">Markdown</main>'; fi
    ;;
  GET:/api/v1/documents/33333333-3333-4333-8333-333333333333/content)
    body='<title>通用 Markdown 模板预览</title>'
    ;;
  DELETE:/api/v1/documents/*|DELETE:/api/v1/companies/*) code=204; body= ;;
  GET:/healthz) type=application/json; body='{"status":"ok"}' ;;
  GET:/) body='<html><body>企业研究资料库</body></html>' ;;
  GET:/admin) code=308; location=/admin/ ;;
  GET:/admin/) body=$admin_index ;;
  GET:/admin/assets/app.js) type=application/javascript; body='console.log("admin")' ;;
  GET:/admin/assets/app.css) type=text/css; body='body{color:#111}' ;;
  GET:/admin/review/example) body=$admin_index ;;
  GET:/api/health/live) type=application/json; body='{"status":"live"}' ;;
  GET:/api/health/ready)
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

const runSmokeWithFakes = async (overrides = {}, timeout = 30_000) => {
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
    FAKE_COMPANY_NAME_FILE: join(root, 'company-name'),
    FAKE_TIMEOUT_MARKER: join(root, 'timeout-once'),
    FAKE_HEALTH_MARKER: join(root, 'health-starting-once'),
    ...overrides,
  }
  let result
  try {
    const output = await execFileAsync('bash', ['scripts/compose-smoke.sh'], {
      cwd: repositoryRoot,
      env,
      maxBuffer: 1024 * 1024,
      timeout,
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
  const packages = workspace
    .split(/\r?\n/)
    .map((line) => line.match(/^\s*-\s+(.+?)\s*$/)?.[1])
    .filter(Boolean)
  assert.deepEqual(packages, ['apps/web', 'apps/admin'])
  assert.ok(packages.every((entry) => !entry.includes('*')), 'workspace entries must not use wide globs')
})

test('serves the admin application from its reserved path', async () => {
  const adminViteConfig = stripJavaScriptComments(await read('apps/admin/vite.config.ts'))
  assert.match(adminViteConfig, /^(?!\s*\/\/)\s*base:\s*['"]\/admin\/['"]\s*,?\s*$/m)
})

test('publishes a safe local environment template', async () => {
  const env = await read('.env.example')
  for (const key of [
    'POSTGRES_DB',
    'POSTGRES_USER',
    'POSTGRES_PASSWORD',
    'DATABASE_URL',
    'ADMIN_USERNAME',
    'ADMIN_PASSWORD_HASH',
    'CORS_ORIGINS',
    'CONTENT_ROOT',
    'SESSION_COOKIE_SECURE',
    'SESSION_LIFETIME_SECONDS',
    'APP_ENVIRONMENT',
    'USER_REGISTRATION_ENABLED',
    'COMMENT_WRITES_ENABLED',
    'USER_SESSION_LIFETIME_SECONDS',
    'USER_TOKEN_SIGNING_KEY',
    'EMAIL_BACKEND',
    'EMAIL_CAPTURE_PATH',
    'SMTP_HOST',
    'SMTP_PORT',
    'SMTP_USERNAME',
    'SMTP_PASSWORD',
    'SMTP_STARTTLS',
    'SMTP_SENDER',
    'PUBLIC_BASE_URL',
    'EMAIL_DISPATCH_INTERVAL_SECONDS',
    'EMAIL_MAX_ATTEMPTS',
  ]) assert.match(env, new RegExp(`^${key}=`, 'm'))
  assert.match(env, /^CONTENT_ROOT=\.\.\/\.\.\/var\/content$/m)
  assert.match(env, /^USER_REGISTRATION_ENABLED=false$/m)
  assert.match(env, /^COMMENT_WRITES_ENABLED=true$/m)
  assert.match(env, /^SMTP_PASSWORD=$/m)
  assert.doesNotMatch(env, /^SMTP_PASSWORD=.+$/m)
  assert.doesNotMatch(env, /ayaseeri|buffett/i)
})

test('wires every community setting into the existing API service', async () => {
  const { stdout } = await execFileAsync(
    'docker',
    ['compose', '--env-file', '.env.example', 'config', '--format', 'json'],
    { cwd: repositoryRoot, maxBuffer: 1024 * 1024 },
  )
  const compose = JSON.parse(stdout)
  const environment = compose.services.api.environment

  assert.deepEqual(Object.keys(compose.services).sort(), ['admin', 'api', 'edge', 'postgres', 'web'])
  for (const key of [
    'APP_ENVIRONMENT',
    'USER_REGISTRATION_ENABLED',
    'COMMENT_WRITES_ENABLED',
    'USER_SESSION_LIFETIME_SECONDS',
    'USER_TOKEN_SIGNING_KEY',
    'EMAIL_BACKEND',
    'EMAIL_CAPTURE_PATH',
    'SMTP_HOST',
    'SMTP_PORT',
    'SMTP_USERNAME',
    'SMTP_PASSWORD',
    'SMTP_STARTTLS',
    'SMTP_SENDER',
    'PUBLIC_BASE_URL',
    'EMAIL_DISPATCH_INTERVAL_SECONDS',
    'EMAIL_MAX_ATTEMPTS',
  ]) assert.ok(Object.hasOwn(environment, key), `API service missing ${key}`)
  assert.equal(environment.USER_REGISTRATION_ENABLED, 'false')
  assert.equal(environment.COMMENT_WRITES_ENABLED, 'true')
  assert.equal(environment.SMTP_PASSWORD, '')
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
    '.ruff_cache/',
    '.mypy_cache/',
    'coverage/',
    '/var/',
  ]) assert.ok(rules.includes(rule), `missing .gitignore rule: ${rule}`)
})

test('documents the direct-document slice, service boundaries, and authenticated security scope', async () => {
  const readme = await read('README.md')
  const architecture = markdownSection(readme, '五个服务')
  const hybrid = markdownSection(readme, '混合开发')
  const unavailable = markdownSection(readme, '当前不包含')

  for (const [service, responsibility, boundary] of [
    ['edge', /路由|分发/, /127\.0\.0\.1:8080/],
    ['web', /公开站点|阅读/, /Compose[^|]*3000/],
    ['admin', /管理端|上传/, /Compose[^|]*8080/],
    ['api', /FastAPI|资料/, /Compose[^|]*8000/],
    ['postgres', /PostgreSQL|数据库/, /127\.0\.0\.1:5432/],
  ]) {
    const row = markdownTableRow(architecture, service)
    assert.match(row, responsibility, `${service} row must state its responsibility`)
    assert.match(row, boundary, `${service} row must state its port boundary`)
  }
  assert.match(architecture, /127\.0\.0\.1:8080/)
  assert.match(architecture, /127\.0\.0\.1:5432/)
  assert.match(architecture, /Web、Admin 和 API[^\n]*只在 Compose 网络内/)

  for (const target of ['make dev-web', 'make dev-admin', 'make dev-api']) {
    assert.ok(hybrid.includes(target), `hybrid section must document ${target}`)
  }
  for (const address of ['127.0.0.1:3000', '127.0.0.1:5173/admin/', '127.0.0.1:8000/api/health/live']) {
    assert.ok(hybrid.includes(address), `hybrid section must document ${address}`)
  }
  assert.match(unavailable, /不包含|不可用/)
  assert.match(unavailable, /多管理员/)
  assert.match(unavailable, /二次验证/)
  assert.match(unavailable, /HTTPS Nginx/)
  assert.doesNotMatch(unavailable, /资料上传[^。]*不可用/)
})

test('maps every public Make target to its command in one README table entry', async () => {
  const targets = markdownSection(await read('README.md'), 'Make 目标与底层命令')

  for (const [target, commands] of [
    ['make setup', ['corepack pnpm install --frozen-lockfile', 'cd apps/api && uv sync --frozen']],
    ['make admin-password-hash', ['./scripts/hash-admin-password.sh']],
    ['make deploy-aliyun', ['./scripts/deploy-aliyun-ecs.sh']],
    ['make dev-infra', ['docker compose --env-file .env up -d postgres']],
    ['make dev', ['make -j3 dev-web dev-admin dev-api']],
    ['make db-upgrade', ['cd apps/api && uv run --env-file ../../.env alembic upgrade head']],
    ['make check', [
      'node --test tests/docs.test.mjs tests/prototype.test.mjs tests/scaffold.test.mjs',
      'corepack pnpm --filter @company/web check',
      'corepack pnpm --filter @company/admin check',
      'cd apps/api && uv run ruff check .',
      'cd apps/api && uv run ruff format --check .',
      'cd apps/api && uv run mypy src',
      'cd apps/api && uv run pytest',
    ]],
    ['make compose-up', ['docker compose --env-file .env up --build -d']],
    ['make compose-smoke', ['./scripts/compose-smoke.sh']],
    ['make compose-down', ['docker compose --env-file .env down']],
  ]) {
    const row = markdownTableRow(targets, target)
    for (const command of commands) assert.ok(row.includes(command), `${target} row must expose ${command}`)
  }
})

test('gives each Make target exact prerequisites and a bounded recipe', async () => {
  const makefile = await read('Makefile')
  const dev = makeTarget(makefile, 'dev')
  assert.deepEqual(dev.prerequisites, ['require-env'])
  assert.deepEqual(dev.recipe, ['+$(MAKE) -j3 dev-web dev-admin dev-api'])

  const infrastructure = makeTarget(makefile, 'dev-infra')
  assert.deepEqual(infrastructure.prerequisites, ['require-env'])
  assert.deepEqual(infrastructure.recipe, ['docker compose --env-file .env up -d postgres'])

  const check = makeTarget(makefile, 'check')
  assert.ok(check.prerequisites.every((dependency) => !/docker|compose/i.test(dependency)))
  assert.ok(check.recipe.every((command) => !/docker|compose/i.test(command)))
  for (const command of [
    'node --test tests/docs.test.mjs tests/prototype.test.mjs tests/scaffold.test.mjs',
    '$(PNPM) --filter @company/web check',
    '$(PNPM) --filter @company/admin check',
    'cd apps/api && $(UV) run ruff check .',
    'cd apps/api && $(UV) run ruff format --check .',
    'cd apps/api && $(UV) run mypy src',
    'cd apps/api && $(UV) run pytest',
  ]) assert.ok(check.recipe.includes(command), `check must run ${command}`)

  const composeUp = makeTarget(makefile, 'compose-up')
  assert.deepEqual(composeUp.prerequisites, ['require-env'])
  assert.deepEqual(composeUp.recipe, ['docker compose --env-file .env up --build -d'])
  assert.deepEqual(makeTarget(makefile, 'compose-smoke').recipe, ['./scripts/compose-smoke.sh'])
  const composeDown = makeTarget(makefile, 'compose-down')
  assert.deepEqual(composeDown.recipe, ['docker compose --env-file .env down'])
  assert.ok(composeDown.recipe.every((command) => !/(?:^|\s)-v(?:\s|$)/.test(command)))

  const setup = makeTarget(makefile, 'setup')
  assert.ok(setup.recipe.includes('$(PNPM) install --frozen-lockfile'))
  assert.ok(setup.recipe.includes('cd apps/api && $(UV) sync --frozen'))
  assert.deepEqual(makeTarget(makefile, 'db-upgrade'), {
    prerequisites: ['require-env'],
    recipe: ['cd apps/api && $(UV) run --env-file ../../.env alembic upgrade head'],
  })
  assert.deepEqual(makeTarget(makefile, 'dev-api').prerequisites, ['db-upgrade'])
  assert.deepEqual(makeTarget(makefile, 'dev-api').recipe, [
    'cd apps/api && $(UV) run --env-file ../../.env uvicorn --factory company_api.main:create_app --reload --host 0.0.0.0 --port 8000',
  ])
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

  const apiRules = (await read('apps/api/.dockerignore')).split(/\r?\n/)
  for (const rule of [
    '.venv',
    'tests',
    '.pytest_cache',
    '.ruff_cache',
    '.mypy_cache',
    '__pycache__',
    '*.pyc',
    '.env',
    '.env.*',
    'coverage',
  ]) assert.ok(apiRules.includes(rule), `missing API context .dockerignore rule: ${rule}`)
})

test('copies Nuxt public assets into the web image build', async () => {
  const dockerfile = await read('apps/web/Dockerfile')

  assert.match(
    dockerfile,
    /^COPY apps\/web\/public apps\/web\/public$/m,
    'web image must include favicon and brand assets from apps/web/public',
  )
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

  assert.deepEqual(Object.keys(compose.networks).sort(), ['backend', 'edge'])
  assert.deepEqual(Object.keys(compose.services.edge.networks), ['edge'])
  assert.deepEqual(Object.keys(compose.services.web.networks), ['edge'])
  assert.deepEqual(Object.keys(compose.services.admin.networks), ['edge'])
  assert.deepEqual(Object.keys(compose.services.postgres.networks), ['backend'])
  assert.deepEqual(Object.keys(compose.services.api.networks).sort(), ['backend', 'edge'])
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
  assert.match(compose.services.api.environment.ADMIN_PASSWORD_HASH.replaceAll('$$', '$'), /^\$argon2id\$/)
  assert.equal(compose.services.api.environment.SESSION_COOKIE_SECURE, 'false')
  const optionalCommunityValues = new Set([
    'EMAIL_CAPTURE_PATH',
    'SMTP_HOST',
    'SMTP_USERNAME',
    'SMTP_PASSWORD',
    'SMTP_SENDER',
  ])
  for (const [key, value] of Object.entries(compose.services.api.environment)) {
    if (!optionalCommunityValues.has(key)) assert.notEqual(value, '', `${key} must not be empty`)
  }
  const postgresData = compose.services.postgres.volumes.find((mount) => mount.type === 'volume' && mount.source === 'postgres_data')
  assert.ok(postgresData)
  assert.equal(postgresData.target, '/var/lib/postgresql')
  assert.ok(compose.volumes.postgres_data)
})

test('Compose persists document content and migrates before API start', async () => {
  const composeSource = await read('compose.yaml')
  const apiDockerfile = await read('apps/api/Dockerfile')
  const apiEntrypoint = await read('apps/api/docker-entrypoint.sh').catch(() => '')
  const apiRuntime = [apiDockerfile, apiEntrypoint].join('\n')

  assert.match(composeSource, /content_data:\/data\/content/)
  assert.match(composeSource, /CONTENT_ROOT:\s*\/data\/content/)
  assert.match(apiRuntime, /alembic upgrade head/)
  assert.match(apiRuntime, /mkdir -p \/data\/content/)
  assert.match(apiRuntime, /chown[^\n]+10001|chown[^\n]+app/)
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
  assert.match(smoke, /configured_identity[^\n]*\^0\+\$/)
  assert.match(smoke, /configured_identity[^\n]*!=\s*"root"/)

  for (const route of ['/healthz', '/admin', '/admin/', '/api/health/live', '/api/health/ready', '/api/v1/auth/session', '/api/v1/auth/login']) {
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
  assert.match(smoke, /X-CSRF-Token/)
  assert.match(smoke, /--cookie-jar/)
  assert.match(smoke, /application\|text\)\/javascript/)
  assert.match(smoke, /text\/css/)
  for (const body of ['{"status":"live"}', '{"status":"ready"}', '{"status":"not_ready"}']) {
    assert.ok(smoke.includes(body), `smoke must assert exact body ${body}`)
  }
  assert.match(smoke, /for service in web admin api edge; do[^]*assert_non_root_uid\s+"\$service"[^]*done/)
  assert.ok(smoke.includes('doc/templates/markdown/examples/ceo-interview.md'))
  assert.ok(smoke.includes('doc/templates/markdown/showcase.html'))
  assert.match(smoke, /class=["']research-document["']/)
  assert.match(smoke, /通用 Markdown 模板预览/)
  assert.match(smoke, /python3 -c/)
  assert.doesNotMatch(smoke, /\bjq\b/)
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

test('smoke accepts Compose expose-only port sentinels as internal ports', async () => {
  const result = await runSmokeWithFakes()

  assert.equal(result.code, 0, result.stderr)
  assert.match(result.stdout, /compose smoke passed/)
})

test('smoke does not recover a company by name after successful cleanup', async () => {
  const result = await runSmokeWithFakes()

  assert.equal(result.code, 0, result.stderr)
  assert.doesNotMatch(result.curlLog, /GET .*\/api\/v1\/companies connect=/)
})

test('smoke waits for containers to become healthy', async () => {
  const result = await runSmokeWithFakes({ FAKE_HEALTH_STARTING_ONCE: '1' })

  assert.equal(result.code, 0, result.stderr)
  assert.match(result.stdout, /compose smoke passed/)
})

test('smoke fails immediately for terminal container states', async () => {
  for (const overrides of [
    { FAKE_HEALTH_UNHEALTHY: '1' },
    { FAKE_SERVICE_STATE: 'exited' },
  ]) {
    const result = await runSmokeWithFakes(overrides, 2_000)

    assert.notEqual(result.code, 0)
    assert.match(result.stderr, /terminal state.*(?:unhealthy|exited)/)
  }
})

test('smoke rejects real host port bindings', async () => {
  const result = await runSmokeWithFakes({
    FAKE_PORT_BINDINGS: '[{"HostIp":"127.0.0.1","HostPort":"12345"}]',
  })

  assert.notEqual(result.code, 0)
  assert.match(result.stderr, /unexpectedly has a host mapping/)
})

test('smoke rejects a root Config.User identity including group-qualified forms', async () => {
  for (const configuredUser of ['0:101', '00:101', '000:101', 'root:101']) {
    const result = await runSmokeWithFakes({ FAKE_EDGE_ID_FAIL: '1', FAKE_CONFIG_USER: configuredUser })
    assert.notEqual(result.code, 0)
    assert.match(result.stderr, /no verifiable non-root user/)
  }
})

test('smoke exit trap restores postgres when a post-stop assertion fails', async () => {
  const result = await runSmokeWithFakes({ FAKE_BAD_NOT_READY: '1' })

  assert.notEqual(result.code, 0)
  assert.match(result.stderr, /unexpected response body/)
  assert.match(result.dockerLog, /stop postgres[^]*start postgres/)
  assert.equal(result.postgresStopped, false)
})

test('smoke cleanup removes uploaded documents and the company after a content assertion fails', async () => {
  const result = await runSmokeWithFakes({ FAKE_BAD_MARKDOWN: '1' })

  assert.notEqual(result.code, 0)
  assert.match(result.stderr, /Markdown content marker missing/)
  assert.match(result.curlLog, /DELETE .*\/api\/v1\/documents\/22222222-2222-4222-8222-222222222222/)
  assert.match(result.curlLog, /DELETE .*\/api\/v1\/documents\/33333333-3333-4333-8333-333333333333/)
  assert.match(result.curlLog, /DELETE .*\/api\/v1\/companies\/11111111-1111-4111-8111-111111111111/)
})

test('smoke cleanup finds the exact company name after an ambiguous create response', async () => {
  for (const overrides of [
    { FAKE_COMPANY_RESPONSE_MALFORMED: '1' },
    { FAKE_COMPANY_POST_TIMEOUT: '1' },
  ]) {
    const result = await runSmokeWithFakes(overrides)

    assert.equal(result.code, 1)
    assert.match(result.curlLog, /GET .*\/api\/v1\/companies\b.*connect=[1-9][0-9]* max=[1-9][0-9]*/)
    assert.match(result.curlLog, /DELETE .*\/api\/v1\/companies\/11111111-1111-4111-8111-111111111111/)
    assert.doesNotMatch(result.stderr, /\{malformed|Traceback|JSONDecodeError/)
  }
})

test('smoke rejects non-canonical company ids and recovers the exact created company', async () => {
  for (const [kind, leakedValue] of [
    ['null', 'None'],
    ['number', '42'],
    ['invalid', 'not-a-uuid'],
    ['noncanonical', 'AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA'],
  ]) {
    const result = await runSmokeWithFakes({ FAKE_COMPANY_RESPONSE_ID_KIND: kind })

    assert.equal(result.code, 1)
    assert.match(result.stderr, /could not validate created company/)
    assert.doesNotMatch(result.stderr, new RegExp(`${leakedValue}|Traceback|"id"`))
    assert.match(result.curlLog, /GET .*\/api\/v1\/companies connect=/)
    assert.match(result.curlLog, /DELETE .*\/api\/v1\/companies\/11111111-1111-4111-8111-111111111111/)
    assert.doesNotMatch(result.curlLog, new RegExp(`/api/v1/companies/${leakedValue}(?:/|\\s)`))
  }
})

test('smoke rejects a valid company id paired with the wrong response name', async () => {
  const otherCompanyId = '55555555-5555-4555-8555-555555555555'
  const result = await runSmokeWithFakes({ FAKE_COMPANY_RESPONSE_NAME_MISMATCH: '1' })

  assert.equal(result.code, 1)
  assert.match(result.stderr, /could not validate created company/)
  assert.doesNotMatch(result.stderr, /another-company|55555555|Traceback|"name"/)
  assert.match(result.curlLog, /GET .*\/api\/v1\/companies connect=/)
  assert.match(result.curlLog, /DELETE .*\/api\/v1\/companies\/11111111-1111-4111-8111-111111111111/)
  assert.doesNotMatch(result.curlLog, new RegExp(`/api/v1/companies/${otherCompanyId}(?:/|\\s)`))
})

test('smoke cleanup does not guess when multiple companies share the exact smoke name', async () => {
  const result = await runSmokeWithFakes({
    FAKE_COMPANY_RESPONSE_MALFORMED: '1',
    FAKE_DUPLICATE_COMPANY_NAME: '1',
  })

  assert.equal(result.code, 1)
  assert.match(result.curlLog, /GET .*\/api\/v1\/companies\b/)
  assert.doesNotMatch(result.curlLog, /DELETE .*\/api\/v1\/companies\//)
})

test('smoke rejects duplicate upload formats before fetching document content', async () => {
  const result = await runSmokeWithFakes({ FAKE_DUPLICATE_UPLOAD_FORMAT: '1' })

  assert.equal(result.code, 1)
  assert.match(result.stderr, /exactly one Markdown, one HTML, and zero errors with canonical content URLs/)
  assert.doesNotMatch(result.stderr, /22222222|33333333|"items"/)
  assert.doesNotMatch(result.curlLog, /^GET .*\/api\/v1\/documents\//m)
})

test('smoke rejects a content URL that does not match its document id', async () => {
  const result = await runSmokeWithFakes({ FAKE_MISMATCHED_CONTENT_URL: '1' })

  assert.equal(result.code, 1)
  assert.match(result.stderr, /exactly one Markdown, one HTML, and zero errors with canonical content URLs/)
  assert.doesNotMatch(result.stderr, /22222222|33333333|"items"/)
  assert.doesNotMatch(result.curlLog, /^GET .*\/api\/v1\/documents\//m)
})

test('Aliyun deploy entrypoint is syntactically valid and exposes a safe dry run', async () => {
  const deployer = await read('scripts/deploy-aliyun-ecs.sh')
  const syntax = await execFileAsync('bash', ['-n', 'scripts/deploy-aliyun-ecs.sh'], {
    cwd: repositoryRoot,
  })
  const dryRun = await execFileAsync('bash', ['scripts/deploy-aliyun-ecs.sh', '--dry-run'], {
    cwd: repositoryRoot,
  })

  assert.equal(syntax.stderr, '')
  for (const contract of [
    /ControlMaster=auto/,
    /make -C "\$ROOT" check/,
    /company-backup/,
    /rsync -az --delete/,
    /build-ecs-image-bundle\.sh/,
    /sha256sum -c/,
    /load-ecs-image-bundle\.sh/,
    /SESSION_COOKIE_SECURE=true/,
    /systemctl reload nginx/,
    /write_status.*401/s,
  ]) assert.match(deployer, contract)
  assert.match(dryRun.stdout, /构建 linux\/amd64 离线镜像包/)
  assert.match(dryRun.stdout, /更新宿主机 Nginx/)
  assert.doesNotMatch(deployer, /114\.55\.141\.118/)
  assert.doesNotMatch(deployer, /ADMIN_PASSWORD_HASH='\$argon2/)
})

test('production deployment preserves community secrets and creates one persistent signing key', async () => {
  const deployer = await read('scripts/deploy-aliyun-ecs.sh')

  assert.match(deployer, /USER_TOKEN_SIGNING_KEY/)
  assert.match(deployer, /secrets\.token_urlsafe\(32\)/)
  assert.match(deployer, /USER_REGISTRATION_ENABLED=false/)
  assert.match(deployer, /COMMENT_WRITES_ENABLED=true/)
  assert.doesNotMatch(deployer, /(?:echo|printf)[^\n]*USER_TOKEN_SIGNING_KEY[^\n]*\$/)
  assert.doesNotMatch(deployer, /SMTP_PASSWORD=/)
})

test('production Nginx rate limits each public community write boundary by IP', async () => {
  const nginx = stripLineComments(await read('infra/aliyun-ecs/nginx.conf'))

  assert.match(nginx, /limit_req_status\s+429\s*;/)
  for (const zone of ['user_auth', 'user_session', 'user_register', 'user_reset', 'comment_write', 'comment_report']) {
    assert.match(nginx, new RegExp(`limit_req_zone[^;]+zone=${zone}:`), `missing ${zone} IP zone`)
    assert.match(nginx, new RegExp(`limit_req\\s+zone=${zone}\\b`), `unused ${zone} IP zone`)
  }
  for (const route of [
    '= /api/v1/user-auth/session',
    '= /api/v1/user-auth/register',
    '= /api/v1/user-auth/login',
    '= /api/v1/user-auth/password-reset/request',
    '= /api/v1/user-auth/password-reset/confirm',
  ]) assert.ok(nginx.includes(`location ${route}`), `missing precise Nginx location: ${route}`)
  assert.match(nginx, /location\s+~\s+\^\/api\/v1\/documents\/[^\n]+\/comments\$/)
  assert.match(nginx, /location\s+~\s+\^\/api\/v1\/comments\/[^\n]+\/reports\$/)
  assert.match(nginx, /location\s+\/api\/\s*\{/)
  assert.doesNotMatch(nginx, /location\s+\^~\s+\/api\//)
})

test('bootstrap and Compose smoke keep public writes and test email capture contained', async () => {
  const bootstrap = await read('infra/aliyun-ecs/nginx-bootstrap.conf')
  const smoke = await read('scripts/compose-smoke.sh')

  assert.match(bootstrap, /location \^~ \/api\/[\s\S]*limit_except GET HEAD OPTIONS[\s\S]*deny all/)
  assert.match(smoke, /APP_ENVIRONMENT=test/)
  assert.match(smoke, /EMAIL_BACKEND=file/)
  assert.match(smoke, /EMAIL_CAPTURE_PATH=/)
  assert.match(smoke, /USER_REGISTRATION_ENABLED=true/)
  assert.match(smoke, /USER_COOKIE_FILE/)
  assert.match(smoke, /SECOND_USER_COOKIE_FILE/)
  assert.match(smoke, /user-auth\/register/)
  assert.match(smoke, /user-auth\/verify-email/)
  assert.match(smoke, /admin\/comments\/\$comment_id\/approve/)
  assert.match(smoke, /users\/me\/notifications/)
  assert.match(smoke, /DELETE FROM users WHERE normalized_email/)
  assert.match(smoke, /rm -f[^\n]*EMAIL_CAPTURE_PATH/)
})

test('documents every quality command and concrete setup recovery steps', async () => {
  const readme = await read('README.md')
  const quality = markdownSection(readme, '质量检查')
  for (const command of [
    'node --test tests/docs.test.mjs tests/prototype.test.mjs tests/scaffold.test.mjs',
    'corepack pnpm --filter @company/web check',
    'corepack pnpm --filter @company/admin check',
    'cd apps/api && uv run ruff check .',
    'cd apps/api && uv run ruff format --check .',
    'cd apps/api && uv run mypy src',
    'cd apps/api && uv run pytest',
  ]) assert.ok(quality.includes(command), `quality section must expose ${command}`)

  const troubleshooting = markdownSection(readme, '常见问题')
  assert.match(troubleshooting, /### frozen lockfile 不一致/)
  assert.match(troubleshooting, /corepack pnpm install --frozen-lockfile/)
  assert.match(troubleshooting, /uv sync --frozen/)
  assert.match(troubleshooting, /### Docker daemon 未启动/)
  assert.match(troubleshooting, /docker info/)
})
