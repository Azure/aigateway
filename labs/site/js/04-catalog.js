// Catalog filters (URL-synced) and home page bits.
function initCatalog() {
  const grid = $('#lab-grid');
  if (!grid || !$('.page-catalog')) return;
  const cards = $$('.lab-card', grid);
  const q = $('#catalog-q');
  const count = $('#catalog-count');
  const empty = $('#catalog-empty');
  const clear = $('#filters-clear');
  const chips = $$('.chip[data-filter]');
  const state = { category: new Set(), level: new Set(), track: new Set(), path: new Set(), status: new Set(), q: '' };

  const params = new URLSearchParams(location.search);
  for (const k of ['category', 'level', 'track', 'path', 'status']) (params.get(k) || '').split(',').filter(Boolean).forEach((v) => state[k].add(v));
  state.q = params.get('q') || '';
  q.value = state.q;

  const apply = (push = true) => {
    const terms = norm(state.q).split(/\s+/).filter(Boolean);
    let n = 0;
    cards.forEach((c) => {
      const d = c.dataset;
      const ok = (!state.category.size || state.category.has(d.category))
        && (!state.level.size || state.level.has(d.level))
        && (!state.track.size || d.tracks.split(' ').some((t) => state.track.has(t)))
        && (!state.path.size || d.paths.split(' ').some((p) => state.path.has(p)))
        && (!state.status.size || state.status.has(d.status))
        && terms.every((t) => norm(d.text).includes(t) || d.lab.startsWith(t));
      c.hidden = !ok; if (ok) n++;
    });
    chips.forEach((ch) => ch.setAttribute('aria-pressed', state[ch.dataset.filter].has(ch.dataset.value)));
    const any = state.q || Object.entries(state).some(([k, v]) => k !== 'q' && v.size);
    count.textContent = any ? `${n} of ${cards.length} labs` : `${cards.length} labs`;
    empty.hidden = n > 0;
    clear.hidden = !any;
    if (push) {
      const u = new URL(location.href);
      for (const k of ['category', 'level', 'track', 'path', 'status']) state[k].size ? u.searchParams.set(k, [...state[k]].join(',')) : u.searchParams.delete(k);
      state.q ? u.searchParams.set('q', state.q) : u.searchParams.delete('q');
      history.replaceState(null, '', u);
    }
  };
  chips.forEach((ch) => ch.addEventListener('click', () => {
    const set = state[ch.dataset.filter];
    set.has(ch.dataset.value) ? set.delete(ch.dataset.value) : set.add(ch.dataset.value);
    apply();
  }));
  let t;
  q.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => { state.q = q.value.trim(); apply(); }, 120); });
  const reset = () => { for (const k of ['category', 'level', 'track', 'path', 'status']) state[k].clear(); state.q = ''; q.value = ''; apply(); };
  clear.addEventListener('click', reset);
  $$('[data-clear-filters]').forEach((b) => b.addEventListener('click', reset));
  apply(false);
}

// Hero preview: selecting a part of the map opens a preview of the lab that teaches it, with its related labs.
// Without popover support or JavaScript, every part stays a plain link to its lab. Modifier clicks still navigate.
function initHeroPreview() {
  const src = $('#hx-data');
  const root = src?.closest('.hx');
  if (!root || !HTMLElement.prototype.hasOwnProperty('popover')) return;
  const data = JSON.parse(src.textContent);
  const ic = data.icons;
  const triggers = $$('[data-hx-part]', root).filter((t) => data.parts[t.dataset.hxPart]?.labs.length);
  if (!triggers.length) return;
  triggers.forEach((t) => {
    t.removeAttribute('title');
    t.setAttribute('aria-haspopup', 'dialog');
    t.setAttribute('aria-controls', 'hx-preview');
    t.setAttribute('aria-expanded', 'false');
  });
  const hint = $('.hx-hint', root); if (hint) hint.hidden = false;

  const pop = h('<div class="hxp" id="hx-preview" popover="manual" role="dialog" aria-labelledby="hxp-title" tabindex="-1"></div>');
  document.body.append(pop);
  const sheet = matchMedia('(max-width: 720px)');
  const art = new Map();
  let cur = null; let raf = 0; let uid = 0;

  // The lab's diagram, inlined so it follows the theme. Ids are prefixed so they can't clash with the page.
  const loadArt = (url) => {
    if (!art.has(url)) {
      art.set(url, fetch(url).then((r) => (r.ok ? r.text() : Promise.reject(r.status))).then((txt) => {
        const svg = new DOMParser().parseFromString(txt, 'image/svg+xml').documentElement;
        if (svg.nodeName !== 'svg') throw new Error('not an svg');
        $$('script, foreignObject, title, desc', svg).forEach((n) => n.remove());
        [svg, ...$$('*', svg)].forEach((n) => [...n.attributes].forEach((a) => { if (/^on/i.test(a.name)) n.removeAttribute(a.name); }));
        ['role', 'aria-labelledby', 'aria-describedby', 'aria-label', 'width', 'height'].forEach((a) => svg.removeAttribute(a));
        svg.setAttribute('aria-hidden', 'true');
        svg.setAttribute('focusable', 'false');
        const p = `hxp${(uid += 1)}-`;
        let out = new XMLSerializer().serializeToString(svg);
        for (const id of $$('[id]', svg).map((n) => n.id)) {
          const e = id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
          out = out.replace(new RegExp(`\\bid="${e}"`, 'g'), `id="${p}${id}"`)
            .replace(new RegExp(`url\\(#${e}\\)`, 'g'), `url(#${p}${id})`)
            .replace(new RegExp(`href="#${e}"`, 'g'), `href="#${p}${id}"`);
        }
        return out;
      }));
    }
    return art.get(url);
  };

  const progress = (slug) => {
    const r = labRatio(slug);
    if (r >= 1) return `<span class="hxp-progress done">${ic.check}Completed</span>`;
    return r > 0 ? `<span class="hxp-progress">${Math.round(r * 100)}% done</span>` : '';
  };

  const render = (t) => {
    const part = data.parts[t.dataset.hxPart];
    const [slug, ...rel] = part.labs;
    const l = data.labs[slug];
    const [name, where] = part.ctx.split(' · ');
    const mark = t.querySelector('.hx-mark');
    const logo = t.querySelector('img');
    const icon = mark ? mark.outerHTML : (logo && !logo.classList.contains('hx-brand') ? `<span class="hx-mark" aria-hidden="true">${logo.outerHTML}</span>` : '');
    const go = slug === 'quickstart' ? 'Open the quick start' : `Open ${l.label.toLowerCase()}`;
    pop.style.setProperty('--c', `var(--cat-${l.color})`);
    pop.innerHTML = `<span class="hxp-arrow" aria-hidden="true"></span>
<div class="hxp-in">
  <div class="hxp-head${t.classList.contains('hx-cap') ? ' hxp-head-cap' : ''}">${icon}<span class="hxp-part">${name}${where ? ` <span>· ${where}</span>` : ''}</span><button type="button" class="icon-btn hxp-close" aria-label="Close preview">${ic.close}</button></div>
  ${l.art ? `<a class="hxp-art is-loading" href="${l.url}" tabindex="-1" aria-hidden="true"></a>` : ''}
  <div class="hxp-body">
    <h3 class="hxp-title" id="hxp-title"><a href="${l.url}">${l.title}</a></h3>
    <p class="hxp-sum">${l.sum}</p>
    <div class="hxp-facts"><span class="lab-card-num">${l.num}</span><span class="meta">${l.cat}</span>${l.st}<span class="meta">${l.level}</span><span class="meta">${ic.clock}${l.dur}</span>${l.tracks}</div>
    <div class="hxp-actions"><a class="btn btn-primary" href="${l.url}">${go}${ic.arrow}</a>${progress(slug)}</div>
  </div>
  ${rel.length ? `<div class="hxp-rel"><h4>Related labs</h4><ul>${rel.map((s) => { const r = data.labs[s]; return `<li><a href="${r.url}" style="--c:var(--cat-${r.color})"><b>${r.num}</b><span>${r.short}</span>${ic.arrow}</a></li>`; }).join('')}</ul></div>` : ''}
</div>`;
    $('.hxp-close', pop).addEventListener('click', () => close());
    const box = $('.hxp-art', pop);
    if (box) {
      loadArt(l.art).then((svg) => { if (box.isConnected) { box.innerHTML = svg; box.classList.remove('is-loading'); } })
        .catch(() => { if (box.isConnected) { box.remove(); place(); } });
    }
  };

  // Next to the part when there's room: below, above, right, then left. A bottom sheet on narrow screens.
  const place = () => {
    if (!cur) return;
    const vw = document.documentElement.clientWidth; const vh = innerHeight; const gap = 10; const m = 12;
    if (sheet.matches) {
      pop.dataset.side = 'sheet';
      ['top', 'left', '--hxp-max'].forEach((p) => pop.style.removeProperty(p));
      return;
    }
    const t = cur.getBoundingClientRect();
    if (t.bottom < 0 || t.top > vh) { close(false); return; }
    pop.style.removeProperty('--hxp-max');
    const w = pop.offsetWidth; const ht = pop.offsetHeight;
    const room = { bottom: vh - t.bottom - gap - m, top: t.top - gap - m, right: vw - t.right - gap - m, left: t.left - gap - m };
    let side = ['bottom', 'top', 'right', 'left'].find((s) => (s === 'bottom' || s === 'top' ? room[s] >= ht : room[s] >= w && vh - 2 * m >= ht));
    if (!side) side = room.bottom >= room.top ? 'bottom' : 'top';
    const clamp = (v, lo, hi) => Math.max(lo, Math.min(v, hi));
    const cx = t.left + t.width / 2; const cy = t.top + t.height / 2;
    let x; let y; let max = vh - 2 * m;
    if (side === 'bottom' || side === 'top') {
      max = Math.max(160, room[side]);
      const hh = Math.min(ht, max);
      x = clamp(cx - w / 2, m, vw - w - m);
      y = side === 'bottom' ? t.bottom + gap : t.top - gap - hh;
      pop.style.setProperty('--ax', `${clamp(cx - x, 18, w - 18)}px`);
    } else {
      const hh = Math.min(ht, max);
      x = side === 'right' ? t.right + gap : t.left - gap - w;
      y = clamp(cy - hh / 2, m, vh - hh - m);
      pop.style.setProperty('--ay', `${clamp(cy - y, 18, hh - 18)}px`);
    }
    pop.dataset.side = side;
    pop.style.setProperty('--hxp-max', `${Math.floor(max)}px`);
    pop.style.left = `${Math.round(x)}px`;
    pop.style.top = `${Math.round(y)}px`;
  };
  const schedule = () => { if (cur && !raf) raf = requestAnimationFrame(() => { raf = 0; place(); }); };

  const open = (t) => {
    if (cur) cur.setAttribute('aria-expanded', 'false');
    cur = t;
    render(t);
    t.setAttribute('aria-expanded', 'true');
    if (!pop.matches(':popover-open')) pop.showPopover();
    place();
    pop.focus({ preventScroll: true });
  };
  function close(restore = true) {
    if (!cur) return;
    const t = cur; cur = null;
    t.setAttribute('aria-expanded', 'false');
    if (pop.matches(':popover-open')) pop.hidePopover();
    if (restore) t.focus({ preventScroll: true });
  }

  triggers.forEach((t) => t.addEventListener('click', (e) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    if (cur === t) close(); else open(t);
  }));
  // Dismiss on a press outside the preview (including the sheet's backdrop) or on Escape.
  document.addEventListener('pointerdown', (e) => {
    if (!cur) return;
    const r = pop.getBoundingClientRect();
    const inside = pop.contains(e.target) && e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
    if (!inside && !triggers.some((t) => t.contains(e.target))) close(false);
  });
  pop.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { e.preventDefault(); close(); } else trapFocus(e, pop);
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && cur && !pop.contains(document.activeElement)) close(); });
  addEventListener('scroll', schedule, { passive: true });
  addEventListener('resize', schedule);
  sheet.addEventListener('change', schedule);
}

// Inlined diagrams: pause flows when off-screen.
function initDiagrams() {
  const figs = $$('.figure-svg svg');
  if (!figs.length || reduceMotion || !('IntersectionObserver' in window)) return;
  const io = new IntersectionObserver((ents) => ents.forEach((e) => e.target.classList.toggle('dg-paused', !e.isIntersecting)), { rootMargin: '100px' });
  figs.forEach((f) => io.observe(f));
}
