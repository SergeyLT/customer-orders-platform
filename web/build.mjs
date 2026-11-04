import { createHash } from 'node:crypto';
import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.dirname(fileURLToPath(import.meta.url));
const output = path.join(root, 'dist');
await rm(output, { recursive: true, force: true });
await mkdir(path.join(output, 'assets'), { recursive: true });
const pages = {};
for (const page of ['index.html', 'admin.html']) pages[page] = await readFile(path.join(root, page), 'utf8');
for (const file of ['styles.css', 'app.js', 'form-data.js', 'analytics.js', 'admin.js', 'admin.css']) {
  let contents = await readFile(path.join(root, file), 'utf8');
  if (file === 'app.js') {
    const module = await readFile(path.join(root, 'form-data.js'), 'utf8');
    const hash = createHash('sha256').update(module).digest('hex').slice(0, 12);
    contents = contents.replace("'./form-data.js'", `'./form-data.${hash}.js'`);
  }
  const hash = createHash('sha256').update(contents).digest('hex').slice(0, 12);
  const name = file.replace(/\.(css|js)$/, `.${hash}.$1`);
  await writeFile(path.join(output, 'assets', name), contents);
  for (const page of Object.keys(pages)) pages[page] = pages[page].replaceAll(`./${file}`, `/assets/${name}`);
}
for (const [page, html] of Object.entries(pages)) await writeFile(path.join(output, page), html);
await cp(path.join(root, 'swagger-auth.js'), path.join(output, 'assets', 'swagger-auth.js'));
await cp(path.join(root, 'favicon.svg'), path.join(output, 'favicon.svg'));
await mkdir(path.join(output, 'assets', 'swagger'), { recursive: true });
for (const name of ['swagger-ui-bundle.js', 'swagger-ui.css']) {
  await cp(path.join(root, 'node_modules', 'swagger-ui-dist', name), path.join(output, 'assets', 'swagger', name));
}
console.log('Frontend собран в web/dist: хешированные CSS/JS и локальные ресурсы Swagger.');
