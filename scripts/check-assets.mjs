import { access, readFile, readdir, stat } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const required = [
  'static/css/app.css',
  'static/js/app.js',
  'static/js/ai-renderer.js',
  'static/vendor/alpine.min.js',
  'static/vendor/marked.umd.js',
  'static/vendor/purify.min.js',
  'static/vendor/echarts.min.js',
  'static/vendor/mermaid.min.js',
  'static/fonts/inter-latin-variable.woff2',
  'static/fonts/cormorant-garamond-latin-variable.woff2',
];

for (const file of required) {
  const path = resolve(root, file);
  await access(path);
  const info = await stat(path);
  if (!info.size) throw new Error(`${file} is empty`);
}

const templates = await readFile(resolve(root, 'templates/base.html'), 'utf8');
const remoteAsset = /<(?:script|link)[^>]+(?:src|href)=["']https?:\/\//i;
if (remoteAsset.test(templates)) {
  throw new Error('templates/base.html still contains a remote runtime asset');
}
if (templates.includes('echarts.min.js') || templates.includes('mermaid.min.js')) {
  throw new Error('heavy visualization libraries must not be loaded by the base shell');
}

async function listFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map(entry => {
    const path = resolve(directory, entry.name);
    return entry.isDirectory() ? listFiles(path) : [path];
  }));
  return nested.flat();
}

const templateFiles = await listFiles(resolve(root, 'templates'));
for (const file of templateFiles.filter(file => file.endsWith('.html'))) {
  const source = await readFile(file, 'utf8');
  if (remoteAsset.test(source)) throw new Error(`${file} contains a remote runtime asset`);
  if (/\bx-html\s*=/.test(source)) throw new Error(`${file} bypasses the safe AI renderer with x-html`);
}

const criticalAssets = [
  'static/css/app.css',
  'static/js/app.js',
  'static/js/ai-renderer.js',
  'static/vendor/alpine.min.js',
  'static/vendor/marked.umd.js',
  'static/vendor/purify.min.js',
];
let criticalBytes = 0;
for (const file of criticalAssets) criticalBytes += (await stat(resolve(root, file))).size;
if (criticalBytes > 300 * 1024) {
  throw new Error(`critical frontend assets exceed 300 KiB (${criticalBytes} bytes)`);
}

process.stdout.write(`verified ${required.length} local frontend assets; critical payload ${criticalBytes} bytes\n`);
