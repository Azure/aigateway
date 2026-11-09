#!/usr/bin/env node
// Builds the Azure AI Gateway Labs site from labs/<NN-slug>/README.md into ../docs (GitHub Pages).
//   node build.mjs           sync the GitHub chrome of the lab READMEs, then build once
//   node build.mjs --sync    only sync the lab READMEs and labs/README.md (see site/github.mjs)
//   node build.mjs --strict  build without writing sources; fail on warnings, including out-of-sync READMEs
//   node build.mjs --watch   rebuild on change
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { initHighlighter, renderLab, escapeHtml } from './site/markdown.mjs';
import { parseLab, stripGitHub, syncLab, syncIndex, syncSkill, findVideo, ghSlug } from './site/github.mjs';
import { readSetupTasks, inlineMd } from './site/setup.mjs';
import { layout, homePage, catalogPage, labPage, releaseNotesPage, setupPage, troubleshootingPage, notFoundPage } from './site/templates.mjs';

const LABS = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(LABS, '..');
// LABS_OUT and LABS_SITE_URL build a copy for another host (see tools/deploy-swa.sh).
const OUT = process.env.LABS_OUT ? path.resolve(process.env.LABS_OUT) : path.join(ROOT, 'docs');
const SITE_SRC = path.join(LABS, 'site');
const SKILL_NAME = 'azure-ai-gateway-labs';
const SKILL_FILE = path.join(LABS, 'skills', SKILL_NAME, 'SKILL.md');
const BASE_URL = (process.env.LABS_SITE_URL || 'https://azure.github.io/aigateway/').replace(/\/?$/, '/');
const BASE_PATH = new URL(BASE_URL).pathname;
const RELEASE_NOTES = path.join(LABS, 'RELEASE-NOTES.md');
const SETUP = path.join(LABS, 'SETUP.md');
const TROUBLESHOOTING = path.join(LABS, 'TROUBLESHOOTING.md');
const GENERATED = ['index.html', '404.html', 'labs', 'release-notes', 'setup', 'troubleshooting', 'assets', 'search.json', 'llms.txt', 'llms-full.txt', 'skills', 'sitemap.xml', 'robots.txt', '.nojekyll'];
const MEDIA_RE = /\.(png|jpe?g|gif|webp|svg|mp4|webm|avif)$/i;
const REQUIRED = ['title', 'summary', 'category', 'level', 'duration', 'tracks', 'objectives'];

const warnings = [];
const warn = (msg) => warnings.push(msg);
// The Setup guide's tasks, which the <!-- setup: … --> directives list. Read from SETUP.md at the start of a build.
let setupTasks = [];

function rmGenerated() {
  fs.mkdirSync(OUT, { recursive: true });
  for (const f of GENERATED) fs.rmSync(path.join(OUT, f), { recursive: true, force: true });
}

function copyDir(src, dest, filter = () => true) {
  if (!fs.existsSync(src)) return;
  for (const e of fs.readdirSync(src, { withFileTypes: true })) {
    if (e.name.startsWith('.')) continue;
    const s = path.join(src, e.name);
    const d = path.join(dest, e.name);
    if (e.isDirectory()) copyDir(s, d, filter);
    else if (filter(s)) { fs.mkdirSync(dest, { recursive: true }); fs.copyFileSync(s, d); }
  }
}

function write(rel, content) {
  const f = path.join(OUT, rel);
  fs.mkdirSync(path.dirname(f), { recursive: true });
  fs.writeFileSync(f, content);
}

// A lab folder with a root azure.yaml is an azd template. azd can't init from a repo subfolder, so the lab runs azd
// in labs/<slug> of a clone: it either clones the repo itself, lists the setup guide's clone task in a
// <!-- setup: … --> checklist, or links to that task. A code block
// must move into the lab folder, and a clone block must move into it too and use the site's branch: the default
// branch, or --branch with that name.
function checkTemplate(lab, site) {
  if (!fs.existsSync(path.join(lab.dir, 'azure.yaml'))) return;
  const folder = `labs/${lab.slug}`;
  const cd = new RegExp(`\\b(?:cd|Set-Location)\\s+\\S*${folder}\\s*(?:&&\\s*)?$`, 'm');
  const blocks = [...lab.content.matchAll(/^```[^\n]*\n([\s\S]*?)^```/gm)].map((m) => m[1]);
  const clones = blocks.filter((b) => /\bgit clone\b/.test(b) && b.includes(site.repo));
  const listsClone = /^<!--\s*setup:[^>]*\bclone\b[^>]*-->/m.test(lab.content);
  if (!clones.length && !listsClone && !lab.content.includes('SETUP.md#clone-the-labs-repo')) {
    warn(`${lab.slug}: has an azd template, but doesn't clone ${site.repo}, list the clone setup task, or link to SETUP.md#clone-the-labs-repo`);
  }
  if (!blocks.some((b) => cd.test(b))) warn(`${lab.slug}: has an azd template, but no code block moves into ${folder}`);
  for (const b of clones) {
    if (!cd.test(b)) warn(`${lab.slug}: the template clone block doesn't move into ${folder}`);
    const branch = b.match(/--branch[\s=](\S+)/);
    if (branch && branch[1] !== site.branch) warn(`${lab.slug}: the template clone block uses branch ${branch[1]}, not ${site.branch}`);
  }
}

// Readers paste shell blocks into macOS zsh, so keep them paste-safe (AUTHORING.md, "CLI comments and status lines").
// Status-line emoji must come from the AUTHORING.md table: zsh 5.9 draws newer emoji as <0001f9e0> and miscounts
// the width of emoji with a variation selector. And when a paste arrives line by line, oh-my-zsh's url-quote-magic
// escapes the glob characters that follow a quoted URL on a line that continues an open quote or heredoc.
const SHELL_EMOJI = new Set([...'📦📝🏭✨🚀⏳🔌🔖🔧📂🚮🚨💡🔑👤🔐🌐🆔📍🤖🚦📊🔒📄✅']);
function checkShellBlocks(name, content) {
  const fences = /^[ \t]*```(bash|sh|zsh|shell|powershell|pwsh)\b[^\n]*\n([\s\S]*?)^[ \t]*```/gm;
  for (const [, lang, body] of content.matchAll(fences)) {
    for (const [e] of body.matchAll(/\p{Extended_Pictographic}\uFE0F?/gu)) {
      if (!SHELL_EMOJI.has(e)) warn(`${name}: ${lang} block uses ${e}; pick a status emoji from the AUTHORING.md table`);
    }
    if (lang === 'powershell' || lang === 'pwsh') continue;
    const stack = []; let heredoc = null;
    for (const line of body.split('\n')) {
      if (heredoc) {
        if (line.trim() === heredoc) heredoc = null;
        else if (urlThenGlob(line)) warn(`${name}: heredoc line "${line.trim().slice(0, 60)}" has a glob character after a URL`);
        continue;
      }
      if (stack.length && stack.at(-1) !== 'cmd' && urlThenGlob(line)) {
        warn(`${name}: quoted continuation "${line.trim().slice(0, 60)}" has a glob character after a URL; keep it on one line`);
      }
      for (let j = 0; j < line.length; j++) {
        const c = line[j]; const top = stack.at(-1);
        if (top === 'sq') { if (c === "'") stack.pop(); continue; }
        if (c === '\\') { j++; continue; }
        if (line.startsWith('$(', j)) { stack.push('cmd'); j++; continue; }
        if (top === 'dq') { if (c === '"') stack.pop(); continue; }
        if (c === "'") stack.push('sq');
        else if (c === '"') stack.push('dq');
        else if (c === ')' && top === 'cmd') stack.pop();
        else if (c === '#' && (j === 0 || /\s/.test(line[j - 1]))) break;
        else if (line.startsWith('<<', j)) {
          const m = line.slice(j).match(/^<<-?\s*['"]?(\w+)['"]?/);
          if (m) { heredoc = m[1]; j += m[0].length - 1; }
        }
      }
    }
  }
}
const urlThenGlob = (line) => /[a-z][\w+.-]*:\/\/[^\s"']*["']?[*?[\]^(|)~#{}=]/i.test(line);

function gitUpdated(dir) {
  try {
    const out = execFileSync('git', ['log', '-1', '--format=%cI', '--', path.relative(ROOT, dir)], { cwd: ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
    return out || null;
  } catch { return null; }
}

// Prefix ids inside inlined SVGs so several diagrams can share one page.
let svgCounter = 0;
function prefixSvgIds(svg) {
  const p = `s${(svgCounter += 1)}-`;
  const ids = [...svg.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]);
  let out = svg;
  for (const id of ids) {
    const esc = id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    out = out
      .replace(new RegExp(`\\bid="${esc}"`, 'g'), `id="${p}${id}"`)
      .replace(new RegExp(`url\\(#${esc}\\)`, 'g'), `url(#${p}${id})`)
      .replace(new RegExp(`(xlink:)?href="#${esc}"`, 'g'), (m, x) => `${x || ''}href="#${p}${id}"`)
      .replace(new RegExp(`(aria-labelledby|aria-describedby)="${esc}"`, 'g'), `$1="${p}${id}"`);
  }
  return out;
}

function loadLabs(catalog) {
  const dirs = fs.readdirSync(LABS, { withFileTypes: true })
    .filter((d) => d.isDirectory() && /^(\d{2}-[a-z0-9-]+|quickstart)$/.test(d.name) && fs.existsSync(path.join(LABS, d.name, 'README.md')))
    .map((d) => d.name);
  const cats = new Set(catalog.categories.map((c) => c.id));
  const labs = dirs.map((slug) => {
    const source = fs.readFileSync(path.join(LABS, slug, 'README.md'), 'utf8');
    const { data, matter: meta, body } = parseLab(source);
    // A build for another host (LABS_SITE_URL) points links to the labs site at that host.
    const content = stripGitHub(body).replaceAll(catalog.site.pages, BASE_URL);
    const notebook = fs.readdirSync(path.join(LABS, slug)).filter((f) => f.endsWith('.ipynb')).sort()[0] || null;
    // Notebooks ship without outputs: saved outputs can hold keys, tokens, and subscription IDs, and they bloat diffs.
    if (notebook) {
      const cells = JSON.parse(fs.readFileSync(path.join(LABS, slug, notebook), 'utf8')).cells || [];
      const ran = cells.filter((c) => c.cell_type === 'code' && ((c.outputs || []).length || c.execution_count != null)).length;
      if (ran) warn(`${slug}: ${notebook} has saved outputs in ${ran} code cell${ran === 1 ? '' : 's'}; clear all outputs before you commit`);
    } else if ((data.tracks || []).includes('code')) {
      warn(`${slug}: has a code track, but no ${slug}.ipynb; every lab with code runs it from a notebook`);
    }
    for (const k of REQUIRED) if (data[k] == null) warn(`${slug}: missing front matter "${k}"`);
    // "Do this: that" in a YAML list parses as a mapping and renders as [object Object].
    for (const k of ['objectives', 'tags', 'tracks', 'prereqs']) {
      if ((data[k] || []).some((v) => typeof v !== 'string')) warn(`${slug}: front matter "${k}" has an item that isn't text; avoid ": " in it`);
    }
    // The quick start is the one unnumbered lab: it shows a bolt instead of a number.
    const quick = slug === 'quickstart';
    const num = quick ? '⚡' : slug.slice(0, 2);
    if (data.category && !cats.has(data.category)) warn(`${slug}: unknown category "${data.category}"`);
    // The iac track's name: its first marker's label, else "Bicep + azd" for an azd template, else "Bicep".
    const iacLabel = body.match(/<!-- track: iac \| ([^>]+?) -->/)?.[1].trim()
      || (fs.existsSync(path.join(LABS, slug, 'azure.yaml')) ? 'Bicep + azd' : 'Bicep');
    return {
      ...data,
      slug,
      num,
      quick,
      label: quick ? 'Quick start' : `Lab ${num}`,
      short: catalog.shortTitles?.[slug] || data.title,
      tracks: data.tracks || [],
      iacLabel,
      tags: (data.tags || []).map(String),
      duration: Number(data.duration) || 0,
      order: data.order ?? Number(slug.slice(0, 2)),
      paths: catalog.paths.filter((p) => p.labs.includes(slug)).map((p) => p.id),
      updated: gitUpdated(path.join(LABS, slug)),
      notebook,
      video: findVideo(content),
      source,
      raw: `---\n${meta}\n---\n\n${content}`,
      content,
      dir: path.join(LABS, slug),
    };
  });
  labs.sort((a, b) => a.order - b.order || a.slug.localeCompare(b.slug));
  const known = new Set(labs.map((l) => l.slug));
  for (const p of catalog.paths) for (const s of p.labs) if (!known.has(s)) warn(`path "${p.id}" references missing lab ${s}`);
  for (const l of labs) for (const s of l.prereqs || []) if (!known.has(s)) warn(`${l.slug}: prereq ${s} not found`);
  return labs;
}

// labsPrefix is how the rendered page reaches the labs folder: lab pages are siblings, other pages use ../labs/.
function makeCtx(lab, site, knownSlugs, { labsPrefix = '../' } = {}) {
  const ghBase = `${site.repo}/blob/${site.branch}`;
  const media = new Set();
  const ctx = {
    labDir: lab.dir,
    media,
    setupTasks,
    setupHref(id) { return this.resolveLink(`${path.relative(lab.dir, SETUP).split(path.sep).join('/')}#${id}`).url; },
    ghBlob: (file) => `${ghBase}/labs/${lab.slug}/${file}`,
    resolveAsset(href) {
      if (/^(https?:)?\/\//.test(href) || href.startsWith('data:')) return href;
      const abs = path.resolve(lab.dir, decodeURI(href.split(/[?#]/)[0]));
      if (!fs.existsSync(abs)) warn(`${lab.slug}: missing image ${href}`);
      else if (abs.startsWith(lab.dir + path.sep)) media.add(path.relative(lab.dir, abs));
      return href;
    },
    inlineSvg(href) {
      if (/^(https?:)?\/\//.test(href)) return null;
      const abs = path.resolve(lab.dir, href);
      if (!abs.startsWith(path.join(LABS, 'assets', 'diagrams') + path.sep) || !fs.existsSync(abs)) return null;
      const svg = fs.readFileSync(abs, 'utf8').replace(/<\?xml[^>]*>\s*/, '').replace(/<!--[\s\S]*?-->/g, '');
      // The wrapping <figure role="img" aria-label> names the diagram, so the inner SVG is presentational.
      return prefixSvgIds(svg).replace(/<svg\b([^>]*)>/, (m, attrs) => `<svg${attrs.replace(/\s(role|aria-labelledby|aria-label)="[^"]*"/g, '')} aria-hidden="true" focusable="false">`);
    },
    resolveLink(href) {
      if (/^(https?:|mailto:)/.test(href)) return { url: href, external: !href.startsWith(BASE_URL) };
      if (href.startsWith('#')) return { url: href, external: false };
      const [p, hash] = href.split('#');
      const h = hash ? `#${hash}` : '';
      const abs = path.resolve(lab.dir, decodeURI(p));
      const relLabs = path.relative(LABS, abs).split(path.sep).join('/');
      const m = relLabs.match(/^(\d{2}-[a-z0-9-]+|quickstart)(?:\/(?:README\.md)?)?$/);
      if (m) {
        if (!knownSlugs.has(m[1])) warn(`${lab.slug}: link to unknown lab ${href}`);
        return { url: m[1] === lab.slug ? (h || './') : `${labsPrefix}${m[1]}/${h}`, external: false };
      }
      if (relLabs === 'README.md') return { url: `${labsPrefix}${h}`, external: false };
      if (relLabs === 'RELEASE-NOTES.md') return { url: `${labsPrefix}../release-notes/${h}`, external: false };
      if (relLabs === 'SETUP.md') return { url: path.posix.normalize(`${labsPrefix}../setup/`) + h, external: false };
      if (relLabs === 'TROUBLESHOOTING.md') return { url: path.posix.normalize(`${labsPrefix}../troubleshooting/`) + h, external: false };
      if (!fs.existsSync(abs)) warn(`${lab.slug}: broken link ${href}`);
      if (relLabs.startsWith('assets/') || (abs.startsWith(lab.dir + path.sep) && MEDIA_RE.test(abs))) {
        if (abs.startsWith(lab.dir + path.sep)) media.add(path.relative(lab.dir, abs));
        return { url: href, external: false };
      }
      const relRepo = path.relative(ROOT, abs).split(path.sep).join('/');
      if (relRepo.startsWith('..')) { warn(`${lab.slug}: link escapes repo ${href}`); return { url: href, external: false }; }
      const isDir = p.endsWith('/') || (fs.existsSync(abs) && fs.statSync(abs).isDirectory());
      return { url: `${site.repo}/${isDir ? 'tree' : 'blob'}/${site.branch}/${relRepo}${h}`, external: true };
    },
  };
  return ctx;
}

const htmlToText = (html) => html
  .replace(/<(script|style|svg)[\s\S]*?<\/\1>/g, ' ')
  .replace(/<pre[\s\S]*?<\/pre>/g, ' ')
  .replace(/<[^>]+>/g, ' ')
  .replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&')
  .replace(/\s+/g, ' ').trim();

function checkAnchors(lab, html, allHtml, guides) {
  const ids = new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));
  for (const m of html.matchAll(/href="#([^"]+)"/g)) if (!ids.has(m[1])) warn(`${lab.slug}: anchor #${m[1]} not found`);
  for (const m of html.matchAll(/href="\.\.\/(\d{2}-[a-z0-9-]+|quickstart)\/#([^"]+)"/g)) {
    const other = allHtml.get(m[1]);
    if (other && !other.includes(` id="${m[2]}"`)) warn(`${lab.slug}: anchor ../${m[1]}/#${m[2]} not found`);
  }
  checkGuideAnchors(lab.slug, html, guides);
}

// Links into the guides, from any page: ../setup/#id or ../../troubleshooting/#id.
const GUIDE_FILES = { setup: 'SETUP.md', troubleshooting: 'TROUBLESHOOTING.md' };
function checkGuideAnchors(name, html, guides) {
  for (const m of html.matchAll(/href="(?:\.\.\/)+(setup|troubleshooting)\/#([^"]+)"/g)) {
    const file = GUIDE_FILES[m[1]];
    if (guides[m[1]] == null) warn(`${name}: links to ${file}, but labs/${file} doesn't exist`);
    else if (!guides[m[1]].includes(` id="${m[2]}"`)) warn(`${name}: anchor ${file}#${m[2]} not found`);
  }
}

// Regenerates the GitHub-only chrome in the lab READMEs and labs/README.md. With check=true, reports stale
// files as warnings instead of writing them.
function syncSources(labs, catalog, { check = false } = {}) {
  const site = catalog.site;
  const stale = [];
  // GitHub readers get a footer link to their lab's section of TROUBLESHOOTING.md: the section that starts with a
  // link to the lab.
  const tsSections = new Map();
  if (fs.existsSync(TROUBLESHOOTING)) {
    for (const m of fs.readFileSync(TROUBLESHOOTING, 'utf8').matchAll(/^## (.+)\n\n[^\n]*?\]\((?:\.\/)?([a-z0-9-]+)\/README\.md\)/gm)) {
      if (!tsSections.has(m[2])) tsSections.set(m[2], ghSlug(m[1]));
    }
  }
  for (const lab of labs) {
    const file = path.join(lab.dir, 'README.md');
    const next = syncLab(lab.source, { lab, labs, catalog, site, setupTasks, troubleshooting: tsSections.get(lab.slug) });
    if (next === lab.source) continue;
    stale.push(path.relative(ROOT, file));
    if (!check) { fs.writeFileSync(file, next); lab.source = next; }
  }
  const indexFile = path.join(LABS, 'README.md');
  const index = fs.readFileSync(indexFile, 'utf8');
  const { text, missing } = syncIndex(index, { labs, catalog });
  for (const m of missing) warn(`labs/README.md: missing generated region "<!-- gh:begin ${m} -->"`);
  if (text !== index) {
    stale.push(path.relative(ROOT, indexFile));
    if (!check) fs.writeFileSync(indexFile, text);
  }
  const skill = fs.readFileSync(SKILL_FILE, 'utf8');
  const synced = syncSkill(skill, { labs, catalog });
  for (const m of synced.missing) warn(`${path.relative(ROOT, SKILL_FILE)}: missing generated region "<!-- gh:begin ${m} -->"`);
  if (synced.text !== skill) {
    stale.push(path.relative(ROOT, SKILL_FILE));
    if (!check) fs.writeFileSync(SKILL_FILE, synced.text);
  }
  if (check) for (const f of stale) warn(`${f} is out of sync with its metadata; run "npm run sync"`);
  else if (stale.length) console.log(`Synced ${stale.length} file(s): ${stale.join(', ')}`);
  return stale;
}

// Renders labs/RELEASE-NOTES.md. Each "## <date>" section is one product release: an "### <title>" heading and a
// link to https://ai.gateway.azure.com/docs/releases/YYYY-MM-DD, then the table that maps each change to a lab.
async function renderReleaseNotes(site, known, rendered, guides) {
  if (!fs.existsSync(RELEASE_NOTES)) return null;
  const source = stripGitHub(fs.readFileSync(RELEASE_NOTES, 'utf8'));
  const page = { dir: LABS, slug: 'release-notes' };
  const ctx = makeCtx(page, site, known, { labsPrefix: '../labs/' });
  const { html, toc } = await renderLab(source, ctx);
  for (const m of ctx.media) {
    const dest = path.join(OUT, 'release-notes', m);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(path.join(LABS, m), dest);
  }
  const ids = new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));
  for (const m of html.matchAll(/href="#([^"]+)"/g)) if (!ids.has(m[1])) warn(`RELEASE-NOTES.md: anchor #${m[1]} not found`);
  for (const m of html.matchAll(/href="\.\.\/labs\/(\d{2}-[a-z0-9-]+|quickstart)\/#([^"]+)"/g)) {
    if (!rendered.get(m[1])?.includes(` id="${m[2]}"`)) warn(`RELEASE-NOTES.md: anchor ${m[1]}#${m[2]} not found`);
  }
  checkGuideAnchors('RELEASE-NOTES.md', html, guides);

  const releases = [];
  for (const section of source.split(/^(?=## )/m).slice(1)) {
    const date = section.match(/^## (.+)/)[1].trim();
    const title = section.match(/^### (.+)/m)?.[1].trim();
    const product = section.match(/https:\/\/ai\.gateway\.azure\.com\/docs\/releases\/(\d{4}-\d{2}-\d{2})/)?.[1];
    if (!title || !product) continue;
    const id = toc.find((t) => t.text === date)?.id;
    releases.push({ date, title: title.replace(/[*`_]/g, ''), product, id });
  }
  if (!releases.length) warn('RELEASE-NOTES.md: no release sections found (expected "## <date>", "### <title>", and a product release link)');
  const sections = html.split(/(?=<h2 id=")/).map((part) => {
    const id = part.match(/^<h2 id="([^"]+)"/)?.[1];
    if (!id) return part;
    const r = releases.find((x) => x.id === id);
    return r ? `<section class="release" data-release="${r.product}">${part}</section>` : `<section class="release-extra">${part}</section>`;
  }).join('');
  return {
    source, html: sections, toc, releases,
    description: 'What changed in the Azure AI Gateway labs for each product release, and where to practice every new feature.',
  };
}

// Renders a guide page: labs/SETUP.md at /setup/, or labs/TROUBLESHOOTING.md at /troubleshooting/.
async function renderGuide(file, slug, site, known, rendered) {
  if (!fs.existsSync(file)) return null;
  const name = path.basename(file);
  const source = stripGitHub(fs.readFileSync(file, 'utf8'));
  checkShellBlocks(name, source);
  const ctx = makeCtx({ dir: LABS, slug }, site, known, { labsPrefix: '../labs/' });
  const { html, toc } = await renderLab(source, ctx);
  for (const m of ctx.media) {
    const dest = path.join(OUT, slug, m);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(path.join(LABS, m), dest);
  }
  const ids = new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));
  for (const m of html.matchAll(/href="#([^"]+)"/g)) if (!ids.has(m[1])) warn(`${name}: anchor #${m[1]} not found`);
  for (const m of html.matchAll(/href="\.\.\/labs\/(\d{2}-[a-z0-9-]+|quickstart)\/#([^"]+)"/g)) {
    if (!rendered.get(m[1])?.includes(` id="${m[2]}"`)) warn(`${name}: anchor ${m[1]}#${m[2]} not found`);
  }
  const headings = [...html.matchAll(/<h([23]) id="([^"]+)"><a class="anchor"[^>]*>#<\/a>([\s\S]*?)<\/h\1>/g)]
    .map((m) => ({ id: m[2], text: htmlToText(m[3]), level: Number(m[1]) }));
  return { source, html, toc, headings };
}

// The Setup guide: the one-time tasks that the labs link to instead of repeating them.
async function renderSetup(site, known, rendered) {
  const guide = await renderGuide(SETUP, 'setup', site, known, rendered);
  return guide && {
    ...guide,
    description: 'The one-time tasks that the Azure AI Gateway labs share: permissions, tools, sign-in, the aigateway extension, resource providers, regions, the labs repo, and azd.',
  };
}

// The Troubleshooting page: one "## " section of rows per lab, plus setup and deployment. A lab's section starts with a
// link to the lab, and its table starts with a Step column: the steps where readers see each error. The build moves
// the steps into the symptom cell, and each of those steps gets a Troubleshoot button that opens its errors.
async function renderTroubleshooting(site, known, rendered, labs) {
  const guide = await renderGuide(TROUBLESHOOTING, 'troubleshooting', site, known, rendered);
  if (!guide) return null;
  for (const lab of labs) {
    lab.troubleshooting = null;
    lab.tsSteps = new Map();
    if (/^## Troubleshooting\s*$/m.test(lab.content)) warn(`${lab.slug}: remove the Troubleshooting section; the steps' Troubleshoot buttons open TROUBLESHOOTING.md`);
  }
  const bySlug = new Map(labs.map((l) => [l.slug, l]));
  let rows = 0;
  const sections = [];
  // The first paragraph is the page's lead, in the hero.
  let lead = '';
  const html = guide.html.split(/(?=<h2 id=")/).map((part) => {
    const id = part.match(/^<h2 id="([^"]+)"/)?.[1];
    if (!id) return part.replace(/^\s*<p>([\s\S]*?)<\/p>\s*/, (_, p) => { lead = p; return ''; });
    const title = guide.toc.find((t) => t.id === id)?.text || id;
    const slug = part.match(/^<h2[\s\S]*?<\/h2>\s*<p>(?:(?!<\/p>)[\s\S])*?href="\.\.\/labs\/([a-z0-9-]+)\/"/)?.[1];
    const lab = slug && bySlug.get(slug);
    if (lab) {
      if (lab.troubleshooting) warn(`TROUBLESHOOTING.md: "${title}" and #${lab.troubleshooting} both link to ${slug}/README.md first`);
      else lab.troubleshooting = id;
      part = mapTsSteps(part, lab, `TROUBLESHOOTING.md#${id}`);
    }
    const n = (part.match(/<tr[ >]/g) || []).length - (part.match(/<thead>/g) || []).length;
    if (!n) warn(`TROUBLESHOOTING.md: section "${title}" has no table rows`);
    rows += n;
    sections.push({ id, title, rows: n, text: htmlToText(part.replace(/^<h2[\s\S]*?<\/h2>/, '')) });
    return `<section class="ts-section" data-ts="${id}">${part}</section>`;
  }).join('');
  for (const lab of labs) if (!lab.troubleshooting) warn(`TROUBLESHOOTING.md: no section starts with a link to ${lab.slug}/README.md`);
  return {
    ...guide, html, sections, rows, lead,
    description: 'The errors you might hit in the Azure AI Gateway labs, with their likely causes and fixes: setup and deployment, and every lab.',
  };
}

// The Step cell names one or more step titles, separated by <br>. A title matches the lab's steps with that title in
// every track, unless "(Track, Track)" after it names the tracks. "Any step" marks an error that no step owns.
function mapTsSteps(part, lab, name) {
  const table = part.match(/<table><thead><tr>([\s\S]*?)<\/tr><\/thead><tbody>([\s\S]*?)<\/tbody><\/table>/);
  if (!table) return part;
  const heads = [...table[1].matchAll(/<th[^>]*>([\s\S]*?)<\/th>/g)].map((m) => htmlToText(m[1]));
  if (heads[0] !== 'Step') {
    warn(`${name}: start the table with a Step column: the steps where readers see each error, or "Any step"`);
    return part;
  }
  const steps = lab.steps || [];
  const head = table[1].replace(/^<th[^>]*>[\s\S]*?<\/th>/, '');
  const body = table[2].replace(/<tr><td[^>]*>([\s\S]*?)<\/td><td([^>]*)>([\s\S]*?)<\/td>/g, (all, cell, attrs, symptom) => {
    const refs = cell.split(/<br\s*\/?>/).map((r) => htmlToText(r)).filter(Boolean);
    const ids = new Set();
    const links = [];
    for (const ref of refs) {
      if (ref === 'Any step') {
        if (refs.length > 1) warn(`${name}: "Any step" can't be combined with steps: ${refs.join(' | ')}`);
        continue;
      }
      const m = ref.match(/^(.*?)(?:\s+\(([^()]+)\))?$/);
      let [title, tracks] = [m[1], m[2]?.split(/\s*,\s*/)];
      let found = steps.filter((s) => s.title === title);
      // A title can end in parentheses itself, such as "(optional)".
      if (tracks && !found.length) { [title, tracks] = [ref, null]; found = steps.filter((s) => s.title === ref); }
      if (!found.length) { warn(`${name}: no step "${title}" in ${lab.slug}/README.md`); continue; }
      if (tracks) {
        for (const t of tracks) if (!found.some((s) => s.label === t)) warn(`${name}: ${lab.slug}/README.md has no step "${title}" in its ${t} track`);
        found = found.filter((s) => tracks.includes(s.label));
        if (!found.length) continue;
      }
      for (const s of found) ids.add(s.id);
      links.push(`<a href="../labs/${lab.slug}/#${found[0].anchor}">${escapeHtml(ref)}</a>`);
    }
    if (!refs.length) warn(`${name}: a row has no step; name the steps where readers see the error, or write "Any step"`);
    for (const id of ids) lab.tsSteps.set(id, (lab.tsSteps.get(id) || 0) + 1);
    const where = links.length
      ? `<span class="ts-where"><span class="ts-where-label">${links.length > 1 ? 'Steps' : 'Step'}</span> ${links.join('<span class="ts-where-sep" aria-hidden="true"> · </span>')}</span>`
      : '';
    return `<tr data-steps="${[...ids].join(' ')}"><td${attrs}>${symptom}${where}</td>`;
  });
  return part.replace(table[0], `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`);
}

// Adds a Troubleshoot button next to Done on each step that has errors on the Troubleshooting page.
function addStepTroubleshooting(lab, html) {
  if (!lab.troubleshooting || !lab.tsSteps?.size) return html;
  const byId = new Map((lab.steps || []).map((s) => [s.id, s]));
  return html.replace(/<section class="step" data-step="([^"]+)">([\s\S]*?)<div class="step-btns">/g, (all, id, between) => {
    const n = lab.tsSteps.get(id);
    const step = byId.get(id);
    if (!n || !step) return all;
    const label = [step.label, step.title].filter(Boolean).join(' › ');
    const errors = `${n} known error${n === 1 ? '' : 's'}`;
    return `<section class="step" data-step="${id}">${between}<div class="step-btns">`
      + `<button class="step-ts" type="button" data-ts-step="${id}" data-ts-label="${escapeHtml(label)}" title="Troubleshoot this step: ${errors}, with ${n === 1 ? 'its fix' : 'their fixes'}">`
      + `${TS_ICON}<span>Troubleshoot</span> <b>${n}</b><span class="sr-only"> known error${n === 1 ? '' : 's'} in this step</span></button>`;
  });
}
const TS_ICON = '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7.5"/><circle cx="10" cy="10" r="3"/><path d="m4.7 4.7 3.2 3.2M12.1 12.1l3.2 3.2M15.3 4.7l-3.2 3.2M7.9 12.1l-3.2 3.2"/></svg>';

export async function build({ strict = false } = {}) {
  const t0 = Date.now();
  warnings.length = 0;
  svgCounter = 0;
  const catalog = JSON.parse(fs.readFileSync(path.join(LABS, 'catalog.json'), 'utf8'));
  const ogVersion = createHash('sha256').update(fs.readFileSync(path.join(SITE_SRC, 'og-image.jpg'))).digest('hex').slice(0, 8);
  const site = { ...catalog.site, baseUrl: BASE_URL, ogVersion };
  setupTasks = readSetupTasks(SETUP);
  for (const t of setupTasks) if (!t.when) warn(`SETUP.md: the task table has no row for #${t.id} (setup task "${t.key}")`);
  const labs = loadLabs(catalog);
  const known = new Set(labs.map((l) => l.slug));
  syncSources(labs, catalog, { check: strict });
  rmGenerated();

  // Static assets
  copyDir(path.join(LABS, 'assets'), path.join(OUT, 'labs', 'assets'));
  fs.mkdirSync(path.join(OUT, 'assets'), { recursive: true });
  const parts = (dir, ext) => fs.readdirSync(path.join(SITE_SRC, dir)).filter((f) => f.endsWith(ext)).sort()
    .map((f) => `/* ${f} */\n${fs.readFileSync(path.join(SITE_SRC, dir, f), 'utf8').trim()}\n`).join('\n');
  fs.writeFileSync(path.join(OUT, 'assets', 'site.css'), parts('css', '.css'));
  fs.writeFileSync(path.join(OUT, 'assets', 'site.js'), `(() => {\n'use strict';\n${parts('js', '.js')}\n})();\n`);
  for (const f of ['favicon.svg', 'og-image.jpg']) fs.copyFileSync(path.join(SITE_SRC, f), path.join(OUT, 'assets', f));
  fs.writeFileSync(path.join(OUT, '.nojekyll'), '');

  const shared = {
    labs: labs.map((l) => ({ slug: l.slug, num: l.num, title: l.title, short: l.short })),
    paths: catalog.paths.map((p) => ({ id: p.id, title: p.title, labs: p.labs.filter((s) => known.has(s)) })),
    setup: setupTasks.map((t) => ({ key: t.key, id: t.id, title: inlineMd(t.title), when: inlineMd(t.when), check: t.check || undefined })),
  };

  // Labs
  const rendered = new Map();
  const searchIndex = [];
  for (const lab of labs) {
    const ctx = makeCtx(lab, site, known);
    try {
      const { html, toc, tracks: used, steps } = await renderLab(lab.content, ctx);
      Object.assign(lab, { html, toc, usedTracks: used, steps });
      for (const t of used) if (!lab.tracks.includes(t)) warn(`${lab.slug}: track "${t}" used in the body but missing from front matter tracks`);
    } catch (e) {
      throw new Error(`${lab.slug}: ${e.message}`);
    }
    rendered.set(lab.slug, lab.html);
    for (const m of ctx.media) {
      const dest = path.join(OUT, 'labs', lab.slug, m);
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.copyFileSync(path.join(lab.dir, m), dest);
    }
    checkTemplate(lab, site);
    checkShellBlocks(lab.slug, lab.content);
    const headings = [...lab.html.matchAll(/<h([23]) id="([^"]+)"><a class="anchor"[^>]*>#<\/a>([\s\S]*?)<\/h\1>/g)]
      .map((m) => ({ id: m[2], text: htmlToText(m[3]), level: Number(m[1]) }));
    searchIndex.push({
      slug: lab.slug, num: lab.num, quick: lab.quick || undefined, title: lab.title, summary: lab.summary, category: lab.category,
      level: lab.level, duration: lab.duration, tracks: lab.tracks, tags: lab.tags,
      headings: headings.filter((h, i, a) => a.findIndex((x) => x.text === h.text) === i).slice(0, 60),
      text: htmlToText(lab.html).slice(0, 6000),
    });
  }

  // Guides: labs/SETUP.md at /setup/ and labs/TROUBLESHOOTING.md at /troubleshooting/. The labs link to them, so
  // render them before checking the labs' anchors.
  const setup = await renderSetup(site, known, rendered);
  const trouble = await renderTroubleshooting(site, known, rendered, labs);
  // The Troubleshooting panel lists the sections and fetches their rows from /troubleshooting/ when it opens.
  if (trouble) shared.troubleshooting = trouble.sections.map(({ id, title, rows }) => ({ id, title, rows }));
  const guides = { setup: setup?.html, troubleshooting: trouble?.html };
  if (setup) checkGuideAnchors('SETUP.md', setup.html, guides);
  if (trouble) checkGuideAnchors('TROUBLESHOOTING.md', trouble.html, guides);
  if (setup) {
    searchIndex.push({
      slug: 'setup', page: true, url: 'setup/', num: '', title: 'Setup guide', summary: setup.description, tags: ['setup', 'prerequisites'],
      headings: setup.headings, text: htmlToText(setup.html).slice(0, 6000),
    });
    write('setup/index.html', layout({
      rel: '../', site, kind: 'setup', title: 'Setup guide', description: setup.description,
      body: setupPage({ rel: '../', site, ...setup }), canonical: `${BASE_URL}setup/`, data: shared,
    }));
    write('setup/index.md', setup.source);
  }
  if (trouble) {
    searchIndex.push({
      slug: 'troubleshooting', page: true, url: 'troubleshooting/', num: '', icon: 'lifebuoy', title: 'Troubleshooting',
      summary: trouble.description, tags: ['troubleshooting', 'errors', 'fix'],
      headings: [], text: htmlToText(trouble.lead),
      sections: trouble.sections.map(({ id, title, text }) => ({ id, title, text: text.slice(0, 8000) })),
    });
    write('troubleshooting/index.html', layout({
      rel: '../', site, kind: 'troubleshooting', title: 'Troubleshooting', description: trouble.description,
      body: troubleshootingPage({ rel: '../', site, ...trouble }), canonical: `${BASE_URL}troubleshooting/`, data: shared,
    }));
    write('troubleshooting/index.md', trouble.source);
  }

  for (const [i, lab] of labs.entries()) {
    checkAnchors(lab, lab.html, rendered, guides);
    const rel = '../../';
    const html = addStepTroubleshooting(lab, lab.html);
    const body = labPage({ rel, site, catalog, labs, lab, html, toc: lab.toc, prev: labs[i - 1], next: labs[i + 1] });
    write(`labs/${lab.slug}/index.html`, layout({
      rel, site, kind: 'lab', title: lab.title, description: lab.summary, body,
      canonical: `${BASE_URL}labs/${lab.slug}/`,
      data: { ...shared, lab: lab.slug, ts: lab.troubleshooting, tracks: lab.tracks, mermaid: lab.html.includes('class="mermaid"') },
    }));
    write(`labs/${lab.slug}/index.md`, lab.raw);
  }

  const totals = { labs: labs.length, minutes: labs.reduce((a, l) => a + l.duration, 0) };

  // Release notes: labs/RELEASE-NOTES.md is the source of truth, rendered at /release-notes/
  const notes = await renderReleaseNotes(site, known, rendered, guides);
  if (notes) {
    write('release-notes/index.html', layout({
      rel: '../', site, kind: 'releases', title: 'Release notes', description: notes.description,
      body: releaseNotesPage({ rel: '../', site, ...notes }), canonical: `${BASE_URL}release-notes/`, data: shared,
    }));
    write('release-notes/index.md', notes.source);
  }

  write('index.html', layout({ rel: '', site, kind: 'home', title: '', description: site.tagline, body: homePage({ rel: '', site, catalog, labs, totals, latest: notes?.releases[0] }), canonical: BASE_URL, data: shared }));
  write('labs/index.html', layout({ rel: '../', site, kind: 'catalog', title: 'All labs', description: `${labs.length} hands-on labs for Azure AI Gateway.`, body: catalogPage({ rel: '../', catalog, labs }), canonical: `${BASE_URL}labs/`, data: shared }));
  write('404.html', layout({ rel: BASE_PATH, site, kind: 'notfound', title: 'Page not found', body: notFoundPage({ rel: BASE_PATH }), data: shared }));
  write('search.json', JSON.stringify(searchIndex));

  // Agent and crawler friendly outputs
  const llms = [`# ${site.title}`, '', `> ${site.tagline}`, '',
    'Hands-on labs for Azure AI Gateway. Each lab has portal, Azure CLI, REST, Bicep, or code tracks.', '',
    `Product docs: ${site.docs}`, `Portal: ${site.portal}`, `Source: ${site.repo}/tree/${site.branch}/labs`,
    `Agent skill: ${BASE_URL}skills/${SKILL_NAME}/SKILL.md`, ...(setup ? [`Setup guide: ${BASE_URL}setup/index.md`] : []), ...(trouble ? [`Troubleshooting: ${BASE_URL}troubleshooting/index.md`] : []), ...(notes ? [`Release notes: ${BASE_URL}release-notes/index.md`] : []), '', '## Labs', '',
    ...labs.map((l) => `- [${l.num} ${l.title}](${BASE_URL}labs/${l.slug}/index.md): ${l.summary}`), '',
    '## Learning paths', '', ...catalog.paths.map((p) => `- ${p.title}: ${p.labs.filter((s) => known.has(s)).join(', ')}`), ''].join('\n');
  write('llms.txt', llms);
  // The agent skill, without the generated-region markers
  write(`skills/${SKILL_NAME}/SKILL.md`, fs.readFileSync(SKILL_FILE, 'utf8').replace(/^<!-- gh:(?:begin\b[^>]*|end) -->\n/gm, ''));
  write('llms-full.txt', [...(setup ? [`<!-- ${BASE_URL}setup/ -->\n${setup.source.trim()}\n`] : []), ...labs.map((l) => `<!-- ${BASE_URL}labs/${l.slug}/ -->\n${l.raw.trim()}\n`),
    ...(trouble ? [`<!-- ${BASE_URL}troubleshooting/ -->\n${trouble.source.trim()}\n`] : [])].join('\n\n'));
  const urls = ['', 'labs/', ...(setup ? ['setup/'] : []), ...(trouble ? ['troubleshooting/'] : []), ...(notes ? ['release-notes/'] : []), ...labs.map((l) => `labs/${l.slug}/`)];
  write('sitemap.xml', `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.map((u) => `  <url><loc>${escapeHtml(BASE_URL + u)}</loc></url>`).join('\n')}\n</urlset>\n`);
  write('robots.txt', `User-agent: *\nAllow: /\nSitemap: ${BASE_URL}sitemap.xml\n`);

  console.log(`Built ${labs.length} labs into ${path.relative(process.cwd(), OUT) || '.'} in ${Date.now() - t0} ms`);
  if (warnings.length) {
    console.warn(`\n${warnings.length} warning(s):`);
    for (const w of warnings) console.warn(`  - ${w}`);
  }
  return { labs, warnings: [...warnings] };
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  if (process.argv.includes('--sync')) {
    const catalog = JSON.parse(fs.readFileSync(path.join(LABS, 'catalog.json'), 'utf8'));
    setupTasks = readSetupTasks(SETUP);
    const stale = syncSources(loadLabs(catalog), catalog);
    if (!stale.length) console.log('Lab READMEs are in sync.');
    for (const w of warnings) console.warn(`  - ${w}`);
    process.exit(warnings.length ? 1 : 0);
  }
  await initHighlighter();
  const strict = process.argv.includes('--strict');
  const result = await build({ strict });
  if (strict && result.warnings.length) process.exitCode = 1;
  if (process.argv.includes('--watch')) {
    let timer;
    console.log('Watching labs/ for changes…');
    fs.watch(LABS, { recursive: true }, (_, file) => {
      if (!file || file.includes('node_modules') || file.startsWith('.')) return;
      clearTimeout(timer);
      timer = setTimeout(() => build({ strict }).catch((e) => console.error(e.message)), 150);
    });
  }
}
