import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

// resolve() drops the trailing separator so the `root + sep` containment check below matches real files.
const root = resolve(fileURLToPath(new URL('../', import.meta.url)));
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.json': 'application/json', '.md': 'text/plain' };
const port = Number(process.env.PORT || 5173);
http.createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    // Never serve hidden files or folders such as .env (Gemini key) or .git. Gemini endpoints live in scripts/serve.py.
    if (pathname.split('/').some(part => part.startsWith('.'))) { res.writeHead(404).end('Not found'); return; }
    const path = resolve(root, '.' + pathname);
    if (path !== root && !path.startsWith(root + sep)) { res.writeHead(403).end(); return; }
    const file = extname(path) ? path : resolve(root, 'index.html');
    const body = await readFile(file);
    res.writeHead(200, { 'Content-Type': types[extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-cache' }).end(body);
  } catch { res.writeHead(404).end('Not found'); }
}).listen(port, '127.0.0.1', () => console.log(`GeoIssue ready at http://127.0.0.1:${port}`));
