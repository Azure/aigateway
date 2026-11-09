// Troubleshooting page: filter the error rows by code, message, or lab as you type. ?q= prefills the filter.
function initTroubleshooting() {
  const input = $('#ts-q');
  if (!input) return;
  const count = $('#ts-count'), empty = $('#ts-empty'), total = Number(count.dataset.total);
  const sections = $$('.ts-section').map((sec) => ({
    sec,
    // The heading and the lab link match every row of the section, so "token limits" shows all of lab 06.
    head: norm([...sec.children].filter((el) => !el.matches('.table-wrap')).map((el) => el.textContent).join(' ')),
    rows: $$('tbody tr', sec).map((tr) => ({ tr, text: norm(tr.textContent) })),
    nav: $(`.rn-nav-list a[data-toc="${sec.dataset.ts}"]`)?.closest('li'),
  }));
  const apply = () => {
    const terms = norm(input.value).split(/\s+/).filter(Boolean);
    let shown = 0;
    for (const s of sections) {
      let n = 0;
      for (const r of s.rows) {
        const ok = terms.every((t) => r.text.includes(t) || s.head.includes(t));
        r.tr.hidden = !ok;
        if (ok) n++;
      }
      s.sec.hidden = !n;
      if (s.nav) s.nav.hidden = !n;
      shown += n;
    }
    count.textContent = terms.length ? `${shown} of ${total} errors` : `${total} errors`;
    empty.hidden = shown > 0;
  };
  input.addEventListener('input', apply);
  input.addEventListener('keydown', (e) => { if (e.key === 'Escape' && input.value) { e.preventDefault(); input.value = ''; apply(); } });
  const q = new URLSearchParams(location.search).get('q');
  if (q) {
    input.value = q;
    apply();
    const target = location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (target) requestAnimationFrame(() => target.scrollIntoView());
  }
}
