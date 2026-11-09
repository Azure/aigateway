// Lab page: tracks, code tabs, step progress, TOC, read progress, completion, lightbox, nav, mermaid, paths.
const LAB = $('.lab-main[data-lab]')?.dataset.lab || null;

function selectTrack(id, { persist = true, scroll = false } = {}) {
  let changed = false;
  $$('.tracks').forEach((group) => {
    const tabs = $$('.track-tab', group);
    if (!tabs.some((t) => t.dataset.track === id)) return;
    tabs.forEach((t) => { const on = t.dataset.track === id; t.setAttribute('aria-selected', on); t.tabIndex = on ? 0 : -1; });
    $$(':scope > .track-panel', group).forEach((p) => { p.hidden = p.dataset.track !== id; });
    changed = true;
  });
  if (!changed) return;
  if (persist) {
    store.set('track', id);
    const u = new URL(location.href); u.searchParams.set('track', id); history.replaceState(null, '', u);
  }
  updateProgressUI();
  if (scroll) { const first = $('.tracks'); first && first.getBoundingClientRect().top < 0 && first.scrollIntoView({ block: 'start' }); }
}
function initTracks() {
  const groups = $$('.tracks');
  if (!groups.length) return;
  groups.forEach((g) => {
    const tabs = $$('.track-tab', g);
    tabs.forEach((t, i) => {
      t.addEventListener('click', () => selectTrack(t.dataset.track, { scroll: true }));
      t.addEventListener('keydown', (e) => {
        const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
        if (!d) return;
        e.preventDefault();
        const n = tabs[(i + d + tabs.length) % tabs.length];
        n.focus(); selectTrack(n.dataset.track);
      });
    });
  });
  const fromUrl = new URLSearchParams(location.search).get('track');
  const pref = fromUrl || store.get('track', null);
  if (pref) selectTrack(pref, { persist: !!fromUrl });
  revealHash();
  addEventListener('hashchange', () => revealHash());
}
// A link to a step in another track, such as a step link in Troubleshooting, shows that track first.
function revealHash(force = false) {
  let el;
  try { el = location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1))); } catch { return; }
  if (!el) return;
  const panel = el.closest('.track-panel');
  if (panel?.hidden) selectTrack(panel.dataset.track);
  else if (!force) return;
  requestAnimationFrame(() => el.scrollIntoView({ block: 'start' }));
}

// Shows the tab with this label in every code tab group, such as Bash or PowerShell.
function pickCodeTab(label, root = document) {
  $$('.code-tabs', root).forEach((block) => {
    const tabs = $$('.code-tab', block);
    const t = tabs.find((x) => x.dataset.tabLabel === label);
    if (!t) return;
    tabs.forEach((x) => { const on = x === t; x.setAttribute('aria-selected', on); x.tabIndex = on ? 0 : -1; });
    $$('.code-panel', block).forEach((p) => { p.hidden = p.id !== t.getAttribute('aria-controls'); });
  });
}
// Binds the code tab groups in root, such as the Setup guide panel, and applies the reader's last choice.
function bindCodeTabs(root) {
  $$('.code-tabs', root).forEach((block) => {
    const tabs = $$('.code-tab', block);
    tabs.forEach((t, i) => {
      t.addEventListener('click', () => { pickCodeTab(t.dataset.tabLabel); store.set('codeTab', t.dataset.tabLabel); });
      t.addEventListener('keydown', (e) => {
        const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
        if (!d) return;
        e.preventDefault();
        const n = tabs[(i + d + tabs.length) % tabs.length]; n.focus(); n.click();
      });
    });
  });
  const pref = store.get('codeTab', null);
  if (pref) pickCodeTab(pref, root);
  $$('.code-expand', root).forEach((b) => { b.dataset.label = b.dataset.label || $('span', b).textContent; });
}
function initCodeTabs() {
  bindCodeTabs(document);
  document.addEventListener('click', (e) => {
    const b = e.target.closest('.code-expand');
    if (!b) return;
    const block = b.closest('.code');
    const open = block.classList.toggle('expanded');
    b.setAttribute('aria-expanded', open);
    $('span', b).textContent = open ? 'Show less' : b.dataset.label || 'Show all';
    if (!open) block.scrollIntoView({ block: 'nearest' });
  });
}

// Steps that count toward progress: outside tracks, or inside the visible track panel.
const countedSteps = () => $$('#lab-content .step').filter((s) => { const p = s.closest('.track-panel'); return !p || !p.hidden; });
// Pass persist = false when another tab changed the progress, so the two tabs don't keep overwriting each other's total.
function updateProgressUI(persist = true) {
  if (!LAB) return;
  const prog = labProgress(LAB);
  const steps = countedSteps();
  $$('#lab-content .step').forEach((s) => {
    const on = !!prog.steps[s.dataset.step];
    s.classList.toggle('done', on);
    $('.step-check', s)?.setAttribute('aria-pressed', on);
  });
  const done = steps.filter((s) => prog.steps[s.dataset.step]).length;
  const total = steps.length;
  if (persist && prog.total !== total) saveLabProgress(LAB, { total });
  const ratio = prog.done ? 1 : total ? done / total : 0;
  const ring = $('.ring-fill'); if (ring) ring.style.setProperty('--p', ratio);
  const label = $('#progress-label');
  if (label) label.textContent = prog.done ? 'Lab complete' : `${done} of ${total} steps`;
  const box = $('#lab-complete');
  if (box) {
    box.classList.toggle('done', prog.done);
    const btn = $('[data-complete-lab] span', box);
    if (btn) btn.textContent = prog.done ? 'Completed' : 'Mark lab complete';
    const h2 = $('h2', box); if (h2) h2.textContent = prog.done ? 'Nice work. Lab complete.' : 'Finished the lab?';
  }
  updateLabLinks();
}
function initSteps() {
  if (!LAB) return;
  document.addEventListener('click', (e) => {
    const b = e.target.closest('.step-check');
    if (!b) return;
    const step = b.closest('.step');
    const prog = labProgress(LAB);
    const on = !prog.steps[step.dataset.step];
    prog.steps[step.dataset.step] = on;
    if (!on) delete prog.steps[step.dataset.step];
    saveLabProgress(LAB, { steps: prog.steps });
    updateProgressUI();
    const steps = countedSteps();
    if (on && steps.every((s) => labProgress(LAB).steps[s.dataset.step])) toast('All steps done. Mark the lab complete at the end.', IC.check);
  });
  $('[data-complete-lab]')?.addEventListener('click', () => {
    const p = labProgress(LAB);
    saveLabProgress(LAB, { done: !p.done });
    updateProgressUI();
    if (!p.done) toast('Lab marked complete', IC.check);
  });
  $$('[data-reset-progress]').forEach((b) => b.addEventListener('click', () => {
    saveLabProgress(LAB, { steps: {}, done: false });
    updateProgressUI(); toast('Progress reset for this lab', IC.reset);
  }));
  updateProgressUI();
}

// Progress markers across the site (sidebar, cards, path lists, path buttons).
function updateLabLinks() {
  $$('[data-lab-link]').forEach((a) => {
    const r = labRatio(a.dataset.labLink);
    const st = $('.side-state', a);
    if (st) { st.classList.toggle('done', r >= 1); st.classList.toggle('partial', r > 0 && r < 1); }
    const li = a.closest('.path-steps li'); if (li) li.classList.toggle('done', r >= 1);
  });
  $$('[data-progress-for]').forEach((el) => {
    const r = labRatio(el.dataset.progressFor);
    el.hidden = r <= 0; el.style.setProperty('--p', r);
    el.closest('.lab-card')?.classList.toggle('done', r >= 1);
  });
  $$('[data-path-start]').forEach((a) => {
    const p = D.paths.find((x) => x.id === a.dataset.pathStart);
    if (!p) return;
    const ratios = p.labs.map(labRatio);
    if (!ratios.some((r) => r > 0)) return;
    const next = p.labs.find((s, i) => ratios[i] < 1);
    a.href = `${D.rel}labs/${next || p.labs[0]}/?path=${p.id}`;
    a.firstChild.textContent = next ? 'Continue path ' : 'Review path ';
  });
}

function initPathBanner() {
  const banner = $('#path-banner');
  if (!banner || !LAB) return;
  const q = new URLSearchParams(location.search).get('path');
  let pid = q || store.get('activePath', null);
  const path = D.paths.find((p) => p.id === pid && p.labs.includes(LAB));
  if (!path) return;
  store.set('activePath', path.id);
  const i = path.labs.indexOf(LAB);
  const ratio = path.labs.filter((s) => labRatio(s) >= 1).length / path.labs.length;
  const link = (s, dir) => { const l = D.labs.find((x) => x.slug === s); return `<a href="${D.rel}labs/${s}/?path=${path.id}">${dir === 'prev' ? '← ' : ''}${escHtml(l?.short || s)}${dir === 'next' ? ' →' : ''}</a>`; };
  banner.innerHTML = `<strong>${IC.flag}${escHtml(path.title)}</strong><p>Lab ${i + 1} of ${path.labs.length} in this learning path</p>
    <div class="path-banner-bar"><span style="--p:${ratio}"></span></div>
    <div class="path-banner-nav">${i > 0 ? link(path.labs[i - 1], 'prev') : '<span></span>'}${i < path.labs.length - 1 ? link(path.labs[i + 1], 'next') : '<span></span>'}</div>
    <button class="link-btn" type="button" data-leave-path>Leave path</button>`;
  banner.hidden = false;
  $$('.sidebar [data-lab-link]').forEach((a) => a.classList.toggle('in-path', path.labs.includes(a.dataset.labLink)));
  $('[data-leave-path]', banner).addEventListener('click', () => {
    store.del('activePath'); banner.hidden = true;
    $$('.sidebar .in-path').forEach((a) => a.classList.remove('in-path'));
    const u = new URL(location.href); u.searchParams.delete('path'); history.replaceState(null, '', u);
  });
  $$('[data-pager]').forEach((a) => {
    const target = path.labs[i + (a.dataset.pager === 'next' ? 1 : -1)];
    if (target) a.href = `${D.rel}labs/${target}/?path=${path.id}`;
  });
}

function initToc() {
  const links = $$('.toc-list a[data-toc], .rn-nav-list a[data-toc]');
  if (!links.length) return;
  const map = new Map(links.map((a) => [a.dataset.toc, a]));
  const heads = links.map((a) => document.getElementById(a.dataset.toc)).filter(Boolean);
  let current = null;
  const setActive = (id) => {
    if (id === current) return; current = id;
    links.forEach((a) => a.classList.toggle('active', a.dataset.toc === id));
    const a = map.get(id); const box = $('.toc-inner') || $('.rn-nav');
    if (a && box && (a.offsetTop < box.scrollTop || a.offsetTop > box.scrollTop + box.clientHeight - 40)) box.scrollTop = a.offsetTop - box.clientHeight / 3;
  };
  const onScroll = () => {
    const y = 140;
    let id = heads[0]?.id;
    for (const hd of heads) { if (hd.offsetParent === null) continue; if (hd.getBoundingClientRect().top - y <= 0) id = hd.id; else break; }
    setActive(id);
    const main = $('.lab-main');
    if (main) {
      const r = main.getBoundingClientRect();
      const ratio = Math.min(1, Math.max(0, -r.top / Math.max(1, r.height - innerHeight)));
      $('.read-progress span')?.style.setProperty('--read', ratio.toFixed(4));
    }
  };
  let ticking = false;
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(() => { onScroll(); ticking = false; }); } }, { passive: true });
  onScroll();
}

function initLightbox() {
  let box;
  document.addEventListener('click', (e) => {
    const z = e.target.closest('button.zoom');
    if (!z) return;
    const img = $('img', z);
    if (!box) {
      box = h(`<div class="lightbox" role="dialog" aria-modal="true" aria-label="Image preview" hidden><button class="icon-btn lightbox-close" type="button" aria-label="Close">${IC.close}</button><p class="lightbox-cap"></p></div>`);
      box.insertBefore(document.createElement('img'), $('.lightbox-cap', box));
      document.body.append(box);
      const close = () => { box.hidden = true; document.body.style.overflow = ''; box.lastFocus?.focus?.(); };
      box.addEventListener('click', close);
      // The Close button is the only control, so Tab keeps focus on it.
      box.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape') { ev.preventDefault(); close(); } else if (ev.key === 'Tab') { ev.preventDefault(); $('.lightbox-close', box).focus(); }
      });
    }
    $('img', box).src = img.currentSrc || img.src;
    $('img', box).alt = img.alt;
    $('.lightbox-cap', box).textContent = z.closest('figure')?.querySelector('figcaption')?.textContent || img.alt || '';
    box.lastFocus = z; box.hidden = false; document.body.style.overflow = 'hidden';
    $('.lightbox-close', box).focus();
  });
}

// Edge's scareware blocker scans full-screen pages and can mistake a narrated product walkthrough for a scam,
// so lab videos never use the Fullscreen API: Expand, double-click, and F open an in-page theater view.
function initVideos() {
  const frames = $$('.figure-video .video-frame');
  if (!frames.length) return;
  let stage, current, holder;
  const close = () => {
    if (!current) return;
    const frame = current;
    holder.replaceWith(frame);
    stage.hidden = true; document.body.style.overflow = '';
    current = holder = null;
    $('.video-expand', frame)?.focus();
  };
  const open = (frame) => {
    if (current) close();
    if (!stage) {
      stage = h(`<div class="video-theater" role="dialog" aria-modal="true" hidden><button class="icon-btn video-theater-close" type="button" aria-label="Close video">${IC.close}</button><p class="video-theater-cap"></p></div>`);
      document.body.append(stage);
      stage.addEventListener('click', (e) => { if (e.target === stage) close(); });
      $('.video-theater-close', stage).addEventListener('click', close);
      stage.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { e.preventDefault(); close(); }
        else if (e.key === 'Tab') { e.preventDefault(); const b = $('.video-theater-close', stage); (document.activeElement === b ? $('video', stage) : b).focus(); }
      });
    }
    const caption = frame.closest('figure')?.querySelector('figcaption')?.textContent || '';
    holder = h('<div class="video-holder" aria-hidden="true"></div>');
    holder.style.height = `${frame.offsetHeight}px`;
    // Moving a playing <video> within the document keeps it playing.
    frame.replaceWith(holder);
    stage.insertBefore(frame, $('.video-theater-cap', stage));
    $('.video-theater-cap', stage).textContent = caption;
    stage.setAttribute('aria-label', caption || 'Video');
    current = frame; stage.hidden = false; document.body.style.overflow = 'hidden';
    $('video', frame).focus();
  };
  const toggle = (frame) => (current === frame ? close() : open(frame));
  for (const frame of frames) {
    const video = $('video', frame);
    const btn = h(`<button class="video-expand" type="button" title="Expand (F)">${IC.expand}<span>Expand</span></button>`);
    frame.append(btn);
    btn.addEventListener('click', () => open(frame));
    const onBar = (e) => e.clientY > video.getBoundingClientRect().bottom - 72;
    const setPaused = (p) => { if (video.paused !== p) { if (p) video.pause(); else video.play().catch(() => {}); } };
    let before;
    // Chromium has no click-to-play on the video surface (Firefox does), so toggle only when the browser didn't.
    video.addEventListener('click', (e) => {
      if (e.detail > 1 || onBar(e)) return;
      const was = before = video.paused;
      setTimeout(() => { if (video.paused === was) setPaused(!was); }, 0);
    });
    // Double-click only expands/collapses: restore the play state from before the first click.
    video.addEventListener('dblclick', (e) => {
      e.preventDefault();
      const restore = onBar(e) ? undefined : before;
      toggle(frame);
      if (restore !== undefined) setTimeout(() => setPaused(restore), 0);
    }, true);
    video.addEventListener('keydown', (e) => {
      if ((e.key === 'f' || e.key === 'F') && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); toggle(frame); }
    });
    const sync = () => frame.classList.toggle('is-playing', !video.paused);
    video.addEventListener('play', sync); video.addEventListener('pause', sync);
  }
  // Last resort if a browser still enters full screen (e.g. a context-menu item): leave it and use the theater view.
  document.addEventListener('fullscreenchange', () => {
    const frame = document.fullscreenElement?.closest?.('.video-frame') || frames.find((f) => f.contains(document.fullscreenElement));
    if (frame) document.exitFullscreen().catch(() => {}).finally(() => open(frame));
  });
}

function initNav() {
  const toggle = $('.nav-toggle');
  if (!toggle) return;
  const scrim = $('.sidebar-scrim');
  // While the drawer is open, the page behind it is inert so focus stays in the topbar and the drawer (WCAG 2.4.3, 2.4.11).
  const behind = () => $$('body > .skip-link, #main, .lab-layout > .toc, body > .footer');
  const set = (open) => {
    document.body.classList.toggle('nav-open', open);
    toggle.setAttribute('aria-expanded', open);
    toggle.setAttribute('aria-label', open ? 'Close lab navigation' : 'Open lab navigation');
    if (scrim) scrim.hidden = !open;
    behind().forEach((el) => { el.inert = open; });
    if (open) {
      centerSidebar();
      setTimeout(() => ($('.sidebar-inner a[aria-current]') || $('.sidebar-inner a'))?.focus({ preventScroll: true }), 30);
    }
  };
  toggle.addEventListener('click', () => set(!document.body.classList.contains('nav-open')));
  $$('[data-nav-close]').forEach((x) => x.addEventListener('click', () => set(false)));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && document.body.classList.contains('nav-open')) { set(false); toggle.focus(); } });
  matchMedia('(min-width: 901px)').addEventListener('change', (e) => { if (e.matches && document.body.classList.contains('nav-open')) set(false); });
}
function centerSidebar() {
  const inner = $('.sidebar-inner'); const cur = $('.sidebar-inner a[aria-current]');
  if (inner && cur) inner.scrollTop = Math.max(0, cur.offsetTop - inner.clientHeight / 2);
}

async function initMermaid() {
  const blocks = $$('pre.mermaid');
  if (!blocks.length) return;
  blocks.forEach((b) => { b.dataset.src = b.textContent; });
  let mermaid;
  const render = async () => {
    try {
      mermaid = mermaid || (await import('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs')).default;
      const dark = document.documentElement.dataset.theme === 'dark';
      mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: dark ? 'dark' : 'neutral', fontFamily: getComputedStyle(document.body).fontFamily });
      blocks.forEach((b) => { b.removeAttribute('data-processed'); b.textContent = b.dataset.src; });
      await mermaid.run({ nodes: blocks });
    } catch (e) { console.warn('Mermaid failed to load', e); }
  };
  const io = new IntersectionObserver((ents) => { if (ents.some((x) => x.isIntersecting)) { io.disconnect(); render(); } }, { rootMargin: '400px' });
  blocks.forEach((b) => io.observe(b));
  document.addEventListener('aigw:theme', () => { if (mermaid) render(); });
}
