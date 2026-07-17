import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const docDirectory = new URL('../doc/', import.meta.url);

function currentDocUrl(name) {
  return new URL(name, docDirectory);
}

function readCurrentDoc(name) {
  const url = currentDocUrl(name);
  assert.equal(existsSync(url), true, `missing current document: doc/${name}`);
  return readFileSync(url, 'utf8');
}

function h2Headings(markdown) {
  return [...markdown.matchAll(/^## (.+)$/gm)].map(([, heading]) => heading);
}

function h2Section(markdown, heading) {
  const marker = `## ${heading}`;
  const start = markdown.indexOf(marker);
  assert.notEqual(start, -1, `missing section: ${marker}`);
  const next = markdown.indexOf('\n## ', start + marker.length);
  return markdown.slice(start, next === -1 ? markdown.length : next);
}

function assertRestoreUsesSameBackupId(backupSection) {
  assert.match(
    backupSection,
    /pg_restore[^\n]+\n\s+< "\/srv\/company\/backups\/\$BACKUP_ID\.postgres\.dump"/
  );
  assert.match(
    backupSection,
    /tar -C \/srv\/company\/data -xzf "\/srv\/company\/backups\/\$BACKUP_ID\.html\.tar\.gz"/
  );
}

function assertSeoRobotsRules(robotsSection, indexableSection, privatePagesSection) {
  for (const path of ['/admin/', '/api/', '/preview/']) {
    assert.match(robotsSection, new RegExp(`^Disallow: ${path.replaceAll('/', '\\/')}$`, 'm'));
  }
  assert.match(robotsSection, /robots\.txt 只是抓取提示/);
  assert.match(indexableSection, /\| 草稿、撤回、无效内容 \| `noindex,nofollow` 且不公开 \| 公开请求返回 404 或 410 \|/);
  assert.match(privatePagesSection, /静态校验失败、可信加载检查失败或元数据无效的记录不得发布，公开请求返回 404/);
}

function healthRoutes(markdown) {
  return [...new Set(markdown.match(/\/api\/health\/(?:live|ready)/g) || [])].sort();
}

function assertInfrastructureHealthContract(backend, deployment) {
  assert.deepEqual(healthRoutes(backend), ['/api/health/live', '/api/health/ready']);
  assert.deepEqual(healthRoutes(deployment), healthRoutes(backend));
  assert.match(backend, /除 `\/api\/health\/live` 与 `\/api\/health\/ready` 外，所有业务 API 都使用 `\/api\/v1` 前缀/);
  assert.match(backend, /这两个基础设施端点是唯一不版本化例外，不要求管理员认证，只返回最小状态且不泄露内部信息/);
  assert.match(deployment, /`\/api\/health\/live` 与 `\/api\/health\/ready` 是唯一不版本化的基础设施例外/);
  assert.match(deployment, /不要求管理员认证，只返回最小状态且不泄露内部信息/);
}

function assertAuthoritativePublicationGate(productUi, backend) {
  const reading = h2Section(productUi, 'HTML 阅读区');
  const review = h2Section(productUi, '审核、预览与发布');
  const managementApi = h2Section(backend, '管理 API');
  const transaction = h2Section(backend, '发布与撤回事务');

  assert.match(reading, /管理员浏览器本地 `HEAD` 与 iframe `load` 只控制本地预览的 loading\/error UI/);
  assert.match(reading, /本地失败继续禁用发布按钮，并触发和显示本地错误状态；本地成功绝不能解锁发布/);
  assert.match(review, /管理端触发可信 load-check 后只轮询权威结果，不提交或决定 `passed`/);
  assert.match(review, /发布按钮与 publish API 必须等待当前 `record id`、`version`、`content_sha256`、`nonce` 对应的权威 checker 结果为 `passed`/);
  assert.match(managementApi, /load-check 的 POST 只触发可信检查任务，不接受状态字段；GET 只供管理端轮询/);
  assert.match(transaction, /发布 API[^。]+当前 `record id`、`version`、`content_sha256` 与 `nonce`[^。]+可信 load-check[^。]+`passed`/);
  assert.doesNotMatch(productUi, /本地成功(?:可以|可|会|将)[^。；]*(?:解锁|启用|恢复)[^。；]*发布/);
}

function assertRateLimitAndQueueContract(backend) {
  const section = h2Section(backend, '限流与任务队列');
  assert.match(section, /登录按 IP：15 分钟最多 10 次/);
  assert.match(section, /公开列表与详情按 IP：每分钟最多 120 次/);
  assert.match(section, /上传与扫描合并按管理员：每分钟最多 20 次/);
  assert.match(section, /load-check 触发按管理员：每分钟最多 6 次/);
  assert.match(section, /每个快照最多 1 个 `queued` 或 `running` 任务/);
  assert.match(section, /每个管理员最多 2 个 `queued` 或 `running` 任务/);
  assert.match(section, /全局最多 4 个并发 headless Chromium/);
  assert.match(section, /等待队列最多 100 个任务/);
  assert.match(section, /重复触发返回现有 task id 或已保存的幂等结果，不重复排队或占用新容量；新任务超出限流或遇到队列已满时返回 429，并设置 `Retry-After`/);
  assert.match(section, /单机内存计数只允许首版单进程部署；横向扩展必须改用共享限流存储与共享任务队列/);
}

test('README is the current documentation entry point', () => {
  const markdown = readCurrentDoc('README.md');
  assert.match(markdown, /^# 企业快照库文档/m);
  assert.match(markdown, /HTML 是网站唯一发布物/);
  assert.match(markdown, /MD.+审计.+重新生成/s);
  assert.match(markdown, /prototype\.html/);
  assert.match(markdown, /DEVELOPMENT\.md/);
  assert.match(markdown, /PRODUCT_UI\.md/);
  assert.match(markdown, /BACKEND\.md/);
  assert.match(markdown, /DEPLOYMENT\.md/);
  assert.match(markdown, /SEO\.md/);
});

test('DEVELOPMENT describes one HTML publication mainline', () => {
  const markdown = readCurrentDoc('DEVELOPMENT.md');
  assert.match(markdown, /^# 企业快照库开发总纲/m);
  assert.match(markdown, /Skill[\s\S]+HTML[\s\S]+校验[\s\S]+审核[\s\S]+发布/);
  assert.match(markdown, /MD.+不参与网站运行/s);
  for (const term of ['Vue', 'Nuxt', 'Vite', 'TypeScript', 'FastAPI', 'PostgreSQL', 'Nginx', 'Docker']) {
    assert.match(markdown, new RegExp(term));
  }
  assert.doesNotMatch(markdown, /上传 Markdown|扫描 `?content\/inbox|Markdown 是.+唯一事实来源/);
});

test('DEVELOPMENT document map uses clickable relative links', () => {
  const map = h2Section(readCurrentDoc('DEVELOPMENT.md'), '文档地图');
  for (const name of ['PRODUCT_UI.md', 'BACKEND.md', 'DEPLOYMENT.md', 'SEO.md']) {
    assert.match(map, new RegExp(`\\[${name.replace('.', '\\.')}\\]\\(\\./${name.replace('.', '\\.')}\\)`));
  }
});

const retiredCurrentDocs = [
  'PAGE_MAIN.md',
  'PAGE_SEARCH.md',
  'PAGE_SNAPSHOT.md',
  'PAGE_ADMIN.md',
  'API_DESIGN.md',
  'DATABASE_DESIGN.md',
  'MARKDOWN_SPEC.md'
];

test('product UI has one public and administrator interaction contract', () => {
  const markdown = readCurrentDoc('PRODUCT_UI.md');
  for (const phrase of ['公司目录', 'HTML 阅读', '移动端', '抽屉', '登录', '上传', '审核', '发布', '撤回', 'sandbox']) {
    assert.match(markdown, new RegExp(phrase));
  }
  assert.doesNotMatch(markdown, /MarkdownPreview|上传 Markdown|Markdown 正文/);
});

test('backend contract indexes HTML without storing its body', () => {
  const markdown = readCurrentDoc('BACKEND.md');
  for (const phrase of ['FastAPI', 'PostgreSQL', 'SHA-256', '草稿', '已发布', '已撤回', '审计', 'OpenAPI']) {
    assert.match(markdown, new RegExp(phrase));
  }
  assert.match(markdown, /不保存 HTML 正文/);
  assert.match(markdown, /MD 不进入后端/);
  assert.doesNotMatch(markdown, /上传 Markdown|scan-inbox|解析 Markdown/);
});

test('backend defines the complete administrator authentication API', () => {
  const markdown = readCurrentDoc('BACKEND.md');
  for (const route of [
    '/api/v1/auth/login',
    '/api/v1/auth/me',
    '/api/v1/auth/logout',
    '/api/v1/auth/change-password'
  ]) {
    assert.ok(markdown.includes(route), `missing authentication route: ${route}`);
  }
});

test('backend login bootstraps session CSRF through same-origin JSON only', () => {
  const markdown = readCurrentDoc('BACKEND.md');
  for (const phrase of [
    '登录请求不要求 Session CSRF Token',
    'application/json',
    'Origin',
    'Referer',
    '同源',
    '登录限流',
    '失败审计',
    'HttpOnly; Secure; SameSite=Strict',
    '所有非 GET 管理请求'
  ]) {
    assert.match(markdown, new RegExp(phrase));
  }
  assert.match(markdown, /POST \/api\/v1\/auth\/login[\s\S]+登录请求不要求 Session CSRF Token[\s\S]+application\/json/);
  assert.match(markdown, /Origin[\s\S]+缺失[\s\S]+Referer[\s\S]+同源/);
  assert.match(markdown, /登录限流[\s\S]+失败审计[\s\S]+HttpOnly; Secure; SameSite=Strict[\s\S]+CSRF Token/);
  assert.match(markdown, /logout[\s\S]+change-password[\s\S]+所有非 GET 管理请求[\s\S]+Session CSRF/);
});

test('backend assigns authoritative load-check to a trusted internal checker', () => {
  const markdown = readCurrentDoc('BACKEND.md');
  for (const phrase of [
    '管理员客户端不得',
    'passed',
    '可信 load-checker',
    '内部认证',
    'headless Chromium',
    'sandboxed iframe',
    'record id',
    'version',
    'content_sha256',
    'nonce',
    '行锁'
  ]) {
    assert.match(markdown, new RegExp(phrase));
  }
  assert.match(markdown, /静态校验[\s\S]+clean[\s\S]+record id[\s\S]+version[\s\S]+content_sha256[\s\S]+nonce[\s\S]+受控预览 URL/);
  assert.match(markdown, /可信 load-checker[\s\S]+内部认证[\s\S]+HEAD[\s\S]+headless Chromium[\s\S]+sandboxed iframe[\s\S]+load[\s\S]+error[\s\S]+timeout/);
  assert.match(markdown, /管理员客户端不得[\s\S]+passed/);
  assert.match(markdown, /行锁[\s\S]+content_sha256[\s\S]+version[\s\S]+nonce[\s\S]+可信 load-check[\s\S]+passed/);
  assert.doesNotMatch(markdown, /客户端调用[^。]+load-check[^。]+回报 `passed`/);
});

test('backend and deployment share the unversioned infrastructure health exception', () => {
  const backend = readCurrentDoc('BACKEND.md');
  const deployment = readCurrentDoc('DEPLOYMENT.md');
  assertInfrastructureHealthContract(backend, deployment);

  const mismatchedDeployment = deployment.replaceAll('/api/health/live', '/api/v1/health/live');
  assert.notEqual(mismatchedDeployment, deployment, 'health-route mutation was not applied');
  assert.throws(
    () => assertInfrastructureHealthContract(backend, mismatchedDeployment),
    /api\/health\/live|deep-equal/
  );
});

test('product UI local preview cannot bypass the backend authoritative publication gate', () => {
  const productUi = readCurrentDoc('PRODUCT_UI.md');
  const backend = readCurrentDoc('BACKEND.md');
  assertAuthoritativePublicationGate(productUi, backend);

  const unsafeUi = productUi.replace('本地成功绝不能解锁发布', '本地成功可以解锁发布');
  assert.notEqual(unsafeUi, productUi, 'local-success gate mutation was not applied');
  assert.throws(() => assertAuthoritativePublicationGate(unsafeUi, backend), /本地成功/);
});

test('backend defines concrete rate limits and bounded load-check queues', () => {
  assertRateLimitAndQueueContract(readCurrentDoc('BACKEND.md'));
});

test('superseded current documents are removed', () => {
  for (const name of retiredCurrentDocs) {
    assert.equal(existsSync(currentDocUrl(name)), false, `retired document remains: doc/${name}`);
  }
});

test('deployment targets Aliyun with persistent HTML content', () => {
  const markdown = readCurrentDoc('DEPLOYMENT.md');
  assert.deepEqual(h2Headings(markdown), [
    '当前状态与目标',
    '服务组成',
    'Docker Compose',
    '本地开发',
    '环境变量与密钥',
    '网络与安全组',
    'HTML 内容卷',
    'Nginx 路由与缓存',
    '阿里云 ECS',
    'www.ayaseeri.com 与 HTTPS',
    '首次部署',
    '日常发布与回滚',
    '备份与恢复',
    '健康检查、日志与告警'
  ]);

  const target = h2Section(markdown, '当前状态与目标');
  assert.match(target, /Nginx 是唯一公开容器[^。]+Nuxt 公开端、Vue\/Vite 管理端、FastAPI、可信 load-checker 和 PostgreSQL 全部留在内部网络/);

  const services = h2Section(markdown, '服务组成');
  assert.match(services, /可信 load-checker[^。]+内部认证[^。]+权威加载检查。/);
  assert.match(services, /它没有公网路由，管理员客户端不能写入 `passed` 结果。/);

  const compose = h2Section(markdown, 'Docker Compose');
  assert.match(compose, /容器绝不挂载 Docker socket/);

  const secrets = h2Section(markdown, '环境变量与密钥');
  assert.match(secrets, /TLS 证书与私钥只读挂载给 Nginx，不挂载给其他容器/);

  const content = h2Section(markdown, 'HTML 内容卷');
  assert.match(content, /生产使用独立、持久化的 HTML 内容卷，和仓库内 `doc\/snapshots\/` 示例严格分离/);
  assert.match(content, /只有 FastAPI 能以读写方式挂载完整 HTML 内容卷/);

  const caching = h2Section(markdown, 'Nginx 路由与缓存');
  assert.match(caching, /独立、已发布的 HTML 响应[^。]+`Cache-Control: public, no-cache`[^。]+ETag[^。]+每次请求都必须重验证/);
  assert.match(caching, /撤回事务完成后的下一次请求必须返回 404 或 410/);
  assert.match(caching, /禁止以 `stale-if-error`[^。]+继续返回已撤回正文/);
  assert.match(caching, /`\/admin\/`、`\/api\/`[^。]+使用 `Cache-Control: no-store`，不得进入共享公开缓存/);

  const backup = h2Section(markdown, '备份与恢复');
  assert.match(backup, /维护模式必须阻断并排空所有会修改索引或 HTML 内容卷的操作/);
  assert.match(backup, /pg_dump --format=custom --username="\$POSTGRES_USER" --dbname="\$POSTGRES_DB"/);
  assert.match(backup, /pg_restore --exit-on-error --no-owner --username="\$POSTGRES_USER" --dbname="\$POSTGRES_DB"/);
  assert.match(backup, /> "\/srv\/company\/backups\/\$BACKUP_ID\.postgres\.dump"\ntar[^\n]+"\/srv\/company\/backups\/\$BACKUP_ID\.html\.tar\.gz"/);
  assert.match(backup, /删除并重新创建空数据库，同时清空 HTML 目录/);
  assert.match(backup, /rm -rf \/srv\/company\/data\/html/);
  assert.match(backup, /dropdb[^\n]+--username="\$POSTGRES_USER"[^\n]+\n\s+createdb --username="\$POSTGRES_USER"/);
  assert.match(backup, /恢复后核对索引路径、文件 SHA-256、发布\/撤回状态和审计记录/);
  assertRestoreUsesSameBackupId(backup);

  const mismatchedRestore = backup.replace(
    'tar -C /srv/company/data -xzf "/srv/company/backups/$BACKUP_ID.html.tar.gz"',
    'tar -C /srv/company/data -xzf "/srv/company/backups/$RESTORE_ID.html.tar.gz"'
  );
  assert.notEqual(mismatchedRestore, backup, 'restore mutation was not applied');
  assert.throws(() => assertRestoreUsesSameBackupId(mismatchedRestore), /BACKUP_ID/);

  assert.doesNotMatch(markdown, /Markdown 正文|恢复.*Markdown|content\/inbox/);
  assert.equal(existsSync(currentDocUrl('DOCKER.md')), false, 'retired doc/DOCKER.md remains');
});

test('SEO indexes standalone published HTML instead of iframe contents', () => {
  const markdown = readCurrentDoc('SEO.md');
  assert.deepEqual(h2Headings(markdown), [
    '当前原型限制',
    '可索引页面',
    '独立 HTML 发布地址',
    '工作区与 canonical',
    '元数据',
    'Open Graph 与结构化数据',
    'Sitemap 与 robots',
    '管理端、草稿与撤回',
    '性能与发布检查'
  ]);

  const limitations = h2Section(markdown, '当前原型限制');
  assert.match(limitations, /iframe 外壳可以说明产品、公司目录和阅读入口，但不能让搜索引擎把嵌入的快照文本可靠地当作外壳页面的可索引正文/);

  const standalone = h2Section(markdown, '独立 HTML 发布地址');
  assert.match(standalone, /每条已发布快照获得稳定的独立 HTML 发布地址/);
  assert.match(standalone, /历史地址发布后保持稳定/);
  assert.match(standalone, /最新公司路由[^。]+是便利入口。/);
  assert.match(standalone, /它应 302\/307 到当前最新独立 HTML[^。]+canonical 指向当前版本的独立 HTML。/);

  const canonical = h2Section(markdown, '工作区与 canonical');
  assert.match(canonical, /每个历史独立 HTML 的 canonical 指向自身/);
  assert.match(canonical, /最新公司路由的 canonical 指向当时最新的独立 HTML/);

  const metadata = h2Section(markdown, '元数据');
  assert.match(metadata, /来自已通过校验的 HTML\/index metadata/);
  assert.match(metadata, /不从另一种源文件格式临时解析/);

  const social = h2Section(markdown, 'Open Graph 与结构化数据');
  assert.match(social, /禁止按 User-Agent 返回不同正文，禁止 cloaking 或专供爬虫的页面/);

  const sitemap = h2Section(markdown, 'Sitemap 与 robots');
  assert.match(sitemap, /sitemap 只包含已发布的独立 HTML/);
  assert.match(sitemap, /撤回事务完成后立即移除/);
  assert.doesNotMatch(sitemap, /公开入口页/);

  const indexable = h2Section(markdown, '可索引页面');
  const privatePages = h2Section(markdown, '管理端、草稿与撤回');
  assert.match(privatePages, /管理端页面始终输出 `noindex,nofollow`/);
  assert.match(privatePages, /草稿和受控预览输出 `X-Robots-Tag: noindex, nofollow`/);
  assert.match(privatePages, /撤回事务[^。]+从 sitemap 删除/);
  assert.match(privatePages, /API 响应不是落地页，不进入搜索索引/);
  assertSeoRobotsRules(sitemap, indexable, privatePages);

  const missingPreviewRule = sitemap.replace('Disallow: /preview/\n', '');
  assert.notEqual(missingPreviewRule, sitemap, 'robots mutation was not applied');
  assert.throws(() => assertSeoRobotsRules(missingPreviewRule, indexable, privatePages), /preview/);

  assert.doesNotMatch(markdown, /完整 Markdown 正文|Markdown 标记/);
});

const currentMarkdownDocs = [
  'README.md',
  'DEVELOPMENT.md',
  'PRODUCT_UI.md',
  'BACKEND.md',
  'DEPLOYMENT.md',
  'SEO.md'
];

test('published HTML and audit-only Markdown source pairs exist', () => {
  for (const path of [
    'snapshots/published/贵州茅台.html',
    'snapshots/published/哔哩哔哩.html',
    'snapshots/sources/贵州茅台.md',
    'snapshots/sources/哔哩哔哩.md'
  ]) assert.equal(existsSync(currentDocUrl(path)), true, `missing doc/${path}`);
});

test('current documents do not restore the retired Markdown runtime', () => {
  const combined = currentMarkdownDocs.map(readCurrentDoc).join('\n');
  assert.doesNotMatch(combined, /上传 Markdown|扫描 `?content\/inbox|Markdown 是.+唯一事实来源|网站.+解析 Markdown/s);
  assert.match(combined, /HTML 是网站唯一发布物/);
});

test('relative Markdown links in current documents resolve', () => {
  for (const name of currentMarkdownDocs) {
    const source = readCurrentDoc(name);
    const sourcePath = fileURLToPath(currentDocUrl(name));
    for (const match of source.matchAll(/\[[^\]]+\]\((?!https?:|#)([^)#]+)(?:#[^)]+)?\)/g)) {
      const target = decodeURIComponent(match[1]);
      assert.equal(existsSync(resolve(dirname(sourcePath), target)), true, `broken link in doc/${name}: ${target}`);
    }
  }
});

test('doc root contains only current entry documents and the prototype', () => {
  const rootFiles = readdirSync(docDirectory, { withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .sort();
  assert.deepEqual(rootFiles, [
    'BACKEND.md',
    'DEPLOYMENT.md',
    'DEVELOPMENT.md',
    'PRODUCT_UI.md',
    'README.md',
    'SEO.md',
    'prototype.html'
  ]);
});
