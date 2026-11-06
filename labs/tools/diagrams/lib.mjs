// Shared SVG primitives for the labs diagrams. Every diagram embeds the same style block,
// so inlining several diagrams in one page is safe. Colors come from --dg-* variables:
// inlined on the site they follow the page theme; opened standalone (GitHub, <img>) the
// svg:root blocks below supply light and dark palettes.
const LIGHT = '--dg-bg:#fff;--dg-surface:#fff;--dg-surface-2:#f7f7f9;--dg-stroke:#d6d6dc;--dg-text:#242424;--dg-muted:#616161;--dg-violet:#7e5be8;--dg-azure:#0f6cbd;--dg-cyan:#0a9fd8;--dg-magenta:#c2147c;--dg-green:#107c10;--dg-amber:#c46a00;--dg-red:#c50f1f;--dg-gw:#f4f0ff;--dg-gw-stroke:#b9a6f5;--dg-zone:#f6f8fb';
const DARK = '--dg-bg:#151518;--dg-surface:#1f1f24;--dg-surface-2:#26262c;--dg-stroke:#3b3b44;--dg-text:#f3f3f5;--dg-muted:#a9a9b2;--dg-violet:#a58bff;--dg-azure:#62abf5;--dg-cyan:#3ccbf4;--dg-magenta:#f472b6;--dg-green:#6cc56c;--dg-amber:#f0a33a;--dg-red:#f1707b;--dg-gw:rgba(142,91,255,.14);--dg-gw-stroke:rgba(165,139,255,.55);--dg-zone:rgba(255,255,255,.03)';
const TONES = ['violet', 'azure', 'cyan', 'magenta', 'green', 'amber', 'red'];
const STYLE = `svg:root{${LIGHT}}@media (prefers-color-scheme:dark){svg:root{${DARK}}}
svg:root>.dg-root>.dg-bg{fill:var(--dg-bg)}
.dg-root{font-family:'Segoe UI Variable Text','Segoe UI',system-ui,-apple-system,'Helvetica Neue',sans-serif}
${TONES.map((t) => `.tn-${t}{--tn:var(--dg-${t})}`).join('')}
.dg-bg{fill:none}
.dg-t{fill:var(--dg-text);font-size:14px;font-weight:600}
.dg-s{fill:var(--dg-muted);font-size:12px}
.dg-m{fill:var(--dg-muted);font-family:ui-monospace,'Cascadia Code',SFMono-Regular,Menlo,monospace;font-size:11.5px}
.dg-cap{fill:var(--dg-muted);font-size:11px;font-weight:700;letter-spacing:.08em}
.dg-cap-tn{fill:var(--tn);font-size:11px;font-weight:700;letter-spacing:.08em}
.dg-box{fill:var(--dg-surface);stroke:var(--dg-stroke);stroke-width:1.25}
.dg-box-tn{fill:var(--dg-surface);stroke:var(--tn);stroke-width:1.5}
.dg-ghost{fill:none;stroke:var(--dg-stroke);stroke-width:1.25;stroke-dasharray:5 5}
.dg-zone{fill:var(--dg-zone);stroke:var(--dg-stroke);stroke-width:1.25;stroke-dasharray:4 4}
.dg-gw{fill:var(--dg-gw);stroke:var(--dg-gw-stroke);stroke-width:1.5}
.dg-chip{fill:var(--tn);fill-opacity:.13}
.dg-ic{fill:none;stroke:var(--tn);stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.dg-pill{fill:var(--tn);fill-opacity:.12;stroke:var(--tn);stroke-opacity:.35}
.dg-pill-t{fill:var(--tn);font-size:11.5px;font-weight:600}
.dg-line{fill:none;stroke:var(--dg-stroke);stroke-width:1.75}
.dg-flow{fill:none;stroke:var(--tn);stroke-width:2;stroke-dasharray:6 10;stroke-linecap:round;animation:dg-flow 1.4s linear infinite}
.dg-dash{fill:none;stroke:var(--tn);stroke-width:1.75;stroke-dasharray:4 5}
.dg-ah{fill:var(--dg-muted)}
.dg-dot{fill:var(--tn)}
.dg-bar{fill:var(--dg-surface-2);stroke:var(--dg-stroke)}
.dg-bar-fill{fill:var(--tn)}
@keyframes dg-flow{to{stroke-dashoffset:-32}}
@media (prefers-reduced-motion:reduce){.dg-flow{animation:none}}
.dg-paused .dg-flow{animation-play-state:paused}`;

export const ICONS = {
  app: 'M4 5h16v14H4z M4 9h16 M7 7h.01',
  agent: 'M6 9h12v10H6z M12 9V6 M12 4.5v.01 M9.5 13.5v.01 M14.5 13.5v.01 M10 16.5h4 M4 13v2 M20 13v2',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4.5 20c1.4-3.6 4.2-5.5 7.5-5.5s6.1 1.9 7.5 5.5',
  users: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M2.5 20c1.2-3.3 3.6-5 6.5-5s5.3 1.7 6.5 5 M16 4.5a3.5 3.5 0 0 1 0 6.5 M18 14.5c1.6.6 2.8 2.4 3.5 5',
  key: 'M8 20a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M10.9 13.1 19 5 M16 8l2.5 2.5 M14 10l2 2',
  shield: 'M12 3l7.5 3v6c0 4.6-3.2 7.9-7.5 9-4.3-1.1-7.5-4.4-7.5-9V6z M9 12l2 2 4-4',
  gauge: 'M4 17a8 8 0 1 1 16 0 M12 17l3.5-4.5 M7 17h.01 M17 17h.01',
  coins: 'M12 10c3.9 0 7-1.3 7-3s-3.1-3-7-3-7 1.3-7 3 3.1 3 7 3z M5 7v5c0 1.7 3.1 3 7 3s7-1.3 7-3V7 M5 12v5c0 1.7 3.1 3 7 3s7-1.3 7-3v-5',
  filter: 'M4 5h16l-6 7.5V18l-4 2v-7.5z',
  route: 'M6 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M8 18h5a3 3 0 0 0 3-3V9a3 3 0 0 1 3-3 M16.5 3.5 19 6l-2.5 2.5',
  server: 'M4 4h16v6H4z M4 14h16v6H4z M8 7h.01 M8 17h.01',
  chart: 'M4 4v16h16 M8 16v-4 M12 16V8 M16 16v-6',
  globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M3 12h18 M12 3c2.7 2.6 2.7 15.4 0 18 M12 3c-2.7 2.6-2.7 15.4 0 18',
  eye: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  layers: 'M12 3l9 5-9 5-9-5z M3 12.5l9 5 9-5 M3 16.5l9 5 9-5',
  models: 'M12 3l8 4.5v9L12 21l-8-4.5v-9z M4 7.5 12 12l8-4.5 M12 12v9',
  tools: 'M14.5 4.5a4.5 4.5 0 0 0-4.3 5.8L4 16.5 7.5 20l6.2-6.2a4.5 4.5 0 0 0 5.8-4.3l-2.7 2.7-3-3z',
  lock: 'M6 11h12v9H6z M8.5 11V8a3.5 3.5 0 0 1 7 0v3 M12 15v2',
  cloud: 'M7 18.5h10a4 4 0 0 0 .6-8A6 6 0 0 0 6.2 9.6 4.5 4.5 0 0 0 7 18.5z',
  doc: 'M6 3h8l4 4v14H6z M14 3v4h4 M9 12h6 M9 16h6',
  code: 'M6 3h8l4 4v14H6z M14 3v4h4 M10 12l-2 2 2 2 M14 12l2 2-2 2',
  plug: 'M9 3v5 M15 3v5 M6 8h12v3a6 6 0 0 1-12 0z M12 17v4',
  grid: 'M4 4h7v7H4z M13 4h7v7h-7z M4 13h7v7H4z M13 13h7v7h-7z',
  toolbox: 'M3 8h18v12H3z M8.5 8V5h7v3 M3 13h18 M10 13v2h4v-2',
  terminal: 'M3.5 5h17v14h-17z M7 10l3 2-3 2 M12.5 15h4.5',
  bolt: 'M13 3 5 14h6l-1 7 8-11h-6z',
  check: 'M5 12.5l4.5 4.5L19 7',
  block: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M5.6 5.6l12.8 12.8',
  network: 'M9 3h6v5H9z M12 8v4 M5 12h14 M5 12v3 M19 12v3 M12 12v3 M3 15h4v5H3z M10 15h4v5h-4z M17 15h4v5h-4z',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v5l3 2',
  sparkle: 'M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6-5.6-1.9 5.6-1.9z M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z',
  dns: 'M4 5h16v5H4z M4 14h16v5H4z M7 7.5h3 M7 16.5h3 M15 7.5h.01 M15 16.5h.01',
  m365: 'M5 7.5 12 4l7 3.5v9L12 20l-7-3.5z M12 4v16 M5 7.5l7 4 7-4',
};

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
export const warnings = [];
let current = '';
const tw = (s, size, k = 0.56) => String(s).length * size * k;
function fit(text, avail, size, k, what) {
  if (tw(text, size, k) > avail + 1) warnings.push(`${current}: "${text}" (${what}) may overflow by ~${Math.round(tw(text, size, k) - avail)}px`);
}

export const text = (x, y, s, cls = 'dg-s', anchor = 'start', extra = '') => `<text x="${x}" y="${y}" class="${cls}"${anchor !== 'start' ? ` text-anchor="${anchor}"` : ''}${extra}>${esc(s)}</text>`;
export const icon = (name, x, y, size = 20) => `<path class="dg-ic" transform="translate(${x} ${y}) scale(${+(size / 24).toFixed(4)})" d="${ICONS[name] || ICONS.sparkle}"/>`;

// A card with optional icon chip, title and up to two sub lines.
export function box(x, y, w, h, { t, s, s2, icon: ic, tone = 'violet', mono = false, accent = false } = {}) {
  let out = `<g class="tn-${tone}"><rect class="${accent ? 'dg-box-tn' : 'dg-box'}" x="${x}" y="${y}" width="${w}" height="${h}" rx="10"/>`;
  let tx = x + 14;
  if (ic) {
    const cs = h >= 56 ? 34 : 28, cy = y + (h - cs) / 2;
    out += `<rect class="dg-chip" x="${x + 11}" y="${cy}" width="${cs}" height="${cs}" rx="8"/>${icon(ic, x + 11 + (cs - 20) / 2, cy + (cs - 20) / 2)}`;
    tx = x + 11 + cs + 11;
  }
  const subs = [s, s2].filter(Boolean);
  const block = 16 + subs.length * 16;
  const ty = y + (h - block) / 2 + 13;
  const avail = x + w - tx - 10;
  if (t) { fit(t, avail, 14, 0.56, 'title'); out += text(tx, ty, t, 'dg-t'); }
  subs.forEach((line, i) => {
    const m = mono === 'all' || (mono && i === subs.length - 1);
    fit(line, avail, m ? 11.5 : 12, m ? 0.62 : 0.52, 'sub'); out += text(tx, ty + 17 + i * 16, line, m ? 'dg-m' : 'dg-s');
  });
  return `${out}</g>`;
}
// A square node with a large icon and a caption underneath (pipelines).
export function node(cx, y, ic, lbl, { tone = 'violet', sub, size = 56, accent = true } = {}) {
  const x = cx - size / 2;
  let out = `<g class="tn-${tone}"><rect class="${accent ? 'dg-box-tn' : 'dg-box'}" x="${x}" y="${y}" width="${size}" height="${size}" rx="14"/>`;
  out += `<rect class="dg-chip" x="${x + 6}" y="${y + 6}" width="${size - 12}" height="${size - 12}" rx="10"/>${icon(ic, cx - 13, y + size / 2 - 13, 26)}`;
  out += text(cx, y + size + 18, lbl, 'dg-t', 'middle', ' style="font-size:12.5px"');
  if (sub) out += text(cx, y + size + 34, sub, 'dg-s', 'middle', ' style="font-size:11px"');
  return `${out}</g>`;
}
export function zone(x, y, w, h, lbl, { gw = false, tone = 'violet', ic } = {}) {
  let out = `<g class="tn-${tone}"><rect class="${gw ? 'dg-gw' : 'dg-zone'}" x="${x}" y="${y}" width="${w}" height="${h}" rx="16"/>`;
  if (lbl) {
    const lx = x + 16;
    if (ic) out += icon(ic, lx, y + 10, 16);
    out += text(ic ? lx + 22 : lx, y + 23, lbl.toUpperCase(), gw ? 'dg-cap-tn' : 'dg-cap');
  }
  return `${out}</g>`;
}
export const pillW = (lbl, mono = false) => Math.round(tw(lbl, 11.5, mono ? 0.62 : 0.57) + 20);
export function pill(x, y, lbl, { tone = 'violet', w, mono = false, anchor = 'start' } = {}) {
  const width = w || pillW(lbl, mono);
  const x0 = anchor === 'middle' ? x - width / 2 : anchor === 'end' ? x - width : x;
  return `<g class="tn-${tone}"><rect class="dg-pill" x="${x0}" y="${y}" width="${width}" height="22" rx="11"/>${text(x0 + width / 2, y + 15, lbl, 'dg-pill-t', 'middle', mono ? ' style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px"' : '')}</g>`;
}
// A row of pills that wraps inside a width.
export function pills(x, y, labels, { tone = 'violet', maxW = 9999, gap = 6 } = {}) {
  let cx = x, cy = y, out = '';
  for (const l of labels) {
    const [lbl, t] = Array.isArray(l) ? l : [l, tone];
    const w = pillW(lbl);
    if (cx + w > x + maxW) { cx = x; cy += 28; }
    out += pill(cx, cy, lbl, { tone: t, w }); cx += w + gap;
  }
  return out;
}
// Arrow: grey base line with arrow head plus an animated colored flow on top.
export function arrow(d, { tone = 'violet', flow = true, dashed = false, head = true } = {}) {
  const m = head ? ' marker-end="url(#ah)"' : '';
  if (dashed) return `<g class="tn-${tone}"><path class="dg-dash" d="${d}"${m}/></g>`;
  return `<g class="tn-${tone}"><path class="dg-line" d="${d}"${m}/>${flow ? `<path class="dg-flow" d="${d}"/>` : ''}</g>`;
}
export const label = (x, y, s, { anchor = 'middle', cls = 'dg-s', bg = true } = {}) => {
  const w = tw(s, 12, 0.52) + 12;
  const x0 = anchor === 'middle' ? x - w / 2 : anchor === 'end' ? x - w : x;
  return `${bg ? `<rect x="${x0}" y="${y - 13}" width="${w}" height="18" rx="4" style="fill:var(--dg-bg)"/>` : ''}${text(anchor === 'middle' ? x : anchor === 'end' ? x - 6 : x + 6, y, s, cls, anchor)}`;
};
export function bar(x, y, w, ratio, { tone = 'green', h = 8 } = {}) {
  return `<g class="tn-${tone}"><rect class="dg-bar" x="${x}" y="${y}" width="${w}" height="${h}" rx="${h / 2}"/><rect class="dg-bar-fill" x="${x}" y="${y}" width="${Math.max(h, w * ratio)}" height="${h}" rx="${h / 2}"/></g>`;
}
export const dot = (cx, cy, tone = 'violet', r = 3.5) => `<circle class="dg-dot tn-${tone}" cx="${cx}" cy="${cy}" r="${r}"/>`;
export const list = (x, y, items, { tone = 'violet', gap = 22, cls = 'dg-s' } = {}) => items.map((it, i) => dot(x + 4, y + i * gap - 4, tone) + text(x + 14, y + i * gap, it, cls)).join('');

export function svgDoc(name, { title, desc, w = 960, h, body }) {
  current = name;
  const b = typeof body === 'function' ? body() : body;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-labelledby="title desc" data-name="${name}">
<title id="title">${esc(title)}</title>
<desc id="desc">${esc(desc)}</desc>
<defs><style>${STYLE}</style><marker id="ah" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path class="dg-ah" d="M0 0 10 5 0 10z"/></marker></defs>
<g class="dg-root"><rect class="dg-bg" width="${w}" height="${h}"/>
${b}
</g></svg>
`;
}
