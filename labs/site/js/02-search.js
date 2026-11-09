// Search (Ctrl/Cmd + K) over search.json.
let searchIndex = null, searchModal, searchSel = 0, searchItems = [];

async function loadSearch() {
  if (searchIndex) return searchIndex;
  try { searchIndex = await (await fetch(`${D.rel}search.json`)).json(); } catch { searchIndex = []; }
  return searchIndex;
}
const norm = (s) => String(s || '').toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '');
function hl(text, terms) {
  let out = escHtml(text);
  terms.filter((t) => t.length > 1).forEach((t) => {
    out = out.replace(new RegExp(`(${t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'ig'), '<mark>$1</mark>');
  });
  return out;
}
function snippet(text, terms) {
  const n = norm(text);
  const i = terms.reduce((best, t) => { const k = n.indexOf(t); return k >= 0 && (best < 0 || k < best) ? k : best; }, -1);
  if (i < 0) return '';
  const start = Math.max(0, i - 50);
  return (start ? '…' : '') + text.slice(start, start + 140).replace(/\s+/g, ' ') + '…';
}

function runSearch(q) {
  const terms = norm(q).split(/\s+/).filter(Boolean);
  const res = [];
  for (const lab of searchIndex || []) {
    // Pages (the guides) carry their own URL and show only when the query matches them.
    const url = lab.url ? `${D.rel}${lab.url}` : `${D.rel}labs/${lab.slug}/`;
    const kind = lab.page ? 'page' : 'lab';
    if (!terms.length) { if (!lab.page) res.push({ score: lab.quick ? 101 : 100 - Number(lab.num), lab, url, kind }); continue; }
    const fields = { title: norm(lab.title), num: lab.num || '', summary: norm(lab.summary), tags: norm((lab.tags || []).join(' ')), text: norm(lab.text) };
    let score = 0, all = true;
    for (const t of terms) {
      let s = 0;
      if (fields.num === t) s += 40;
      if (fields.title.includes(t)) s += fields.title.split(/\W+/).includes(t) ? 24 : 16;
      if (fields.tags.includes(t)) s += 10;
      if (fields.summary.includes(t)) s += 6;
      if (fields.text.includes(t)) s += 2;
      if (!s) all = false;
      score += s;
    }
    if (all && score) res.push({ score, lab, url, kind, snip: score < 16 * terms.length ? snippet(lab.text, terms) : '' });
    for (const hd of lab.headings || []) {
      const ht = norm(hd.text);
      if (terms.length && terms.every((t) => ht.includes(t))) res.push({ score: score * 0.4 + 8 + (hd.level === 2 ? 2 : 0), lab, url: `${url}#${hd.id}`, kind: 'section', heading: hd.text });
    }
    // Pages with sections (Troubleshooting) match each section's text, and open the page filtered by the query.
    for (const sec of terms.length ? lab.sections || [] : []) {
      const st = norm(sec.title), sx = norm(sec.text);
      let s = 0;
      for (const t of terms) { const k = (st.includes(t) ? 12 : 0) + (sx.includes(t) ? 4 : 0); if (!k) { s = 0; break; } s += k; }
      if (s) res.push({ score: s + 6, lab, url: `${url}?q=${encodeURIComponent(q.trim())}#${sec.id}`, kind: 'section', heading: sec.title, snip: snippet(sec.text, terms) });
    }
  }
  res.sort((a, b) => b.score - a.score);
  return { terms, items: res.slice(0, terms.length ? 24 : 30) };
}

function renderSearch(q) {
  const { terms, items } = runSearch(q);
  searchItems = items; searchSel = 0;
  const box = $('.search-results', searchModal);
  if (!items.length) { box.innerHTML = `<div class="search-empty">No results for “${escHtml(q)}”. Try “budget”, “MCP” or “Entra”.</div>`; return; }
  const labsHtml = items.filter((x) => x.kind === 'lab');
  const pages = items.filter((x) => x.kind === 'page');
  const secs = items.filter((x) => x.kind === 'section');
  const row = (x, i) => `<a class="sr-item" href="${x.url}" role="option" id="sr-${i}" aria-selected="${i === 0}">
    <span class="sr-num">${x.lab.quick ? IC.bolt : x.lab.page ? IC[x.lab.icon] || IC.tools : x.lab.num}</span><span class="sr-body">
    <span class="sr-title">${hl(x.kind === 'section' ? x.heading : x.lab.title, terms)}</span>
    <span class="sr-sub">${x.kind === 'section' ? `in ${escHtml(x.lab.title)}` : escHtml(x.lab.summary)}</span>
    ${x.snip ? `<span class="sr-snippet">${hl(x.snip, terms)}</span>` : ''}</span></a>`;
  let i = 0;
  // Guides go first when they match better than the best lab.
  const guidesFirst = pages.length && (!labsHtml.length || pages[0].score > labsHtml[0].score);
  const groups = [[terms.length ? 'Labs' : 'All labs', labsHtml], ['Guides', pages]];
  if (guidesFirst) groups.reverse();
  groups.push(['Sections', secs]);
  searchItems = groups.flatMap(([, list]) => list);
  box.innerHTML = groups.filter(([, list]) => list.length)
    .map(([name, list]) => `<div class="search-group">${name}</div>${list.map((x) => row(x, i++)).join('')}`).join('');
}
function moveSel(d) {
  const els = $$('.sr-item', searchModal);
  if (!els.length) return;
  searchSel = (searchSel + d + els.length) % els.length;
  els.forEach((el, i) => el.setAttribute('aria-selected', i === searchSel));
  els[searchSel].scrollIntoView({ block: 'nearest' });
  $('input', searchModal).setAttribute('aria-activedescendant', els[searchSel].id);
}

async function openSearch() {
  if (!searchModal) {
    searchModal = h(`<div class="modal search-modal" role="dialog" aria-modal="true" aria-label="Search labs" hidden>
      <div class="modal-scrim" data-close></div>
      <div class="modal-card">
        <div class="search-box">${IC.search}<input type="search" placeholder="Search labs, policies, steps…" aria-label="Search" role="combobox" aria-expanded="true" aria-controls="search-results" autocomplete="off" spellcheck="false"><kbd>Esc</kbd></div>
        <div class="search-results" id="search-results" role="listbox"></div>
        <div class="search-foot"><span><kbd>↑</kbd><kbd>↓</kbd>navigate</span><span><kbd>↵</kbd>open</span><span><kbd>Esc</kbd>close</span></div>
      </div></div>`);
    document.body.append(searchModal);
    const input = $('input', searchModal);
    input.addEventListener('input', () => renderSearch(input.value));
    searchModal.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { e.preventDefault(); closeSearch(); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); moveSel(1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); moveSel(-1); }
      else if (e.key === 'Enter') { const el = $$('.sr-item', searchModal)[searchSel]; if (el) { e.preventDefault(); location.href = el.href; closeSearch(); } }
      else trapFocus(e, $('.modal-card', searchModal));
    });
    $$('[data-close]', searchModal).forEach((b) => b.addEventListener('click', closeSearch));
    searchModal.addEventListener('click', (e) => { if (e.target.closest('.sr-item')) closeSearch(); });
  }
  searchModal.lastFocus = document.activeElement;
  searchModal.hidden = false;
  document.body.style.overflow = 'hidden';
  const input = $('input', searchModal);
  input.select(); input.focus();
  await loadSearch();
  renderSearch(input.value);
}
function closeSearch() {
  if (!searchModal || searchModal.hidden) return;
  searchModal.hidden = true; document.body.style.overflow = '';
  searchModal.lastFocus?.focus?.();
}
function initSearch() {
  $$('[data-search-open]').forEach((b) => b.addEventListener('click', openSearch));
  // Only a modified shortcut: single-character shortcuts break speech input (WCAG 2.1.4).
  document.addEventListener('keydown', (e) => {
    if ((e.key === 'k' || e.key === 'K') && (e.metaKey || e.ctrlKey)) { e.preventDefault(); openSearch(); }
  });
}
