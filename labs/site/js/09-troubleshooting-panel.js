// Troubleshooting panel: the Troubleshooting page's sections in a side panel, like the Setup guide. Every link to
// troubleshooting/ opens it, except on that page. On a lab page, the lab's own section comes first, open, and a step's
// Troubleshoot button opens only that step's errors.
const TS = D.troubleshooting || [];
const TS_URL = new URL(`${D.rel}troubleshooting/`, location.href);
const onTsPage = () => location.pathname.replace(/index\.html$/, '') === TS_URL.pathname;
const tsErrors = (n) => `${n} error${n === 1 ? '' : 's'}`;
let tsDrawer;
let tsLoad;
let tsRows = [];
let tsOpenBefore = null;
let tsStep = null;

function buildTsDrawer() {
  const here = D.ts;
  const list = here ? [...TS.filter((t) => t.id === here), ...TS.filter((t) => t.id !== here)] : TS;
  const total = TS.reduce((n, t) => n + t.rows, 0);
  const rows = list.map((t) => {
    const m = t.title.match(/^Lab (\d{2}): (.+)$/);
    const icon = m
      ? `<span class="ts-row-num"><span class="sr-only">Lab </span>${m[1]}</span>`
      : `<span class="ts-row-icon" aria-hidden="true">${t.id === 'setup-and-deployment' ? IC.tools : IC.bolt}</span>`;
    return `<section class="setup-row ts-row${t.id === here ? ' here' : ''}" data-ts-row="${t.id}">
      <div class="setup-row-head">
        <button class="setup-row-toggle" type="button" aria-expanded="false" aria-controls="tsp-${t.id}" id="tsh-${t.id}">
          ${icon}<span class="setup-row-text"><span class="setup-row-title">${escHtml(m ? m[2] : t.title)}</span><span class="setup-row-when" data-ts-n>${tsErrors(t.rows)}</span></span>${t.id === here ? '<span class="ts-here">This lab</span>' : ''}${chevron}
        </button>
      </div>
      <div class="setup-row-body" id="tsp-${t.id}" role="region" aria-labelledby="tsh-${t.id}" hidden>
        <div class="setup-row-content prose ts-row-content"><p class="setup-loading">Loading…</p></div>
      </div>
    </section>`;
  }).join('');
  tsDrawer = h(`<div class="drawer setup-drawer ts-drawer" role="dialog" aria-modal="true" aria-labelledby="ts-title" hidden>
    <div class="drawer-scrim" data-close></div>
    <div class="drawer-card">
      <div class="drawer-head"><h2 id="ts-title">${IC.lifebuoy}Troubleshooting</h2><button class="icon-btn" type="button" data-close aria-label="Close">${IC.close}</button></div>
      <p class="drawer-note">The errors you might hit in the labs, with their likely causes and fixes.</p>
      <div class="ts-step-bar" data-ts-step-bar hidden>
        <span class="ts-step-chip"><span class="ts-step-kicker">Step</span><span class="ts-step-label" data-ts-step-label></span></span>
        <button class="ts-step-all" type="button" data-ts-step-clear>Show all errors</button>
      </div>
      <div class="ts-filter ts-panel-filter" role="search">
        <label class="ts-filter-box">${IC.search}<span class="sr-only">Filter the errors</span><input type="search" data-ts-q placeholder="Filter by error code or message" autocomplete="off" spellcheck="false" aria-describedby="ts-panel-count"></label>
        <span class="ts-count" id="ts-panel-count" aria-live="polite" data-ts-count data-total="${total}">${tsErrors(total)}</span>
      </div>
      <div class="setup-rows ts-rows">${rows}
        <p class="ts-empty" data-ts-empty hidden>No errors match your filter. Try an error code such as <code>429</code>, or a word from the message.</p>
        <p class="setup-help">${IC.tools}<span>Not set up yet? Start with the <a href="${D.rel}setup/">Setup guide</a>.</span></p>
      </div>
      <div class="drawer-foot">
        <a class="btn btn-ghost btn-sm" href="${TS_URL.href}" data-ts-page>${IC.expand}Open as a page</a>
        <button class="btn btn-primary btn-sm" type="button" data-close>Done</button>
      </div>
    </div></div>`);
  document.body.append(tsDrawer);
  const input = $('[data-ts-q]', tsDrawer);
  $$('[data-close]', tsDrawer).forEach((b) => b.addEventListener('click', closeTs));
  tsDrawer.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      if (e.target === input && input.value) { input.value = ''; filterTs(); } else closeTs();
      return;
    }
    trapFocus(e, $('.drawer-card', tsDrawer));
  });
  tsDrawer.addEventListener('click', (e) => {
    if (e.target.closest('[data-ts-step-clear]')) {
      setTsStep(null);
      loadTs().then(() => { filterTs(); showTsRow($(`.ts-row[data-ts-row="${CSS.escape(D.ts || '')}"]`, tsDrawer)); });
      return;
    }
    const toggle = e.target.closest('.setup-row-toggle');
    if (toggle) expandTsRow(toggle.closest('.ts-row'), toggle.getAttribute('aria-expanded') !== 'true', !input.value.trim());
  });
  input.addEventListener('input', () => loadTs().then(filterTs));
}

// While a filter is on, every section with a match is open. Without one, the panel is an accordion.
function expandTsRow(row, open = true, only = true) {
  if (!row) return;
  if (open && only) $$('.ts-row.open', tsDrawer).forEach((r) => { if (r !== row) expandTsRow(r, false); });
  row.classList.toggle('open', open);
  $('.setup-row-toggle', row).setAttribute('aria-expanded', open);
  $('.setup-row-body', row).hidden = !open;
  syncTsPageLink();
}
function showTsRow(row) {
  if (!row) return;
  expandTsRow(row, true, !$('[data-ts-q]', tsDrawer).value.trim());
  requestAnimationFrame(() => row.scrollIntoView({ block: 'start', behavior: reduceMotion ? 'auto' : 'smooth' }));
}

// "Open as a page" keeps the filter, or else the open section.
function syncTsPageLink() {
  const link = $('.drawer-foot [data-ts-page]', tsDrawer);
  if (!link) return;
  const q = $('[data-ts-q]', tsDrawer).value.trim();
  const open = $('.ts-row.open', tsDrawer)?.dataset.tsRow;
  link.href = `${TS_URL.href}${q ? `?q=${encodeURIComponent(q)}` : open ? `#${open}` : ''}`;
}

// Loads the sections' rows from /troubleshooting/, once.
function loadTs() {
  if (tsLoad) return tsLoad;
  tsLoad = fetch(TS_URL).then((r) => { if (!r.ok) throw new Error(r.status); return r.text(); }).then((html) => {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const sections = new Map($$('.ts-section', doc).map((s) => [s.dataset.ts, s]));
    if (!sections.size) throw new Error('no sections');
    tsRows = $$('.ts-row', tsDrawer).map((row) => {
      const box = $('.ts-row-content', row);
      const sec = sections.get(row.dataset.tsRow);
      if (!sec) {
        box.innerHTML = `<p><a href="${TS_URL.href}#${row.dataset.tsRow}" data-ts-page>Open this section on the Troubleshooting page</a>.</p>`;
        return { row, head: '', trs: [] };
      }
      const parts = [...sec.children].filter((el) => el.tagName !== 'H2');
      box.replaceChildren(...parts.map((n) => document.importNode(n, true)));
      $$('.anchor', box).forEach((a) => a.remove());
      $$('[id]', box).forEach((el) => { el.id = `ts-${el.id}`; });
      $$('a[href]', box).forEach((a) => {
        const href = a.getAttribute('href');
        a.href = href.startsWith('#') ? `${TS_URL.href}${href}` : new URL(href, TS_URL).href;
      });
      $$('img[src], source[src]', box).forEach((el) => { el.src = new URL(el.getAttribute('src'), TS_URL).href; });
      applyValues(box);
      watchScrollRegions(box);
      return {
        row,
        // The section's title and lab link match every row, so "token limits" shows all of lab 06.
        head: norm([$('.setup-row-title', row).textContent, ...parts.filter((el) => !el.matches('.table-wrap')).map((el) => el.textContent)].join(' ')),
        trs: $$('tbody tr', box).map((tr) => ({ tr, text: norm(tr.textContent), steps: (tr.dataset.steps || '').split(' ').filter(Boolean) })),
      };
    });
  }).catch(() => {
    tsLoad = null;
    $$('.ts-row-content', tsDrawer).forEach((box) => {
      const id = box.closest('.ts-row').dataset.tsRow;
      box.innerHTML = `<p>Couldn't load these errors. <a href="${TS_URL.href}#${id}" data-ts-page>Open them on the Troubleshooting page</a>.</p>`;
    });
  });
  return tsLoad;
}

// The text filter matches every term. A step's context shows only its errors, in the lab's section.
function filterTs() {
  if (!tsRows.length) return;
  const input = $('[data-ts-q]', tsDrawer);
  const terms = norm(input.value).split(/\s+/).filter(Boolean);
  const active = terms.length > 0 || !!tsStep;
  const count = $('[data-ts-count]', tsDrawer), total = Number(count.dataset.total);
  if (active && !tsOpenBefore) tsOpenBefore = $$('.ts-row.open', tsDrawer);
  let shown = 0;
  for (const r of tsRows) {
    const inStep = !tsStep || r.row.dataset.tsRow === D.ts;
    let n = 0;
    for (const x of r.trs) {
      const ok = inStep && (!tsStep || x.steps.includes(tsStep.id)) && terms.every((t) => x.text.includes(t) || r.head.includes(t));
      x.tr.hidden = !ok;
      if (ok) n++;
    }
    shown += n;
    r.row.hidden = active && !n;
    $('[data-ts-n]', r.row).textContent = active ? `${n} of ${tsErrors(r.trs.length)}` : tsErrors(r.trs.length);
    if (active) expandTsRow(r.row, n > 0, false);
  }
  if (!active && tsOpenBefore) {
    const before = tsOpenBefore;
    tsOpenBefore = null;
    $$('.ts-row.open', tsDrawer).forEach((r) => { if (!before.includes(r)) expandTsRow(r, false); });
    before.forEach((r) => expandTsRow(r, true, false));
  }
  count.textContent = tsStep ? `${tsErrors(shown)} in this step` : terms.length ? `${shown} of ${tsErrors(total)}` : tsErrors(total);
  $('[data-ts-empty]', tsDrawer).hidden = !active || shown > 0;
  $('.ts-rows', tsDrawer).scrollTop = 0;
  syncTsPageLink();
}

// Sets or clears the step's context: { id, label } from the step's Troubleshoot button.
function setTsStep(step) {
  tsStep = step && D.ts ? step : null;
  const bar = $('[data-ts-step-bar]', tsDrawer);
  bar.hidden = !tsStep;
  $('[data-ts-step-label]', tsDrawer).textContent = tsStep?.label || '';
  $('[data-ts-q]', tsDrawer).placeholder = tsStep ? "Filter this step's errors" : 'Filter by error code or message';
}

function openTs(hash = '', q = null, step = null) {
  if (!TS.length) { location.href = TS_URL.href + hash; return; }
  closeSetup();
  if (!tsDrawer) buildTsDrawer();
  if (tsDrawer.hidden) tsDrawer.lastFocus = document.activeElement;
  tsDrawer.hidden = false;
  const input = $('[data-ts-q]', tsDrawer);
  // A link with ?q= sets the filter. A link to a section, or a step's button, clears an old filter that could hide it.
  const had = tsStep;
  setTsStep(step);
  const clear = q == null && (hash || step) && input.value;
  if (q != null || clear) input.value = q || '';
  if (clear || had || tsStep) filterTs();
  const id = decodeURIComponent(String(hash).replace(/^#/, '')) || (!$('.ts-row.open', tsDrawer) && D.ts) || '';
  const row = id && $(`.ts-row[data-ts-row="${CSS.escape(id)}"]`, tsDrawer);
  if (row) showTsRow(row);
  // A fine pointer gets the filter, ready to type; a touch screen doesn't get its keyboard pushed up.
  setTimeout(() => (matchMedia('(pointer: fine)').matches ? input : $('[data-close].icon-btn', tsDrawer)).focus({ preventScroll: true }), 30);
  loadTs().then(() => {
    if (q == null && !tsStep) return;
    filterTs();
    if (row && !row.hidden) showTsRow(row);
  });
}
function closeTs() {
  if (!tsDrawer || tsDrawer.hidden) return;
  tsDrawer.hidden = true;
  tsDrawer.lastFocus?.focus?.();
}

function initTsPanel() {
  if (!TS.length) return;
  const page = onTsPage();
  document.addEventListener('click', (e) => {
    const stepBtn = e.target.closest('[data-ts-step]');
    if (stepBtn && D.ts) { openTs(`#${D.ts}`, null, { id: stepBtn.dataset.tsStep, label: stepBtn.dataset.tsLabel }); return; }
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest('a[href]');
    if (!a || a.target === '_blank' || a.hasAttribute('download') || a.closest('.search-modal')) return;
    let u;
    try { u = new URL(a.href, location.href); } catch { return; }
    const toTs = u.origin === TS_URL.origin && u.pathname.replace(/index\.html$/, '') === TS_URL.pathname;
    // Any other link in the panel, such as a same-page link on the Setup page, closes it first.
    if (!toTs || a.hasAttribute('data-ts-page')) {
      if (!a.closest('.ts-drawer')) return;
      closeTs();
      // A link to a step of this lab shows the step, in its track, without reloading the page.
      if (u.origin === location.origin && u.pathname === location.pathname && u.hash) {
        e.preventDefault();
        if (location.hash === u.hash) revealHash(true); else location.hash = u.hash;
      }
      return;
    }
    if (page) { if (a.closest('.setup-drawer')) closeSetup(); return; }
    e.preventDefault();
    openTs(u.hash, u.searchParams.get('q'));
  });
}
