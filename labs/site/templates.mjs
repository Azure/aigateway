// HTML templates for the Azure AI Gateway Labs site.
import { escapeHtml as esc, TRACK_ICONS, TRACK_LABELS } from './markdown.mjs';

const P = (d, extra = '') => `<svg class="i" viewBox="0 0 20 20" aria-hidden="true"${extra}>${d}</svg>`;
export const I = {
  search: P('<circle cx="8.5" cy="8.5" r="5"/><path d="m12.5 12.5 4.5 4.5"/>'),
  sun: P('<circle cx="10" cy="10" r="3.5"/><path d="M10 2v1.5M10 16.5V18M2 10h1.5M16.5 10H18M4.3 4.3l1.1 1.1M14.6 14.6l1.1 1.1M4.3 15.7l1.1-1.1M14.6 5.4l1.1-1.1"/>'),
  moon: P('<path d="M16.5 12.2A6.8 6.8 0 0 1 7.8 3.5a6.8 6.8 0 1 0 8.7 8.7Z"/>'),
  pause: P('<circle cx="10" cy="10" r="7.5"/><path d="M8.2 7.2v5.6M11.8 7.2v5.6"/>'),
  github: '<svg class="i i-fill" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 0a8 8 0 0 0-2.53 15.59c.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.92-.89-1.17-.89-1.17-.73-.5.05-.49.05-.49.8.06 1.23.83 1.23.83.72 1.22 1.88.87 2.34.66.07-.52.28-.87.5-1.07-1.78-.2-3.65-.89-3.65-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.28.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 8 0Z"/></svg>',
  clock: P('<circle cx="10" cy="10" r="7.5"/><path d="M10 5.5V10l3 2"/>'),
  notebook: P('<rect x="4.5" y="2.5" width="12" height="15" rx="2"/><path d="M3 6h3M3 10h3M3 14h3M9 7h4.5M9 10.5h4.5"/>'),
  level: P('<path d="M4 16v-3M10 16V9M16 16V4"/>'),
  stream: P('<path d="M2.5 6c2-1.5 3.5-1.5 5 0s3 1.5 5 0 3.5-1.5 5 0M2.5 10c2-1.5 3.5-1.5 5 0s3 1.5 5 0 3.5-1.5 5 0M2.5 14c2-1.5 3.5-1.5 5 0s3 1.5 5 0 3.5-1.5 5 0"/>'),
  bolt: P('<path d="M11.2 2.5 4.5 11h4.6l-.8 6.5 6.7-8.5h-4.6z"/>'),
  arrowR: P('<path d="M4 10h12M11.5 5.5 16 10l-4.5 4.5"/>'),
  arrowL: P('<path d="M16 10H4M8.5 5.5 4 10l4.5 4.5"/>'),
  chevR: P('<path d="m8 5 5 5-5 5"/>'),
  check: P('<path d="m5 10.5 3.2 3.2L15 6.8"/>'),
  external: P('<path d="M11 3.5h5.5V9M16.5 3.5 9 11M14 12v4.5H3.5V6H8"/>'),
  menu: P('<path d="M3 5.5h14M3 10h14M3 14.5h14"/>'),
  close: P('<path d="m5 5 10 10M15 5 5 15"/>'),
  edit: P('<path d="M12.5 4 16 7.5 7.5 16H4v-3.5Z"/><path d="m11 5.5 3.5 3.5"/>'),
  markdown: P('<rect x="2" y="4.5" width="16" height="11" rx="2"/><path d="M5 12.5v-5l2 2.5 2-2.5v5M13 7.5v5M11 10.5l2 2 2-2"/>'),
  sliders: P('<path d="M3 6h7M14 6h3M3 14h3M10 14h7"/><circle cx="12" cy="6" r="2"/><circle cx="8" cy="14" r="2"/>'),
  book: P('<path d="M3.5 4.5c2.5-1 4.5-1 6.5.5 2-1.5 4-1.5 6.5-.5v11c-2.5-1-4.5-1-6.5.5-2-1.5-4-1.5-6.5-.5Z"/><path d="M10 5v11"/>'),
  flag: P('<path d="M5 17.5V3M5 3.5h9.5l-2 3.5 2 3.5H5"/>'),
  trophy: P('<path d="M6.5 3.5h7v4a3.5 3.5 0 0 1-7 0Z"/><path d="M6.5 5H4a2.5 2.5 0 0 0 2.6 3M13.5 5H16a2.5 2.5 0 0 1-2.6 3M10 11v3M7 16.5h6"/>'),
  rocket: P('<path d="M11.5 3.5c2.5-1 4.5-.5 5 0 .5.5 1 2.5 0 5L12 13l-5-5Z"/><path d="M7 8 4.5 7.5 3 9.5l3 1M12 13l.5 2.5-2 1.5-1-3M6.5 13.5 4 16"/><circle cx="13" cy="7" r="1.2"/>'),
  platform: P('<path d="M10 2.5 17 6l-7 3.5L3 6Z"/><path d="m3 10 7 3.5 7-3.5M3 14l7 3.5 7-3.5"/>'),
  code: P('<path d="m7 6-4 4 4 4M13 6l4 4-4 4"/>'),
  shield: P('<path d="M10 2.5 16 5v4.5c0 4-2.7 6.7-6 8-3.3-1.3-6-4-6-8V5Z"/><path d="m7.3 10 2 2 3.5-3.6"/>'),
  chart: P('<path d="M3 3v14h14"/><path d="m6 13 3.5-4 3 2.5L17 6"/>'),
  models: P('<path d="M10 2.5 16.5 6v8L10 17.5 3.5 14V6Z"/><path d="M3.5 6 10 9.5 16.5 6M10 9.5v8"/>'),
  gauge: P('<path d="M3.5 14a6.5 6.5 0 1 1 13 0"/><path d="m10 14 3.5-4.5"/><circle cx="10" cy="14" r="1"/>'),
  coins: P('<ellipse cx="8" cy="6" rx="5" ry="2.5"/><path d="M3 6v3.5C3 10.9 5.2 12 8 12s5-1.1 5-2.5V6"/><path d="M7 12.4V14c0 1.4 2.2 2.5 5 2.5s5-1.1 5-2.5v-3.5c0-1.2-1.6-2.2-3.8-2.4"/>'),
  tools: P('<path d="M12.5 3a4 4 0 0 0-3.8 5.3L3.5 13.5a1.5 1.5 0 0 0 0 2.1l.9.9a1.5 1.5 0 0 0 2.1 0l5.2-5.2A4 4 0 0 0 17 7.5l-2.3 2.3-2.3-.4-.4-2.3L14.3 4.8A4 4 0 0 0 12.5 3Z"/>'),
  key: P('<circle cx="6.5" cy="13.5" r="3.5"/><path d="m9 11 7.5-7.5M14 6l2 2M12 8l1.5 1.5"/>'),
  agent: P('<rect x="4" y="6.5" width="12" height="9" rx="3"/><path d="M10 3.5v3M7.5 11h.01M12.5 11h.01M2 10.5v2M18 10.5v2"/>'),
  filter: P('<path d="M3 4.5h14l-5.5 6.5v5l-3 1.5V11Z"/>'),
  receipt: P('<path d="M5 2.5h10v15l-2-1.3-1.7 1.3-1.3-1.3-1.3 1.3L7 16.2 5 17.5Z"/><path d="M8 7h4M8 10h4"/>'),
  radar: P('<circle cx="10" cy="10" r="7.5"/><circle cx="10" cy="10" r="4"/><path d="m10 10 5-5"/>'),
  building: P('<path d="M3.5 17.5V5l6-2.5v15M9.5 7.5h7v10M2 17.5h16M6 7.5h1M6 10.5h1M6 13.5h1M12 10.5h2M12 13.5h2"/>'),
  sparkle: P('<path d="M10 2.5 11.6 8.4 17.5 10l-5.9 1.6L10 17.5l-1.6-5.9L2.5 10l5.9-1.6Z"/>'),
  route: P('<circle cx="5" cy="5" r="2"/><circle cx="15" cy="15" r="2"/><path d="M7 5h5.5a2.5 2.5 0 0 1 0 5h-5a2.5 2.5 0 0 0 0 5H13"/>'),
  compass: P('<circle cx="10" cy="10" r="7.5"/><path d="m12.8 7.2-1.6 4-4 1.6 1.6-4Z"/>'),
  plug: P('<path d="M7 2.5v4M13 2.5v4M5 6.5h10v3a5 5 0 0 1-10 0ZM10 14.5v3"/>'),
  server: P('<rect x="3" y="3" width="14" height="6" rx="1.5"/><rect x="3" y="11" width="14" height="6" rx="1.5"/><path d="M6 6h.01M6 14h.01"/>'),
  layers: P('<path d="M10 2.5 17.5 6.5 10 10.5 2.5 6.5Z"/><path d="m2.5 10 7.5 4 7.5-4M2.5 13.5l7.5 4 7.5-4"/>'),
  play: P('<path d="M6.5 4.5v11l9-5.5Z"/>'),
  portal: TRACK_ICONS.portal.replace('<svg ', '<svg class="i" '),
  cli: TRACK_ICONS.cli.replace('<svg ', '<svg class="i" '),
  iac: TRACK_ICONS.iac.replace('<svg ', '<svg class="i" '),
  rest: TRACK_ICONS.rest.replace('<svg ', '<svg class="i" '),
  checkpoint: P('<circle cx="10" cy="10" r="7.5"/><path d="m6.5 10.2 2.3 2.3 4.7-4.8"/>'),
  broom: P('<path d="m13 3-4.5 7.5M5 10.5h7l1.5 7h-10Z"/><path d="M7 13.5v4M10 13.5v4"/>'),
  lifebuoy: P('<circle cx="10" cy="10" r="7.5"/><circle cx="10" cy="10" r="3"/><path d="m4.7 4.7 3.2 3.2M12.1 12.1l3.2 3.2M15.3 4.7l-3.2 3.2M7.9 12.1l-3.2 3.2"/>'),
  wrench: P('<path d="M12.5 3a4 4 0 0 0-3.8 5.3L3.5 13.5a1.5 1.5 0 0 0 0 2.1l.9.9a1.5 1.5 0 0 0 2.1 0l5.2-5.2A4 4 0 0 0 17 7.5l-2.3 2.3-2.3-.4-.4-2.3L14.3 4.8A4 4 0 0 0 12.5 3Z"/>'),
};

export const CATEGORY_ICONS = {
  foundations: 'compass', models: 'models', tools: 'tools', governance: 'gauge',
  security: 'shield', observability: 'chart', agents: 'agent', production: 'building',
};
const trackIcon = (t) => (t === 'notebook' ? I.notebook : (TRACK_ICONS[t] || TRACK_ICONS.code).replace('<svg ', '<svg class="i" '));
const SHORT_TRACK = { portal: 'Portal', cli: 'CLI', iac: 'Bicep', code: 'Code', rest: 'REST', notebook: 'Notebook' };
// A lab's tracks, plus a notebook chip when the lab has a Jupyter notebook.
const labTracks = (lab) => [...lab.tracks, ...(lab.notebook ? ['notebook'] : [])];
const fmtDuration = (m) => (m >= 60 ? `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ''}` : `${m} min`);
export const labUrl = (rel, slug) => `${rel}labs/${slug}/`;
const levelDots = (level) => {
  const n = { Beginner: 1, Intermediate: 2, Advanced: 3 }[level] || 1;
  return `<span class="level-dots" aria-hidden="true">${[1, 2, 3].map((i) => `<i${i <= n ? ' class="on"' : ''}></i>`).join('')}</span>`;
};

// ---------- Layout ----------
export function layout({ rel, title, description, body, kind, site, canonical, extraHead = '', data = {} }) {
  const fullTitle = title ? `${title} · ${site.title}` : site.title;
  return `<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(fullTitle)}</title>
<meta name="description" content="${esc(description || site.tagline)}">
<meta property="og:title" content="${esc(fullTitle)}">
<meta property="og:description" content="${esc(description || site.tagline)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="${esc(site.title)}">
${canonical ? `<meta property="og:url" content="${esc(canonical)}">` : ''}
<meta property="og:image" content="${esc(site.baseUrl)}assets/og-image.jpg${site.ogVersion ? `?v=${site.ogVersion}` : ''}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Azure AI Gateway Labs. Apps, agents, and code connect through one gateway to models, tools, and connectors.">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="${esc(site.baseUrl)}assets/og-image.jpg${site.ogVersion ? `?v=${site.ogVersion}` : ''}">
${canonical ? `<link rel="canonical" href="${esc(canonical)}">` : ''}
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1b1a1f" media="(prefers-color-scheme: dark)">
<link rel="icon" href="${rel}assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="${rel}assets/site.css">
<script>(function(){var d=document.documentElement;try{var t=localStorage.getItem('aigw-theme');if(!t)t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';d.dataset.theme=t;}catch(e){}try{var m=JSON.parse(localStorage.getItem('aigw-motion'));if(m==null)m=matchMedia('(prefers-reduced-motion: reduce)').matches?'off':'on';d.dataset.motion=m;}catch(e){d.dataset.motion='on';}})();</script>
${extraHead}
</head>
<body class="page-${kind}">
<a class="skip-link" href="#main">Skip to content</a>
${topbar(rel, site, kind)}
${body}
${footer(rel, site)}
<script>window.AIGW=${JSON.stringify({ rel, ...data }).replace(/</g, '\\u003c')};</script>
<script src="${rel}assets/site.js" defer></script>
</body>
</html>
`;
}

function topbar(rel, site, kind) {
  return `<header class="topbar">
  <div class="topbar-inner">
    ${kind === 'lab' ? `<button class="icon-btn nav-toggle" type="button" aria-label="Open lab navigation" aria-controls="sidebar" aria-expanded="false">${I.menu}</button>` : ''}
    <a class="brand" href="${rel}index.html" aria-label="Azure AI Gateway Labs home">
      <img class="brand-logo" src="${rel}assets/favicon.svg" width="28" height="28" alt="">
      <span class="brand-name"><span class="brand-azure">Azure </span>AI Gateway</span> <span class="brand-badge">Labs</span>
    </a>
    <nav class="topnav" aria-label="Primary">
      <a href="${rel}labs/"${kind === 'catalog' || kind === 'lab' ? ' aria-current="page"' : ''}>All labs</a>
      <a href="${rel}index.html#paths">Learning paths</a>
      <a href="${rel}index.html#use-cases">Use cases</a>
      <a href="${rel}release-notes/"${kind === 'releases' ? ' aria-current="page"' : ''}>What's new</a>
    </nav>
    <div class="topbar-actions">
      <button class="search-trigger" type="button" data-search-open aria-keyshortcuts="Control+K Meta+K">${I.search}<span>Search labs</span><kbd data-kbd aria-hidden="true">Ctrl K</kbd></button>
      <a class="topbar-link hide-sm" href="${site.docs}" target="_blank" rel="noopener">Documentation</a>
      <button class="icon-btn motion-toggle" type="button" data-motion-toggle aria-pressed="false" aria-label="Pause animations" title="Pause animations">${I.pause}</button>
      <button class="icon-btn" type="button" data-theme-toggle aria-pressed="false" aria-label="Dark mode" title="Dark mode"><span class="theme-sun">${I.sun}</span><span class="theme-moon">${I.moon}</span></button>
      <a class="icon-btn hide-sm" href="${site.repo}" target="_blank" rel="noopener" aria-label="GitHub repository">${I.github}</a>
      <a class="btn btn-primary btn-pill btn-sm hide-xs" href="${site.portal}" target="_blank" rel="noopener">Open portal</a>
    </div>
  </div>
</header>`;
}

function footer(rel, site) {
  const year = new Date().getFullYear();
  return `<footer class="footer">
  <div class="footer-inner">
    <div class="footer-brand">
      <a class="brand" href="${rel}index.html"><img class="brand-logo" src="${rel}assets/favicon.svg" width="24" height="24" alt=""><span class="brand-name">Azure AI Gateway</span> <span class="brand-badge">Labs</span></a>
      <p>Hands-on labs for Azure AI Gateway.</p>
    </div>
    <div class="footer-cols">
      <div><h2>Labs</h2><a href="${rel}labs/">All labs</a><a href="${rel}index.html#paths">Learning paths</a><a href="${rel}index.html#use-cases">Use cases</a><a href="${rel}setup/">Setup guide</a><a href="${rel}troubleshooting/">Troubleshooting</a><a href="${rel}release-notes/">Release notes</a><a href="${rel}skills/azure-ai-gateway-labs/SKILL.md" title="azure-ai-gateway-labs: the agent skill that teaches coding agents how to use these labs">Agent skill</a></div>
      <div><h2>Product</h2><a href="${site.portal}" target="_blank" rel="noopener">AI Gateway portal</a><a href="${site.docs}" target="_blank" rel="noopener">Documentation</a><a href="${site.learn}" target="_blank" rel="noopener">Microsoft Learn</a></div>
      <div><h2>Contribute</h2><a href="${site.repo}" target="_blank" rel="noopener">GitHub repository</a><a href="${site.repo}/blob/${site.branch}/labs/AUTHORING.md" target="_blank" rel="noopener">Authoring guide</a><a href="${site.repo}/issues/new?labels=labs" target="_blank" rel="noopener">Report an issue</a></div>
    </div>
  </div>
  <div class="footer-legal"><span>© ${year} Microsoft</span><a href="https://go.microsoft.com/fwlink/?LinkId=521839" target="_blank" rel="noopener">Privacy</a><a href="https://go.microsoft.com/fwlink/?LinkID=206977" target="_blank" rel="noopener">Terms of use</a><a href="https://www.microsoft.com/trademarks" target="_blank" rel="noopener">Trademarks</a></div>
</footer>`;
}

// ---------- Shared pieces ----------
function trackChips(tracks, { labels = true } = {}) {
  return `<span class="track-chips">${tracks.map((t) => `<span class="track-chip" title="${esc(t === 'notebook' ? 'Jupyter notebook' : TRACK_LABELS[t] || t)}">${trackIcon(t)}${labels ? `<span>${esc(SHORT_TRACK[t] || t)}</span>` : ''}</span>`).join('')}</span>`;
}

// Lab number, or a bolt for the unnumbered quick start.
const numHtml = (l) => (l.quick ? `<span class="num-quick" title="${esc(l.label)}">${I.bolt}</span>` : l.num);

function statusBadge(status) {
  if (!status) return '';
  const label = { new: 'New', preview: 'Preview', emerging: 'Emerging' }[status] || status;
  return `<span class="badge badge-${esc(status)}">${esc(label)}</span>`;
}

export function labCard(lab, rel, cat, { compact = false } = {}) {
  const icon = I[CATEGORY_ICONS[lab.category]] || I.book;
  const paths = (lab.paths || []).join(' ');
  const text = [lab.title, lab.summary, ...(lab.tags || []), cat?.title].join(' ').toLowerCase();
  return `<a class="lab-card${compact ? ' lab-card-compact' : ''}" href="${labUrl(rel, lab.slug)}" data-lab="${lab.slug}" data-category="${lab.category}" data-level="${esc(lab.level)}" data-tracks="${labTracks(lab).join(' ')}" data-status="${esc(lab.status || '')}" data-paths="${paths}" data-text="${esc(text)}" style="--c: var(--cat-${cat?.color || 'violet'})">
  <div class="lab-card-top">
    <span class="lab-card-num">${numHtml(lab)}</span>
    <span class="lab-card-icon">${icon}</span>
    ${statusBadge(lab.status)}
    <span class="lab-card-progress" data-progress-for="${lab.slug}" hidden></span>
  </div>
  <div class="lab-card-body">
    <span class="lab-card-cat">${esc(cat?.title || lab.category)}</span>
    <h3 class="lab-card-title">${esc(lab.title)}</h3>
    ${compact ? '' : `<p class="lab-card-summary">${esc(lab.summary)}</p>`}
    <div class="lab-card-meta">
      <span class="meta">${levelDots(lab.level)}${esc(lab.level)}</span>
      <span class="meta">${I.clock}${fmtDuration(lab.duration)}</span>
      ${trackChips(labTracks(lab), { labels: false })}
    </div>
  </div>
</a>`;
}

// ---------- Hero illustration ----------
function heroDiagram(rel) {
  // Animated Apps / Agents → AI Gateway → Models / MCP flow, themed with CSS variables.
  const left = [
    { y: 70, label: 'Apps', icon: I.portal },
    { y: 170, label: 'Agents', icon: I.agent },
    { y: 270, label: 'Coding agents', icon: I.code },
  ];
  const right = [
    { y: 50, label: 'Microsoft Foundry', logo: 'microsoft-foundry' },
    { y: 120, label: 'OpenAI · Anthropic', logo: 'anthropic' },
    { y: 190, label: 'Bedrock · Vertex AI', logo: 'aws-bedrock' },
    { y: 270, label: 'MCP servers & APIs', icon: I.tools },
  ];
  const cx = 320; const cy = 170;
  const curve = (x1, y1, x2, y2) => `M${x1} ${y1} C ${(x1 + x2) / 2} ${y1}, ${(x1 + x2) / 2} ${y2}, ${x2} ${y2}`;
  const paths = [
    ...left.map((n, i) => ({ id: `hl${i}`, d: curve(152, n.y + 20, cx - 56, cy), cls: 'in', dur: 2.6 + i * 0.4 })),
    ...right.map((n, i) => ({ id: `hr${i}`, d: curve(cx + 56, cy, 466, n.y + 20), cls: i === 3 ? 'tool' : 'out', dur: 2.4 + i * 0.35 })),
  ];
  const chips = [
    { label: 'Entra ID', a: -150 }, { label: 'Token limits', a: -95 }, { label: 'Budgets', a: -30 },
    { label: 'Content safety', a: 30 }, { label: 'Tool controls', a: 95 }, { label: 'OpenTelemetry', a: 150 },
  ];
  return `<svg class="hero-diagram" viewBox="0 0 640 340" role="img" aria-label="Apps, agents, and coding agents call AI Gateway, which applies identity, limits, budgets, safety, tool controls, and telemetry before routing to models from any provider and to MCP servers.">
  <defs>
    <radialGradient id="hd-glow" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="var(--hd-glow)" stop-opacity=".55"/><stop offset="1" stop-color="var(--hd-glow)" stop-opacity="0"/></radialGradient>
    <linearGradient id="hd-ring" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3BD5FF"/><stop offset=".5" stop-color="#7e5be8"/><stop offset="1" stop-color="#BB45EA"/></linearGradient>
  </defs>
  <circle cx="${cx}" cy="${cy}" r="120" fill="url(#hd-glow)"/>
  <circle class="hd-orbit" cx="${cx}" cy="${cy}" r="96"/>
  <circle class="hd-orbit hd-orbit-2" cx="${cx}" cy="${cy}" r="70"/>
  ${paths.map((p) => `<path id="${p.id}" class="hd-link hd-${p.cls}" d="${p.d}"/>`).join('')}
  ${paths.map((p, i) => `<circle class="hd-dot hd-dot-${p.cls}" r="3.2"><animateMotion dur="${p.dur}s" begin="-${(i * 0.37 + 0.2).toFixed(2)}s" repeatCount="indefinite" keyPoints="0;1" keyTimes="0;1" calcMode="linear"><mpath href="#${p.id}"/></animateMotion></circle>`).join('')}
  ${left.map((n) => `<g class="hd-node" transform="translate(16 ${n.y})"><rect width="136" height="40" rx="8"/><g transform="translate(12 10)" class="hd-ico">${n.icon.replace('class="i"', 'class="i" width="20" height="20"')}</g><text x="40" y="25">${esc(n.label)}</text></g>`).join('')}
  ${right.map((n) => `<g class="hd-node" transform="translate(466 ${n.y})"><rect width="164" height="40" rx="8"/>${n.logo ? `<image href="${rel}labs/assets/providers/${n.logo}.png" x="11" y="10" width="20" height="20"/>` : `<g transform="translate(11 10)" class="hd-ico">${n.icon.replace('class="i"', 'class="i" width="20" height="20"')}</g>`}<text x="38" y="25">${esc(n.label)}</text></g>`).join('')}
  <g class="hd-core">
    <circle cx="${cx}" cy="${cy}" r="50" class="hd-pulse"/>
    <circle cx="${cx}" cy="${cy}" r="50" class="hd-core-bg"/>
    <circle cx="${cx}" cy="${cy}" r="50" fill="none" stroke="url(#hd-ring)" stroke-width="2"/>
    <image href="${rel}assets/favicon.svg" x="${cx - 19}" y="${cy - 31}" width="38" height="38"/>
    <text x="${cx}" y="${cy + 26}" text-anchor="middle" class="hd-core-label">AI Gateway</text>
  </g>
  ${chips.map((c) => {
    const r = 112; const rad = (c.a - 90) * Math.PI / 180;
    const x = cx + r * Math.cos(rad); const y = cy + r * Math.sin(rad) * 0.98;
    const w = c.label.length * 6.1 + 18;
    return `<g class="hd-chip" transform="translate(${(x - w / 2).toFixed(1)} ${(y - 11).toFixed(1)})"><rect class="hd-chip-base" width="${w.toFixed(1)}" height="22" rx="11"/><rect width="${w.toFixed(1)}" height="22" rx="11"/><text x="${(w / 2).toFixed(1)}" y="15" text-anchor="middle">${esc(c.label)}</text></g>`;
  }).join('')}
</svg>`;
}

// ---------- Home ----------
export function homePage({ rel, site, catalog, labs, totals, latest }) {
  const byId = Object.fromEntries(labs.map((l) => [l.slug, l]));
  const cats = Object.fromEntries(catalog.categories.map((c) => [c.id, c]));
  const quick = byId.quickstart;
  const essentials = catalog.paths.find((p) => p.id === 'essentials');
  const startHref = labUrl(rel, quick ? 'quickstart' : labs[0].slug);
  // Condensed from a real run of the quick start's Azure CLI track. One block per line, so narrow screens wrap with a hanging indent.
  const qsLines = [
    ['qs-st', '⏳ Gateway <span class="qs-hl qs-nb">aigw-540780</span> is provisioning in the background'],
    ['qs-st', '✨ Model deployment <span class="qs-hl">gpt-5-mini</span> is ready'],
    ['qs-st', '🚀 Gateway <span class="qs-hl qs-nb">aigw-540780</span> <span class="qs-ok">is ready</span>'],
    ['qs-st', '🔖 Alias <span class="qs-hl">gpt-5-mini</span> is ready'],
    ['qs-st', '🔑 API key <span class="qs-nb">app-first-call</span> is ready'],
    ['qs-st qs-url', '🌐 Runtime URL: <span class="qs-hl">https://aigw-54078-q2mv7x4kz9hpt.eastus2-01.ai.gateway.azure.com</span>'],
    ['qs-gap qs-hang', '<span class="qs-prompt">$</span> curl $AI_GATEWAY_URL/…/chat/completions -H "api-key: …"'],
    ['qs-st', '🤖 An AI gateway sits between applications and AI models, routing requests while managing access, security, and usage.'],
  ].map(([c, h]) => `<span class="qs-line${c ? ` ${c}` : ''}">${h}</span>`).join('');

  const trackCards = [
    { id: 'portal', title: 'Portal', text: 'Click-by-click guides in the AI Gateway portal, with exact labels and screenshots.' },
    { id: 'cli', title: 'Azure CLI', text: 'Repeatable az aigateway and az deployment commands you can paste into Bash or PowerShell.' },
    { id: 'iac', title: 'Bicep + azd', text: 'Self-contained azd templates: clone a lab, run azd up, and clean up with azd down.' },
    { id: 'code', title: 'Code & REST', text: 'Python, TypeScript, and .NET clients, agent frameworks, and REST calls.' },
  ];

  const pathCards = catalog.paths.map((p) => {
    const pl = p.labs.map((s) => byId[s]).filter(Boolean);
    const mins = pl.reduce((a, l) => a + l.duration, 0);
    return `<article class="path-card" data-path="${p.id}">
      <div class="path-card-head"><span class="path-icon">${I[p.icon] || I.flag}</span><div><h3>${esc(p.title)}</h3><span class="path-persona">${esc(p.persona)}</span></div></div>
      <p>${esc(p.description)}</p>
      <ol class="path-steps">${pl.map((l) => `<li><a href="${labUrl(rel, l.slug)}?path=${p.id}" data-lab-link="${l.slug}"><span class="path-num">${numHtml(l)}</span><span class="path-title">${esc(l.short || l.title)}</span><span class="path-check" aria-hidden="true">${I.check}</span></a></li>`).join('')}</ol>
      <div class="path-card-foot"><span class="meta">${I.book}${pl.length} labs</span><span class="meta">${I.clock}${fmtDuration(mins)}</span><a class="btn btn-secondary btn-sm" href="${labUrl(rel, pl[0].slug)}?path=${p.id}" data-path-start="${p.id}">Start path ${I.arrowR}</a></div>
    </article>`;
  }).join('');

  const useCase = (u, kind) => {
    const l = byId[u.lab];
    return `<a class="usecase ${kind}" href="${labUrl(rel, u.lab)}">
      <span class="usecase-icon">${I[u.icon] || I.sparkle}</span>
      <span class="usecase-body"><span class="usecase-title">${esc(u.title)}</span><span class="usecase-text">${esc(u.text)}</span>${l ? `<span class="usecase-lab">${l.label} · ${esc(l.short || l.title)} ${I.arrowR}</span>` : ''}</span>
    </a>`;
  };

  const catTiles = catalog.categories.map((c) => {
    const n = labs.filter((l) => l.category === c.id).length;
    return `<a class="cat-tile" href="${rel}labs/?category=${c.id}" style="--c: var(--cat-${c.color})"><span class="cat-tile-icon">${I[CATEGORY_ICONS[c.id]]}</span><span class="cat-tile-title">${esc(c.title)}</span><span class="cat-tile-desc">${esc(c.description)}</span><span class="cat-tile-count">${n} lab${n === 1 ? '' : 's'}</span></a>`;
  }).join('');

  const featured = ['02-first-model-call', '04-federate-mcp-tools', '06-token-limits', '07-cost-budgets', '11-entra-rbac', '16-foundry-hosted-agent']
    .map((s) => byId[s]).filter(Boolean).map((l) => labCard(l, rel, cats[l.category])).join('');

  const body = `<main id="main" class="home">
  <section class="hero">
    <div class="hero-bg" aria-hidden="true"></div>
    <div class="hero-inner container">
      <div class="hero-copy">
        ${latest ? `<a class="hero-news" href="${rel}release-notes/#${latest.id}"><span class="hero-news-tag">New</span><span class="hero-news-text">${esc(latest.title)}</span>${I.arrowR}</a>` : ''}
        <p class="eyebrow">Azure AI Gateway labs</p>
        <h1>Learn AI Gateway by <span class="grad-text">building with it</span></h1>
        <p class="hero-lead">${esc(site.tagline)} Guided labs for customers and field teams: publish models from any provider, federate MCP tools, enforce limits and budgets, go keyless, observe every token, and govern agents.</p>
        <div class="hero-cta">
          <a class="btn btn-primary btn-lg" href="${startHref}">${I.bolt}Start the 5-minute quick start</a>
          <a class="btn btn-secondary btn-lg" href="${rel}labs/">Browse all ${totals.labs} labs</a>
        </div>
        <dl class="hero-stats">
          <div><dt>Labs</dt><dd>${totals.labs}</dd></div>
          <div><dt>Learning paths</dt><dd>${catalog.paths.length}</dd></div>
          <div><dt>Hands-on time</dt><dd>${Math.round(totals.minutes / 60)} h</dd></div>
          <div title="Portal, Azure CLI, Bicep and azd, Code and REST"><dt>Tracks per lab</dt><dd>4</dd></div>
        </dl>
      </div>
      <div class="hero-visual">${heroDiagram(rel)}</div>
    </div>
  </section>
${quick ? `
  <section class="section qs-band" id="quick-start" aria-labelledby="qs-band-title"><div class="container">
    <div class="qs-card">
      <div class="qs-copy">
        <p class="eyebrow"><span class="num-quick">${I.bolt}</span>Start here · ${quick.duration} minutes</p>
        <h2 id="qs-band-title">Your first model call in five minutes</h2>
        <p>In the AI Gateway portal, with a few Azure CLI commands in Cloud Shell, or with one <code>azd up</code>, you create a gateway, publish a Microsoft Foundry model behind an alias, and create a runtime key. Then you make your first call through the gateway, the way an app does: with the alias and the key.</p>
        <ol class="qs-steps">
          <li><span class="qs-step-num">1</span><span><strong>Understand</strong> the building blocks</span><span class="qs-step-time">1 min</span></li>
          <li><span class="qs-step-num">2</span><span><strong>Create</strong> a gateway in the portal, Azure CLI, or azd</span><span class="qs-step-time">3 min</span></li>
          <li><span class="qs-step-num">3</span><span><strong>Call</strong> the model through the gateway</span><span class="qs-step-time">1 min</span></li>
        </ol>
        <div class="qs-cta">
          <a class="btn btn-primary" href="${startHref}">Start the quick start ${I.arrowR}</a>
          ${essentials ? `<a class="btn btn-ghost" href="#paths">Then go deeper: ${esc(essentials.title)}</a>` : ''}
        </div>
      </div>
      <figure class="qs-terminal">
        <div class="qs-terminal-bar" aria-hidden="true"><span></span><span></span><span></span><b>Azure CLI · Bash</b></div>
        <pre tabindex="0"><code>${qsLines}</code></pre>
        <figcaption>Condensed from a real run of the Azure CLI track.</figcaption>
      </figure>
    </div>
  </div></section>` : ''}

  <section class="section" id="tracks"><div class="container">
    <div class="section-head"><p class="eyebrow">How you learn</p><h2>Your tools, your pace</h2><p>Every lab offers the tracks that fit the task. Pick one and the site remembers it across labs.</p></div>
    <div class="track-grid">
      ${trackCards.map((t) => `<div class="track-card"><span class="track-card-icon">${I[t.id] || I.code}</span><h3>${t.title}</h3><p>${t.text}</p></div>`).join('')}
    </div>
    <ul class="feature-row">
      <li>${I.checkpoint}<span><strong>Checkpoints</strong> after every task</span></li>
      <li>${I.sliders}<span><strong>Your values</strong> fill every command</span></li>
      <li>${I.play}<span><strong>Interactive simulators</strong> for limits, budgets, and tools</span></li>
      <li>${I.broom}<span><strong>Clean-up</strong> and troubleshooting for every lab</span></li>
    </ul>
  </div></section>

  <section class="section section-tinted" id="paths"><div class="container">
    <div class="section-head"><p class="eyebrow">Learning paths</p><h2>Follow a path built for your role</h2><p>Each path strings labs together in order. Your progress is saved in this browser.</p></div>
    <div class="path-grid">${pathCards}</div>
  </div></section>

  <section class="section" id="use-cases"><div class="container">
    <div class="section-head"><p class="eyebrow">Use cases</p><h2>From the essentials to what's emerging</h2><p>Start with the controls every AI platform needs, then explore agent-era governance.</p></div>
    <div class="usecase-cols">
      <div class="usecase-col"><h3 class="usecase-col-title"><span class="dot dot-core"></span>Core use cases</h3>${catalog.useCases.core.map((u) => useCase(u, 'core')).join('')}</div>
      <div class="usecase-col"><h3 class="usecase-col-title"><span class="dot dot-emerging"></span>Emerging use cases</h3>${catalog.useCases.emerging.map((u) => useCase(u, 'emerging')).join('')}</div>
    </div>
  </div></section>

  <section class="section section-tinted" id="categories"><div class="container">
    <div class="section-head"><p class="eyebrow">Catalog</p><h2>Explore by topic</h2></div>
    <div class="cat-grid">${catTiles}</div>
    <div class="section-head section-head-row"><h2 class="h3">Popular labs</h2><a class="link-arrow" href="${rel}labs/">See all labs ${I.arrowR}</a></div>
    <div class="lab-grid">${featured}</div>
  </div></section>

  <section class="section" id="anatomy"><div class="container">
    <div class="anatomy">
      <div class="anatomy-copy">
        <p class="eyebrow">Inside every lab</p>
        <h2>Built for doing, not just reading</h2>
        <ul class="anatomy-list">
          <li><span class="anatomy-n">1</span><div><strong>Scenario and diagram.</strong> Who has the problem, and how the gateway solves it.</div></li>
          <li><span class="anatomy-n">2</span><div><strong>How it works.</strong> The concept in two minutes, often with a live simulator.</div></li>
          <li><span class="anatomy-n">3</span><div><strong>Step-by-step tracks.</strong> Portal, CLI, REST, Bicep, or code. Mark each step done.</div></li>
          <li><span class="anatomy-n">4</span><div><strong>Verify and clean up.</strong> Checkpoints prove it works, then remove what you created.</div></li>
        </ul>
        <a class="btn btn-secondary" href="${labUrl(rel, '06-token-limits')}">See an example lab ${I.arrowR}</a>
      </div>
      <div class="anatomy-visual" aria-hidden="true">
        <div class="mock">
          <div class="mock-bar"><i></i><i></i><i></i><span>Throttle tokens per caller with token limits</span></div>
          <div class="mock-body">
            <div class="mock-tabs"><span class="on">${I.portal}Portal</span><span>${I.cli}Azure CLI</span><span>${I.rest}REST</span><span>${I.iac}Bicep</span></div>
            <div class="mock-step done"><span class="mock-n">${I.check}</span><div><b>Start the policy wizard</b><span class="mock-path"><em>Policies</em>›<em>Add policy</em>›<em>Token rate limit</em></span></div></div>
            <div class="mock-step done"><span class="mock-n">${I.check}</span><div><b>Choose where the limit applies</b><span class="mock-line w70"></span></div></div>
            <div class="mock-step"><span class="mock-n">3</span><div><b>Configure the allowance</b><span class="mock-line w90"></span><span class="mock-line w50"></span></div></div>
            <div class="mock-check">${I.checkpoint}<span><b>Checkpoint</b> Policies lists a Token rate limit for your model.</span></div>
            <div class="mock-code"><span class="c1">$</span> ./trigger-token-limit.sh chat 8<br><span class="c2">1  200  713</span><br><span class="c2">2  200  431</span><br><span class="c3">4  429  Retry-After: 41</span></div>
          </div>
        </div>
      </div>
    </div>
  </div></section>

  <section class="section" id="resources"><div class="container">
    <div class="section-head"><p class="eyebrow">Resources</p><h2>Keep going</h2></div>
    <div class="resource-grid">
      <a class="resource" href="${site.portal}" target="_blank" rel="noopener"><span class="resource-icon">${I.portal}</span><span><b>AI Gateway portal</b><span>Create and manage gateways, models, tools, and policies.</span></span>${I.external}</a>
      <a class="resource" href="${site.docs}" target="_blank" rel="noopener"><span class="resource-icon">${I.book}</span><span><b>Documentation</b><span>Concepts, quickstarts, and release notes.</span></span>${I.external}</a>
      <a class="resource" href="${site.learn}" target="_blank" rel="noopener"><span class="resource-icon">${I.layers}</span><span><b>Microsoft Learn overview</b><span>What Azure AI Gateway is and how it relates to API Management.</span></span>${I.external}</a>
      <a class="resource" href="${site.repo}/tree/${site.branch}/cli" target="_blank" rel="noopener"><span class="resource-icon">${I.cli}</span><span><b>AI Gateway CLI extension</b><span>The az aigateway extension and its command reference.</span></span>${I.external}</a>
      <a class="resource" href="https://learn.microsoft.com/azure/foundry/agents/quickstarts/quickstart-hosted-agent" target="_blank" rel="noopener"><span class="resource-icon">${I.agent}</span><span><b>Foundry hosted agents</b><span>Build agent code and deploy it to Microsoft Foundry with azd.</span></span>${I.external}</a>
      <a class="resource" href="${site.repo}" target="_blank" rel="noopener"><span class="resource-icon">${I.sparkle}</span><span><b>Coding-agent plugin</b><span>Skills for Copilot, Claude Code, Cursor, and Gemini.</span></span>${I.external}</a>
    </div>
  </div></section>
</main>`;
  return body;
}

// ---------- Catalog ----------
export function catalogPage({ rel, catalog, labs }) {
  const cats = Object.fromEntries(catalog.categories.map((c) => [c.id, c]));
  const levels = ['Beginner', 'Intermediate', 'Advanced'];
  const tracks = ['portal', 'cli', 'iac', 'rest', 'code', 'notebook'];
  const chip = (group, value, label, extra = '') => `<button class="chip" type="button" data-filter="${group}" data-value="${value}" aria-pressed="false"${extra}>${label}</button>`;
  return `<main id="main" class="catalog">
  <section class="page-hero">
    <div class="page-hero-bg" aria-hidden="true"></div>
    <div class="container">
      <nav class="breadcrumb" aria-label="Breadcrumb"><a href="${rel}index.html">Home</a><span>/</span><span aria-current="page">All labs</span></nav>
      <h1>All labs</h1>
      <p class="lead">${labs.length} hands-on labs, from your first governed call to agent governance in production.</p>
      <div class="catalog-search">${I.search}<input type="search" id="catalog-q" placeholder="Filter by keyword, for example MCP, budget, or Entra" aria-label="Filter labs" autocomplete="off"><span class="catalog-count" id="catalog-count" aria-live="polite"></span></div>
    </div>
  </section>
  <div class="container catalog-body">
    <aside class="filters" aria-label="Filters">
      <div class="filter-group"><h2>Topic</h2><div class="chip-col">${catalog.categories.map((c) => chip('category', c.id, `<span class="cat-dot" style="--c: var(--cat-${c.color})"></span>${esc(c.title)}<span class="chip-count">${labs.filter((l) => l.category === c.id).length}</span>`)).join('')}</div></div>
      <div class="filter-group"><h2>Level</h2><div class="chip-row">${levels.map((l) => chip('level', l, `${levelDots(l)}${l}`)).join('')}</div></div>
      <div class="filter-group"><h2>Track</h2><div class="chip-row">${tracks.map((t) => chip('track', t, `${trackIcon(t)}${SHORT_TRACK[t]}`)).join('')}</div></div>
      <div class="filter-group"><h2>Learning path</h2><div class="chip-col">${catalog.paths.map((p) => chip('path', p.id, `${I[p.icon] || I.flag}${esc(p.title)}`)).join('')}</div></div>
      <div class="filter-group"><h2>Status</h2><div class="chip-row">${chip('status', 'new', 'New')}${chip('status', 'emerging', 'Emerging')}</div></div>
      <button class="btn btn-ghost btn-sm" type="button" id="filters-clear" hidden>${I.close}Clear filters</button>
    </aside>
    <div class="catalog-results">
      <div class="lab-grid" id="lab-grid">${labs.map((l) => labCard(l, rel, cats[l.category])).join('')}</div>
      <div class="empty" id="catalog-empty" hidden>${I.search}<h2>No labs match those filters</h2><p>Try fewer filters or a different keyword.</p><button class="btn btn-secondary btn-sm" type="button" data-clear-filters>Clear filters</button></div>
    </div>
  </div>
</main>`;
}

// ---------- Lab ----------
export function labPage({ rel, site, catalog, labs, lab, html, toc, prev, next }) {
  const cats = Object.fromEntries(catalog.categories.map((c) => [c.id, c]));
  const cat = cats[lab.category];
  const byId = Object.fromEntries(labs.map((l) => [l.slug, l]));
  const sidebar = catalog.categories.map((c) => {
    const items = labs.filter((l) => l.category === c.id);
    if (!items.length) return '';
    return `<div class="side-group"><h2 style="--c: var(--cat-${c.color})">${esc(c.title)}</h2><ul>${items.map((l) => `<li><a href="${labUrl(rel, l.slug)}"${l.slug === lab.slug ? ' aria-current="page"' : ''} data-lab-link="${l.slug}"><span class="side-num">${numHtml(l)}</span><span class="side-title">${esc(l.short || l.title)}</span><span class="side-state" aria-hidden="true"></span></a></li>`).join('')}</ul></div>`;
  }).join('');

  const prereqs = (lab.prereqs || []).map((s) => byId[s]).filter(Boolean);
  const editUrl = `${site.repo}/edit/${site.branch}/labs/${lab.slug}/README.md`;
  const srcUrl = `${site.repo}/tree/${site.branch}/labs/${lab.slug}`;
  const notebookUrl = lab.notebook ? `${site.repo}/blob/${site.branch}/labs/${lab.slug}/${encodeURIComponent(lab.notebook)}` : '';
  const updated = lab.updated ? new Date(lab.updated) : null;
  const updatedText = updated ? updated.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) : '';

  const pager = `<nav class="pager" aria-label="Previous and next labs">
    ${prev ? `<a class="pager-link prev" href="${labUrl(rel, prev.slug)}" data-pager="prev"><span class="pager-dir">${I.arrowL}Previous</span><span class="pager-title">${prev.quick ? prev.label : prev.num} · ${esc(prev.title)}</span></a>` : '<span></span>'}
    ${next ? `<a class="pager-link next" href="${labUrl(rel, next.slug)}" data-pager="next"><span class="pager-dir">Next${I.arrowR}</span><span class="pager-title">${next.quick ? next.label : next.num} · ${esc(next.title)}</span></a>` : '<span></span>'}
  </nav>`;

  return `<div class="lab-layout" style="--c: var(--cat-${cat?.color || 'violet'})">
  <div class="read-progress" aria-hidden="true"><span></span></div>
  <aside class="sidebar" id="sidebar" aria-label="Labs">
    <div class="sidebar-inner">
      <a class="side-back" href="${rel}labs/">${I.arrowL}All labs</a>
      <div class="path-banner" id="path-banner" hidden></div>
      ${sidebar}
    </div>
  </aside>
  <div class="sidebar-scrim" data-nav-close hidden></div>
  <main id="main" class="lab-main" data-lab="${lab.slug}">
    <nav class="breadcrumb" aria-label="Breadcrumb"><a href="${rel}labs/">Labs</a><span>/</span><a href="${rel}labs/?category=${lab.category}">${esc(cat?.title || lab.category)}</a><span>/</span><span aria-current="page">${lab.label}</span></nav>
    <header class="lab-header">
      <div class="lab-eyebrow"><span class="lab-eyebrow-icon">${I[CATEGORY_ICONS[lab.category]] || I.book}</span>${esc(cat?.title || lab.category)} · ${lab.label}${statusBadge(lab.status)}</div>
      <h1>${esc(lab.title)}</h1>
      <p class="lead">${esc(lab.summary)}</p>
      <div class="lab-meta">
        <span class="meta-pill">${levelDots(lab.level)}${esc(lab.level)}</span>
        <span class="meta-pill">${I.clock}${fmtDuration(lab.duration)}</span>
        <span class="meta-pill meta-tracks">${trackChips(labTracks(lab))}</span>
        ${updatedText ? `<span class="meta-updated">Updated <time datetime="${updated.toISOString().slice(0, 10)}">${updatedText}</time></span>` : ''}
      </div>
      <div class="lab-actions">
        <button class="btn btn-secondary btn-sm" type="button" data-values-open>${I.sliders}Your values</button>
        <button class="btn btn-secondary btn-sm" type="button" data-setup-open>${I.wrench}Setup guide<span class="setup-badge" data-setup-badge hidden></span></button>
        <button class="btn btn-ghost btn-sm" type="button" data-copy-md="index.md">${I.markdown}Copy as Markdown</button>${lab.video ? `
        <a class="btn btn-ghost btn-sm" href="#${lab.video.id}" title="${esc(lab.video.title)}">${I.play}Watch video</a>` : ''}${notebookUrl ? `
        <a class="btn btn-ghost btn-sm" href="${notebookUrl}" target="_blank" rel="noopener" title="Run this lab end to end in Jupyter">${I.notebook}Notebook</a>` : ''}
        <a class="btn btn-ghost btn-sm" href="${srcUrl}" target="_blank" rel="noopener">${I.github}Source</a>
        <a class="btn btn-ghost btn-sm" href="${editUrl}" target="_blank" rel="noopener">${I.edit}Edit</a>
      </div>
    </header>
    <section class="lab-overview">
      <div class="overview-col">
        <h2>${I.flag}What you'll do</h2>
        <ul class="objectives">${(lab.objectives || []).map((o) => `<li>${I.check}<span>${esc(o)}</span></li>`).join('')}</ul>
      </div>
      <div class="overview-col">
        <h2>${I.book}Before you start</h2>
        ${prereqs.length ? `<ul class="prereq-list">${prereqs.map((p) => `<li><a href="${labUrl(rel, p.slug)}" data-lab-link="${p.slug}"><span class="side-num">${numHtml(p)}</span>${esc(p.title)}<span class="side-state" aria-hidden="true"></span></a></li>`).join('')}</ul>` : '<p class="muted">No prerequisite labs. Start here.</p>'}
        <p class="overview-tracks">Tracks: ${lab.tracks.map((t) => `<span>${esc((t === 'iac' && lab.iacLabel) || TRACK_LABELS[t] || t)}</span>`).join(', ')}${lab.notebook ? ', <span>Notebook</span>' : ''}</p>
      </div>
    </section>
    <article class="prose" id="lab-content">
${html}
    </article>
    <section class="lab-complete" id="lab-complete">
      <div class="lab-complete-icon">${I.trophy}</div>
      <div><h2>Finished the lab?</h2><p>Mark it complete to track your progress across paths. It's saved only in this browser.</p></div>
      <button class="btn btn-primary" type="button" data-complete-lab>${I.check}<span>Mark lab complete</span></button>
    </section>
    ${pager}
    <p class="feedback">Found a problem or have an idea? <a href="${site.repo}/issues/new?labels=labs&title=${encodeURIComponent(`[${lab.label}] `)}" target="_blank" rel="noopener">Open an issue</a> or <a href="${editUrl}" target="_blank" rel="noopener">edit this lab on GitHub</a>.</p>
  </main>
  <aside class="toc" aria-label="On this page">
    <div class="toc-inner">
      <div class="toc-progress">
        <svg viewBox="0 0 40 40" class="ring" aria-hidden="true"><circle cx="20" cy="20" r="16"/><circle cx="20" cy="20" r="16" class="ring-fill" pathLength="100"/></svg>
        <div><span class="toc-progress-label" id="progress-label">0 of 0 steps</span><button class="link-btn" type="button" data-reset-progress>Reset</button></div>
      </div>
      <h2>On this page</h2>
      <ul class="toc-list">${toc.map((t) => `<li><a href="#${t.id}" data-toc="${t.id}">${esc(t.text)}</a></li>`).join('')}</ul>
      <div class="toc-help">
        <button class="toc-tool" type="button" data-values-open>${I.sliders}<span>Your values</span></button>
        <a class="toc-tool" href="${rel}setup/" title="The one-time tasks: permissions, tools, sign-in, the aigateway extension, regions, the labs repo, and azd">${I.wrench}<span>Setup guide</span><span class="setup-badge" data-setup-badge hidden></span></a>
        ${lab.troubleshooting ? `<a class="toc-tool" href="${rel}troubleshooting/#${lab.troubleshooting}" title="The errors you might hit in this lab, with their likely causes and fixes">${I.lifebuoy}<span>Troubleshooting</span></a>` : ''}
        <a class="toc-tool" href="${site.portal}" target="_blank" rel="noopener">${I.portal}<span>Open the portal</span></a>
        <a class="toc-tool" href="${site.docs}" target="_blank" rel="noopener">${I.book}<span>Product docs</span></a>
      </div>
    </div>
  </aside>
</div>`;
}

// ---------- Release notes ----------
export function releaseNotesPage({ rel, site, html, releases }) {
  const fmt = (iso) => new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
  const nav = releases.map((r, i) => `<li><a href="#${r.id}" data-toc="${r.id}"><time datetime="${r.product}">${fmt(r.product)}</time><span>${esc(r.title)}</span>${i === 0 ? '<span class="rn-latest">Latest</span>' : ''}</a></li>`).join('');
  return `<main id="main" class="releases">
  <section class="page-hero">
    <div class="page-hero-bg" aria-hidden="true"></div>
    <div class="container">
      <nav class="breadcrumb" aria-label="Breadcrumb"><a href="${rel}index.html">Home</a><span>/</span><span aria-current="page">Release notes</span></nav>
      <h1>What's new in the labs</h1>
      <p class="lead">Every Azure AI Gateway release, and where to practice it. The labs follow the <a href="${site.docs}/releases/${releases[0]?.product || ''}" target="_blank" rel="noopener">product release notes</a>: each entry lists the new product features and the lab that covers each one.</p>
      <div class="hero-cta">
        ${releases[0] ? `<a class="btn btn-primary btn-sm rn-hero-latest" href="#${releases[0].id}" title="Latest: ${esc(releases[0].title)}">${I.sparkle}<span>Latest: ${esc(releases[0].title)}</span></a>` : ''}
        <a class="btn btn-ghost btn-sm" href="${site.repo}/blob/${site.branch}/labs/RELEASE-NOTES.md" target="_blank" rel="noopener">${I.github}View on GitHub</a>
        <button class="btn btn-ghost btn-sm" type="button" data-copy-md="index.md">${I.markdown}Copy as Markdown</button>
      </div>
    </div>
  </section>
  <div class="container rn-body">
    <aside class="rn-nav" aria-label="Releases">
      <h2>Releases</h2>
      <ol class="rn-nav-list">${nav}</ol>
    </aside>
    <article class="prose rn-prose" id="lab-content">
${html}
    </article>
  </div>
</main>`;
}

// ---------- Guides: Setup guide and Troubleshooting ----------
function guidePage({ rel, site, cls, title, lead, file, cta = '', html, toc, navLabel = (t) => esc(t.text), before = '' }) {
  const nav = toc.map((t) => `<li><a href="#${t.id}" data-toc="${t.id}"><span>${navLabel(t)}</span></a></li>`).join('');
  return `<main id="main" class="releases ${cls}">
  <section class="page-hero">
    <div class="page-hero-bg" aria-hidden="true"></div>
    <div class="container">
      <nav class="breadcrumb" aria-label="Breadcrumb"><a href="${rel}index.html">Home</a><span>/</span><span aria-current="page">${title}</span></nav>
      <h1>${title}</h1>
      <p class="lead">${lead}</p>
      <div class="hero-cta">
        ${cta}
        <a class="btn btn-ghost btn-sm" href="${site.repo}/blob/${site.branch}/labs/${file}" target="_blank" rel="noopener">${I.github}View on GitHub</a>
        <button class="btn btn-ghost btn-sm" type="button" data-copy-md="index.md">${I.markdown}Copy as Markdown</button>
      </div>
    </div>
  </section>
  <div class="container rn-body">
    <aside class="rn-nav" aria-label="On this page">
      <h2>On this page</h2>
      <ol class="rn-nav-list">${nav}</ol>
    </aside>
    <article class="prose rn-prose" id="lab-content">
${before}${html}
    </article>
  </div>
</main>`;
}

export function setupPage({ rel, site, html, toc }) {
  return guidePage({
    rel, site, cls: 'setup', title: 'Setup guide', file: 'SETUP.md', html, toc,
    lead: 'The one-time tasks that every lab builds on: permissions, tools, sign-in, the <code>aigateway</code> extension, resource providers, regions, the labs repo, and the azd workflow. Do each one once, and mark it done.',
    cta: `<span class="setup-pill setup-pill-hero" data-setup-pill hidden></span>
        <button class="btn btn-primary btn-sm" type="button" data-values-open>${I.sliders}<span>Set your values</span></button>`,
  });
}

export function troubleshootingPage({ rel, site, html, toc, rows, lead }) {
  const filter = `<div class="ts-filter" role="search">
      <label class="ts-filter-box">${I.search}<span class="sr-only">Filter the errors</span><input id="ts-q" type="search" placeholder="Filter by error code or message" autocomplete="off" spellcheck="false" aria-describedby="ts-count"></label>
      <span class="ts-count" id="ts-count" aria-live="polite" data-total="${rows}">${rows} errors</span>
    </div>
    <p class="ts-empty" id="ts-empty" hidden>No errors match your filter. Try an error code such as <code>429</code>, or a word from the message.</p>
`;
  return guidePage({
    rel, site, cls: 'troubleshooting', title: 'Troubleshooting', file: 'TROUBLESHOOTING.md', html, toc, before: filter,
    lead,
    navLabel: (t) => {
      const m = t.text.match(/^Lab (\d{2}): (.+)$/);
      return m ? `<b class="rn-nav-num">${m[1]}</b>${esc(m[2])}` : esc(t.text);
    },
  });
}

export function notFoundPage({ rel }) {
  return `<main id="main" class="notfound">
  <div class="notfound-inner">
    <p class="eyebrow">404</p>
    <h1>This page took a different route</h1>
    <p class="lead">The page you're looking for doesn't exist or has moved.</p>
    <div class="hero-cta"><a class="btn btn-primary" href="${rel}labs/">Browse all labs</a><a class="btn btn-secondary" href="${rel}index.html">Go home</a></div>
  </div>
</main>`;
}
