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
