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

test('superseded current documents are removed', () => {
  for (const name of retiredCurrentDocs) {
    assert.equal(existsSync(currentDocUrl(name)), false, `retired document remains: doc/${name}`);
  }
});
