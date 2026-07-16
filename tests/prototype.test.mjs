import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';

const docDirectory = new URL('../doc/', import.meta.url);
const prototypePath = new URL('../doc/prototype.html', import.meta.url);

function readSnapshotAsset(fileName) {
  const url = new URL(fileName, docDirectory);
  assert.equal(existsSync(url), true, `missing ${fileName}`);
  return readFileSync(url, 'utf8');
}

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

test('prototype is a standalone HTML document', () => {
  const html = readPrototype();
  assert.match(html, /^<!doctype html>/i);
  assert.match(html, /id="app"/);
  assert.match(html, /window\.prototypeApp/);
  assert.doesNotMatch(html, /<(?:script|img)[^>]+src=["']https?:\/\//i);
  assert.doesNotMatch(html, /<link[^>]+href=["']https?:\/\//i);
  assert.doesNotMatch(html, /@import\s+url\(["']?https?:\/\//i);
  assert.match(html, /<link rel="icon" href="data:,">/);
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
    'data-action="select-company"',
    'renderSnapshotFrame',
    '企业财报 HTML'
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

test('administrator manages two valid HTML snapshots and one invalid draft', () => {
  const html = readPrototype();
  assert.match(html, /id: 'published-maotai-html'[\s\S]*snapshotId: 'cn-600519-html'[\s\S]*status: 'published'[\s\S]*report: 'clean'/);
  assert.match(html, /id: 'published-bilibili-html'[\s\S]*snapshotId: 'hk-09626-html'[\s\S]*status: 'published'[\s\S]*report: 'clean'/);
  assert.match(html, /id: 'demo-invalid-html'[\s\S]*snapshotId: null[\s\S]*status: 'draft'[\s\S]*report: 'html-error'/);
  assert.doesNotMatch(html, /draft-tencent|published-meituan|id: 'demo-invalid'/);
});

test('administrator copy and preview use the HTML artifact', () => {
  const html = readPrototype();
  for (const required of ['上传 HTML', '使用演示 HTML', 'HTML 文件', '页面标题', 'text/html', '完成 HTML 校验', "renderSnapshotFrame(snapshot, 'review')", 'HTML 校验失败，无法生成预览']) assert.ok(html.includes(required), `missing ${required}`);
  assert.doesNotMatch(html, /上传 Markdown|使用演示 Markdown|完成 Markdown 校验/);
});

test('invalid HTML is blocked with two explicit errors and no iframe', () => {
  const html = readPrototype();
  assert.match(html, /'html-error': \{[\s\S]*errors: \[[\s\S]*HTML 缺少非空 &lt;title&gt;[\s\S]*HTML 包含远程 &lt;script&gt;[\s\S]*warnings: \[\]/);
  assert.match(html, /data-action="publish" \$\{hasErrors \? 'disabled' : ''\}/);
  assert.match(html, /if \(!record\.snapshotId\) return renderInvalidHtmlPreview\(\)/);
});

test('public workspace defaults to Moutai and reconciles selection after filtering', () => {
  const html = readPrototype();
  assert.match(html, /selectedSnapshotId: 'cn-600519-html'/);
  assert.match(html, /companyDrawerOpen: false/);
  assert.match(html, /function selectedPublicSnapshot\(\)/);
  assert.match(html, /function publicSelectionPatch\(patch\)/);
  assert.match(html, /results\.some\(\(snapshot\) => snapshot\.id === nextSelectedId\)/);
  assert.match(html, /nextSelectedId = results\[0\]\?\.id \|\| null/);
});

test('homepage renders a master-detail financial workspace', () => {
  const html = readPrototype();
  for (const required of [
    "class='company-workspace'",
    "aria-label='公司目录'",
    "class='company-directory__scroll'",
    'data-action="select-company"',
    "aria-current='${selected ? 'true' : 'false'}'",
    'renderCompanyDirectory',
    'renderWorkspaceDetail',
    '企业财报 HTML'
  ]) assert.ok(html.includes(required), `missing ${required}`);
  assert.match(html, /grid-template-columns: 320px minmax\(0, 1fr\)/);
  assert.match(html, /\.company-directory__scroll[^}]*overflow-y: auto/s);
});

test('public workspace loads registered HTML through a sandboxed iframe', () => {
  const html = readPrototype();
  for (const required of [
    'function renderSnapshotFrame(snapshot, mode)',
    "class='snapshot-html-frame'",
    "src='${escapeHtml(snapshot.htmlPath)}'",
    "title='${escapeHtml(snapshot.companyName)}企业财报快照'",
    'sandbox',
    'data-frame-load',
    '正在加载 HTML 快照',
    'HTML 快照未能加载，请检查文件路径'
  ]) assert.ok(html.includes(required), `missing ${required}`);
  assert.match(html, /\.snapshot-html-frame \{[^}]*width: 100%;[^}]*height: 100%;/s);
  assert.match(html, /\.snapshot-frame-shell \{[^}]*flex: 1;/s);
  assert.doesNotMatch(html, /sandbox=["'][^"']+/, 'iframe sandbox must have no allowances');
});

test('standalone snapshot iframe has a definite height chain', () => {
  const html = readPrototype();
  const shellRule = html.match(/\.snapshot-frame-shell--standalone\s*\{([^}]*)\}/s);
  assert.ok(shellRule, 'missing standalone snapshot shell rule');
  assert.match(
    shellRule[1],
    /(?:^|;)\s*height:\s*calc\(100dvh\s*-\s*150px\);/,
    'standalone shell needs a definite height for its 100%-height iframe'
  );
  const frameRule = html.match(/\.snapshot-frame-shell--standalone\s+\.snapshot-html-frame\s*\{([^}]*)\}/s);
  assert.ok(frameRule, 'standalone iframe needs its own definite-height rule');
  assert.match(frameRule[1], /height:\s*calc\(100dvh\s*-\s*150px\);/);
});

test('HTTP snapshot loading requires a successful HEAD check and iframe load', () => {
  const html = readPrototype();
  for (const required of [
    'function preflightSnapshotFrame(frame)',
    "fetch(frame.src, { method: 'HEAD'",
    'response.ok',
    "frame.dataset.frameHttpStatus = 'ok'",
    "frame.dataset.frameLoadStatus = 'loaded'",
    "window.location.protocol === 'file:'",
    "frame.dataset.frameHttpStatus === 'ok' && frame.dataset.frameLoadStatus === 'loaded'"
  ]) assert.ok(html.includes(required), `missing ${required}`);
  assert.match(html, /if \(!response\.ok\)[^\n]*throw new Error/);
});

test('public company cards contain identity metadata but no copied financial metrics', () => {
  const html = readPrototype();
  assert.match(html, /HTML 快照/);
  assert.match(html, /已发布/);
  assert.doesNotMatch(html, /function metricItems\(/);
  assert.doesNotMatch(html, /class='mini-metrics'/);
  assert.doesNotMatch(html, /class='verdict(?:\s|')/);
});

test('mobile company drawer has complete dismissal and focus contracts', () => {
  const html = readPrototype();
  for (const required of [
    'data-action="open-company-drawer"',
    'data-action="close-company-drawer"',
    "role='dialog' aria-modal='true'",
    'data-drawer-initial',
    'function openCompanyDrawer()',
    'function closeCompanyDrawer',
    'function trapFocus',
    "document.body.classList.toggle('company-drawer-open'"
  ]) assert.ok(html.includes(required), `missing ${required}`);
  assert.match(html, /\.company-drawer-layer[^}]*position: fixed/s);
  assert.match(html, /width: min\(88vw, 340px\)/);
  assert.match(html, /\.prototype-stage\.is-mobile \.company-workspace > \.company-directory:not\(\.company-directory--drawer\)/);
});

test('HTML snapshot manifest registers only generated public reports', () => {
  const manifest = embeddedJson(readPrototype(), 'html-snapshot-manifest');
  assert.deepEqual(manifest.map((item) => item.id), ['cn-600519-html', 'hk-09626-html']);
  assert.deepEqual(manifest.map((item) => item.companyName), ['贵州茅台', '哔哩哔哩']);
  assert.deepEqual(manifest.map((item) => item.status), ['published', 'published']);
  assert.equal(manifest[0].htmlPath, './价值线_贵州茅台_企业快照版.html');
  assert.equal(manifest[1].htmlPath, './价值线_哔哩哔哩_企业快照版.html');
});

test('generated HTML snapshots are self-contained safe documents', () => {
  const manifest = embeddedJson(readPrototype(), 'html-snapshot-manifest');
  for (const snapshot of manifest) {
    const html = readSnapshotAsset(snapshot.fileName);
    assert.match(html, /^<!doctype html>/i, `${snapshot.fileName} missing doctype`);
    assert.match(html, /<html[^>]+lang=["']zh-CN["']/i, `${snapshot.fileName} missing lang`);
    assert.match(html, /<meta[^>]+charset=["']?utf-8/i, `${snapshot.fileName} missing charset`);
    assert.match(html, /<meta[^>]+name=["']viewport["']/i, `${snapshot.fileName} missing viewport`);
    assert.match(html, /<title>[^<]+<\/title>/i, `${snapshot.fileName} missing title`);
    assert.match(html, /<style>[\s\S]+<\/style>/i, `${snapshot.fileName} missing style`);
    assert.match(html, /<body>[\s\S]+<\/body>/i, `${snapshot.fileName} missing body`);
    assert.ok(html.includes(snapshot.companyName), `${snapshot.fileName} missing company`);
    assert.ok(html.includes(snapshot.titleTicker), `${snapshot.fileName} missing title ticker`);
    assert.doesNotMatch(html, /<script\b/i, `${snapshot.fileName} contains script`);
    assert.doesNotMatch(html, /<iframe\b/i, `${snapshot.fileName} contains iframe`);
    assert.doesNotMatch(html, /(?:src|href)=["']https?:\/\//i, `${snapshot.fileName} contains remote asset`);
    assert.doesNotMatch(html, /@import\s+(?:url\()?\s*["']?https?:\/\//i, `${snapshot.fileName} contains remote import`);
  }
});

test('prototype no longer stores or renders copied financial bodies', () => {
  const html = readPrototype();
  for (const obsolete of [
    'maotai-snapshot-data',
    'renderValueLineBody',
    'renderValueLineSnapshot',
    'renderValueTable',
    'renderEvidenceNote',
    'renderSimpleSnapshot',
    'renderSimpleWorkspaceBody',
    'renderResearchSection',
    'metricItems',
    'table-earliest',
    'table-latest',
    'hk-00700-2025',
    'hk-03690-2025',
    '¥15,563.14亿元',
    '.snapshot-page',
    '.snapshot-head',
    '.snapshot-kicker',
    '.snapshot-title',
    '.snapshot-summary',
    '.workspace-detail__scroll',
    'data-workspace-scroll'
  ]) assert.equal(html.includes(obsolete), false, `obsolete content remains: ${obsolete}`);
});
