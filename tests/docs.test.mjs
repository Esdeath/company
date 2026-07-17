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
