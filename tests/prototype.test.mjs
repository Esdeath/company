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
const FORM_TAG_PATTERN = /<\s*form\b/i;
const META_REFRESH_PATTERN = /<\s*meta\b[^>]*\bhttp-equiv\s*=\s*(?:"\s*refresh\s*"|'\s*refresh\s*'|refresh(?=[\s/>]))/i;
const JAVASCRIPT_URL_PATTERN = /\b(?:href|src|action|formaction)\s*=\s*(?:["']\s*javascript\s*:|javascript\s*:)/i;
const EVENT_ATTRIBUTE_PATTERN = /\bon[a-z][\w:-]*\s*=/i;
const LEGACY_EMBED_PATTERN = /<\s*(?:object|embed|applet)\b/i;
const TOP_NAVIGATION_TARGET_PATTERN = /\btarget\s*=\s*(?:"\s*_(?:top|parent)\s*"|'\s*_(?:top|parent)\s*'|_(?:top|parent)(?=[\s/>]))/i;
const BASE_TAG_PATTERN = /<\s*base\b/i;

const chromePath = [
  process.env.CHROME_PATH,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser'
].find((candidate) => candidate && existsSync(candidate));

function readSnapshotAsset(htmlPath) {
  const url = new URL(htmlPath, docDirectory);
  assert.equal(existsSync(url), true, `missing ${htmlPath}`);
  return readFileSync(url, 'utf8');
}

function readPrototype() {
  return readFileSync(prototypePath, 'utf8');
}

function assertSafeSnapshotHtml(html, label) {
  assert.doesNotMatch(html, /<script\b/i, `${label} contains script`);
  assert.doesNotMatch(html, /<iframe\b/i, `${label} contains iframe`);
  assert.doesNotMatch(html, FORM_TAG_PATTERN, `${label} contains form`);
  assert.doesNotMatch(html, META_REFRESH_PATTERN, `${label} contains meta refresh`);
  assert.doesNotMatch(html, JAVASCRIPT_URL_PATTERN, `${label} contains javascript URL`);
  assert.doesNotMatch(html, EVENT_ATTRIBUTE_PATTERN, `${label} contains event handler`);
  assert.doesNotMatch(html, LEGACY_EMBED_PATTERN, `${label} contains object, embed, or applet`);
  assert.doesNotMatch(html, TOP_NAVIGATION_TARGET_PATTERN, `${label} contains top-level navigation target`);
  assert.doesNotMatch(html, BASE_TAG_PATTERN, `${label} contains base element`);
  assert.doesNotMatch(html, REMOTE_ATTRIBUTE_PATTERN, `${label} contains remote asset`);
  assert.doesNotMatch(html, REMOTE_CSS_URL_PATTERN, `${label} contains remote CSS URL`);
  assert.doesNotMatch(html, REMOTE_IMPORT_PATTERN, `${label} contains remote import`);
}

function collectSemanticSnapshotViolations(html) {
  const parsed = new DOMParser().parseFromString(html, 'text/html');
  const violations = [];
  const urlAttributes = new Set(['href', 'src', 'srcset', 'poster', 'action', 'formaction']);
  const add = (code) => {
    if (!violations.includes(code)) violations.push(code);
  };
  const inspectUrlCandidate = (candidate, codes, policy = 'attribute') => {
    const normalized = candidate.trim().replace(/[\u0000-\u0020\u007f]+/g, '').toLowerCase();
    const safeStyleData = /^data:image\/(?:png|gif|jpe?g|webp|avif)(?:[;,]|$)/.test(normalized);
    const dangerousAttributeData = /^data:(?:text\/html|application\/xhtml\+xml|image\/svg\+xml|text\/javascript|application\/javascript)(?:[;,]|$)/.test(normalized);
    if (normalized.startsWith('javascript:')) add(codes.javascript);
    else if (normalized.startsWith('vbscript:')) add(codes.vbscript);
    else if (/^(?:https?:)?\/\//.test(normalized)) add(codes.remote);
    else if (normalized.startsWith('data:') && (
      policy === 'attribute' ? dangerousAttributeData : policy === 'style' ? !safeStyleData : true
    )) {
      add(codes.dangerousData);
    } else if (policy === 'style' && normalized && !normalized.startsWith('#') && !safeStyleData) {
      add(codes.external);
    } else if (policy === 'import' && normalized) {
      add(codes.external);
    }
  };
  const inspectUrlAttribute = (attributeLocalName, codeName, value) => {
    const candidates = attributeLocalName === 'srcset'
      ? value.split(',').map((candidate) => candidate.trim().split(/\s+/, 1)[0])
      : [value];
    for (const candidate of candidates) {
      inspectUrlCandidate(candidate, {
        javascript: `url-javascript:${codeName}`,
        vbscript: `url-vbscript:${codeName}`,
        dangerousData: `url-dangerous-data:${codeName}`,
        remote: `url-remote:${codeName}`
      });
    }
  };
  const inspectStyleSources = (styleSources) => {
    for (const styleSource of styleSources) {
      if (!styleSource) continue;
      const cssUrlPattern = /url\(\s*(?:(["'])([\s\S]*?)\1|([^)]*))\s*\)/gi;
      for (const match of styleSource.matchAll(cssUrlPattern)) {
        inspectUrlCandidate(match[2] ?? match[3] ?? '', {
          javascript: 'style-url-javascript',
          vbscript: 'style-url-vbscript',
          dangerousData: 'style-url-dangerous-data',
          remote: 'style-url-remote',
          external: 'style-url-external'
        }, 'style');
      }
    }
  };
  const inspectStyleDeclaration = (style) => {
    const propertyValues = [];
    for (const propertyName of style) propertyValues.push(style.getPropertyValue(propertyName));
    inspectStyleSources(propertyValues);
  };
  const inspectInlineStyle = (element) => {
    inspectStyleSources([element.getAttribute('style')]);
    inspectStyleDeclaration(element.style);
  };
  const inspectRuleList = (rules) => {
    for (const rule of rules) {
      if (rule.type === CSSRule.IMPORT_RULE) {
        inspectUrlCandidate(rule.href, {
          javascript: 'style-import-javascript',
          vbscript: 'style-import-vbscript',
          dangerousData: 'style-import-dangerous-data',
          remote: 'style-import-remote',
          external: 'style-import-external'
        }, 'import');
      }
      if (rule.style) inspectStyleDeclaration(rule.style);
      if ('cssRules' in rule) {
        try {
          inspectRuleList(rule.cssRules);
        } catch {
          add('style-block-parse-error');
        }
      }
    }
  };
  const inspectStyleBlock = (element) => {
    try {
      if (!element.sheet) {
        add('style-block-parse-error');
        return;
      }
      inspectRuleList(element.sheet.cssRules);
    } catch {
      add('style-block-parse-error');
    }
  };

  for (const element of parsed.querySelectorAll('*')) {
    const tagName = element.localName;
    if (tagName === 'script') add('script-element');
    if (tagName === 'iframe') add('iframe-element');
    if (tagName === 'form') add('form-element');
    if (tagName === 'object') add('legacy-object');
    if (tagName === 'embed') add('legacy-embed');
    if (tagName === 'applet') add('legacy-applet');
    if (tagName === 'base') add('base-element');
    if (tagName === 'meta' && element.getAttribute('http-equiv')?.trim().toLowerCase() === 'refresh') {
      add('meta-refresh');
    }
    if (['_top', '_parent'].includes(element.getAttribute('target')?.trim().toLowerCase())) {
      add('top-navigation-target');
    }
    if (element.hasAttribute('style')) inspectInlineStyle(element);
    if (tagName === 'style') inspectStyleBlock(element);
    for (const attribute of element.attributes) {
      const attributeName = attribute.name.toLowerCase();
      const attributeLocalName = attribute.localName.toLowerCase();
      if (attributeLocalName.startsWith('on')) add(`event-handler:${attributeName}`);
      if (urlAttributes.has(attributeLocalName)) {
        inspectUrlAttribute(attributeLocalName, attributeName, attribute.value);
      }
    }
  }
  return violations;
}

async function semanticSnapshotViolations(browser, html) {
  return browser.evaluate(`(${collectSemanticSnapshotViolations.toString()})(${JSON.stringify(html)})`);
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
  const byPath = new Map(manifest.map((snapshot) => [
    new URL(snapshot.htmlPath, 'http://localhost/doc/prototype.html').pathname,
    snapshot
  ]));
  const controls = new Map(manifest.map((snapshot) => [snapshot.id, { headStatus: 200, getStatus: 200, getDelayMs: 0 }]));
  const requests = [];
  const server = createServer((request, response) => {
    const pathname = new URL(request.url, 'http://localhost').pathname;
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
      response.end(status === 200 && request.method !== 'HEAD' ? readSnapshotAsset(snapshot.htmlPath) : '');
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

async function stopChrome(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  await new Promise((resolve) => {
    const forceKill = setTimeout(() => child.kill('SIGKILL'), 2000);
    child.once('exit', () => {
      clearTimeout(forceKill);
      resolve();
    });
    child.kill('SIGTERM');
  });
}

async function cleanBrowserResources(child, cdp, userDataDirectory) {
  try {
    cdp?.close();
  } finally {
    await stopChrome(child);
    rmSync(userDataDirectory, { recursive: true, force: true });
  }
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
  let cdp = null;
  try {
    const browserEndpoint = await waitForChromeEndpoint(child);
    const pageEndpoint = await waitForPageEndpoint(browserEndpoint);
    cdp = await connectCdp(pageEndpoint);
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Page.navigate', { url });
    let closed = false;
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
        if (closed) return;
        closed = true;
        await cleanBrowserResources(child, cdp, userDataDirectory);
      }
    };
  } catch (error) {
    await cleanBrowserResources(child, cdp, userDataDirectory);
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
  let browser = null;
  try {
    browser = await startBrowser(server.url);
    await browser.waitFor(
      "Boolean(window.prototypeApp) && document.querySelectorAll('[data-action=\"select-company\"]').length === 2",
      'initial public company directory'
    );

    await t.test('browser semantic scan rejects decoded dangerous HTML without false positives', async () => {
      const entityBypass = '<a href="javascript&colon;alert(1)">x</a>';
      assert.doesNotMatch(entityBypass, JAVASCRIPT_URL_PATTERN, 'raw regex unexpectedly caught the entity bypass');
      const decodedHref = await browser.evaluate(`new DOMParser()
        .parseFromString(${JSON.stringify(entityBypass)}, 'text/html')
        .querySelector('a')
        .getAttribute('href')`);
      assert.equal(decodedHref, 'javascript:alert(1)');

      const styleBypass = '<div style="background:url(h&#116;tp://example.com/x.png)"></div>';
      const svgBypass = '<svg><a xlink:href="h&#116;tp://example.com/x">x</a></svg>';
      const decodedCssAndSvg = await browser.evaluate(`(() => {
        const styleElement = new DOMParser()
          .parseFromString(${JSON.stringify(styleBypass)}, 'text/html')
          .querySelector('div');
        const svgLink = new DOMParser()
          .parseFromString(${JSON.stringify(svgBypass)}, 'text/html')
          .querySelector('a');
        const xlinkHref = [...svgLink.attributes].find((attribute) => attribute.localName === 'href');
        return {
          styleAttribute: styleElement.getAttribute('style'),
          backgroundImage: styleElement.style.backgroundImage,
          svgAttributeName: xlinkHref.name,
          svgAttributeLocalName: xlinkHref.localName,
          svgAttributeNamespace: xlinkHref.namespaceURI,
          svgAttributeValue: xlinkHref.value
        };
      })()`);
      assert.deepEqual(decodedCssAndSvg, {
        styleAttribute: 'background:url(http://example.com/x.png)',
        backgroundImage: 'url("http://example.com/x.png")',
        svgAttributeName: 'xlink:href',
        svgAttributeLocalName: 'href',
        svgAttributeNamespace: 'http://www.w3.org/1999/xlink',
        svgAttributeValue: 'http://example.com/x'
      });

      const cssEscapeBlock = '<style>body{background:url(h\\74tp://example.com/x.png)}</style>';
      const cssImportBlock = '<style>@import "h\\74tp://example.com/x.css";</style>';
      assert.doesNotMatch(cssEscapeBlock, REMOTE_CSS_URL_PATTERN, 'raw CSS URL regex unexpectedly decoded CSS escape');
      assert.doesNotMatch(cssImportBlock, REMOTE_IMPORT_PATTERN, 'raw CSS import regex unexpectedly decoded CSS escape');
      const detachedCssom = await browser.evaluate(`(() => {
        const parsedStyle = new DOMParser().parseFromString(${JSON.stringify(cssEscapeBlock)}, 'text/html');
        const parsedImport = new DOMParser().parseFromString(${JSON.stringify(cssImportBlock)}, 'text/html');
        const styleSheet = parsedStyle.querySelector('style').sheet;
        const importSheet = parsedImport.querySelector('style').sheet;
        return {
          detachedDefaultView: parsedStyle.defaultView,
          styleSheetAvailable: Boolean(styleSheet),
          styleRuleCssText: styleSheet.cssRules[0].cssText,
          backgroundImage: styleSheet.cssRules[0].style.backgroundImage,
          importSheetAvailable: Boolean(importSheet),
          importRuleCssText: importSheet.cssRules[0].cssText,
          importHref: importSheet.cssRules[0].href
        };
      })()`);
      assert.equal(detachedCssom.detachedDefaultView, null);
      assert.equal(detachedCssom.styleSheetAvailable, true);
      assert.match(detachedCssom.styleRuleCssText, /http:\/\/example\.com\/x\.png/);
      assert.equal(detachedCssom.backgroundImage, 'url("http://example.com/x.png")');
      assert.equal(detachedCssom.importSheetAvailable, true);
      assert.match(detachedCssom.importRuleCssText, /http:\/\/example\.com\/x\.css/);
      assert.equal(detachedCssom.importHref, 'http://example.com/x.css');

      const dangerousFixtures = [
        ['script element', '<script>alert(1)</script>', ['script-element']],
        ['iframe element', '<iframe src="/safe"></iframe>', ['iframe-element']],
        ['form element', '<form></form>', ['form-element']],
        ['meta refresh', '<meta http-equiv="refresh" content="0;url=/admin">', ['meta-refresh']],
        ['encoded meta refresh', '<meta http-equiv="re&#x66;resh" content="0;url=/admin">', ['meta-refresh']],
        ['encoded meta refresh without semicolon', '<meta http-equiv="re&#102resh" content="0;url=/admin">', ['meta-refresh']],
        ['javascript href', '<a href="javascript:alert(1)">x</a>', ['url-javascript:href']],
        ['javascript named entity', entityBypass, ['url-javascript:href']],
        ['javascript hex entity', '<a href="java&#x73;cript:alert(1)">x</a>', ['url-javascript:href']],
        ['javascript decimal entity', '<a href="&#106;avascript:alert(1)">x</a>', ['url-javascript:href']],
        ['javascript decimal entity without semicolon', '<a href="&#106avascript:alert(1)">x</a>', ['url-javascript:href']],
        ['vbscript href', '<a href="vbscript:msgbox(1)">x</a>', ['url-vbscript:href']],
        ['dangerous data href', '<a href="data:text/html,<script>alert(1)</script>">x</a>', ['url-dangerous-data:href']],
        ['encoded remote href', '<a href="h&#x74;tp://example.com/x">x</a>', ['url-remote:href']],
        ['encoded remote href without semicolon', '<a href="h&#116tp://example.com/x">x</a>', ['url-remote:href']],
        ['remote src', '<img src="https://example.com/x.png">', ['url-remote:src']],
        ['remote srcset', '<img srcset="/safe.png 1x, https://example.com/x.png 2x">', ['url-remote:srcset']],
        ['remote poster', '<video poster="//example.com/x.png"></video>', ['url-remote:poster']],
        ['remote action', '<div action="http://example.com/save"></div>', ['url-remote:action']],
        ['remote formaction', '<button formaction="//example.com/save">x</button>', ['url-remote:formaction']],
        ['numeric entity remote style URL', styleBypass, ['style-url-remote']],
        ['named entity remote style URL', '<div style="background:url(&sol;&sol;example.com/x.png)"></div>', ['style-url-remote']],
        ['javascript style URL', '<div style="background:url(java&#x73;cript:alert(1))"></div>', ['style-url-javascript']],
        ['vbscript style URL', '<div style="background:url(vbscript:msgbox(1))"></div>', ['style-url-vbscript']],
        ['dangerous data style URL', '<div style="background:url(data:image/svg+xml,<svg></svg>)"></div>', ['style-url-dangerous-data']],
        ['relative style URL', '<div style="background:url(./local.png)"></div>', ['style-url-external']],
        ['numeric entity remote SVG href', svgBypass, ['url-remote:xlink:href']],
        ['named entity remote SVG href', '<svg><a xlink:href="&sol;&sol;example.com/x">x</a></svg>', ['url-remote:xlink:href']],
        ['javascript SVG href', '<svg><a xlink:href="java&#x73;cript:alert(1)">x</a></svg>', ['url-javascript:xlink:href']],
        ['relative style block URL', '<style>body{background:url(./local.png)}</style>', ['style-url-external']],
        ['CSS escape remote style block URL', cssEscapeBlock, ['style-url-remote']],
        ['CSS escape import', cssImportBlock, ['style-import-remote']],
        ['relative import', '<style>@import "./local.css";</style>', ['style-import-external']],
        ['nested media remote URL', '<style>@media (min-width:1px){body{background:url(https://example.com/x.png)}}</style>', ['style-url-remote']],
        ['font face relative URL', '<style>@font-face{font-family:test;src:url(./font.woff2)}</style>', ['style-url-external']],
        ['keyframes remote URL', '<style>@keyframes pulse{from{background:url(https://example.com/x.png)}to{color:#123456}}</style>', ['style-url-remote']],
        ['unavailable style sheet', '<style type="text/plain">body{color:#123456}</style>', ['style-block-parse-error']],
        ['event handler', '<div onclick="alert(1)"></div>', ['event-handler:onclick']],
        ['object element', '<object data="/safe"></object>', ['legacy-object']],
        ['embed element', '<embed src="/safe">', ['legacy-embed']],
        ['applet element', '<applet></applet>', ['legacy-applet']],
        ['encoded top target', '<a target="&#95;top" href="/safe">x</a>', ['top-navigation-target']],
        ['encoded parent target', '<a target=&#95;parent href=/safe>x</a>', ['top-navigation-target']],
        ['encoded parent target without semicolon', '<a target=&#95parent href=/safe>x</a>', ['top-navigation-target']],
        ['base element', '<base href="/safe">', ['base-element']]
      ];

      for (const [label, html, expectedCodes] of dangerousFixtures) {
        assert.deepEqual(await semanticSnapshotViolations(browser, html), expectedCodes, label);
      }

      const harmlessFixtures = [
        ['fragment href', '<a href="#section">x</a>'],
        ['entity in text', '<p>javascript&colon;alert(1)</p>'],
        ['entity in data attribute', '<div data-example="javascript&colon;alert(1)"></div>'],
        ['viewport meta', '<meta name="viewport" content="width=device-width">'],
        ['blank target', '<a target="_blank" href="/safe">x</a>'],
        ['safe embedded image', '<img src="data:image/png;base64,iVBORw0KGgo=">'],
        ['safe style image data', '<div style="background:url(data:image/png;base64,iVBORw0KGgo=)"></div>'],
        ['inline color', '<div style="color:#123456"></div>'],
        ['style fragment', '<div style="filter:url(#shadow)"></div>'],
        ['SVG xlink fragment', '<svg><a xlink:href="#section">x</a></svg>'],
        ['style block image data', '<style>body{background:url(data:image/png;base64,iVBORw0KGgo=)}</style>'],
        ['style block fragment', '<style>body{filter:url(#shadow)}</style>'],
        ['style block color', '<style>body{color:#123456}</style>'],
        ['nested rule without URL', '<style>@media (min-width:1px){body{color:#123456}}</style>'],
        ['relative URL attributes', '<img src="/safe.png" srcset="/safe.png 1x"><video poster="/safe.png"></video>']
      ];

      for (const [label, html] of harmlessFixtures) {
        assert.deepEqual(await semanticSnapshotViolations(browser, html), [], label);
      }

      const manifest = embeddedJson(readPrototype(), 'html-snapshot-manifest');
      for (const snapshot of manifest) {
        assert.deepEqual(
          await semanticSnapshotViolations(browser, readSnapshotAsset(snapshot.htmlPath)),
          [],
          snapshot.fileName
        );
      }
    });

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
    try {
      await browser?.close();
    } finally {
      await server.close();
    }
  }
});

test('HTML snapshot manifest registers only generated public reports', () => {
  const manifest = embeddedJson(readPrototype(), 'html-snapshot-manifest');
  assert.deepEqual(manifest.map((item) => item.id), ['cn-600519-html', 'hk-09626-html']);
  assert.deepEqual(manifest.map((item) => item.companyName), ['贵州茅台', '哔哩哔哩']);
  assert.deepEqual(manifest.map((item) => item.status), ['published', 'published']);
  assert.equal(manifest[0].htmlPath, './snapshots/published/贵州茅台.html');
  assert.equal(manifest[0].fileName, '贵州茅台.html');
  assert.equal(manifest[1].htmlPath, './snapshots/published/哔哩哔哩.html');
  assert.equal(manifest[1].fileName, '哔哩哔哩.html');
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

test('snapshot safety scan rejects every dangerous capability injected into a safe asset', () => {
  const [safeSnapshot] = embeddedJson(readPrototype(), 'html-snapshot-manifest');
  const safeHtml = readSnapshotAsset(safeSnapshot.htmlPath);
  const dangerousFixtures = [
    ['form element', '<form></form>', /contains form/],
    ['meta refresh quoted', '<meta http-equiv="refresh" content="0;url=/admin">', /contains meta refresh/],
    ['meta refresh unquoted', '<meta http-equiv=refresh content=0>', /contains meta refresh/],
    ['javascript href quoted', '<a href="javascript:alert(1)">x</a>', /contains javascript URL/],
    ['javascript href unquoted', '<a href=javascript:alert(1)>x</a>', /contains javascript URL/],
    ['javascript src quoted', "<img src='javascript:alert(1)'>", /contains javascript URL/],
    ['javascript src unquoted', '<img src=javascript:alert(1)>', /contains javascript URL/],
    ['javascript action quoted', "<div action='javascript:alert(1)'></div>", /contains javascript URL/],
    ['javascript action unquoted', '<div action=javascript:alert(1)></div>', /contains javascript URL/],
    ['javascript formaction quoted', '<button formaction="javascript:alert(1)">x</button>', /contains javascript URL/],
    ['javascript formaction unquoted', '<button formaction=javascript:alert(1)>x</button>', /contains javascript URL/],
    ['event attribute quoted', '<div onclick="alert(1)">x</div>', /contains event handler/],
    ['event attribute unquoted', '<img onerror=alert(1)>', /contains event handler/],
    ['object element', '<object data="/file"></object>', /contains object, embed, or applet/],
    ['embed element', '<embed src="/file">', /contains object, embed, or applet/],
    ['applet element', '<applet></applet>', /contains object, embed, or applet/],
    ['top target quoted', '<a target="_top" href="/">x</a>', /contains top-level navigation target/],
    ['top target unquoted self-closing', '<a target=_top/>', /contains top-level navigation target/],
    ['parent target quoted', "<a target='_parent' href='/'>x</a>", /contains top-level navigation target/],
    ['parent target unquoted', '<a target=_parent href=/>x</a>', /contains top-level navigation target/],
    ['base element', '<base href="/">', /contains base element/]
  ];

  for (const [label, fixture, expectedError] of dangerousFixtures) {
    const mutatedHtml = safeHtml.replace('</body>', `${fixture}</body>`);
    assert.notEqual(mutatedHtml, safeHtml, `${label} mutation was not applied`);
    assert.throws(() => assertSafeSnapshotHtml(mutatedHtml, label), expectedError, label);
  }
});

test('generated HTML snapshots are self-contained safe documents', () => {
  const manifest = embeddedJson(readPrototype(), 'html-snapshot-manifest');
  for (const snapshot of manifest) {
    const html = readSnapshotAsset(snapshot.htmlPath);
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
    assertSafeSnapshotHtml(html, snapshot.fileName);
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
