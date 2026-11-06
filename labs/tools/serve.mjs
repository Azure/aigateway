#!/usr/bin/env node
// Serves ../docs under /aigateway/ to mirror GitHub Pages. Usage: node tools/serve.mjs [port]
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'docs');
const BASE = '/aigateway/';
// The repo was renamed from Azure/ai-gateway, so forward old preview links to the same page.
const LEGACY_BASE = '/ai-gateway/';
const PORT = Number(process.argv[2] || process.env.PORT || 4173);
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp', '.mp4': 'video/mp4', '.webm': 'video/webm', '.vtt': 'text/vtt; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8', '.md': 'text/markdown; charset=utf-8', '.xml': 'application/xml', '.ico': 'image/x-icon',
};

http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname.startsWith(LEGACY_BASE)) {
    res.writeHead(301, { Location: `${BASE}${url.pathname.slice(LEGACY_BASE.length)}${url.search}` });
    return res.end();
  }
  if (!url.pathname.startsWith(BASE)) { res.writeHead(302, { Location: BASE }); return res.end(); }
  let rel;
  try { rel = decodeURIComponent(url.pathname.slice(BASE.length)); } catch { res.writeHead(400); return res.end(); }
  let file = path.join(ROOT, rel);
  // Require a path separator after ROOT, so a sibling such as docs-private/ can't pass the check.
  if (file !== ROOT && !file.startsWith(ROOT + path.sep)) { res.writeHead(403); return res.end(); }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) {
    if (!url.pathname.endsWith('/')) { res.writeHead(301, { Location: `${url.pathname}/${url.search}` }); return res.end(); }
    file = path.join(file, 'index.html');
  }
  if (!fs.existsSync(file)) {
    res.writeHead(404, { 'Content-Type': TYPES['.html'] });
    return fs.createReadStream(path.join(ROOT, '404.html')).pipe(res);
  }
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream', 'Cache-Control': 'no-cache' });
  fs.createReadStream(file).pipe(res);
}).listen(PORT, () => console.log(`Serving docs/ at http://localhost:${PORT}${BASE}`));
