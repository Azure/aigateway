// Lists the AI Gateway product releases published at https://ai.gateway.azure.com/docs/ and shows which ones
// labs/RELEASE-NOTES.md doesn't cover yet. The docs site is a single-page app that a plain fetch can't read, so the
// changelog and the pages are read from its JavaScript bundle.
//
//   node tools/product-releases.mjs                 new releases: changelog entry and full release page
//   node tools/product-releases.mjs --all           the same for every release
//   node tools/product-releases.mjs --json          machine-readable output
//   node tools/product-releases.mjs --check         exit 1 when a release isn't covered (for CI)
//   node tools/product-releases.mjs --pages         list every docs page
//   node tools/product-releases.mjs --page /docs/policies
//                                                   print one docs page as text
//   node tools/product-releases.mjs --save-bundle /tmp/aigw-docs.js
//                                                   also save the docs bundle, to search it for portal labels
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const DOCS = 'https://ai.gateway.azure.com/docs/';
const ORIGIN = new URL(DOCS).origin;
const NOTES = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'RELEASE-NOTES.md');

const args = process.argv.slice(2);
const flag = (name) => args.includes(name);
const option = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : undefined; };

async function get(url) {
  const res = await fetch(url, { headers: { 'user-agent': 'ai-gateway-labs-release-check' } });
  if (!res.ok) throw new Error(`GET ${url} returned ${res.status}`);
  return res.text();
}

// The changelog is a template literal: "\r" escapes before real line breaks, and "\`" or "\${" for literal characters.
const unescape = (s) => s.replace(/\\r/g, '').replace(/\\([`$\\])/g, '$1');

function parseReleases(bundle) {
  const start = bundle.search(/\n## \d{4}-\d{2}-\d{2}\\r\n/);
  if (start < 0) return [];
  let end = start;
  while (end < bundle.length && !(bundle[end] === '`' && bundle[end - 1] !== '\\')) end++;
  const text = unescape(bundle.slice(start, end)).trim();
  return text.split(/^(?=## \d{4}-\d{2}-\d{2}\s*$)/m).map((block) => {
    const date = block.match(/^## (\d{4}-\d{2}-\d{2})/)?.[1];
    const heading = block.match(/^### \[(.+?)\]\((\/docs\/releases\/[^)]+)\)/m) || block.match(/^### (.+)$/m);
    if (!date || !heading) return null;
    const body = block.replace(/^## .*\n+/, '').replace(/^### .*\n+/m, '').trim();
    const route = heading[2] || `/docs/releases/${date}`;
    return {
      date,
      title: heading[1].trim(),
      url: new URL(route, ORIGIN).href,
      route,
      summary: body.replace(/<!--[\s\S]*?-->/g, '').trim().split(/\n\s*\n/)[0].replace(/\s+/g, ' '),
      docs: [...body.matchAll(/<!-- docs: (\S+) -->/g)].map((m) => m[1]),
      features: [...body.matchAll(/^#### (.+)$/gm)].map((m) => m[1].trim()),
      body: body.replace(/<!-- docs: .* -->\n*/g, '').trim(),
    };
  }).filter(Boolean);
}

// Every docs page is a React component that the router maps to a path.
function listPages(bundle) {
  return [...bundle.matchAll(/path:"(\/docs[^"]*)",element:[\w$]+\.jsx\(([\w$]+),\{\}\)/g)].map((m) => ({ route: m[1], component: m[2] }));
}

// Renders a page component's JSX back to Markdown-like text: headings, paragraphs, list items, links, and the
// URLs of its screenshots.
function pageText(bundle, route) {
  const component = listPages(bundle).find((p) => p.route === route)?.component;
  const start = component ? bundle.indexOf(`function ${component}(`) : -1;
  if (start < 0) return null;
  const end = bundle.slice(start + 1).search(/\}(?:function [\w$]+\(|const [\w$]+=|let [\w$]+=|var [\w$]+=)/);
  const code = bundle.slice(start, end < 0 ? undefined : start + 1 + end + 1);
  const assets = new Map([...bundle.matchAll(/(?:const |,)([\w$]+)="(\/assets\/[^"]+\.(?:png|jpe?g|svg|webp|gif|mp4))"/g)].map((m) => [m[1], m[2]]));
  const block = { h1: '\n\n# ', h2: '\n\n## ', h3: '\n\n### ', h4: '\n\n#### ', p: '\n\n', li: '\n- ', figcaption: '\n\nCaption: ', pre: '\n\n', tr: '\n|', td: ' | ', th: ' | ', time: '\n\n' };
  const literal = (x) => { try { return JSON.parse(`"${x}"`); } catch { return x; } };
  const re = /[\w$]+\.jsxs?\("(\w+)"|(?:children|alt):"((?:[^"\\]|\\.)*)"|[[,]"((?:[^"\\]|\\.)*)"(?=[,\]])|src:([\w$]+)|href:"([^"]+)"/g;
  let out = '';
  for (const m of code.matchAll(re)) {
    if (m[1]) out += block[m[1]] ?? '';
    else if (m[2] !== undefined) out += literal(m[2]);
    else if (m[3] !== undefined) out += literal(m[3]);
    else if (m[4] && assets.has(m[4])) out += `\n\nImage: ${ORIGIN}${assets.get(m[4])}\nAlt text: `;
    else if (m[5]) out += ` (${new URL(m[5], ORIGIN).href}) `;
  }
  return out.replace(/[ \t]+\n/g, '\n').replace(/ {2,}/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
}

async function loadReleases() {
  const html = await get(DOCS);
  const scripts = [...new Set([...html.matchAll(/(?:src|href)="([^"]+\.js)"/g)].map((m) => new URL(m[1], DOCS).href))];
  if (!scripts.length) throw new Error(`No JavaScript bundle found in ${DOCS}`);
  for (const url of scripts) {
    const bundle = await get(url);
    const releases = parseReleases(bundle);
    if (releases.length) return { releases, bundle, bundleUrl: url };
  }
  throw new Error(`No changelog ("## YYYY-MM-DD" followed by "### [Title](/docs/releases/...)") found in ${scripts.join(', ')}. The docs site changed; read ${DOCS} in a browser instead.`);
}

const notes = fs.existsSync(NOTES) ? fs.readFileSync(NOTES, 'utf8') : '';
const covered = (r) => notes.includes(`/docs/releases/${r.date}`);

const { releases, bundle, bundleUrl } = await loadReleases();
const saveTo = option('--save-bundle');
if (saveTo) fs.writeFileSync(saveTo, unescape(bundle));

if (flag('--pages')) {
  for (const p of listPages(bundle)) console.log(`${ORIGIN}${p.route}`);
  process.exit(0);
}
if (option('--page')) {
  const route = new URL(option('--page'), DOCS).pathname.replace(/\/$/, '') || '/docs';
  const text = pageText(bundle, route);
  if (!text) { console.error(`No docs page at ${route}. Run with --pages to list them.`); process.exit(1); }
  console.log(text);
  process.exit(0);
}

for (const r of releases) r.page = pageText(bundle, r.route);
const missing = releases.filter((r) => !covered(r));
const shown = flag('--all') ? releases : missing;

if (flag('--json')) {
  console.log(JSON.stringify({ source: DOCS, bundle: bundleUrl, releases: releases.map((r) => ({ ...r, covered: covered(r) })) }, null, 2));
} else {
  console.log(`Product releases at ${DOCS} (${releases.length}), newest first:\n`);
  for (const r of releases) console.log(`  ${covered(r) ? '✓' : '✗'} ${r.date}  ${r.title}`);
  console.log(missing.length
    ? `\n${missing.length} release(s) not in labs/RELEASE-NOTES.md yet. Follow "Update the labs" in AGENTS.md.`
    : '\nlabs/RELEASE-NOTES.md covers every product release.');
  for (const r of shown) {
    console.log(`\n${'═'.repeat(100)}\n${r.date}: ${r.title}\n${r.url}\n`);
    if (r.docs.length) console.log(`Product docs: ${r.docs.join(' , ')}\n`);
    console.log(`── Changelog entry ──\n\n${r.body}\n`);
    console.log(`── Release page ──\n\n${r.page ?? `(not found in the bundle; open ${r.url} in a browser)`}`);
  }
  if (saveTo) console.log(`\nSaved the docs bundle to ${saveTo}. Search it for portal labels, for example: grep -o ".\\{80\\}Supported MCP versions.\\{120\\}" ${saveTo}`);
}
if (flag('--check') && missing.length) process.exit(1);
