// Setup guide: the one-time tasks that the labs share (D.setup, from the task table in SETUP.md). Readers mark them
// done in the panel, on the /setup/ page, or in a lab's "One-time setup" checklist, and the checklists hide them.
// Links to the Setup guide open it in a side panel, which loads the sections from /setup/ on first use.
const SETUP = (D.setup || []);
const SETUP_CHECK = SETUP.filter((t) => t.check);
const SETUP_URL = new URL(`${D.rel}setup/`, location.href);
const onSetupPage = () => location.pathname.replace(/index\.html$/, '') === SETUP_URL.pathname;
const setupState = () => store.get('setup', {});
const setupLeft = () => SETUP_CHECK.filter((t) => !setupState()[t.key]);
const setupTitle = (t) => h(`<span>${t.title}</span>`).textContent;
// The tasks that the lab's "One-time setup" checklist lists; empty on other pages.
const labSetupKeys = () => [...new Set($$('[data-setup-check] [data-setup-task]').map((li) => li.dataset.setupTask))];

// The next task to do after `key`, in table order and wrapping around, preferring the lab's own tasks.
function setupNext(key) {
  const i = SETUP_CHECK.findIndex((t) => t.key === key);
  const left = SETUP_CHECK.slice(i + 1).concat(SETUP_CHECK.slice(0, Math.max(i, 0)))
    .filter((t) => !setupState()[t.key]);
  const lab = labSetupKeys();
  return left.find((t) => lab.includes(t.key)) || left[0];
}

function setSetupDone(keys, on) {
  const s = setupState();
  [].concat(keys).forEach((k) => { if (on) s[k] = true; else delete s[k]; });
  store.set('setup', s);
  updateSetupUI();
}

// Marks tasks done with a toast that can undo it.
function markSetupDone(keys, msg) {
  const before = setupState();
  const fresh = [].concat(keys).filter((k) => !before[k]);
  if (!fresh.length) return;
  setSetupDone(fresh, true);
  toast(msg || (setupLeft().length ? 'Marked done. The labs stop listing it.' : 'Setup complete. The labs stop listing it.'), IC.check,
    { label: 'Undo', run: () => setSetupDone(fresh, false) });
}

function updateSetupUI() {
  const s = setupState();
  const left = setupLeft().length;
  const total = SETUP_CHECK.length;
  $$('[data-setup-check]').forEach((card) => {
    const items = $$('[data-setup-task]', card);
    let open = 0;
    items.forEach((li) => {
      const done = !!s[li.dataset.setupTask];
      li.hidden = done;
      li.classList.remove('leaving');
      if (!done) open += 1;
    });
    card.classList.toggle('all-done', !open);
    $('.setup-check-list', card).hidden = !open;
    $('.setup-check-done', card).hidden = !!open;
    const count = $('.setup-check-count', card);
    if (count) count.textContent = open && open < items.length ? `${open} of ${items.length} left` : '';
  });
  // On a lab page, the badge counts only the tasks that the lab's checklist lists.
  const labKeys = labSetupKeys();
  const scope = labKeys.length ? labKeys : SETUP_CHECK.map((t) => t.key);
  const scopeLeft = scope.filter((k) => !s[k]).length;
  $$('[data-setup-badge]').forEach((b) => {
    b.hidden = !total;
    b.classList.toggle('done', !scopeLeft);
    b.innerHTML = scopeLeft ? `${scopeLeft} left` : IC.check;
    b.title = scopeLeft
      ? `${scopeLeft} of ${scope.length} one-time tasks left${labKeys.length ? ' for this lab' : ''}`
      : labKeys.length ? 'Setup done for this lab' : 'Setup complete';
  });
  $$('[data-setup-pill]').forEach((p) => {
    p.hidden = !total;
    p.classList.toggle('done', !left);
    p.innerHTML = left ? `${total - left} of ${total} done` : `${IC.check}Setup complete`;
  });
  $$('[data-setup-meter]').forEach((m) => m.style.setProperty('--p', total ? (total - left) / total : 0));
  $$('[data-setup-toggle]').forEach((b) => {
    const done = !!s[b.dataset.setupToggle];
    b.setAttribute('aria-pressed', done);
    b.closest('[data-setup-row], [data-setup-section]')?.classList.toggle('done', done);
    const label = $('span', b);
    if (label) label.textContent = done ? 'Done' : 'Mark as done';
  });
  $$('[data-setup-next]').forEach((b) => {
    const done = !!s[b.dataset.setupNext];
    $('span', b).textContent = done ? 'Done' : 'Mark as done';
    b.classList.toggle('btn-primary', !done);
    b.classList.toggle('btn-secondary', done);
  });
  if (onSetupPage()) {
    SETUP_CHECK.forEach((t) => $(`.rn-nav-list a[data-toc="${t.id}"]`)?.classList.toggle('setup-done', !!s[t.key]));
  }
}

// ---------- The panel ----------
let setupDrawer;
let setupLoad;
const chevron = SV('<path d="m7.5 5 5 5-5 5"/>');

function buildSetupDrawer() {
  const rows = SETUP.map((t) => `<section class="setup-row${t.check ? '' : ' ref'}" data-setup-row="${t.key}" data-id="${t.id}">
      <div class="setup-row-head">
        ${t.check
          ? `<button class="setup-tick" type="button" aria-pressed="false" data-setup-toggle="${t.key}" aria-label="Mark ${escHtml(setupTitle(t))} as done" title="Mark as done">${IC.check}</button>`
          : `<span class="setup-ref-icon" aria-hidden="true">${IC.info}</span>`}
        <button class="setup-row-toggle" type="button" aria-expanded="false" aria-controls="sgp-${t.id}" id="sgh-${t.id}">
          <span class="setup-row-text"><span class="setup-row-title">${t.title}</span><span class="setup-row-when">${t.when}</span></span>${chevron}
        </button>
      </div>
      <div class="setup-row-body" id="sgp-${t.id}" role="region" aria-labelledby="sgh-${t.id}" hidden>
        <div class="setup-row-content prose"><p class="setup-loading">Loading…</p></div>
        ${t.check ? `<div class="setup-row-actions"><button class="btn btn-primary btn-sm" type="button" data-setup-next="${t.key}">${IC.check}<span>Mark as done</span></button></div>` : ''}
      </div>
    </section>`).join('');
  setupDrawer = h(`<div class="drawer setup-drawer" role="dialog" aria-modal="true" aria-labelledby="setup-title" hidden>
    <div class="drawer-scrim" data-close></div>
    <div class="drawer-card">
      <div class="drawer-head"><h2 id="setup-title">${IC.tools}Setup guide</h2><span class="setup-pill" data-setup-pill hidden></span><button class="icon-btn" type="button" data-close aria-label="Close">${IC.close}</button></div>
      <div class="setup-meter" data-setup-meter aria-hidden="true"><span></span></div>
      <p class="drawer-note">The one-time tasks that the labs share. Mark each one done, and the labs stop listing it. Your progress stays in this browser.</p>
      <div class="setup-rows">${rows}
        <p class="setup-help">${IC.lifebuoy}<span>Something went wrong? See <a href="${D.rel}troubleshooting/#setup-and-deployment">Troubleshooting</a>.</span></p>
      </div>
      <div class="drawer-foot">
        <a class="btn btn-ghost btn-sm" href="${SETUP_URL.href}" data-setup-page>${IC.expand}Open as a page</a>
        <span class="setup-foot-end"><button class="btn btn-ghost btn-sm" type="button" data-setup-reset>${IC.reset}Reset</button><button class="btn btn-primary btn-sm" type="button" data-close>Done</button></span>
      </div>
    </div></div>`);
  document.body.append(setupDrawer);
  $$('[data-close]', setupDrawer).forEach((b) => b.addEventListener('click', closeSetup));
  setupDrawer.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSetup(); trapFocus(e, $('.drawer-card', setupDrawer)); });
  setupDrawer.addEventListener('click', (e) => {
    const toggle = e.target.closest('.setup-row-toggle');
    if (toggle) { expandSetupRow(toggle.closest('.setup-row'), toggle.getAttribute('aria-expanded') !== 'true'); return; }
    const next = e.target.closest('[data-setup-next]');
    if (next) {
      const key = next.dataset.setupNext;
      if (setupState()[key]) return;
      const after = setupNext(key);
      markSetupDone(key);
      if (after) showSetupRow($(`[data-setup-row="${after.key}"]`, setupDrawer));
      else expandSetupRow(next.closest('.setup-row'), false);
      return;
    }
    if (e.target.closest('[data-setup-reset]')) {
      const prev = setupState();
      if (!Object.keys(prev).length) return;
      store.del('setup'); updateSetupUI();
      toast('Setup progress reset', IC.reset, { label: 'Undo', run: () => { store.set('setup', prev); updateSetupUI(); } });
    }
  });
}

function expandSetupRow(row, open = true) {
  if (!row) return;
  if (open) $$('.setup-row.open', setupDrawer).forEach((r) => { if (r !== row) expandSetupRow(r, false); });
  row.classList.toggle('open', open);
  $('.setup-row-toggle', row).setAttribute('aria-expanded', open);
  $('.setup-row-body', row).hidden = !open;
}
function showSetupRow(row, target) {
  if (!row) return;
  expandSetupRow(row, true);
  requestAnimationFrame(() => (target || row).scrollIntoView({ block: 'start', behavior: reduceMotion ? 'auto' : 'smooth' }));
}

// Loads the guide's sections from /setup/, once. Ids get a prefix, so they don't clash with the page's own ids.
function loadSetupSections() {
  if (setupLoad) return setupLoad;
  setupLoad = fetch(SETUP_URL).then((r) => { if (!r.ok) throw new Error(r.status); return r.text(); }).then((html) => {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const content = $('#lab-content', doc);
    if (!content) throw new Error('no content');
    const sections = new Map();
    let current = null;
    [...content.children].forEach((el) => {
      if (el.tagName === 'H2' && el.id) { current = el.id; sections.set(current, []); return; }
      if (current) sections.get(current).push(el);
    });
    $$('.setup-row', setupDrawer).forEach((row) => {
      const box = $('.setup-row-content', row);
      const nodes = sections.get(row.dataset.id);
      if (!nodes) { box.innerHTML = `<p><a href="${SETUP_URL.href}#${row.dataset.id}" data-setup-page>Open this task in the Setup guide</a>.</p>`; return; }
      box.replaceChildren(...nodes.map((n) => document.importNode(n, true)));
      $$('.anchor', box).forEach((a) => a.remove());
      $$('[id]', box).forEach((el) => { el.id = `sg-${el.id}`; });
      $$('[aria-controls], [aria-labelledby]', box).forEach((el) => ['aria-controls', 'aria-labelledby'].forEach((attr) => {
        const v = el.getAttribute(attr);
        if (v) el.setAttribute(attr, v.split(/\s+/).map((x) => `sg-${x}`).join(' '));
      }));
      $$('a[href]', box).forEach((a) => {
        const href = a.getAttribute('href');
        a.href = href.startsWith('#') ? `${SETUP_URL.href}${href}` : new URL(href, SETUP_URL).href;
      });
      $$('img[src], source[src]', box).forEach((el) => { el.src = new URL(el.getAttribute('src'), SETUP_URL).href; });
      applyValues(box);
      bindCodeTabs(box);
      watchScrollRegions(box);
    });
  }).catch(() => {
    setupLoad = null;
    $$('.setup-row-content', setupDrawer).forEach((box) => {
      const id = box.closest('.setup-row').dataset.id;
      box.innerHTML = `<p>Couldn't load this task. <a href="${SETUP_URL.href}#${id}" data-setup-page>Open it in the Setup guide</a>.</p>`;
    });
  });
  return setupLoad;
}

function openSetup(hash = '') {
  if (!SETUP.length) { location.href = SETUP_URL.href + hash; return; }
  closeTs();
  if (!setupDrawer) buildSetupDrawer();
  if (setupDrawer.hidden) setupDrawer.lastFocus = document.activeElement;
  setupDrawer.hidden = false;
  updateSetupUI();
  const id = decodeURIComponent(String(hash).replace(/^#/, ''));
  const row = id && $(`.setup-row[data-id="${CSS.escape(id)}"]`, setupDrawer);
  if (row) showSetupRow(row);
  else if (!id && !$('.setup-row.open', setupDrawer)) {
    const next = setupNext();
    if (next) expandSetupRow($(`[data-setup-row="${next.key}"]`, setupDrawer), true);
  }
  setTimeout(() => $(row ? '.setup-row-toggle' : '[data-close].icon-btn', row || setupDrawer)?.focus({ preventScroll: true }), 30);
  loadSetupSections().then(() => {
    // A link to a part of a task, such as #delete-what-azd-created, opens that task and scrolls to it.
    if (!id || row) return;
    const target = $(`#sg-${CSS.escape(id)}`, setupDrawer);
    if (target) showSetupRow(target.closest('.setup-row'), target);
  });
}
function closeSetup() {
  if (!setupDrawer || setupDrawer.hidden) return;
  setupDrawer.hidden = true;
  setupDrawer.lastFocus?.focus?.();
}

// ---------- Wiring ----------
function initSetup() {
  if (!SETUP.length) return;
  const page = onSetupPage();
  document.addEventListener('click', (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const opener = e.target.closest('[data-setup-open]');
    if (opener) { e.preventDefault(); if (page) closeSetup(); else openSetup(opener.dataset.setupOpen || ''); return; }
    const a = e.target.closest('a[href]');
    if (!a || page || a.target === '_blank' || a.hasAttribute('download') || a.hasAttribute('data-setup-page') || a.closest('.search-modal')) return;
    let u;
    try { u = new URL(a.href, location.href); } catch { return; }
    if (u.origin !== SETUP_URL.origin || u.pathname.replace(/index\.html$/, '') !== SETUP_URL.pathname) return;
    e.preventDefault();
    openSetup(u.hash);
  });
  // The ticks in a lab's checklist: the task slides out, and the toast can undo it.
  document.addEventListener('click', (e) => {
    const tick = e.target.closest('[data-setup-check] .setup-tick');
    if (!tick) return;
    const li = tick.closest('[data-setup-task]');
    const key = li.dataset.setupTask;
    if (setupState()[key]) { updateSetupUI(); return; }
    const t = SETUP_CHECK.find((x) => x.key === key);
    li.classList.add('leaving');
    setTimeout(() => markSetupDone(key, `Marked done: ${setupTitle(t)}. The labs stop listing it.`), reduceMotion ? 0 : 220);
  });
  // A step that does a setup task itself, as in the quick start, marks that task done along with the step.
  // initSteps registers its click handler first, so the step's new state is already saved here.
  if (LAB) document.addEventListener('click', (e) => {
    const step = e.target.closest('.step-check')?.closest('.step');
    const marker = step && $('[data-setup-done]', step);
    if (!marker || !labProgress(LAB).steps[step.dataset.step]) return;
    const keys = marker.dataset.setupDone.split(/\s+/).filter((k) => !setupState()[k]);
    const titles = keys.map((k) => setupTitle(SETUP_CHECK.find((t) => t.key === k)));
    if (keys.length) markSetupDone(keys, `Also marked done in your Setup guide: ${titles.join(', ')}`);
  });
  // The /setup/ page: a "Mark as done" button under each task heading.
  if (page) {
    SETUP_CHECK.forEach((t) => {
      const h2 = $(`#lab-content > h2[id="${t.id}"]`);
      if (!h2) return;
      const bar = h(`<div class="setup-mark" data-setup-section="${t.key}"><button class="btn btn-secondary btn-sm" type="button" aria-pressed="false" data-setup-toggle="${t.key}">${IC.check}<span>Mark as done</span></button><span class="setup-mark-when">${t.when}</span></div>`);
      h2.after(bar);
    });
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-setup-toggle]');
    if (!b) return;
    const key = b.dataset.setupToggle;
    if (setupState()[key]) setSetupDone(key, false);
    else markSetupDone(key);
  });
  updateSetupUI();
}
