import { access, readFile, stat } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const required = [
  'static/css/app.css',
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

process.stdout.write(`verified ${required.length} local frontend assets\n`);
