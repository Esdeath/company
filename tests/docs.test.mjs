import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
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

function healthRoutes(markdown) {
  return [...new Set(markdown.match(/\/api\/health\/(?:live|ready)/g) || [])].sort();
}

test('current docs define one direct HTML and Markdown upload flow', () => {
  const development = readCurrentDoc('DEVELOPMENT.md');
  const backend = readCurrentDoc('BACKEND.md');
  const productUi = readCurrentDoc('PRODUCT_UI.md');

  assert.match(development, /选择或新建公司[\s\S]+上传[\s\S]+HTML[\s\S]+Markdown[\s\S]+立即公开/);
  assert.match(backend, /source\.md[\s\S]+rendered\.html/);
  assert.match(productUi, /HTML 原文件[\s\S]+Markdown 生成页[\s\S]+同一个 iframe 阅读器/);

  for (const markdown of [development, backend, productUi]) {
    assert.doesNotMatch(markdown, /静态校验|load-check|草稿|已撤回|发布门禁|MD 不进入后端/);
  }
});

test('Markdown template is a supported runtime contract', () => {
  const readme = readCurrentDoc('README.md');
  assert.match(readme, /HTML 和 Markdown 都可以上传/);
  assert.match(readme, /templates\/markdown\/showcase\.html/);
  assert.equal(existsSync(currentDocUrl('templates/markdown/template.css')), true);
});

test('direct-upload docs keep the approved design and authenticated boundary visible', () => {
  const development = readCurrentDoc('DEVELOPMENT.md');
  const design = readCurrentDoc('specs/2026-07-18-direct-document-upload-design.md');

  assert.match(development, /Skill 或人工资料 → 管理员选择公司 → 上传 HTML\/Markdown → 按文件保存并建立索引 → 立即公开阅读/);
  assert.match(development, /\[资料直接上传与 Markdown 渲染设计\]\(\.\/specs\/2026-07-18-direct-document-upload-design\.md\)/);
  assert.match(development, /写入接口只接受已登录管理员/);
  assert.match(development, /`X-CSRF-Token`/);
  assert.match(development, /SESSION_COOKIE_SECURE=true/);
  assert.match(design, /状态：已确认/);
});

test('backend defines file storage and per-file failure behavior', () => {
  const backend = readCurrentDoc('BACKEND.md');

  for (const rule of [
    'HTML 保存为 `source.html`，内容响应直接返回该文件。',
    'Markdown 保存为 `source.md`，上传时生成 `rendered.html`，内容响应返回生成文件。',
    '数据库保存公司和资料索引，不保存文件正文。',
    '系统只按扩展名分流，并处理读取、渲染、写入和数据库错误。',
    '批量上传按文件提交；一个文件失败不撤销同批次中已完成的文件。'
  ]) {
    assert.ok(backend.includes(rule), `missing backend rule: ${rule}`);
  }
});

test('direct-upload contract commits each UUID file set before exposing its index', () => {
  const backend = readCurrentDoc('BACKEND.md');
  const design = readCurrentDoc('specs/2026-07-18-direct-document-upload-design.md');

  for (const markdown of [backend, design]) {
    assert.match(markdown, /`company-id` 和 `document-id` 都使用 UUID/);
    assert.match(markdown, /在 staging 准备 `source\.html` 或 `source\.md`，并为 Markdown 准备 `rendered\.html`/);
    assert.match(markdown, /原子移动到 UUID 最终目录/);
    assert.match(markdown, /最终文件存在后才提交资料索引/);
    assert.match(markdown, /数据库提交失败时删除或补偿最终文件/);
    assert.match(markdown, /公开读取只在文件系统和数据库工作都完成后开始/);
  }
});

test('title fallback uses the extensionless original filename stem everywhere', () => {
  const backend = readCurrentDoc('BACKEND.md');
  const design = readCurrentDoc('specs/2026-07-18-direct-document-upload-design.md');
  const seo = readCurrentDoc('SEO.md');

  for (const markdown of [backend, design, seo]) {
    assert.match(markdown, /原始文件名去掉扩展名后的文件名主体/);
  }
});

test('Markdown template documentation defines the inline styles placeholder', () => {
  const templateReadme = readCurrentDoc('templates/markdown/README.md');

  assert.match(templateReadme, /使用四个占位符/);
  assert.match(templateReadme, /`\{\{ document_styles \}\}`/);
  assert.match(templateReadme, /生成的 HTML 内联已批准的 CSS/);
});

test('product UI keeps one sandboxed reader and the mobile company drawer', () => {
  const productUi = readCurrentDoc('PRODUCT_UI.md');

  for (const phrase of ['公司选择', '多文件上传', '逐文件结果', '立即可见', '资料列表', 'iframe', 'sandbox', '移动端公司抽屉']) {
    assert.match(productUi, new RegExp(phrase));
  }
  assert.match(productUi, /<iframe sandbox><\/iframe>/);
});

test('current docs report the completed slice without claiming deferred interactions', () => {
  const readme = readCurrentDoc('README.md');
  const productUi = readCurrentDoc('PRODUCT_UI.md');

  assert.match(readme, /直接资料上传垂直切片已经完成/);
  assert.match(readme, /管理员认证里程碑已经实现/);
  assert.match(readme, /Argon2[\s\S]+HttpOnly[\s\S]+CSRF/);
  for (const phrase of [
    '选择既有公司或新建公司',
    '多文件选择器',
    '逐文件最终结果',
    '空 `sandbox` iframe',
    '移动端公司抽屉',
  ]) {
    assert.ok(productUi.includes(phrase), `missing implemented UI behavior: ${phrase}`);
  }
  for (const deferredClaim of [
    /目录支持公司名称、证券代码和市场筛选/,
    /把文件拖入上传区/,
    /逐文件显示进度/,
    /成功结果显示[^。]+打开阅读器的操作/,
  ]) {
    assert.doesNotMatch(productUi, deferredClaim);
  }
});

test('backend and deployment retain unversioned infrastructure health routes', () => {
  const backend = readCurrentDoc('BACKEND.md');
  const deployment = readCurrentDoc('DEPLOYMENT.md');

  assert.deepEqual(healthRoutes(backend), ['/api/health/live', '/api/health/ready']);
  assert.deepEqual(healthRoutes(deployment), healthRoutes(backend));
  assert.match(backend, /除 `\/api\/health\/live` 与 `\/api\/health\/ready` 外，所有业务 API 都使用 `\/api\/v1` 前缀/);
  assert.match(deployment, /`\/api\/health\/live` 与 `\/api\/health\/ready` 是唯一不版本化的基础设施例外/);
});

test('deployment keeps the Aliyun and private-network boundary', () => {
  const deployment = readCurrentDoc('DEPLOYMENT.md');

  assert.match(deployment, /阿里云 ECS/);
  assert.match(deployment, /宿主机 Nginx 是唯一公网入口/);
  assert.match(deployment, /edge Nginx 是唯一面向宿主机的容器/);
  assert.match(deployment, /PostgreSQL 不加入 `edge`/);
  assert.match(deployment, /不得开放 3000、8000、8080、5432/);
  assert.match(deployment, /https:\/\/www\.ayaseeri\.com\/admin\//);
  assert.match(deployment, /SESSION_COOKIE_SECURE=true/);
  assert.doesNotMatch(deployment, /SSH -L 18080:127\.0\.0\.1:8080/);
  assert.doesNotMatch(deployment, /load-check|草稿|已撤回|发布门禁/);
});

test('repository records the verified Aliyun deployment assets without secrets', () => {
  const root = new URL('../', import.meta.url);
  const paths = [
    'infra/aliyun-ecs/nginx-bootstrap.conf',
    'infra/aliyun-ecs/nginx.conf',
    'infra/aliyun-ecs/systemd/nginx.service',
    'infra/aliyun-ecs/systemd/company-backup.service',
    'infra/aliyun-ecs/systemd/company-backup.timer',
    'infra/aliyun-ecs/letsencrypt/reload-nginx.sh',
    'scripts/build-ecs-image-bundle.sh',
    'scripts/load-ecs-image-bundle.sh',
    'scripts/company-backup.sh',
    'scripts/hash-admin-password.sh',
    'scripts/deploy-aliyun-ecs.sh',
  ];

  for (const path of paths) {
    assert.equal(existsSync(new URL(path, root)), true, `missing deployment asset: ${path}`);
  }

  const nginx = readFileSync(new URL('infra/aliyun-ecs/nginx.conf', root), 'utf8');
  assert.match(nginx, /location \^~ \/admin\/\s*\{[\s\S]*proxy_pass http:\/\/127\.0\.0\.1:8080/);
  assert.match(nginx, /location = \/api\/v1\/auth\/login/);
  assert.match(nginx, /limit_req zone=admin_login/);
  assert.match(nginx, /location = \/api\/v1\/auth\/session/);
  assert.match(nginx, /limit_req zone=admin_session/);
  assert.doesNotMatch(nginx, /limit_except GET HEAD OPTIONS/);
  assert.match(nginx, /proxy_pass http:\/\/127\.0\.0\.1:8080/);
  assert.match(nginx, /\/etc\/letsencrypt\/live\/ayaseeri\.com\/fullchain\.pem/);

  const bootstrap = readFileSync(new URL('infra/aliyun-ecs/nginx-bootstrap.conf', root), 'utf8');
  assert.match(bootstrap, /location \^~ \/admin\/\s*\{\s*return 404;/);
  assert.match(bootstrap, /limit_except GET HEAD OPTIONS/);

  const backup = readFileSync(new URL('scripts/company-backup.sh', root), 'utf8');
  assert.match(backup, /pg_dump/);
  assert.match(backup, /company-research-library_content_data/);
  assert.match(backup, /sha256sum postgres\.dump content\.tar\.gz/);

  const loader = readFileSync(new URL('scripts/load-ecs-image-bundle.sh', root), 'utf8');
  assert.match(loader, /--no-build --pull never/);
  assert.match(loader, /--connect-timeout 2 --max-time 5/);

  const deployer = readFileSync(new URL('scripts/deploy-aliyun-ecs.sh', root), 'utf8');
  assert.match(deployer, /company-backup/);
  assert.match(deployer, /build-ecs-image-bundle\.sh/);
  assert.match(deployer, /load-ecs-image-bundle\.sh/);
  assert.match(deployer, /ADMIN_PASSWORD_HASH/);
  assert.match(deployer, /nginx[^\n]+-t/);
  assert.match(deployer, /authenticated/);

  const combined = paths
    .map((path) => readFileSync(new URL(path, root), 'utf8'))
    .join('\n');
  assert.doesNotMatch(combined, /114\.55\.141\.118/);
  assert.doesNotMatch(combined, /POSTGRES_PASSWORD=[A-Fa-f0-9]{16,}/);
});

test('SEO indexes document content without retired publication states', () => {
  const seo = readCurrentDoc('SEO.md');

  assert.match(seo, /已建立索引的资料内容/);
  assert.match(seo, /HTML 原文件和 Markdown 生成页/);
  assert.match(seo, /Disallow: \/admin\//);
  assert.match(seo, /Disallow: \/api\//);
  assert.doesNotMatch(seo, /静态校验|load-check|草稿|已撤回|发布门禁/);
});
