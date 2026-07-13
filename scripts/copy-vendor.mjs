import { copyFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const files = [
  ['node_modules/alpinejs/dist/cdn.min.js', 'static/vendor/alpine.min.js'],
  ['node_modules/marked/lib/marked.umd.js', 'static/vendor/marked.umd.js'],
  ['node_modules/dompurify/dist/purify.min.js', 'static/vendor/purify.min.js'],
  ['node_modules/echarts/dist/echarts.min.js', 'static/vendor/echarts.min.js'],
  ['node_modules/mermaid/dist/mermaid.min.js', 'static/vendor/mermaid.min.js'],
  ['node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2', 'static/fonts/inter-latin-variable.woff2'],
  ['node_modules/@fontsource-variable/cormorant-garamond/files/cormorant-garamond-latin-wght-normal.woff2', 'static/fonts/cormorant-garamond-latin-variable.woff2'],
];

for (const [source, target] of files) {
  const from = resolve(root, source);
  const to = resolve(root, target);
  await mkdir(dirname(to), { recursive: true });
  await copyFile(from, to);
  process.stdout.write(`copied ${target}\n`);
}
