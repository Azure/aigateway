// Converts GitHub-friendly lab Markdown into rich lab HTML.
//
// The lab README is the single source of truth. Generated GitHub-only chrome (<!-- gh:begin --> regions and
// lines ending in <!-- gh -->, see github.mjs) is stripped before rendering, so the site never shows it.
//
// Conventions (all degrade gracefully on github.com):
//   <!-- track: portal | Portal -->     starts a track panel; consecutive tracks form one tab group
//   <!-- /tracks -->                    ends the current track group
//   <!-- steps --> ... <!-- /steps -->  turns H3 headings in the region into numbered steps
//   <!-- include: infra/main.bicep -->  inlines a file from the lab folder as a code viewer
//   <!-- widget: name {"json":1} -->    mounts an interactive widget from site.js
//   <!-- video: media/x.mp4 | Title --> video player; media/x.jpg is the poster, media/x.vtt the captions file
//   <!-- setup: tools sign-in clone -->  checklist of the Setup guide tasks the lab uses (see setup.mjs)
//   <!-- setup-done: extension -->      inside a step: marking the step done marks these setup tasks done
//   > [!NOTE|TIP|IMPORTANT|WARNING|CAUTION]  GitHub alerts become callouts
//   > **Checkpoint** ...                becomes a checkpoint callout
//   ```bash title="Bash"                titled code blocks; adjacent titled blocks become tabs
import fs from 'node:fs';
import path from 'node:path';
import { Marked } from 'marked';
import { createHighlighter } from 'shiki';
import { stripGitHub, videoInfo } from './github.mjs';
import { SETUP_RE, SETUP_DONE_RE, setupKeys, inlineMd, plainMd } from './setup.mjs';

const LANGS = ['bash', 'shellscript', 'powershell', 'python', 'json', 'jsonc', 'typescript', 'javascript',
  'csharp', 'yaml', 'http', 'bicep', 'kusto', 'text', 'dotenv', 'toml', 'markdown', 'html', 'css', 'xml', 'sql'];
const LANG_ALIASES = { sh: 'bash', shell: 'bash', zsh: 'bash', ps1: 'powershell', pwsh: 'powershell', py: 'python',
  ts: 'typescript', js: 'javascript', cs: 'csharp', 'c#': 'csharp', yml: 'yaml', kql: 'kusto', promql: 'text',
  env: 'dotenv', txt: 'text', plaintext: 'text', console: 'bash', jsonl: 'json', mjs: 'javascript', cjs: 'javascript',
  tsx: 'typescript', jsx: 'javascript', bicepparam: 'bicep', md: 'markdown', csproj: 'xml', example: 'text', http: 'http',
  azcli: 'bash', azurecli: 'bash', dockerfile: 'text', ini: 'toml' };
const LANG_LABELS = { bash: 'Bash', powershell: 'PowerShell', python: 'Python', json: 'JSON', jsonc: 'JSON',
  typescript: 'TypeScript', javascript: 'JavaScript', csharp: 'C#', yaml: 'YAML', http: 'HTTP', bicep: 'Bicep',
  kusto: 'KQL', text: 'Text', dotenv: '.env', toml: 'TOML', markdown: 'Markdown', html: 'HTML', css: 'CSS', xml: 'XML', sql: 'SQL' };

// Placeholders that readers can personalise in the lab settings panel. Keys are never stored.
export const PLACEHOLDERS = {
  'subscription-id': 'Subscription ID',
  'resource-group': 'Resource group',
  'gateway': 'Gateway name',
  'gateway-url': 'Runtime URL',
  'location': 'Region',
  'model-name': 'Model alias',
  'provider-name': 'Model provider',
  'foundry-account-name': 'Foundry account',
  'tenant-id': 'Tenant ID',
};
const PH_RE = new RegExp(`<(${Object.keys(PLACEHOLDERS).join('|')})>`, 'g');
const phToken = (k) => `AIGWPH${k.replace(/-/g, 'X')}AIGWEND`;
const PH_TOKEN_RE = /AIGWPH([A-Za-z]+)AIGWEND/g;

let highlighter;
// Theme colors under 4.5:1 on the code background, replaced with the nearest passing shade (WCAG 1.4.3).
const CODE_COLORS = {
  'github-light': { '#6a737d': '#636c76', '#d73a49': '#c62a39', '#e36209': '#b85000', '#22863a': '#1a7f37' },
  'github-dark-dimmed': { '#768390': '#8b98a5' },
};
export async function initHighlighter() {
  highlighter = await createHighlighter({ themes: ['github-light', 'github-dark-dimmed'], langs: LANGS });
}

export const escapeHtml = (s) => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

export function slugify(text) {
  return String(text).toLowerCase()
    .replace(/<[^>]+>/g, '')
    .replace(/&[a-z]+;/g, '')
    .replace(/[^\p{L}\p{N}\s-]/gu, '')
    .trim().replace(/\s+/g, '-');
}

function parseInfo(info = '') {
  const m = info.match(/^(\S*)\s*(.*)$/);
  const rawLang = (m?.[1] || 'text').toLowerCase();
  const meta = m?.[2] || '';
  const attrs = {};
  for (const a of meta.matchAll(/(\w[\w-]*)=(?:"([^"]*)"|(\S+))/g)) attrs[a[1]] = a[2] ?? a[3];
  const lang = LANG_ALIASES[rawLang] || rawLang;
  return { lang: LANGS.includes(lang) ? lang : 'text', rawLang, attrs };
}

export function highlight(code, lang) {
  const tokenised = code.replace(PH_RE, (_, k) => phToken(k));
  let html = highlighter.codeToHtml(tokenised, {
    lang, themes: { light: 'github-light', dark: 'github-dark-dimmed' }, defaultColor: false, colorReplacements: CODE_COLORS,
  });
  html = html.replace(PH_TOKEN_RE, (_, k) => {
    const key = k.replace(/X/g, '-');
    return `<span class="ph" data-ph="${key}">&lt;${key}&gt;</span>`;
  });
  return html.replace(/^<pre class="shiki[^"]*"[^>]*>/, '<pre class="shiki">');
}

const ICONS = {
  copy: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2"/><path d="M13 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"/></svg>',
  note: '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7.5"/><path d="M10 9v5M10 6.2v.1"/></svg>',
  tip: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7.5 15h5M8 17.5h4M10 2.5a5 5 0 0 0-3 9c.6.5 1 1.2 1 2h4c0-.8.4-1.5 1-2a5 5 0 0 0-3-9Z"/></svg>',
  important: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 4.5A1.5 1.5 0 0 1 4.5 3h11A1.5 1.5 0 0 1 17 4.5v8a1.5 1.5 0 0 1-1.5 1.5H8l-4 3v-3h0.5A1.5 1.5 0 0 1 3 12.5Z"/><path d="M10 6v4M10 12v.1"/></svg>',
  warning: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 3 2 17h16L10 3Z"/><path d="M10 8v4M10 14.5v.1"/></svg>',
  caution: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7 2.5h6L17.5 7v6L13 17.5H7L2.5 13V7Z"/><path d="M10 6.5v4.5M10 13.5v.1"/></svg>',
  checkpoint: '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7.5"/><path d="m6.5 10.2 2.3 2.3 4.7-4.8"/></svg>',
  file: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 2.5h6.5L15 6v11.5H5Z"/><path d="M11 2.5V6.5h4"/></svg>',
  external: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M11 3.5h5.5V9M16.5 3.5 9 11M14 12v4.5H3.5V6H8"/></svg>',
  wrench: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M12.5 3a4 4 0 0 0-3.8 5.3L3.5 13.5a1.5 1.5 0 0 0 0 2.1l.9.9a1.5 1.5 0 0 0 2.1 0l5.2-5.2A4 4 0 0 0 17 7.5l-2.3 2.3-2.3-.4-.4-2.3L14.3 4.8A4 4 0 0 0 12.5 3Z"/></svg>',
  tick: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5.5 10.5 3 3 6-7"/></svg>',
};

// <!-- setup: … -->: the Setup guide tasks that a lab uses. site.js hides the ones the reader marked done.
function setupCheck(list, ctx) {
  const { tasks, unknown } = setupKeys(list, ctx.setupTasks || []);
  if (unknown.length) throw new Error(`unknown setup task "${unknown.join('", "')}" in <!-- setup: ${list} -->`);
  const items = tasks.map((t) => `<li data-setup-task="${t.key}">`
    + `<button class="setup-tick" type="button" aria-pressed="false" title="Mark as done" aria-label="Mark ${escapeHtml(plainMd(t.title))} as done">${ICONS.tick}</button>`
    + `<span class="setup-check-text"><a href="${ctx.setupHref(t.id)}">${inlineMd(t.title)}</a><span class="setup-check-when">${inlineMd(t.when)}</span></span></li>`).join('');
  return `<div class="setup-check" data-setup-check><div class="setup-check-head"><span class="setup-check-icon">${ICONS.wrench}</span>`
    + `<p><strong>One-time setup</strong><span class="setup-check-count"></span><span class="setup-check-sub">The Setup guide tasks that this lab uses. Mark each one done once, and the labs stop listing it.</span></p>`
    + `<button class="btn btn-secondary btn-sm" type="button" data-setup-open>${ICONS.wrench}<span>Setup guide</span></button></div>`
    + `<ul class="setup-check-list">${items}</ul>`
    + `<p class="setup-check-done" hidden>${ICONS.checkpoint}<span>You've done the one-time setup that this lab uses.</span><button class="link-btn" type="button" data-setup-open>Review</button></p></div>`;
}

// A WebVTT file as a readable transcript: one paragraph per run of cues, split where the narration pauses.
function vttTranscript(vtt) {
  const secs = (t) => t.split(':').reduce((acc, x) => acc * 60 + parseFloat(x), 0);
  const paras = [];
  let last = -1;
  for (const block of vtt.replace(/\r/g, '').split(/\n{2,}/)) {
    const lines = block.split('\n');
    const at = lines.findIndex((l) => l.includes('-->'));
    if (at < 0) continue;
    const [start, end] = lines[at].split('-->').map((x) => secs(x.trim().split(/\s/)[0]));
    const text = lines.slice(at + 1).join(' ').replace(/<[^>]+>/g, '').trim();
    if (!text) continue;
    if (!paras.length || start - last > 0.8) paras.push([]);
    paras[paras.length - 1].push(text);
    last = end;
  }
  return paras.map((p) => `<p>${escapeHtml(p.join(' '))}</p>`).join('');
}

function codeBlock({ code, lang, title, include, ghUrl }) {
  const label = title || LANG_LABELS[lang] || lang;
  const head = `<div class="code-head"><span class="code-title">${include ? ICONS.file : ''}${escapeHtml(label)}</span>`
    + `<span class="code-actions">${ghUrl ? `<a class="code-btn" href="${ghUrl}" target="_blank" rel="noopener" title="View on GitHub">${ICONS.external}<span>GitHub</span></a>` : ''}`
    + `<button class="code-btn copy-btn" type="button" title="Copy">${ICONS.copy}<span>Copy</span></button></span></div>`;
  const lines = code.split('\n').length;
  const collapsible = include && lines > 28;
  const group = title && !include ? ' data-group="1"' : '';
  return `<div class="code${collapsible ? ' code-collapsible' : ''}" data-lang="${lang}"${group}>${head}${highlight(code, lang)}`
    + `${collapsible ? `<button class="code-expand" type="button" aria-expanded="false"><span>Show all ${lines} lines</span></button>` : ''}</div>`;
}

const ALERTS = { NOTE: 'Note', TIP: 'Tip', IMPORTANT: 'Important', WARNING: 'Warning', CAUTION: 'Caution' };

function createMarked(ctx) {
  const m = new Marked({ gfm: true });
  const headingIds = new Map();
  m.use({
    walkTokens(token) {
      if (token.type === 'heading') {
        let id = slugify(token.text);
        const n = headingIds.get(id) || 0;
        headingIds.set(id, n + 1);
        if (n) id = `${id}-${n}`;
        token.anchor = id;
        if (token.depth === 2) ctx.toc.push({ id, text: token.text.replace(/[*`_]/g, '') });
      }
    },
    renderer: {
      paragraph(token) {
        const inner = this.parser.parseInline(token.tokens);
        const onlyImages = token.tokens.every((t) => t.type === 'image' || (t.type === 'text' && !t.text.trim()) || t.type === 'br');
        if (onlyImages && token.tokens.some((t) => t.type === 'image')) return `${inner}\n`;
        return `<p>${inner}</p>\n`;
      },
      heading(token) {
        const inner = this.parser.parseInline(token.tokens);
        if (token.depth === 1) return '';
        return `<h${token.depth} id="${token.anchor}"><a class="anchor" href="#${token.anchor}" aria-hidden="true" tabindex="-1">#</a>${inner}</h${token.depth}>\n`;
      },
      code(token) {
        const { lang, attrs } = parseInfo(token.lang);
        if (attrs.widget) return `<div class="widget" data-widget="${escapeHtml(attrs.widget)}"></div>`;
        if (token.lang === 'mermaid') return `<pre class="mermaid">${escapeHtml(token.text)}</pre>`;
        return codeBlock({ code: token.text, lang, title: attrs.title, include: attrs.include, ghUrl: attrs.include ? ctx.ghBlob(attrs.include) : null });
      },
      blockquote(token) {
        const first = token.tokens?.[0];
        const raw = first?.raw ?? '';
        const alert = raw.match(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*\n?/);
        if (alert) {
          const kind = alert[1].toLowerCase();
          const body = this.parser.parse(token.tokens).replace(/^<p>\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(<br>)?\s*/, '<p>');
          return `<div class="callout callout-${kind}"><div class="callout-title">${ICONS[kind]}${ALERTS[alert[1]]}</div>${body.replace(/<p>\s*<\/p>/g, '')}</div>\n`;
        }
        const body = this.parser.parse(token.tokens);
        const cp = body.match(/^<p><strong>(Checkpoint|Verify|Check your work)[^<]*<\/strong>\s*(<br>)?/i);
        if (cp) {
          const title = body.match(/^<p><strong>([^<]*)<\/strong>/)[1];
          return `<div class="callout callout-checkpoint"><div class="callout-title">${ICONS.checkpoint}${escapeHtml(title)}</div>${body.replace(/^<p><strong>[^<]*<\/strong>\s*(<br>)?\s*/, '<p>').replace(/<p>\s*<\/p>/g, '')}</div>\n`;
        }
        return `<blockquote>${body}</blockquote>\n`;
      },
      image({ href, title, text }) {
        const src = ctx.resolveAsset(href);
        if (/\.(mp4|webm)$/i.test(href)) {
          return `<figure class="figure figure-video"><video src="${src}" aria-label="${escapeHtml(text)}" controls muted loop playsinline preload="metadata"></video>${title ? `<figcaption>${escapeHtml(title)}</figcaption>` : ''}</figure>`;
        }
        if (/\.svg$/i.test(href) && ctx.inlineSvg(href)) {
          return `<figure class="figure figure-svg" role="img" aria-label="${escapeHtml(text)}">${ctx.inlineSvg(href)}${title ? `<figcaption>${escapeHtml(title)}</figcaption>` : ''}</figure>`;
        }
        return `<figure class="figure"><button class="zoom" type="button" aria-label="Enlarge image: ${escapeHtml(text)}"><img src="${src}" alt="${escapeHtml(text)}" loading="lazy" decoding="async"></button>${title ? `<figcaption>${escapeHtml(title)}</figcaption>` : ''}</figure>`;
      },
      link({ href, title, tokens }) {
        const text = this.parser.parseInline(tokens);
        const { url, external } = ctx.resolveLink(href);
        return `<a href="${url}"${title ? ` title="${escapeHtml(title)}"` : ''}${external ? ' target="_blank" rel="noopener"' : ''}>${text}${external ? '<span class="ext" aria-hidden="true">↗</span>' : ''}</a>`;
      },
      table(token) {
        const header = token.header.map((c) => `<th${c.align ? ` style="text-align:${c.align}"` : ''}>${this.parser.parseInline(c.tokens)}</th>`).join('');
        const rows = token.rows.map((r) => `<tr>${r.map((c) => `<td${c.align ? ` style="text-align:${c.align}"` : ''}>${this.parser.parseInline(c.tokens)}</td>`).join('')}</tr>`).join('');
        return `<div class="table-wrap"><table><thead><tr>${header}</tr></thead><tbody>${rows}</tbody></table></div>\n`;
      },
    },
  });
  return m;
}

// Turns each h3 into a step. Each step is collected in `steps` ({ id, anchor, title, track, label }) so the build can
// map the Troubleshooting rows to it.
function stepify(html, prefix, steps = [], label = '') {
  // Prefix keeps split() from skipping a heading at index 0 (zero-width matches there never split).
  const parts = `\u0000${html}`.split(/(?=<h3 id=")/);
  parts[0] = parts[0].slice(1);
  if (parts.length < 2) return html;
  let out = parts[0];
  let n = 0;
  for (const p of parts.slice(1)) {
    n += 1;
    const m = p.match(/^<h3 id="([^"]+)">([\s\S]*?)<\/h3>\n?([\s\S]*)$/);
    if (!m) { out += p; continue; }
    const [, id, title, body] = m;
    const stepId = `${prefix}-${id}`;
    steps.push({ id: stepId, anchor: id, title: headingText(title), track: prefix === 'shared' ? '' : prefix, label });
    out += `<section class="step" data-step="${stepId}"><div class="step-rail"><span class="step-num">${n}</span></div>`
      + `<div class="step-main"><div class="step-head"><h3 id="${id}">${title}</h3>`
      + `<div class="step-btns"><button class="step-check" type="button" aria-pressed="false" title="Mark step as done"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5.5 10.5 3 3 6-7"/></svg><span>Done</span></button></div></div>`
      + `<div class="step-body">${body}</div></div></section>`;
  }
  return out;
}

const headingText = (h) => h.replace(/<a class="anchor"[^>]*>#<\/a>/, '').replace(/<[^>]+>/g, '')
  .replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').trim();

function enhanceHtml(html) {
  let tabGroup = 0;
  // Click paths: **A** › **B** › **C**
  html = html.replace(/(<strong>[^<]{1,60}<\/strong>)((?:\s*(?:›|&gt;|→)\s*<strong>[^<]{1,60}<\/strong>)+)/g, (all) => {
    const items = [...all.matchAll(/<strong>([^<]+)<\/strong>/g)].map((x) => x[1]);
    return `<span class="uipath">${items.map((i) => `<span class="uipath-item">${i}</span>`).join('<span class="uipath-sep" aria-hidden="true">›</span>')}</span>`;
  });
  // Adjacent titled code blocks => tabs. Each block's body stops at its own </pre>, so a group can't reach across
  // other content to a later titled block.
  html = html.replace(/(?:<div class="code" data-lang="[^"]+" data-group="1"><div class="code-head"><span class="code-title">[^<]*<\/span>(?:(?!<\/pre>)[\s\S])*<\/pre><\/div>\s*){2,}/g, (group) => {
    const blocks = [...group.matchAll(/<div class="code" data-lang="([^"]+)" data-group="1"><div class="code-head"><span class="code-title">([^<]*)<\/span>[\s\S]*?(<pre class="shiki">[\s\S]*?<\/pre>)<\/div>/g)]
      .map(([, lang, title, pre]) => ({ lang, title: title.replace(/&amp;/g, '&'), pre }));
    if (blocks.length < 2) return group;
    const id = `ct${++tabGroup}`;
    const tabs = blocks.map((b, i) => `<button role="tab" class="code-tab" aria-selected="${i === 0}" data-tab-label="${escapeHtml(b.title)}" id="${id}-t${i}" aria-controls="${id}-p${i}" tabindex="${i ? -1 : 0}">${escapeHtml(b.title)}</button>`).join('');
    const panels = blocks.map((b, i) => `<div role="tabpanel" class="code-panel" id="${id}-p${i}" aria-labelledby="${id}-t${i}"${i ? ' hidden' : ''} data-lang="${b.lang}">${b.pre}</div>`).join('');
    return `<div class="code code-tabs"><div class="code-head"><div class="code-tablist" role="tablist">${tabs}</div>`
      + `<span class="code-actions"><button class="code-btn copy-btn" type="button" title="Copy">${ICONS.copy}<span>Copy</span></button></span></div>${panels}</div>`;
  });
  return html;
}

const TRACK_ICONS = {
  portal: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="2.5" y="3.5" width="15" height="11" rx="2"/><path d="M7 17.5h6M10 14.5v3"/><path d="m9 7 4 2-1.7.7-.7 1.8Z"/></svg>',
  cli: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="2.5" y="3.5" width="15" height="13" rx="2"/><path d="m6 8 2.5 2L6 12M10.5 12.5H14"/></svg>',
  iac: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2.5 17 6.5v7L10 17.5 3 13.5v-7Z"/><path d="M3 6.5 10 10.5l7-4M10 10.5v7"/></svg>',
  code: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="m7 6-4 4 4 4M13 6l4 4-4 4"/></svg>',
  rest: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 7h14M3 13h14"/><path d="m13 4 4 3-4 3M7 10l-4 3 4 3"/></svg>',
};
export const TRACK_LABELS = { portal: 'Portal', cli: 'Azure CLI', iac: 'Bicep + azd', code: 'Code', rest: 'REST' };
export { TRACK_ICONS };

export async function renderLab(markdown, ctx) {
  ctx.toc = [];
  // includes
  let src = stripGitHub(markdown).replace(/<!--\s*include:\s*([^\s]+)(?:\s+(\S+))?\s*-->/g, (_, file, langOverride) => {
    const abs = path.join(ctx.labDir, file);
    if (!fs.existsSync(abs)) throw new Error(`include not found: ${abs}`);
    const ext = path.extname(file).slice(1);
    const lang = langOverride || ext;
    const code = fs.readFileSync(abs, 'utf8').replace(/\s+$/, '');
    const fence = code.includes('```') ? '````' : '```';
    return `${fence}${lang} title="${file}" include="${file}"\n${code}\n${fence}`;
  });
  // widgets
  src = src.replace(/<!--\s*widget:\s*([\w-]+)\s*(\{[\s\S]*?\})?\s*-->/g, (_, name, json) =>
    `<div class="widget" data-widget="${name}"${json ? ` data-config='${json.replace(/'/g, '&#39;')}'` : ''}></div>`);

  // videos
  src = src.replace(/^<!--\s*video:\s*(\S+)\s*(?:\|\s*([^>]*?))?\s*-->[ \t]*$/gm, (_, file, title) => {
    const v = videoInfo(file, title);
    const has = (f) => fs.existsSync(path.resolve(ctx.labDir, f));
    const poster = has(v.poster) ? ` poster="${ctx.resolveAsset(v.poster)}"` : '';
    // Captions are burned into the video, so the caption track is off by default; it lets viewers restyle them.
    const vtt = has(v.captions) ? ctx.resolveAsset(v.captions) : '';
    const track = vtt ? `<track kind="captions" srclang="en" label="English" src="${vtt}">` : '';
    const transcript = vtt ? vttTranscript(fs.readFileSync(path.resolve(ctx.labDir, v.captions), 'utf8')) : '';
    // No native full screen: site.js expands videos into an in-page theater view instead (see initVideos).
    return `<figure class="figure figure-video" id="${v.id}"><div class="video-frame"><video controls controlslist="nofullscreen" playsinline preload="none"${poster} aria-label="${escapeHtml(v.title)}">`
      + `<source src="${ctx.resolveAsset(v.file)}" type="${v.type}">${track}</video></div><figcaption>${escapeHtml(v.title)}</figcaption>`
      + `${transcript ? `<details class="transcript"><summary>Transcript</summary>${transcript}<p class="transcript-dl"><a href="${vtt}" download>Download the captions (WebVTT)</a></p></details>` : ''}</figure>`;
  });

  // setup checklists, and the setup tasks that a step completes
  src = src.replace(SETUP_RE, (_, list) => setupCheck(list, ctx));
  src = src.replace(SETUP_DONE_RE, (_, list) => {
    const { tasks, unknown } = setupKeys(list, ctx.setupTasks || []);
    if (unknown.length) throw new Error(`unknown setup task "${unknown.join('", "')}" in <!-- setup-done: ${list} -->`);
    return `<div hidden data-setup-done="${tasks.map((t) => t.key).join(' ')}"></div>`;
  });

  // Split into segments by track / steps markers
  const markerRe = /<!--\s*(track:\s*([\w-]+)\s*(?:\|\s*([^>]*?))?|\/tracks|steps|\/steps)\s*-->/g;
  const segments = [];
  let last = 0; let mode = 'shared'; let current = null; let group = null; let stepsBuf = null;
  const flush = (text) => {
    if (!text.trim()) return;
    if (mode === 'track') current.md += text;
    else if (mode === 'steps') stepsBuf.md += text;
    else segments.push({ kind: 'md', md: text });
  };
  for (const m of src.matchAll(markerRe)) {
    flush(src.slice(last, m.index));
    last = m.index + m[0].length;
    const kw = m[1];
    if (kw.startsWith('track:')) {
      if (mode !== 'track') { group = { kind: 'tracks', tracks: [] }; segments.push(group); }
      current = { id: m[2], label: (m[3] || TRACK_LABELS[m[2]] || m[2]).trim(), md: '' };
      group.tracks.push(current);
      mode = 'track';
    } else if (kw === '/tracks') { mode = 'shared'; current = null; group = null; }
    else if (kw === 'steps') { stepsBuf = { kind: 'steps', md: '' }; segments.push(stepsBuf); mode = 'steps'; }
    else if (kw === '/steps') { mode = 'shared'; stepsBuf = null; }
  }
  flush(src.slice(last));

  const marked = createMarked(ctx);
  let html = '';
  const tracks = [];
  const steps = [];
  for (const seg of segments) {
    if (seg.kind === 'md') html += marked.parse(seg.md);
    else if (seg.kind === 'steps') html += `<div class="steps">${stepify(marked.parse(seg.md), 'shared', steps)}</div>`;
    else {
      const gid = `tg${tracks.length}`;
      const tabs = seg.tracks.map((t, i) => `<button role="tab" class="track-tab" data-track="${t.id}" aria-selected="${i === 0}" tabindex="${i ? -1 : 0}" id="${gid}-${t.id}-tab" aria-controls="${gid}-${t.id}">${TRACK_ICONS[t.id] || TRACK_ICONS.code}<span>${escapeHtml(t.label)}</span></button>`).join('');
      const panels = seg.tracks.map((t, i) => {
        tracks.push(t.id);
        return `<div class="track-panel" role="tabpanel" data-track="${t.id}" id="${gid}-${t.id}" aria-labelledby="${gid}-${t.id}-tab"${i ? ' hidden' : ''}><div class="steps">${stepify(marked.parse(t.md), t.id, steps, t.label)}</div></div>`;
      }).join('');
      html += `<div class="tracks" data-tracks="${seg.tracks.map((t) => t.id).join(' ')}"><div class="track-bar"><span class="track-bar-label">Choose your track</span><div class="track-tabs" role="tablist" aria-label="Lab track">${tabs}</div></div>${panels}</div>`;
    }
  }
  html = enhanceHtml(html);
  return { html, toc: ctx.toc, tracks: [...new Set(tracks)], steps };
}

export { ICONS };
