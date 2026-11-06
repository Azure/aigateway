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

// Hero: pause the decorative animation when off-screen.
function initHero() {
  const svg = $('.hero-diagram');
  if (!svg || reduceMotion) return;
  new IntersectionObserver(([e]) => {
    svg.style.setProperty('--play', e.isIntersecting ? 'running' : 'paused');
    $$('*', svg).forEach((n) => { n.style.animationPlayState = e.isIntersecting ? 'running' : 'paused'; });
  }).observe(svg);
}

// Inlined diagrams: pause flows when off-screen.
function initDiagrams() {
  const figs = $$('.figure-svg svg');
  if (!figs.length || reduceMotion || !('IntersectionObserver' in window)) return;
  const io = new IntersectionObserver((ents) => ents.forEach((e) => e.target.classList.toggle('dg-paused', !e.isIntersecting)), { rootMargin: '100px' });
  figs.forEach((f) => io.observe(f));
}
