// Lists the AI Gateway product releases published at https://ai.gateway.azure.com/docs/ and shows which ones
// labs/RELEASE-NOTES.md doesn't cover yet. The docs site is a single-page app that a plain fetch can't read: the
// changelog and the docs pages live in lazy-loaded JavaScript chunks, so the tool follows those chunks. The full
// release pages come from the site's /release-notes.md.
//
//   node tools/product-releases.mjs                 new releases: changelog entry and full release page
//   node tools/product-releases.mjs --all           the same for every release
//   node tools/product-releases.mjs --json          machine-readable output
//   node tools/product-releases.mjs --check         exit 1 when a release isn't covered (for CI)
//   node tools/product-releases.mjs --pages         list every docs page
//   node tools/product-releases.mjs --page /docs/security/authenticate-entra
//                                                   print one docs page as text
//   node tools/product-releases.mjs --save-bundle /tmp/aigw-docs.js
//                                                   also save the docs bundle and its chunks, to search them for
//                                                   portal labels
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const DOCS = 'https://ai.gateway.azure.com/docs/';
const ORIGIN = new URL(DOCS).origin;
const RELEASE_NOTES = `${ORIGIN}/release-notes.md`;
const NOTES = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'RELEASE-NOTES.md');

const args = process.argv.slice(2);
const flag = (name) => args.includes(name);
const option = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : undefined; };

// Retries network errors, 429 and 5xx twice, then throws, so a lost chunk never passes for an empty one.
async function get(url, attempts = 3) {
  for (let attempt = 1; ; attempt++) {
    let res;
    try {
      res = await fetch(url, { headers: { 'user-agent': 'ai-gateway-labs-release-check' } });
    } catch (e) {
      if (attempt >= attempts) throw new Error(`GET ${url} failed: ${e.cause?.code ?? e.message}`);
    }
    if (res?.ok) return res.text();
    const transient = !res || res.status === 429 || res.status >= 500;
    if (res && (!transient || attempt >= attempts)) throw new Error(`GET ${url} returned ${res.status}`);
    await new Promise((resolve) => setTimeout(resolve, 1000 * attempt));
  }
}

// Template literals keep "\r" escapes before real line breaks, and "\`" or "\${" for literal characters.
const unescape = (s) => s.replace(/\\r/g, '').replace(/\\([`$\\])/g, '$1');
const literal = (x) => { try { return JSON.parse(`"${x}"`); } catch { return x; } };

// Loads the entry scripts of the docs page, then every chunk they import, directly or through other chunks.
async function loadChunks() {
  const html = await get(DOCS);
  const chunks = new Map();
  let next = [...new Set([...html.matchAll(/(?:src|href)="([^"]+\.js)"/g)].map((m) => new URL(m[1], DOCS).href))];
  if (!next.length) throw new Error(`No JavaScript bundle found in ${DOCS}`);
  while (next.length) {
    const batch = next.splice(0, 24);
    const texts = await Promise.all(batch.map((url) => get(url)));
    batch.forEach((url, i) => chunks.set(url.split('/').pop(), texts[i]));
    for (const text of texts) {
      for (const m of text.matchAll(/["'`](?:\.\/|\/?assets\/)([\w.~-]+\.js)["'`]/g)) {
        const url = `${ORIGIN}/assets/${m[1]}`;
        if (!chunks.has(m[1]) && !next.includes(url)) next.push(url);
      }
    }
  }
  return chunks;
}

// The changelog ("What's new") is a Markdown template literal in its own chunk.
function parseChangelog(chunks) {
  for (const text of chunks.values()) {
    const start = text.search(/\n## \d{4}-\d{2}-\d{2}\\r\n/);
    if (start < 0) continue;
    let end = start;
    while (end < text.length && !(text[end] === '`' && text[end - 1] !== '\\')) end++;
    const body = unescape(text.slice(start, end)).trim();
    const releases = body.split(/^(?=## \d{4}-\d{2}-\d{2}\s*$)/m).map((block) => {
      const date = block.match(/^## (\d{4}-\d{2}-\d{2})/)?.[1];
      const heading = block.match(/^### \[(.+?)\]\((\/docs\/releases[^)]*)\)/m) || block.match(/^### (.+)$/m);
      if (!date || !heading) return null;
      const entry = block.replace(/^## .*\n+/, '').replace(/^### .*\n+/m, '').replace(/<!--[\s\S]*?-->\n*/g, '').trim();
      const route = heading[2] || `/docs/releases#release-${date}`;
      return { date, title: heading[1].trim(), url: new URL(route, ORIGIN).href, route, entry };
    }).filter(Boolean);
    if (releases.length) return releases;
  }
  return [];
}

// /release-notes.md has one "## YYYY-MM-DD | Title" section per release, with its full text and docs links.
function parseReleaseNotes(markdown) {
  const sections = [...markdown.matchAll(/^## (\d{4}-\d{2}-\d{2}) \| (.+)$/gm)];
  return new Map(sections.map((m, i) => {
    const body = markdown.slice(m.index + m[0].length, sections[i + 1]?.index).trim();
    return [m[1], { title: m[2].trim(), body }];
  }));
}

// The docs navigation is a nested array of [id, title, route, browser title, isMarkdown, component or source, hidden].
function listPages(chunks) {
  const pages = new Map();
  for (const text of chunks.values()) {
    for (const m of text.matchAll(/\["[\w-]+","((?:[^"\\]|\\.)*)","(\/docs[^"]*)",(?:"(?:[^"\\]|\\.)*"|null),([01]),"([^"]+)"(?:,!0)?\]/g)) {
      if (!pages.has(m[2])) pages.set(m[2], { route: m[2], title: literal(m[1]), markdown: m[3] === '1', source: m[4] });
    }
  }
  return [...pages.values()];
}

// Markdown pages are template literals in chunks that the Markdown page component imports by source path.
function markdownPage(chunks, source) {
  for (const text of chunks.values()) {
    const m = text.match(new RegExp(`"[./]*content/docs/${source.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}":\\(\\)=>[\\w$]+\\(\\(\\)=>import\\("\\./([^"]+\\.js)"\\)`));
    const chunk = m && chunks.get(m[1]);
    const body = chunk?.match(/`((?:[^`\\]|\\.)*)`/);
    if (body) return unescape(body[1]).replace(/^\s*(?:<!--[\s\S]*?-->\s*)*/, '').trim();
  }
  return null;
}

// React pages are lazy components; renders a component's JSX back to Markdown-like text: headings, paragraphs, list
// items, links, and the URLs of its screenshots.
function reactPage(chunks, component) {
  let code;
  for (const text of chunks.values()) {
    const loader = text.match(new RegExp(`import\\("\\./([^"]+\\.js)"\\)(?:(?!import\\()[^;]){0,400}?\\.then\\([\\w$]+=>\\(\\{default:[\\w$]+\\.${component}\\}\\)\\)`));
    const chunk = loader && chunks.get(loader[1]);
    if (!chunk) continue;
    const exported = chunk.match(new RegExp(`export\\{[^}]*?([\\w$]+) as ${component}\\b`))?.[1] || component;
    const start = chunk.indexOf(`function ${exported}(`);
    if (start < 0) continue;
    const end = chunk.slice(start + 1).search(/\}(?:function [\w$]+\(|const [\w$]+=|let [\w$]+=|var [\w$]+=|export\{)/);
    code = { chunk, body: chunk.slice(start, end < 0 ? undefined : start + 1 + end + 1) };
    break;
  }
  if (!code) return null;
  const assets = new Map([...code.chunk.matchAll(/(?:const |,)([\w$]+)="(\/assets\/[^"]+\.(?:png|jpe?g|svg|webp|gif|mp4))"/g)].map((m) => [m[1], m[2]]));
  const block = { h1: '\n\n# ', h2: '\n\n## ', h3: '\n\n### ', h4: '\n\n#### ', p: '\n\n', li: '\n- ', figcaption: '\n\nCaption: ', pre: '\n\n', tr: '\n|', td: ' | ', th: ' | ', time: '\n\n' };
  const re = /[\w$]+\.jsxs?\("(\w+)"|(?:children|alt|title|label|value):"((?:[^"\\]|\\.)*)"|[[,]"((?:[^"\\]|\\.)*)"(?=[,\]])|src:([\w$]+)|href:"([^"]+)"|`((?:[^`\\]|\\.){40,})`/g;
  let out = '';
  for (const m of code.body.matchAll(re)) {
    if (m[1]) out += block[m[1]] ?? '';
    else if (m[2] !== undefined) out += literal(m[2]);
    else if (m[3] !== undefined) out += literal(m[3]);
    else if (m[4] && assets.has(m[4])) out += `\n\nImage: ${ORIGIN}${assets.get(m[4])}\nAlt text: `;
    else if (m[5]) out += ` (${new URL(m[5], ORIGIN).href}) `;
    else if (m[6] !== undefined) out += `\n\n\`\`\`\n${unescape(m[6])}\n\`\`\`\n\n`;
  }
  return out.replace(/[ \t]+\n/g, '\n').replace(/ {2,}/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
}

function pageText(chunks, releaseNotes, route) {
  if (route === '/docs/releases') return releaseNotes;
  const page = listPages(chunks).find((p) => p.route === route);
  if (!page) return null;
  return page.markdown ? markdownPage(chunks, page.source) : reactPage(chunks, page.source);
}

async function loadReleases() {
  const [chunks, releaseNotes] = await Promise.all([loadChunks(), get(RELEASE_NOTES)]);
  const pages = parseReleaseNotes(releaseNotes);
  const changelog = parseChangelog(chunks);
  const dates = [...new Set([...changelog.map((r) => r.date), ...pages.keys()])].sort().reverse();
  const releases = dates.map((date) => {
    const entry = changelog.find((r) => r.date === date);
    const page = pages.get(date);
    const route = entry?.route ?? `/docs/releases#release-${date}`;
    const docs = [...new Set([...`${entry?.entry ?? ''}\n${page?.body ?? ''}`.matchAll(/\]\((\/docs\/[^)\s]+)\)/g)].map((m) => new URL(m[1], ORIGIN).href))];
    return {
      date,
      title: entry?.title ?? page.title,
      url: new URL(route, ORIGIN).href,
      route,
      summary: (entry?.entry ?? page.body).split(/\n\s*\n/)[0].replace(/\s+/g, ' '),
      docs,
      features: [...(page?.body ?? '').matchAll(/^- \*\*(.+?)\.?\*\*/gm)].map((m) => m[1].trim()),
      body: entry?.entry ?? '',
      page: page?.body ?? null,
    };
  });
  if (!releases.length) throw new Error(`No releases found in ${RELEASE_NOTES} or the changelog chunk of ${DOCS}. The docs site changed; read ${DOCS} in a browser instead.`);
  return { releases, chunks, releaseNotes };
}

const notes = fs.existsSync(NOTES) ? fs.readFileSync(NOTES, 'utf8') : '';
const covered = (r) => notes.includes(`/docs/releases/${r.date}`) || notes.includes(`/docs/releases#release-${r.date}`);

const { releases, chunks, releaseNotes } = await loadReleases();
const saveTo = option('--save-bundle');
if (saveTo) fs.writeFileSync(saveTo, [...chunks].map(([name, text]) => `\n/* ${name} */\n${unescape(text)}`).join('\n') + `\n/* release-notes.md */\n${releaseNotes}`);

if (flag('--pages')) {
  const pages = listPages(chunks);
  if (!pages.some((p) => p.route === '/docs/releases')) pages.push({ route: '/docs/releases', title: 'Release notes' });
  for (const p of pages) console.log(`${ORIGIN}${p.route}  ${p.title}`);
  process.exit(0);
}
if (option('--page')) {
  const route = new URL(option('--page'), DOCS).pathname.replace(/\/$/, '') || '/docs';
  const text = pageText(chunks, releaseNotes, route);
  if (!text) { console.error(`No docs page at ${route}. Run with --pages to list them.`); process.exit(1); }
  console.log(text);
  process.exit(0);
}

const missing = releases.filter((r) => !covered(r));
const shown = flag('--all') ? releases : missing;

if (flag('--json')) {
  console.log(JSON.stringify({ source: DOCS, releaseNotes: RELEASE_NOTES, releases: releases.map((r) => ({ ...r, covered: covered(r) })) }, null, 2));
} else {
  console.log(`Product releases at ${DOCS} (${releases.length}), newest first:\n`);
  for (const r of releases) console.log(`  ${covered(r) ? '✓' : '✗'} ${r.date}  ${r.title}`);
  console.log(missing.length
    ? `\n${missing.length} release(s) not in labs/RELEASE-NOTES.md yet. Follow "Update the labs" in AGENTS.md.`
    : '\nlabs/RELEASE-NOTES.md covers every product release.');
  for (const r of shown) {
    console.log(`\n${'═'.repeat(100)}\n${r.date}: ${r.title}\n${r.url}\n`);
    if (r.docs.length) console.log(`Product docs: ${r.docs.join(' , ')}\n`);
    if (r.body) console.log(`── Changelog entry ──\n\n${r.body}\n`);
    console.log(`── Release page ──\n\n${r.page ?? `(not found in ${RELEASE_NOTES}; open ${r.url} in a browser)`}`);
  }
  if (saveTo) console.log(`\nSaved the docs bundle to ${saveTo}. Search it for portal labels, for example: grep -o ".\\{80\\}Supported MCP versions.\\{120\\}" ${saveTo}`);
}
if (flag('--check') && missing.length) process.exit(1);
