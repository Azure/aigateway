// GitHub rendering layer for the lab Markdown.
//
// Each labs/<NN-slug>/README.md is the single source of truth for both github.com and the labs site.
// Authors write plain Markdown plus the site directives (see markdown.mjs). `npm run sync` (also part of
// `npm run build`) then adds GitHub-only chrome so the file reads well on github.com:
//
//   <!-- gh:begin <kind>: ... -->...<!-- gh:end -->   generated regions: navigation, lab header, footer, the
//                                                      code of included files, and widget and video fallbacks
//   <line> <!-- gh -->                                 generated single lines: <details> wrappers that make
//                                                      tracks and Bash/PowerShell tabs collapsible on GitHub
//
// The site strips all of it with stripGitHub() before rendering, so both views show the same content.
// The metadata block at the top is YAML wrapped in an HTML comment, which GitHub hides.
import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';
import { setupKeys } from './setup.mjs';

const SENTINEL = '<!-- gh -->';
const REGION_RE = /^<!-- gh:begin\b[^>]*-->[\s\S]*?^<!-- gh:end -->[ \t]*(?:\n|$)/gm;
const FENCE_OPEN_RE = /^(\s*)(`{3,}|~{3,})(.*)$/;
const TRACK_RE = /^<!--\s*track:\s*([\w-]+)\s*(?:\|\s*([^>]*?))?\s*-->\s*$/;
const TRACKS_END_RE = /^<!--\s*\/tracks\s*-->\s*$/;
const INCLUDE_RE = /^<!--\s*include:\s*(\S+)(?:\s+(\S+))?\s*-->\s*$/;
const WIDGET_RE = /^<!--\s*widget:\s*([\w-]+)/;
export const VIDEO_RE = /^<!--\s*video:\s*(\S+)\s*(?:\|\s*([^>]*?))?\s*-->[ \t]*$/;
const SETUP_LINE_RE = /^<!--\s*setup:\s*([\w\s-]+?)\s*-->[ \t]*$/;
const LONG_INCLUDE = 28;

export const GH_TRACK_LABELS = { portal: 'Portal', cli: 'Azure CLI', rest: 'REST API', iac: 'Bicep + azd', code: 'Code' };
const SHORT_TRACK_LABELS = { portal: 'Portal', cli: 'CLI', rest: 'REST', iac: 'Bicep', code: 'Code' };
const TRACK_EMOJI = { portal: '🖥️', cli: '⌨️', rest: '🔗', iac: '🏗️', code: '🧑‍💻' };
const WIDGET_TITLES = {
  'request-lifecycle': 'request lifecycle explorer',
  'policy-layers': 'policy layers explorer',
  'tool-patterns': 'tool patterns explorer',
  'alias-retarget': 'alias retargeting demo',
  'alias-routing': 'priority and weight routing simulator',
  'token-limit': 'token limit simulator',
  'request-rate': 'request rate simulator',
  budget: 'cost budget simulator',
  'stream-usage': 'streaming usage simulator',
};

// <!-- video: media/name.mp4 | Title --> plays on the site; media/name.jpg is the poster and media/name.vtt the captions.
export function videoInfo(file, title) {
  const base = file.replace(/\.(mp4|webm)$/i, '');
  return {
    file, title: String(title || 'Video walkthrough').trim(), poster: `${base}.jpg`, captions: `${base}.vtt`,
    id: `video-${path.basename(base)}`, type: /\.webm$/i.test(file) ? 'video/webm' : 'video/mp4',
  };
}

export function findVideo(markdown) {
  for (const line of String(markdown).split('\n')) {
    const m = line.match(VIDEO_RE);
    if (m) return videoInfo(m[1], m[2]);
  }
  return null;
}

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const isBlank = (l) => l == null || !l.trim();

// GitHub-compatible heading anchor (matches markdown.mjs slugify).
export function ghSlug(text) {
  return String(text).toLowerCase()
    .replace(/<[^>]+>/g, '')
    .replace(/[`*_]/g, (c) => (c === '_' ? c : ''))
    .replace(/[^\p{L}\p{N}\s_-]/gu, '')
    .trim().replace(/\s/g, '-');
}

// Reads the metadata block: YAML in an HTML comment (preferred) or classic --- front matter.
export function parseLab(raw) {
  const delimiters = raw.startsWith('---') ? ['---', '---'] : ['<!--', '-->'];
  const file = matter(raw, { delimiters });
  return { data: file.data, matter: file.matter.trim(), body: file.content };
}

function fenceTracker() {
  let open = null;
  return {
    get open() { return open !== null; },
    // Returns true when the line belongs to a fenced code block (including its fences).
    feed(line) {
      if (!open) {
        const m = line.match(FENCE_OPEN_RE);
        if (m && !(m[2][0] === '`' && m[3].includes('`'))) { open = { ch: m[2][0], len: m[2].length }; return true; }
        return false;
      }
      const m = line.match(/^\s*(`{3,}|~{3,})\s*$/);
      if (m && m[1][0] === open.ch && m[1].length >= open.len) open = null;
      return true;
    },
  };
}

// Removes every generated GitHub construct and normalizes blank lines outside code blocks.
export function stripGitHub(md) {
  const src = md.replace(REGION_RE, '');
  const out = [];
  const fence = fenceTracker();
  for (const line of src.split('\n')) {
    const inFence = fence.feed(line);
    if (!inFence && line.trimEnd().endsWith(SENTINEL)) continue;
    if (!inFence && isBlank(line) && (out.length === 0 || out[out.length - 1].blank)) continue;
    out.push({ text: inFence ? line : line.replace(/[ \t]+$/, ''), blank: !inFence && isBlank(line) });
  }
  while (out.length && out[out.length - 1].blank) out.pop();
  return `${out.map((l) => l.text).join('\n')}\n`;
}

function scanFences(lines) {
  const fences = [];
  const fence = fenceTracker();
  let cur = null;
  lines.forEach((line, i) => {
    const wasOpen = fence.open;
    fence.feed(line);
    if (!wasOpen && fence.open) {
      const m = line.match(FENCE_OPEN_RE);
      const title = m[3].match(/\btitle=(?:"([^"]*)"|(\S+))/);
      cur = { start: i, indent: m[1], title: title ? (title[1] ?? title[2]) : null };
    } else if (wasOpen && !fence.open) {
      fences.push({ ...cur, end: i });
      cur = null;
    }
  });
  if (cur) fences.push({ ...cur, end: lines.length - 1 });
  return fences;
}

// Marks runs of adjacent titled code blocks (the site shows them as tabs) for <details> wrapping.
function tabGroups(lines, fences) {
  const wrap = new Map();
  let group = [];
  const flush = () => {
    if (group.length > 1) group.forEach((f, i) => wrap.set(f.start, { ...f, open: i === 0 }));
    group = [];
  };
  for (const f of fences) {
    const prev = group[group.length - 1];
    const adjacent = prev && f.title && prev.indent === f.indent
      && lines.slice(prev.end + 1, f.start).every(isBlank);
    if (f.title && (adjacent || !prev)) group.push(f);
    else { flush(); if (f.title) group.push(f); }
  }
  flush();
  return wrap;
}

function region(kind, body) {
  return [`<!-- gh:begin ${kind}: generated by "npm run sync" from the metadata, do not edit -->`, ...body, '<!-- gh:end -->'];
}

const labLink = (from, l) => `[${l.num} · ${l.short}](${from}${l.slug}/README.md)`;

function includeRegion(labDir, file, langOverride) {
  const abs = path.join(labDir, file);
  if (!fs.existsSync(abs)) return region('include', [`> [!WARNING]`, `> Missing file: \`${file}\``]);
  const code = fs.readFileSync(abs, 'utf8').replace(/\s+$/, '');
  const lang = langOverride || path.extname(file).slice(1) || 'text';
  const ticks = code.includes('```') ? '````' : '```';
  const lines = code.split('\n').length;
  const fenced = [`${ticks}${lang}`, ...code.split('\n'), ticks];
  const link = `📄 [\`${file}\`](${file.split('/').map(encodeURIComponent).join('/')})`;
  if (lines <= LONG_INCLUDE) return region('include', [link, '', ...fenced]);
  return region('include', [link, '', `<details><summary>Show all ${lines} lines</summary>`, '', ...fenced, '', '</details>']);
}

function widgetRegion(name, labUrl) {
  const what = WIDGET_TITLES[name] || `${name.replace(/-/g, ' ')} widget`;
  return region('widget', [`> 🎛️ **Interactive:** try the ${what} in the [web version of this lab](${labUrl}).`]);
}

// The Setup guide tasks that a lab uses, as one line of links. The site renders a checklist instead.
function setupRegion(labDir, list, setupTasks) {
  const { tasks } = setupKeys(list, setupTasks);
  const guide = path.relative(labDir, path.join(path.dirname(labDir), 'SETUP.md')).split(path.sep).join('/');
  const links = tasks.map((t) => `[${t.title}](${guide}#${t.id})`);
  return region('setup', [
    `🧰 **One-time setup** from the [Setup guide](${guide}), if you haven't done it yet:`,
    ...links.map((l, i) => `${l}${i < links.length - 1 ? ' ·' : ''}`),
  ]);
}

// GitHub can't play videos stored in the repo, so the poster links to the player on the site.
function videoRegion(labDir, v, labUrl) {
  const enc = (f) => f.split('/').map(encodeURIComponent).join('/');
  const has = (f) => fs.existsSync(path.join(labDir, f));
  const url = `${labUrl}#${v.id}`;
  const label = v.title.replace(/[[\]"]/g, '');
  const links = [`🎬 [Play with captions on the labs site](${url})`, `⬇️ [Download MP4](${enc(v.file)})`];
  if (has(v.captions)) links.push(`📝 [Captions](${enc(v.captions)})`);
  return region('video', [
    ...(has(v.poster) ? [`[![▶ ${label}](${enc(v.poster)} "${label}")](${url})`, ''] : []),
    `<sub>${links.join(' · ')}</sub>`,
  ]);
}

// Regenerates the GitHub chrome of one lab README. Pure apart from reading included files.
export function syncLab(raw, { lab, labs, catalog, site, setupTasks = [], troubleshooting = null }) {
  const { matter: fm, body } = parseLab(raw);
  const lines = stripGitHub(body).split('\n');
  if (lines[lines.length - 1] === '') lines.pop();
  const idx = labs.findIndex((l) => l.slug === lab.slug);
  const prev = labs[idx - 1];
  const next = labs[idx + 1];
  const cat = catalog.categories.find((c) => c.id === lab.category);
  const siteUrl = `${site.pages}labs/${lab.slug}/`;
  const byId = Object.fromEntries(labs.map((l) => [l.slug, l]));

  const fences = scanFences(lines);
  const fenceAt = new Map(fences.map((f) => [f.start, f]));
  const wrapped = tabGroups(lines, fences);
  const h1 = lines.findIndex((l) => /^# \S/.test(l));
  const h2s = [];
  {
    const fence = fenceTracker();
    for (const l of lines) if (!fence.feed(l) && /^## \S/.test(l)) h2s.push(l.slice(3).trim());
  }

  const out = [];
  const ensureBlank = () => { if (out.length && !isBlank(out[out.length - 1])) out.push(''); };
  const blankIfNext = (i) => { if (i < lines.length && !isBlank(lines[i])) out.push(''); };

  // Header: breadcrumb above the title, lab card below it.
  out.push(...region('nav', [
    `[AI Gateway labs](../README.md) › [${cat?.title || lab.category}](../README.md#${ghSlug(cat?.title || lab.category)}) › ${lab.label}`,
  ]), '');
  const prereqs = (lab.prereqs || []).map((s) => byId[s]).filter(Boolean);
  const tracks = (lab.tracks || []).map((t) => (t === 'iac' && lab.iacLabel) || GH_TRACK_LABELS[t] || t).join(' · ');
  const run = [`🌐 [Interactive version](${siteUrl}) with your own values filled in`];
  const video = findVideo(lines.join('\n'));
  if (video) run.push(`🎬 [Video walkthrough](${siteUrl}#${video.id})`);
  if (lab.notebook) run.push(`📓 [Jupyter notebook](${encodeURIComponent(lab.notebook)})`);
  if (fs.existsSync(path.join(lab.dir, 'infra'))) run.push('📁 [Lab files](infra/)');
  const intro = [
    `> ${String(lab.summary).trim()}`,
    '',
    '| ⏱️ Time | 📶 Level | 🧭 Tracks | ✅ Before you start |',
    '| :-- | :-- | :-- | :-- |',
    `| ${lab.duration} min | ${lab.level} | ${tracks}${lab.notebook ? ' · Notebook' : ''} | ${prereqs.length ? prereqs.map((p) => labLink('../', p)).join('<br>') : 'Nothing, start here'} |`,
    '',
    "**You'll learn to**",
    '',
    ...(lab.objectives || []).map((o) => `- ${o}`),
    '',
    `**Follow along:** ${run.join(' · ')}`,
  ];
  if (h2s.length) intro.push('', `**On this page:** ${h2s.map((t) => `[${t.replace(/[`*]/g, '')}](#${ghSlug(t)})`).join(' · ')}`);

  let start = 0;
  if (h1 >= 0) {
    out.push(lines[h1], '', ...region('intro', intro));
    start = h1 + 1;
    blankIfNext(start);
  } else {
    out.push(...region('intro', intro), '');
  }

  let inTracks = false;
  for (let i = start; i < lines.length; i += 1) {
    const line = lines[i];
    const f = fenceAt.get(i);
    if (f) {
      const w = wrapped.get(i);
      if (w) {
        ensureBlank();
        out.push(`${w.indent}<details${w.open ? ' open' : ''}><summary>${esc(w.title)}</summary> ${SENTINEL}`, '');
      }
      out.push(...lines.slice(f.start, f.end + 1));
      if (w) { out.push(`${w.indent}</details> ${SENTINEL}`); blankIfNext(f.end + 1); }
      i = f.end;
      continue;
    }
    const track = line.match(TRACK_RE);
    if (track || TRACKS_END_RE.test(line)) {
      if (inTracks) { ensureBlank(); out.push(`</details> ${SENTINEL}`); }
      out.push(line);
      if (track) {
        const id = track[1];
        const label = (track[2] || GH_TRACK_LABELS[id] || id).trim();
        out.push(`<details${!inTracks ? ' open' : ''}><summary><b>${TRACK_EMOJI[id] || '🧭'} ${esc(label)}</b></summary> ${SENTINEL}`);
        blankIfNext(i + 1);
        inTracks = true;
      } else {
        inTracks = false;
      }
      continue;
    }
    out.push(line);
    const inc = line.match(INCLUDE_RE);
    if (inc) { out.push(...includeRegion(lab.dir, inc[1], inc[2])); blankIfNext(i + 1); continue; }
    const widget = line.match(WIDGET_RE);
    if (widget) { out.push(...widgetRegion(widget[1], siteUrl)); blankIfNext(i + 1); continue; }
    const vid = line.match(VIDEO_RE);
    if (vid) { out.push(...videoRegion(lab.dir, videoInfo(vid[1], vid[2]), siteUrl)); blankIfNext(i + 1); continue; }
    const setup = line.match(SETUP_LINE_RE);
    if (setup) { out.push(...setupRegion(lab.dir, setup[1], setupTasks)); blankIfNext(i + 1); }
  }

  // Footer: previous / all labs / next, plus learning paths.
  const paths = catalog.paths.filter((p) => p.labs.includes(lab.slug))
    .map((p) => `[${p.title}](../README.md#learning-paths) (${p.labs.indexOf(lab.slug) + 1} of ${p.labs.length})`);
  ensureBlank();
  out.push(...region('footer', [
    '',
    ...(troubleshooting ? [`🛟 **Hit an error?** [Troubleshooting](../TROUBLESHOOTING.md#${troubleshooting}) lists the errors of this lab, the steps where they happen, and their fixes.`, ''] : []),
    '---',
    '',
    '| ⬅️ Previous | 🏠 | Next ➡️ |',
    '| :-- | :-: | --: |',
    `| ${prev ? labLink('../', prev) : ' '} | [All labs](../README.md) | ${next ? labLink('../', next) : ' '} |`,
    ...(paths.length ? ['', `<sub>Learning paths: ${paths.join(' · ')}</sub>`] : []),
  ]));
  return `<!--\n${fm}\n-->\n${out.join('\n')}\n`;
}

// Regenerates the generated regions of labs/README.md (learning paths and the lab catalog).
export function syncIndex(raw, { labs, catalog }) {
  const byId = Object.fromEntries(labs.map((l) => [l.slug, l]));
  const tracks = (l) => (l.tracks || []).map((t) => SHORT_TRACK_LABELS[t] || t).join(' · ');
  const notebooks = labs.filter((l) => l.notebook);
  const shield = (s) => encodeURIComponent(String(s).replace(/-/g, '--').replace(/_/g, '__').replace(/ /g, '_'));
  const badge = (label, message, color, logo) => `<img alt="${esc(label)}: ${esc(message)}" src="https://img.shields.io/badge/${shield(label)}-${shield(message)}-${color}${logo ? `?logo=${logo}&amp;logoColor=white` : ''}">`;
  const regions = {
    badges: [
      '<p align="center">',
      `  <a href="${catalog.site.pages}">${badge('labs site', catalog.site.pages.replace(/^https?:\/\/|\/$/g, ''), '0078D4')}</a>`,
      `  ${badge('labs', labs.length, '5C2D91')}`,
      `  ${badge('learning paths', catalog.paths.length, '107C10')}`,
      `  ${badge('notebooks', notebooks.length, 'F37626', 'jupyter')}`,
      `  ${badge('tracks', 'Portal · CLI · REST · Bicep · Code', '505050')}`,
      '</p>',
    ],
    notebooks: notebooks.length ? [
      '| Notebook | Lab | Time |',
      '| :-- | :-- | --: |',
      ...notebooks.map((l) => `| 📓 [\`${l.notebook}\`](${l.slug}/${encodeURIComponent(l.notebook)}) | [${l.num} · ${l.short}](${l.slug}/README.md) | ${l.duration} min |`),
    ] : ['_No notebooks yet._'],
    paths: [
      '| Path | For | Labs, in order |',
      '| :-- | :-- | :-- |',
      ...catalog.paths.map((p) => `| **${p.title}** | ${p.persona} | ${p.labs.map((s) => byId[s]).filter(Boolean)
        .map((l) => `[${l.num} ${l.short}](${l.slug}/README.md)`).join(' → ')} |`),
    ],
    catalog: catalog.categories.flatMap((c) => {
      const items = labs.filter((l) => l.category === c.id);
      if (!items.length) return [];
      return [
        `### ${c.title}`, '', c.description, '',
        '| # | Lab | Level | Time | Tracks | Notebook |',
        '| :-: | :-- | :-- | --: | :-- | :-: |',
        ...items.map((l) => `| ${l.num} | [${l.title}](${l.slug}/README.md) | ${l.level} | ${l.duration} min | ${tracks(l)} | ${l.notebook ? `[📓](${l.slug}/${encodeURIComponent(l.notebook)})` : ''} |`),
        '',
      ];
    }),
  };
  return replaceRegions(raw, regions);
}

function replaceRegions(raw, regions) {
  const missing = [];
  let out = raw;
  for (const [kind, body] of Object.entries(regions)) {
    const re = new RegExp(`^<!-- gh:begin ${kind}\\b[^>]*-->[\\s\\S]*?^<!-- gh:end -->`, 'm');
    if (!re.test(out)) { missing.push(kind); continue; }
    const lines = body[body.length - 1] === '' ? body.slice(0, -1) : body;
    out = out.replace(re, () => region(kind, lines).join('\n'));
  }
  return { text: out, missing };
}

// Regenerates the generated regions of the azure-ai-gateway-labs agent skill (lab catalog, learning paths, and
// use-case map). Links are absolute so the skill works when it's copied out of the repository.
export function syncSkill(raw, { labs, catalog }) {
  const base = catalog.site.pages;
  const byId = Object.fromEntries(labs.map((l) => [l.slug, l]));
  const tracks = (l) => [...(l.tracks || []).map((t) => SHORT_TRACK_LABELS[t] || t), ...(l.notebook ? ['Notebook'] : [])].join(', ');
  const nums = (slugs) => slugs.map((s) => byId[s]).filter(Boolean).map((l) => l.num).join(' → ');
  const regions = {
    catalog: catalog.categories.flatMap((c) => {
      const items = labs.filter((l) => l.category === c.id);
      if (!items.length) return [];
      return [
        `### ${c.title}`, '',
        ...items.map((l) => {
          const needs = (l.prereqs || []).map((s) => byId[s]?.num).filter(Boolean);
          const meta = [`${l.level}, ${l.duration} min`, tracks(l), needs.length ? `needs ${needs.join(', ')}` : ''].filter(Boolean).join(' · ');
          return `- **${l.num}** [${l.title}](${base}labs/${l.slug}/index.md) \`${l.slug}\` (${meta}): ${l.summary}`;
        }),
        '',
      ];
    }),
    paths: [
      '| Path | For | Labs, in order |',
      '| :-- | :-- | :-- |',
      ...catalog.paths.map((p) => `| ${p.title} | ${p.persona} | ${nums(p.labs)} |`),
    ],
    usecases: [
      '| Use case | Start with |',
      '| :-- | :-- |',
      ...[...(catalog.useCases?.core || []), ...(catalog.useCases?.emerging || [])].filter((u) => byId[u.lab])
        .map((u) => `| ${u.title}: ${u.text.replace(/\.$/, '')} | ${byId[u.lab].num} ${byId[u.lab].short} |`),
    ],
  };
  return replaceRegions(raw, regions);
}
