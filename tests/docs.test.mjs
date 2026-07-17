import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
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

test('superseded current documents are removed', () => {
  for (const name of retiredCurrentDocs) {
    assert.equal(existsSync(currentDocUrl(name)), false, `retired document remains: doc/${name}`);
  }
});

test('deployment targets Aliyun with persistent HTML content', () => {
  const markdown = readCurrentDoc('DEPLOYMENT.md');
  for (const phrase of ['Docker Compose', 'Nginx', '阿里云', 'www.ayaseeri.com', 'HTTPS', 'HTML 内容卷', '备份', '回滚']) {
    assert.match(markdown, new RegExp(phrase));
  }
  assert.doesNotMatch(markdown, /Markdown 正文|恢复.*Markdown|content\/inbox/);
  assert.match(markdown, /维护模式.+阻断并排空所有会修改索引或 HTML 内容卷的操作/s);
  assert.match(markdown, /删除并重新创建空数据库/);
  assert.equal(existsSync(currentDocUrl('DOCKER.md')), false, 'retired doc/DOCKER.md remains');
});

test('SEO indexes standalone published HTML instead of iframe contents', () => {
  const markdown = readCurrentDoc('SEO.md');
  assert.match(markdown, /iframe 外壳.+不能.+索引正文/s);
  assert.match(markdown, /独立 HTML 发布地址/);
  assert.match(markdown, /canonical/);
  assert.match(markdown, /noindex/);
  assert.match(markdown, /sitemap 只包含已发布的独立 HTML/);
  assert.doesNotMatch(markdown, /sitemap[^。]+公开入口页/);
  assert.doesNotMatch(markdown, /完整 Markdown 正文|Markdown 标记/);
});
