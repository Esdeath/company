import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

const docDirectory = new URL('../doc/', import.meta.url);
const prototypePath = new URL('../doc/prototype.html', import.meta.url);
const REMOTE_ATTRIBUTE_PATTERN = /\b(?:src|href|srcset|poster|action|formaction)\s*=\s*(?:"[^"]*(?:https?:)?\/\/[^"]*"|'[^']*(?:https?:)?\/\/[^']*'|[^\s>"']*(?:https?:)?\/\/[^\s>]+)/i;
const REMOTE_CSS_URL_PATTERN = /url\(\s*["']?(?:https?:)?\/\//i;
const REMOTE_IMPORT_PATTERN = /@import\s+(?:url\()?\s*["']?(?:https?:)?\/\//i;

const chromePath = [
  process.env.CHROME_PATH,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser'
].find((candidate) => candidate && existsSync(candidate));

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

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      server.off('error', reject);
      resolve();
    });
  });
}

function closeServer(server) {
  return new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
}

async function startPrototypeServer() {
  const manifest = embeddedJson(readPrototype(), 'html-snapshot-manifest');
  const byPath = new Map(manifest.map((snapshot) => [`/doc/${snapshot.fileName}`, snapshot]));
  const controls = new Map(manifest.map((snapshot) => [snapshot.id, { headStatus: 200, getStatus: 200, getDelayMs: 0 }]));
  const requests = [];
  const server = createServer((request, response) => {
    const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    if (pathname === '/doc/prototype.html') {
      response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
      response.end(readPrototype());
      return;
    }
    const snapshot = byPath.get(pathname);
    if (!snapshot) {
      response.writeHead(404);
      response.end('not found');
      return;
    }
    const control = controls.get(snapshot.id);
    const status = request.method === 'HEAD' ? control.headStatus : control.getStatus;
    requests.push({ method: request.method, snapshotId: snapshot.id, status });
    const send = () => {
      response.writeHead(status, { 'content-type': 'text/html; charset=utf-8' });
      response.end(status === 200 && request.method !== 'HEAD' ? readSnapshotAsset(snapshot.fileName) : '');
    };
    if (request.method === 'GET' && control.getDelayMs) setTimeout(send, control.getDelayMs);
    else send();
  });
  await listen(server);
  const address = server.address();
  return {
    url: `http://127.0.0.1:${address.port}/doc/prototype.html`,
    requests,
    setSnapshot(snapshotId, patch) { Object.assign(controls.get(snapshotId), patch); },
    clearRequests() { requests.length = 0; },
    close() { return closeServer(server); }
  };
}

function waitForChromeEndpoint(process, timeoutMs = 10_000) {
  return new Promise((resolve, reject) => {
    let stderr = '';
    const timeout = setTimeout(() => reject(new Error(`Chrome DevTools endpoint timed out: ${stderr}`)), timeoutMs);
    const finish = (error, endpoint) => {
      clearTimeout(timeout);
      process.stderr.off('data', onData);
      process.off('exit', onExit);
      if (error) reject(error);
      else resolve(endpoint);
    };
    const onData = (chunk) => {
      stderr += chunk;
      const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) finish(null, match[1]);
    };
    const onExit = (code) => finish(new Error(`Chrome exited before DevTools was ready (${code}): ${stderr}`));
    process.stderr.on('data', onData);
    process.once('exit', onExit);
  });
}

async function waitForPageEndpoint(browserEndpoint, timeoutMs = 10_000) {
  const debugOrigin = `http://${new URL(browserEndpoint).host}`;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const targets = await fetch(`${debugOrigin}/json/list`).then((response) => response.json());
      const page = targets.find((target) => target.type === 'page');
      if (page?.webSocketDebuggerUrl) return page.webSocketDebuggerUrl;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error('Chrome page target timed out');
}

async function connectCdp(endpoint) {
  const socket = new WebSocket(endpoint);
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('CDP websocket connection timed out')), 5000);
    socket.addEventListener('open', () => { clearTimeout(timeout); resolve(); }, { once: true });
    socket.addEventListener('error', (event) => { clearTimeout(timeout); reject(event.error || new Error('CDP websocket failed')); }, { once: true });
  });
  let nextId = 1;
  const pending = new Map();
  socket.addEventListener('message', (event) => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(`${message.error.message} (${message.error.code})`));
    else resolve(message.result);
  });
  return {
    send(method, params = {}) {
      const id = nextId++;
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        socket.send(JSON.stringify({ id, method, params }));
      });
    },
    close() { socket.close(); }
  };
}

async function startBrowser(url) {
  assert.ok(chromePath, 'Chrome or Chromium is required for runtime prototype tests');
  const userDataDirectory = mkdtempSync(join(tmpdir(), 'company-prototype-chrome-'));
  const child = spawn(chromePath, [
    '--headless=new',
    '--remote-debugging-port=0',
    `--user-data-dir=${userDataDirectory}`,
    '--disable-background-networking',
    '--disable-component-update',
    '--no-first-run',
    '--no-default-browser-check',
    'about:blank'
  ], { stdio: ['ignore', 'ignore', 'pipe'] });
  try {
    const browserEndpoint = await waitForChromeEndpoint(child);
    const pageEndpoint = await waitForPageEndpoint(browserEndpoint);
    const cdp = await connectCdp(pageEndpoint);
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Page.navigate', { url });
    return {
      async evaluate(expression) {
        const response = await cdp.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
        if (response.exceptionDetails) throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text);
        return response.result.value;
      },
      async waitFor(expression, description, timeoutMs = 8000) {
        const deadline = Date.now() + timeoutMs;
        let lastError;
        while (Date.now() < deadline) {
          try {
            if (await this.evaluate(expression)) return;
          } catch (error) {
            lastError = error;
          }
          await new Promise((resolve) => setTimeout(resolve, 25));
        }
        throw new Error(`Timed out waiting for ${description}${lastError ? `: ${lastError.message}` : ''}`);
      },
      async click(selector) {
        const clicked = await this.evaluate(`(() => { const element = document.querySelector(${JSON.stringify(selector)}); if (!element) return false; element.click(); return true; })()`);
        assert.equal(clicked, true, `missing clickable ${selector}`);
      },
      async close() {
        cdp.close();
        child.kill('SIGTERM');
        await new Promise((resolve) => {
          if (child.exitCode !== null) return resolve();
          child.once('exit', resolve);
          setTimeout(() => { child.kill('SIGKILL'); resolve(); }, 2000).unref();
        });
        rmSync(userDataDirectory, { recursive: true, force: true });
      }
    };
  } catch (error) {
    child.kill('SIGKILL');
    rmSync(userDataDirectory, { recursive: true, force: true });
    throw error;
  }
}

async function openAdminRecord(browser, recordId) {
  await browser.evaluate("window.prototypeApp.navigate('admin-list')");
  const onLogin = await browser.evaluate("Boolean(document.querySelector('main[data-route=\"login\"]'))");
  if (onLogin) {
    await browser.waitFor("Boolean(document.querySelector('#username') && document.querySelector('#password') && document.querySelector('[data-action=\"login\"]'))", 'administrator login form');
    await browser.evaluate(`(() => {
      document.querySelector('#username').value = 'admin';
      document.querySelector('#password').value = 'demo123';
      document.querySelector('[data-action="login"]').requestSubmit();
    })()`);
  }
  await browser.waitFor("Boolean(document.querySelector('main[data-route=\"admin-list\"]'))", 'administrator list');
  await browser.click(`[data-action="review-snapshot"][data-id="${recordId}"]`);
  await browser.waitFor("Boolean(document.querySelector('main[data-route=\"review\"]'))", `review ${recordId}`);
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

test('administrator publication state is the source of truth for public visibility', () => {
  const html = readPrototype();
  for (const required of [
    'function adminRecordForSnapshot(snapshotId)',
    'function isSnapshotPublished(snapshot)',
    'adminRecordForSnapshot(snapshot.id)?.status === \'published\'',
    'htmlSnapshots.filter((snapshot) => snapshot.isLatest && isSnapshotPublished(snapshot))',
    'isSnapshotPublished(snapshot)',
    'const publicPatch = publicSelectionPatch({})',
    'setState({ ...publicPatch, dialog: null })'
  ]) assert.ok(html.includes(required), `missing ${required}`);
  assert.doesNotMatch(html, /selectedPublicSnapshot\(\) \|\| htmlSnapshots\[0\]/);
});

test('withdraw and republish reconcile the selected public snapshot', () => {
  const html = readPrototype();
  assert.match(html, /record\.status = kind === 'publish' \? 'published' : 'withdrawn'[\s\S]*const publicPatch = publicSelectionPatch\(\{\}\)[\s\S]*setState\(\{ \.\.\.publicPatch, dialog: null \}\)/);
  assert.match(html, /function renderSnapshot\(\) \{[\s\S]*renderHtmlSnapshotPage\(selectedPublicSnapshot\(\)\)/);
  assert.match(html, /if \(!snapshot\)[\s\S]*没有可阅读的企业财报 HTML/);
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

test('snapshot load failure becomes an administrator validation error and blocks publishing', () => {
  const html = readPrototype();
  for (const required of [
    "'html-unavailable': { errors: ['HTML 文件不存在或无法访问，请检查文件路径。']",
    'data-snapshot-id',
    'function markSnapshotUnavailable(snapshotId)',
    "record.report = 'html-unavailable'",
    'markSnapshotUnavailable(frame.dataset.snapshotId)',
    'function markSnapshotAvailable(snapshotId)',
    "record.report = 'clean'",
    'data-action="retry-validation"',
    "record.report = 'html-checking'",
    "failedSnapshotIds.delete(record.snapshotId)",
    "data-action=\"publish\" ${hasErrors ? 'disabled' : ''}"
  ]) assert.ok(html.includes(required), `missing ${required}`);
  assert.match(html, /function renderSnapshotFrame\(snapshot, mode\)[\s\S]*failedSnapshotIds\.has\(snapshot\.id\)[\s\S]*HTML 文件不存在或无法访问/);
  assert.match(html, /if \(action === 'retry-validation'\)[\s\S]*retrySnapshotValidation/);
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

test('administrator publication and HTML validation execute as runtime state transitions', async (t) => {
  const server = await startPrototypeServer();
  const browser = await startBrowser(server.url);
  try {
    await browser.waitFor(
      "Boolean(window.prototypeApp) && document.querySelectorAll('[data-action=\"select-company\"]').length === 2",
      'initial public company directory'
    );

    await t.test('withdrawing and republishing reconcile the public directory, selection, and iframe', async () => {
      await openAdminRecord(browser, 'published-maotai-html');
      await browser.click('[data-action="withdraw"]');
      await browser.click('[data-action="confirm-dialog"]');
      await browser.waitFor("document.querySelector('.review-summary')?.innerText.includes('已撤回')", 'withdrawn administrator status');

      await browser.evaluate("window.prototypeApp.navigate('home')");
      await browser.waitFor("document.querySelectorAll('[data-action=\"select-company\"]').length === 1", 'withdrawn company to leave the public directory');
      const withdrawnPublicState = await browser.evaluate(`(() => ({
        directoryIds: [...document.querySelectorAll('[data-action="select-company"]')].map((card) => card.dataset.id),
        selectedId: document.querySelector('[data-action="select-company"][aria-current="true"]')?.dataset.id || null,
        iframeIds: [...document.querySelectorAll('[data-frame-load]')].map((frame) => frame.dataset.snapshotId)
      }))()`);
      assert.deepEqual(withdrawnPublicState.directoryIds, ['hk-09626-html']);
      assert.equal(withdrawnPublicState.selectedId, 'hk-09626-html');
      assert.deepEqual(withdrawnPublicState.iframeIds, ['hk-09626-html']);

      await openAdminRecord(browser, 'published-maotai-html');
      await browser.click('[data-action="publish"]');
      await browser.click('[data-action="confirm-dialog"]');
      await browser.waitFor("document.querySelector('.review-summary')?.innerText.includes('已发布')", 'republished administrator status');
      await browser.evaluate("window.prototypeApp.navigate('home')");
      await browser.waitFor("document.querySelectorAll('[data-action=\"select-company\"]').length === 2", 'republished company to return to the public directory');
      const restoredIds = await browser.evaluate("[...document.querySelectorAll('[data-action=\"select-company\"]')].map((card) => card.dataset.id)");
      assert.deepEqual(new Set(restoredIds), new Set(['cn-600519-html', 'hk-09626-html']));
    });

    await t.test('HEAD and iframe failure persist html-unavailable, remove the iframe, and block a withdrawn record', async () => {
      server.setSnapshot('cn-600519-html', { headStatus: 404, getStatus: 404, getDelayMs: 0 });
      server.clearRequests();
      await openAdminRecord(browser, 'published-maotai-html');
      await browser.waitFor(
        "document.querySelector('main[data-route=\"review\"]')?.innerText.includes('HTML 文件不存在或无法访问，请检查文件路径。') && !document.querySelector('[data-frame-load]')",
        'unavailable HTML administrator error'
      );
      assert.ok(server.requests.some((request) => request.snapshotId === 'cn-600519-html' && request.method === 'HEAD' && request.status === 404));
      assert.ok(server.requests.some((request) => request.snapshotId === 'cn-600519-html' && request.method === 'GET' && request.status === 404));

      await browser.evaluate("window.prototypeApp.navigate('admin-list')");
      await browser.waitFor("Boolean(document.querySelector('main[data-route=\"admin-list\"]'))", 'administrator list after validation failure');
      const failedRowText = await browser.evaluate("document.querySelector('[data-action=\"review-snapshot\"][data-id=\"published-maotai-html\"]')?.closest('tr')?.innerText || ''");
      assert.match(failedRowText, /1 错误/);

      await openAdminRecord(browser, 'published-maotai-html');
      await browser.click('[data-action="withdraw"]');
      await browser.click('[data-action="confirm-dialog"]');
      await browser.waitFor("Boolean(document.querySelector('[data-action=\"publish\"]:disabled'))", 'disabled publish gate after withdrawal');
      const withdrawnFailure = await browser.evaluate(`(() => ({
        reviewText: document.querySelector('main[data-route="review"]').innerText,
        iframeCount: document.querySelectorAll('[data-frame-load]').length,
        publishDisabled: document.querySelector('[data-action="publish"]').disabled
      }))()`);
      assert.match(withdrawnFailure.reviewText, /已撤回/);
      assert.match(withdrawnFailure.reviewText, /HTML 文件不存在或无法访问，请检查文件路径/);
      assert.equal(withdrawnFailure.iframeCount, 0);
      assert.equal(withdrawnFailure.publishDisabled, true);
    });

    await t.test('retry stays blocked after HEAD until iframe load, then restores clean and publishing', async () => {
      server.setSnapshot('cn-600519-html', { headStatus: 200, getStatus: 200, getDelayMs: 1200 });
      server.clearRequests();
      await browser.click('[data-action="retry-validation"]');
      await browser.waitFor(
        "document.querySelector('[data-frame-load]')?.dataset.frameHttpStatus === 'ok'",
        'successful HEAD preflight before delayed iframe load'
      );
      const headOnlyState = await browser.evaluate(`(() => {
        const frame = document.querySelector('[data-frame-load]');
        return {
          httpStatus: frame?.dataset.frameHttpStatus || null,
          loadStatus: frame?.dataset.frameLoadStatus || null,
          reviewText: document.querySelector('main[data-route="review"]').innerText,
          publishDisabled: document.querySelector('[data-action="publish"]').disabled
        };
      })()`);
      assert.equal(headOnlyState.httpStatus, 'ok');
      assert.notEqual(headOnlyState.loadStatus, 'loaded');
      assert.match(headOnlyState.reviewText, /HTML 文件正在重新校验/);
      assert.equal(headOnlyState.publishDisabled, true);

      await browser.waitFor(
        "document.querySelector('main[data-route=\"review\"]')?.innerText.includes('没有错误') && document.querySelector('[data-action=\"publish\"]')?.disabled === false && document.querySelector('[data-frame-load]')?.dataset.frameHttpStatus === 'ok' && document.querySelector('[data-frame-load]')?.dataset.frameLoadStatus === 'loaded'",
        'clean validation after both HEAD and iframe load',
        10_000
      );
      const recoveredState = await browser.evaluate(`(() => ({
        reviewText: document.querySelector('main[data-route="review"]').innerText,
        publishDisabled: document.querySelector('[data-action="publish"]').disabled,
        iframeCount: document.querySelectorAll('[data-frame-load]').length
      }))()`);
      assert.match(recoveredState.reviewText, /没有错误/);
      assert.equal(recoveredState.publishDisabled, false);
      assert.equal(recoveredState.iframeCount, 1);
      assert.ok(server.requests.some((request) => request.snapshotId === 'cn-600519-html' && request.method === 'HEAD' && request.status === 200));
      assert.ok(server.requests.some((request) => request.snapshotId === 'cn-600519-html' && request.method === 'GET' && request.status === 200));
    });
  } finally {
    await browser.close();
    await server.close();
  }
});

test('HTML snapshot manifest registers only generated public reports', () => {
  const manifest = embeddedJson(readPrototype(), 'html-snapshot-manifest');
  assert.deepEqual(manifest.map((item) => item.id), ['cn-600519-html', 'hk-09626-html']);
  assert.deepEqual(manifest.map((item) => item.companyName), ['贵州茅台', '哔哩哔哩']);
  assert.deepEqual(manifest.map((item) => item.status), ['published', 'published']);
  assert.equal(manifest[0].htmlPath, './价值线_贵州茅台_企业快照版.html');
  assert.equal(manifest[1].htmlPath, './价值线_哔哩哔哩_企业快照版.html');
});

test('remote snapshot resource detection covers quoted and unquoted HTML and CSS URLs', () => {
  for (const html of [
    '<img src="https://example.com/a.png">',
    "<a href='//example.com/x'>x</a>",
    '<img src=https://example.com/a.png>',
    '<a href=//example.com/x>x</a>',
    '<img srcset=https://example.com/a.png>',
    '<video poster=//example.com/poster.png>',
    '<form action=https://example.com/save><button formaction=//example.com/submit>x</button></form>'
  ]) assert.match(html, REMOTE_ATTRIBUTE_PATTERN);
  for (const css of [
    'body { background: url("https://example.com/a.png") }',
    'body { background: url(//example.com/a.png) }'
  ]) assert.match(css, REMOTE_CSS_URL_PATTERN);
  for (const css of [
    '@import "https://example.com/base.css";',
    '@import url(//example.com/base.css);'
  ]) assert.match(css, REMOTE_IMPORT_PATTERN);
});

test('generated HTML snapshots are self-contained safe documents', () => {
  const manifest = embeddedJson(readPrototype(), 'html-snapshot-manifest');
  for (const snapshot of manifest) {
    const html = readSnapshotAsset(snapshot.fileName);
    assert.match(html, /^<!doctype html>/i, `${snapshot.fileName} missing doctype`);
    assert.match(html, /<html[^>]+lang=["']zh-CN["']/i, `${snapshot.fileName} missing lang`);
    assert.match(html, /<meta[^>]+charset=["']?utf-8/i, `${snapshot.fileName} missing charset`);
    assert.match(html, /<meta[^>]+name=["']viewport["']/i, `${snapshot.fileName} missing viewport`);
    const titleMatch = html.match(/<title>([^<]+)<\/title>/i);
    assert.ok(titleMatch?.[1].trim(), `${snapshot.fileName} missing title`);
    assert.ok(titleMatch[1].includes(snapshot.companyName), `${snapshot.fileName} title missing company`);
    assert.ok(titleMatch[1].includes(snapshot.titleTicker), `${snapshot.fileName} title missing ticker`);
    assert.match(html, /<style>[\s\S]+<\/style>/i, `${snapshot.fileName} missing style`);
    assert.match(html, /<body>[\s\S]+<\/body>/i, `${snapshot.fileName} missing body`);
    assert.doesNotMatch(html, /<script\b/i, `${snapshot.fileName} contains script`);
    assert.doesNotMatch(html, /<iframe\b/i, `${snapshot.fileName} contains iframe`);
    assert.doesNotMatch(html, REMOTE_ATTRIBUTE_PATTERN, `${snapshot.fileName} contains remote asset`);
    assert.doesNotMatch(html, REMOTE_CSS_URL_PATTERN, `${snapshot.fileName} contains remote CSS URL`);
    assert.doesNotMatch(html, REMOTE_IMPORT_PATTERN, `${snapshot.fileName} contains remote import`);
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
