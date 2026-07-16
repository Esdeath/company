import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const prototypePath = new URL('../doc/prototype.html', import.meta.url);

function readPrototype() {
  return readFileSync(prototypePath, 'utf8');
}

function inlineScript(html) {
  const matches = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  return matches.map((match) => match[1]).join('\n');
}

function embeddedJson(html, id) {
  const pattern = new RegExp(`<script type="application/json" id="${id}">([\\s\\S]*?)<\\/script>`);
  const match = html.match(pattern);
  assert.ok(match, `missing embedded JSON ${id}`);
  return JSON.parse(match[1]);
}

function assertAlignedTable(table, expectedYearCount) {
  assert.equal(table.years.length, expectedYearCount);
  for (const row of table.rows) {
    assert.equal(row.values.length, expectedYearCount, `${row.label} is not aligned`);
  }
}

test('prototype is a standalone HTML document', () => {
  const html = readPrototype();
  assert.match(html, /^<!doctype html>/i);
  assert.match(html, /id="app"/);
  assert.match(html, /window\.prototypeApp/);
  assert.doesNotMatch(html, /<(?:script|img)[^>]+src=["']https?:\/\//i);
  assert.doesNotMatch(html, /<link[^>]+href=["']https?:\/\//i);
  assert.doesNotMatch(html, /@import\s+url\(["']?https?:\/\//i);
  assert.doesNotThrow(() => new Function(inlineScript(html)));
});

test('prototype contains the complete public research flow', () => {
  const html = readPrototype();
  for (const required of [
    'data-route="home"',
    'data-route="snapshot"',
    'data-action="search"',
    'data-action="market"',
    'data-action="sort"',
    'data-action="open-snapshot"',
    'data-action="select-version"',
    'data-action="toggle-toc"',
    '事实',
    '判断',
    '待验证',
    '快照扫描轨'
  ]) assert.ok(html.includes(required), `missing ${required}`);
});

test('prototype contains the complete administrator workflow', () => {
  const html = readPrototype();
  for (const required of [
    'data-route="login"',
    'data-route="admin-list"',
    'data-route="review"',
    'data-action="login"',
    'data-action="simulate-upload"',
    'data-action="scan-inbox"',
    'data-action="review-snapshot"',
    'data-action="publish"',
    'data-action="confirm-dialog"',
    'demo123',
    '校验错误',
    '校验警告'
  ]) assert.ok(html.includes(required), `missing ${required}`);
});

test('prototype exposes responsive and accessibility contracts', () => {
  const html = readPrototype();
  for (const required of [
    'lang="zh-CN"',
    'name="viewport"',
    'data-action="viewport"',
    'role="dialog"',
    'aria-modal="true"',
    'aria-live="polite"',
    '@media (max-width: 767px)',
    '@media (prefers-reduced-motion: reduce)'
  ]) assert.ok(html.includes(required), `missing ${required}`);
});

test('dialog focus returns to the re-rendered action control', () => {
  const html = readPrototype();
  assert.match(html, /lastDialogAction/);
  assert.match(html, /data-action="\$\{lastDialogAction\}"/);
});

test('Moutai payload preserves the Skill facts and aligned history', () => {
  const data = embeddedJson(readPrototype(), 'maotai-snapshot-data');
  assert.equal(data.format, 'value_line');
  assert.equal(data.companyName, '贵州茅台');
  assert.equal(data.ticker, '600519');
  assert.equal(data.quoteAsOf, '2026-07-15 12:05');
  assert.deepEqual(
    data.marketMetrics.map((metric) => metric.value),
    ['¥1,244.97', '18.82×', '5.76×', '4.2%', '¥15,563.14亿元']
  );
  assertAlignedTable(data.perShareHistory, 25);
  assertAlignedTable(data.operatingHistory, 26);
  assert.equal(data.scanChecks.length, 5);
  assert.equal(data.fiveQuestions.length, 5);
});

test('Moutai detail exposes every value-line research module', () => {
  const html = readPrototype();
  for (const required of [
    'renderValueLineSnapshot',
    'renderValueTable',
    'data-value-section="quick-conclusion"',
    'data-value-section="business-model"',
    'data-value-section="per-share-history"',
    'data-value-section="operating-history"',
    'data-value-section="mental-math"',
    'data-value-section="capital-structure"',
    'data-value-section="five-questions"',
    'data-value-section="methodology"',
    'data-action="table-earliest"',
    'data-action="table-latest"'
  ]) assert.ok(html.includes(required), `missing ${required}`);
});

test('Moutai is clean and published while the invalid demo stays admin-only', () => {
  const html = readPrototype();
  assert.match(html, /id: 'published-maotai'[\s\S]*status: 'published'[\s\S]*report: 'clean'/);
  assert.match(html, /id: 'demo-invalid'[\s\S]*companyName: '格式错误示例'[\s\S]*report: 'error'/);
  assert.match(html, /renderReviewSnapshotContent/);
  const data = embeddedJson(html, 'maotai-snapshot-data');
  assert.equal(data.summary.includes('2025年营收和利润转为负增长'), true);
});

test('value-line tables preserve readable mobile behavior', () => {
  const html = readPrototype();
  for (const required of [
    '.value-table-scroll',
    'overflow: auto',
    'position: sticky',
    '.prototype-stage.is-mobile .value-metrics',
    '.prototype-stage.is-mobile .value-duo',
    '@media (max-width: 767px)'
  ]) assert.ok(html.includes(required), `missing ${required}`);
});

test('value-line grid children cannot widen the mobile stage', () => {
  const html = readPrototype();
  assert.match(html, /\.value-duo > \* \{ min-width: 0; \}/);
  assert.match(html, /\.value-section \{[^}]*min-width: 0;/s);
});
