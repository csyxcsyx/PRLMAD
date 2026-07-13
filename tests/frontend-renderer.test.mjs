import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

async function createRenderer() {
  const dom = new JSDOM('<!doctype html><body><div id="target"></div><div id="toastRegion"></div><dialog id="mediaLightbox"><span data-lightbox-caption></span><img></dialog></body>', {
    runScripts: 'outside-only',
    url: 'http://127.0.0.1:8000/',
  });
  dom.window.PRLMAD = {
    normalizeAiText(value) {
      return String(value || '').replace(/\r\n?/g, '\n').trimStart();
    },
    loadScript() {
      return Promise.reject(new Error('lazy dependency unavailable in unit test'));
    },
    notify() {},
  };
  for (const file of [
    'static/vendor/marked.umd.js',
    'static/vendor/purify.min.js',
    'static/js/ai-renderer.js',
  ]) {
    dom.window.eval(await readFile(resolve(root, file), 'utf8'));
  }
  return dom;
}

async function settle(dom) {
  await new Promise(resolvePromise => dom.window.setTimeout(resolvePromise, 20));
}

test('sanitizes model HTML before rendering', async () => {
  const dom = await createRenderer();
  const html = dom.window.PRLMAD.renderMarkdown('<script>alert(1)</script><img src="x" onerror="alert(2)">');
  assert.equal(html.includes('<script'), false);
  assert.equal(html.includes('onerror'), false);
  assert.equal(html.includes('<img'), true);
  dom.window.close();
});

test('enhances final Markdown without changing the wire format', async () => {
  const dom = await createRenderer();
  const target = dom.window.document.getElementById('target');
  const markdown = `# 学习讲义

## 定义
教材结论[资料1]。

## 机制
| 状态 | 含义 |
| --- | --- |
| ready | 就绪 |

## 示例
\`\`\`python
print("ready")
\`\`\`

## 检查点
![状态变化图](/static/example.png)
`;
  dom.window.PRLMAD.renderInto(target, { content: markdown, final: true });
  await settle(dom);
  assert.equal(target.querySelectorAll('.ai-outline').length, 1);
  assert.equal(target.querySelectorAll('.citation-chip').length, 1);
  assert.equal(target.querySelectorAll('.table-scroll').length, 1);
  assert.equal(target.querySelectorAll('.code-shell').length, 1);
  assert.equal(target.querySelectorAll('.ai-figure').length, 1);
  assert.equal(target.querySelector('img').loading, 'lazy');
  dom.window.close();
});

test('defers expensive enhancement while streaming', async () => {
  const dom = await createRenderer();
  const target = dom.window.document.getElementById('target');
  dom.window.PRLMAD.renderInto(target, { content: '```js\nconst ready = true;\n```', final: false });
  await settle(dom);
  assert.equal(target.querySelectorAll('pre').length, 1);
  assert.equal(target.querySelectorAll('.code-shell').length, 0);
  dom.window.close();
});

test('keeps Mermaid source when the lazy renderer is unavailable', async () => {
  const dom = await createRenderer();
  const target = dom.window.document.getElementById('target');
  dom.window.PRLMAD.renderInto(target, { content: '```mermaid\ngraph TD\nA-->B\n```', final: true });
  await settle(dom);
  assert.equal(target.querySelectorAll('.diagram-error').length, 1);
  assert.equal(target.textContent.includes('graph TD'), true);
  dom.window.close();
});
