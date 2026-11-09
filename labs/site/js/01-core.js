// Core helpers, theme, storage, toast, copy, values (placeholders).
const D = window.AIGW || { rel: './', labs: [], paths: [] };
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const h = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; };
const escHtml = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
let reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.dataset.motion === 'off';

const SV = (d) => `<svg class="i" viewBox="0 0 20 20" aria-hidden="true">${d}</svg>`;
const IC = {
  search: SV('<circle cx="8.5" cy="8.5" r="5"/><path d="m12.5 12.5 4.5 4.5"/>'),
  close: SV('<path d="m5 5 10 10M15 5 5 15"/>'),
  check: SV('<path d="m5 10.5 3.2 3.2L15 6.8"/>'),
  x: SV('<circle cx="10" cy="10" r="7.5"/><path d="m7.5 7.5 5 5M12.5 7.5l-5 5"/>'),
  ok: SV('<circle cx="10" cy="10" r="7.5"/><path d="m6.8 10.2 2.2 2.2 4.3-4.6"/>'),
  minus: SV('<circle cx="10" cy="10" r="7.5"/><path d="M6.5 10h7"/>'),
  sliders: SV('<path d="M3 6h7M14 6h3M3 14h3M10 14h7"/><circle cx="12" cy="6" r="2"/><circle cx="8" cy="14" r="2"/>'),
  info: SV('<circle cx="10" cy="10" r="7.5"/><path d="M10 9v5M10 6.2v.1"/>'),
  play: SV('<path d="M6.5 4.5v11l9-5.5Z"/>'),
  expand: SV('<path d="M3.5 7.5v-4h4M12.5 3.5h4v4M16.5 12.5v4h-4M7.5 16.5h-4v-4"/>'),
  reset: SV('<path d="M3.5 10a6.5 6.5 0 1 0 2-4.7"/><path d="M3.5 3.5v3.5H7"/>'),
  user: SV('<circle cx="10" cy="7" r="3.2"/><path d="M3.8 17a6.2 6.2 0 0 1 12.4 0"/>'),
  key: SV('<circle cx="6.5" cy="13.5" r="3.5"/><path d="m9 11 7.5-7.5M14 6l2 2M12 8l1.5 1.5"/>'),
  shield: SV('<path d="M10 2.5 16 5v4.5c0 4-2.7 6.7-6 8-3.3-1.3-6-4-6-8V5Z"/>'),
  gauge: SV('<path d="M3.5 14a6.5 6.5 0 1 1 13 0"/><path d="m10 14 3.5-4.5"/><circle cx="10" cy="14" r="1"/>'),
  coins: SV('<ellipse cx="8" cy="6" rx="5" ry="2.5"/><path d="M3 6v3.5C3 10.9 5.2 12 8 12s5-1.1 5-2.5V6"/><path d="M7 12.4V14c0 1.4 2.2 2.5 5 2.5s5-1.1 5-2.5v-3.5c0-1.2-1.6-2.2-3.8-2.4"/>'),
  filter: SV('<path d="M3 4.5h14l-5.5 6.5v5l-3 1.5V11Z"/>'),
  route: SV('<circle cx="5" cy="5" r="2"/><circle cx="15" cy="15" r="2"/><path d="M7 5h5.5a2.5 2.5 0 0 1 0 5h-5a2.5 2.5 0 0 0 0 5H13"/>'),
  server: SV('<rect x="3" y="3" width="14" height="6" rx="1.5"/><rect x="3" y="11" width="14" height="6" rx="1.5"/><path d="M6 6h.01M6 14h.01"/>'),
  chart: SV('<path d="M3 3v14h14"/><path d="m6 13 3.5-4 3 2.5L17 6"/>'),
  app: SV('<rect x="3" y="3.5" width="14" height="13" rx="2"/><path d="M3 7.5h14M6 5.5h.01M8 5.5h.01"/>'),
  globe: SV('<circle cx="10" cy="10" r="7.5"/><path d="M2.5 10h15M10 2.5c2 2.2 3 4.7 3 7.5s-1 5.3-3 7.5c-2-2.2-3-4.7-3-7.5s1-5.3 3-7.5Z"/>'),
  eye: SV('<path d="M2 10s3-5.5 8-5.5S18 10 18 10s-3 5.5-8 5.5S2 10 2 10Z"/><circle cx="10" cy="10" r="2.5"/>'),
  layers: SV('<path d="M10 2.5 17.5 6.5 10 10.5 2.5 6.5Z"/><path d="m2.5 10 7.5 4 7.5-4M2.5 13.5l7.5 4 7.5-4"/>'),
  models: SV('<path d="M10 2.5 16.5 6v8L10 17.5 3.5 14V6Z"/><path d="M3.5 6 10 9.5 16.5 6M10 9.5v8"/>'),
  lifebuoy: SV('<circle cx="10" cy="10" r="7.5"/><circle cx="10" cy="10" r="3"/><path d="m4.7 4.7 3.2 3.2M12.1 12.1l3.2 3.2M15.3 4.7l-3.2 3.2M7.9 12.1l-3.2 3.2"/>'),
  tools: SV('<path d="M12.5 3a4 4 0 0 0-3.8 5.3L3.5 13.5a1.5 1.5 0 0 0 0 2.1l.9.9a1.5 1.5 0 0 0 2.1 0l5.2-5.2A4 4 0 0 0 17 7.5l-2.3 2.3-2.3-.4-.4-2.3L14.3 4.8A4 4 0 0 0 12.5 3Z"/>'),
  sparkle: SV('<path d="M10 2.5 11.6 8.4 17.5 10l-5.9 1.6L10 17.5l-1.6-5.9L2.5 10l5.9-1.6Z"/>'),
  flag: SV('<path d="M5 17.5V3M5 3.5h9.5l-2 3.5 2 3.5H5"/>'),
  stream: SV('<path d="M2.5 6c2-1.5 3.5-1.5 5 0s3 1.5 5 0 3.5-1.5 5 0M2.5 10c2-1.5 3.5-1.5 5 0s3 1.5 5 0 3.5-1.5 5 0M2.5 14c2-1.5 3.5-1.5 5 0s3 1.5 5 0 3.5-1.5 5 0"/>'),
  bolt: SV('<path d="M11.2 2.5 4.5 11h4.6l-.8 6.5 6.7-8.5h-4.6z"/>'),
  arrowR: SV('<path d="M4 10h12M11.5 5.5 16 10l-4.5 4.5"/>'),
  arrowL: SV('<path d="M16 10H4M8.5 5.5 4 10l4.5 4.5"/>'),
  lock: SV('<rect x="4" y="9" width="12" height="8.5" rx="2"/><path d="M7 9V6.5a3 3 0 0 1 6 0V9"/>'),
};

// Storage (namespaced, JSON, fail-safe)
const store = {
  get(k, d) { try { const v = localStorage.getItem(`aigw-${k}`); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(`aigw-${k}`, JSON.stringify(v)); } catch { /* private mode */ } },
  del(k) { try { localStorage.removeItem(`aigw-${k}`); } catch { /* ignore */ } },
};
const progressAll = () => store.get('progress', {});
function labProgress(slug) {
  const p = progressAll()[slug] || {};
  return { steps: p.steps || {}, total: p.total || 0, done: !!p.done };
}
function saveLabProgress(slug, data) {
  const all = progressAll();
  all[slug] = { ...(all[slug] || {}), ...data };
  store.set('progress', all);
}
function labRatio(slug) {
  const p = labProgress(slug);
  if (p.done) return 1;
  const n = Object.values(p.steps).filter(Boolean).length;
  return p.total ? Math.min(1, n / p.total) : 0;
}

// Theme
function initTheme() {
  const root = document.documentElement;
  const sync = () => $$('[data-theme-toggle]').forEach((b) => b.setAttribute('aria-pressed', root.dataset.theme === 'dark'));
  $$('[data-theme-toggle]').forEach((b) => b.addEventListener('click', () => {
    const t = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = t;
    try { localStorage.setItem('aigw-theme', t); } catch { /* ignore */ }
    sync();
    document.dispatchEvent(new CustomEvent('aigw:theme', { detail: t }));
  }));
  sync();
  $$('[data-kbd]').forEach((k) => { k.textContent = isMac ? '⌘K' : 'Ctrl K'; });
  initMotion();
}

// Pause animations: the looping diagrams, the hero, and the widgets stop (WCAG 2.2.2). The head script applies the
// saved choice before first paint and defaults to paused when the OS asks for reduced motion.
function initMotion() {
  const root = document.documentElement;
  const sync = () => $$('[data-motion-toggle]').forEach((b) => {
    const off = root.dataset.motion === 'off';
    b.setAttribute('aria-pressed', off);
    b.title = off ? 'Animations paused. Select to play them' : 'Pause animations';
  });
  $$('[data-motion-toggle]').forEach((b) => b.addEventListener('click', () => {
    root.dataset.motion = root.dataset.motion === 'off' ? 'on' : 'off';
    store.set('motion', root.dataset.motion);
    reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches || root.dataset.motion === 'off';
    sync();
    document.dispatchEvent(new CustomEvent('aigw:motion'));
    toast(root.dataset.motion === 'off' ? 'Animations paused' : 'Animations playing');
  }));
  sync();
}

// Toast
let toastEl, toastTimer;
// action: { label, run }, a button such as Undo. The toast then stays longer and takes clicks.
// Scroll containers with nothing focusable inside get a tab stop and a name while they overflow,
// so keyboard users can scroll them (WCAG 2.1.1). Panels call this again after they inject content.
const SCROLLERS = 'pre, .table-wrap, .figure-svg, .wd-pipe';
const FOCUSABLE = 'a[href], button, input, select, textarea, [tabindex]:not([data-scroll-stop])';
let scrollRO;
function scrollLabel(el) {
  if (el.matches('pre')) {
    const t = (el.closest('.code')?.querySelector('.code-tab[aria-selected="true"], .code-title')
      || el.closest('.wd-pane')?.querySelector('.wd-pane-title'))?.textContent.trim();
    return t ? `Code: ${t}` : 'Code';
  }
  if (el.matches('.table-wrap')) {
    const head = [...el.querySelectorAll('th')].slice(0, 3).map((th) => th.textContent.trim()).filter(Boolean).join(', ');
    return head ? `Table: ${head}` : 'Table';
  }
  return 'Scrollable content';
}
function syncScroller(el) {
  const cs = getComputedStyle(el);
  const scrolls = (/(auto|scroll)/.test(cs.overflowX) && el.scrollWidth > el.clientWidth + 1)
    || (/(auto|scroll)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight + 1);
  const need = scrolls && !el.querySelector(FOCUSABLE);
  if (need && !el.hasAttribute('data-scroll-stop')) {
    if (el.hasAttribute('tabindex')) return;
    el.setAttribute('data-scroll-stop', '');
    el.tabIndex = 0;
    // A diagram figure already has role="img" and a name.
    if (!el.hasAttribute('role')) { el.setAttribute('role', 'region'); el.setAttribute('aria-label', scrollLabel(el)); el.dataset.scrollRole = ''; }
  } else if (!need && el.hasAttribute('data-scroll-stop')) {
    el.removeAttribute('data-scroll-stop'); el.removeAttribute('tabindex');
    if ('scrollRole' in el.dataset) { el.removeAttribute('role'); el.removeAttribute('aria-label'); delete el.dataset.scrollRole; }
  }
}
function watchScrollRegions(root = document) {
  if (!('ResizeObserver' in window)) return;
  scrollRO = scrollRO || new ResizeObserver((ents) => ents.forEach((e) => syncScroller(e.target)));
  $$(SCROLLERS, root).filter((el) => !el.matches('pre.mermaid')).forEach((el) => scrollRO.observe(el));
}

// Screen-reader-only status messages (WCAG 4.1.3) for feedback that is shown in place, like a copy button's label.
let announcer;
function announce(msg) {
  if (!announcer) { announcer = h('<div class="sr-only" role="status" aria-live="polite"></div>'); document.body.append(announcer); }
  announcer.textContent = '';
  setTimeout(() => { announcer.textContent = msg; }, 50);
}
function toast(msg, icon = IC.check, action) {
  if (!toastEl) { toastEl = h('<div class="toast" role="status" aria-live="polite"></div>'); document.body.append(toastEl); }
  toastEl.innerHTML = `${icon}<span>${escHtml(msg)}</span>`;
  if (action) {
    const b = h(`<button class="toast-action" type="button">${escHtml(action.label)}</button>`);
    b.addEventListener('click', () => { toastEl.classList.remove('show'); action.run(); });
    toastEl.append(b);
  }
  toastEl.classList.toggle('has-action', !!action);
  toastEl.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove('show'), action ? 6000 : 2200);
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch {
    const ta = h('<textarea style="position:fixed;opacity:0"></textarea>');
    ta.value = text; document.body.append(ta); ta.select();
    const ok = document.execCommand('copy'); ta.remove(); return ok;
  }
}

// Values: personalise <placeholders> in code. Never stores secrets.
const VALUE_FIELDS = [
  ['subscription-id', 'Subscription ID', '00000000-0000-0000-0000-000000000000'],
  ['tenant-id', 'Tenant ID', '00000000-0000-0000-0000-000000000000'],
  ['resource-group', 'Resource group', 'rg-aigw-labs'],
  ['gateway', 'Gateway name', 'aigw-labs-001'],
  ['gateway-url', 'Runtime URL', 'https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com'],
  ['location', 'Region', 'eastus2'],
  ['provider-name', 'Model provider', 'foundry'],
  ['model-name', 'Model alias', 'chat'],
  ['foundry-account-name', 'Foundry account', 'ai-labs-foundry'],
];
const getValues = () => store.get('values', {});
// Safari ignores autocomplete="off" and can offer saved cards on GUID fields; it skips fields named "search…".
// The data-* attributes opt out of 1Password, LastPass, Bitwarden, and Dashlane.
const NO_AUTOFILL = 'autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" '
  + 'data-1p-ignore data-lpignore="true" data-bwignore data-form-type="other"';

function applyValues(root = document) {
  const v = getValues();
  $$('.ph[data-ph]', root).forEach((el) => {
    const k = el.dataset.ph; const val = (v[k] || '').trim();
    el.textContent = val || `<${k}>`;
    el.classList.toggle('filled', !!val);
    el.title = val ? `Your value for ${k}. Edit in “Your values”.` : `Replace with your ${k}. Set it once in “Your values”.`;
  });
}

let drawer;
function openValues() {
  if (!drawer) {
    const v = getValues();
    drawer = h(`<div class="drawer" role="dialog" aria-modal="true" aria-labelledby="values-title" hidden>
      <div class="drawer-scrim" data-close></div>
      <div class="drawer-card">
        <div class="drawer-head"><h2 id="values-title">${IC.sliders}Your values</h2><button class="icon-btn" type="button" data-close aria-label="Close">${IC.close}</button></div>
        <p class="drawer-note">Fill these in once and every command in the labs uses them. Values stay in this browser. <strong>Never enter keys or secrets here.</strong></p>
        <div class="values-form" role="group" aria-labelledby="values-title">${VALUE_FIELDS.map(([k, label, ex]) => `<label class="field"><span>${label}<code>&lt;${k}&gt;</code></span><input type="text" id="search-value-${k}" name="search-value-${k}" data-k="${k}" value="${escHtml(v[k] || '')}" placeholder="${ex}" ${NO_AUTOFILL}></label>`).join('')}</div>
        <div class="drawer-foot"><button class="btn btn-ghost btn-sm" type="button" data-clear>${IC.reset}Clear all</button><button class="btn btn-primary btn-sm" type="button" data-close>Done</button></div>
      </div></div>`);
    document.body.append(drawer);
    const form = $('.values-form', drawer);
    form.addEventListener('input', () => {
      const vals = {};
      $$('input[data-k]', form).forEach((i) => { const val = i.value.trim(); if (val) vals[i.dataset.k] = val; });
      store.set('values', vals); applyValues();
    });
    form.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('input')) { e.preventDefault(); closeValues(); } });
    $('[data-clear]', drawer).addEventListener('click', () => { $$('input', form).forEach((i) => { i.value = ''; }); store.del('values'); applyValues(); });
    $$('[data-close]', drawer).forEach((b) => b.addEventListener('click', closeValues));
    drawer.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeValues(); trapFocus(e, $('.drawer-card', drawer)); });
  }
  drawer.lastFocus = document.activeElement;
  drawer.hidden = false;
  setTimeout(() => $('[data-close].icon-btn', drawer)?.focus({ preventScroll: true }), 30);
}
function closeValues() { if (!drawer) return; drawer.hidden = true; drawer.lastFocus?.focus?.(); }

function trapFocus(e, container) {
  if (e.key !== 'Tab') return;
  const f = $$('a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])', container).filter((x) => x.offsetParent !== null);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

// Copy buttons in code blocks (copies with personalised values, without prompts like "$ ").
function codeTextFor(block) {
  const panel = block.classList.contains('code-tabs') ? $('.code-panel:not([hidden])', block) : block;
  const pre = $('pre', panel);
  if (!pre) return '';
  const clone = pre.cloneNode(true);
  const v = getValues();
  $$('.ph[data-ph]', clone).forEach((el) => { el.textContent = (v[el.dataset.ph] || '').trim() || `<${el.dataset.ph}>`; });
  return clone.textContent.replace(/\n$/, '');
}
function initCopy() {
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.copy-btn');
    if (!btn) return;
    const ok = await copyText(codeTextFor(btn.closest('.code')));
    const label = $('span', btn);
    btn.classList.add('copied');
    if (label) label.textContent = ok ? 'Copied' : 'Failed';
    announce(ok ? 'Copied to clipboard' : 'Copy failed');
    setTimeout(() => { btn.classList.remove('copied'); if (label) label.textContent = 'Copy'; }, 1600);
  });
  $$('[data-copy-md]').forEach((b) => b.addEventListener('click', async () => {
    try {
      const res = await fetch(b.dataset.copyMd);
      const ok = await copyText(await res.text());
      toast(ok ? 'Lab copied as Markdown' : 'Copy failed');
    } catch { toast('Could not load the Markdown source', IC.info); }
  }));
  $$('[data-values-open]').forEach((b) => b.addEventListener('click', openValues));
}
