// Widget framework and the quota simulator (token-limit, request-rate, budget).
const WIDGETS = {};
const wdIcon = (name) => IC[name] || IC.sparkle;
function wdShell({ icon, title, desc, kicker = 'Interactive simulation', controls = '', body = '', foot = '' }) {
  return `<div class="wd"><div class="wd-head"><span class="wd-head-icon" aria-hidden="true">${wdIcon(icon)}</span><div><span class="wd-kicker">${kicker}</span><h3 class="wd-title">${title}</h3><p class="wd-desc">${desc}</p></div></div>`
    + (controls ? `<div class="wd-controls">${controls}</div>` : '') + body + (foot ? `<div class="wd-foot">${foot}</div>` : '') + '</div>';
}
function renderWidgets(root = document) {
  $$('.widget[data-widget]', root).forEach((el) => {
    const fn = WIDGETS[el.dataset.widget];
    if (!fn || el.dataset.ready) return;
    let cfg = {};
    try { cfg = JSON.parse(el.dataset.config || '{}'); } catch { console.warn('Bad widget config', el.dataset.config); }
    el.dataset.ready = '1';
    try { fn(el, cfg); } catch (e) { console.error(`Widget ${el.dataset.widget} failed`, e); el.hidden = true; }
  });
}
const wdSeg = (name, opts, sel, multi = false) => `<div class="wd-seg" role="group" data-seg="${name}"${multi ? ' data-multi' : ''}>${opts.map(([v, l]) => `<button type="button" data-v="${v}" aria-pressed="${multi ? sel.includes(v) : sel === v}">${l}</button>`).join('')}</div>`;
const wdField = (label, input, cls = '') => `<label class="wd-field ${cls}"><span>${label}</span>${input}</label>`;
const wdGroup = (label, inner) => `<div class="wd-field"><span>${label}</span>${inner}</div>`;
const wdSelect = (name, opts, sel) => `<select data-k="${name}">${opts.map(([v, l]) => `<option value="${v}"${String(v) === String(sel) ? ' selected' : ''}>${l}</option>`).join('')}</select>`;
const wdRand = (a, b) => a + Math.random() * (b - a);
// The simulated clock stops while animations are paused (WCAG 2.2.2), so countdowns freeze and resume where they left off.
let wdPausedAt = null, wdPausedFor = 0;
const wdNow = () => (wdPausedAt ?? performance.now()) - wdPausedFor;
function wdSyncClock() {
  const off = document.documentElement.dataset.motion === 'off';
  if (off && wdPausedAt === null) wdPausedAt = performance.now();
  else if (!off && wdPausedAt !== null) { wdPausedFor += performance.now() - wdPausedAt; wdPausedAt = null; }
}
wdSyncClock();
document.addEventListener('aigw:motion', wdSyncClock);
function wdBindSeg(root, onChange) {
  $$('.wd-seg', root).forEach((g) => g.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b || b.disabled) return;
    if (g.hasAttribute('data-multi')) b.setAttribute('aria-pressed', b.getAttribute('aria-pressed') !== 'true');
    else $$('button', g).forEach((x) => x.setAttribute('aria-pressed', x === b));
    onChange(g.dataset.seg, $$('button[aria-pressed="true"]', g).map((x) => x.dataset.v));
  }));
}
// Runs fn on an interval only while the element is on-screen, the tab is visible, and animations aren't paused.
function wdTicker(el, fn, ms = 250) {
  let vis = false, id = null;
  const sync = () => { const on = vis && !document.hidden && wdPausedAt === null; if (on && !id) id = setInterval(fn, ms); if (!on && id) { clearInterval(id); id = null; } };
  new IntersectionObserver(([e]) => { vis = e.isIntersecting; sync(); }).observe(el);
  document.addEventListener('visibilitychange', sync);
  document.addEventListener('aigw:motion', () => { sync(); fn(); });
}

const QUOTA_CALLERS = [
  { id: 'a', name: 'App A', av: '#0f6cbd', ident: 'API key · app-a', ip: '203.0.113.10' },
  { id: 'b', name: 'App B', av: '#8a3ffc', ident: 'API key · app-b', ip: '203.0.113.10' },
  { id: 'c', name: 'Batch job', av: '#0e7a5f', ident: 'Entra · managed identity', ip: '198.51.100.24' },
];
const SIM_MS = 20000;
const QUOTA_MODES = {
  'token-limit': {
    icon: 'gauge', title: 'Token rate limit simulator', unit: 'tokens', rolling: true,
    desc: 'Send requests from three callers and watch tokens accumulate against the limit. Change the counter dimensions to see who shares a counter.',
    periods: [['minute', 'Per minute', 60], ['hour', 'Per hour', 3600], ['day', 'Per day', 86400]],
    defaults: (c) => ({ limit: +c.limit || 1000, period: c.period || 'minute' }),
    limitLabel: 'Allowed tokens', periodLabel: 'Time period',
    cost: (s) => Math.max(20, Math.round(s.limit * wdRand(0.14, 0.34))),
    fmt: (v) => Math.round(v).toLocaleString('en-US'),
  },
  'request-rate': {
    icon: 'gauge', title: 'Request rate limit simulator', unit: 'calls',
    desc: 'Each request counts as one call. When a counter reaches the limit, the gateway returns 429 until the renewal period resets.',
    periods: [['30', '30 seconds', 30], ['60', '60 seconds', 60], ['120', '2 minutes', 120], ['300', '5 minutes', 300]],
    defaults: (c) => ({ limit: +c.calls || 5, period: String(c.window || 60) }),
    limitLabel: 'Calls', periodLabel: 'Renewal period',
    cost: () => 1, fmt: (v) => String(Math.round(v)),
  },
  budget: {
    icon: 'coins', title: 'Cost limit simulator', unit: 'USD', budget: true,
    desc: 'Each request adds its estimated cost to the counter. Once spend reaches the budget, the gateway blocks requests until the period renews.',
    periods: [['hour', 'Hourly', 3600], ['day', 'Daily', 86400], ['week', 'Weekly', 604800], ['month', 'Monthly', 2592000], ['year', 'Yearly', 31536000]],
    defaults: (c) => ({ limit: +c.amount || 5, period: c.period || 'day' }),
    limitLabel: 'Budget amount ($)', periodLabel: 'Renewal period',
    cost: (s) => +(s.limit * wdRand(0.12, 0.3)).toFixed(2),
    fmt: (v) => `$${v.toFixed(2)}`,
  },
};

function quotaWidget(el, cfg, mode) {
  const M = QUOTA_MODES[mode];
  const s = { ...M.defaults(cfg), dims: ['identity'], override: false };
  const periodSecs = () => M.periods.find((p) => p[0] === s.period)?.[2] || 60;
  const periodName = () => M.periods.find((p) => p[0] === s.period)?.[1] || s.period;
  let counters = new Map(), winStart = wdNow(), log = [];
  const ovAmount = () => +(s.limit * 3).toFixed(2);

  const controls = wdField(M.limitLabel, `<input type="number" min="1" step="${M.budget ? '0.5' : '1'}" value="${s.limit}" data-k="limit">`)
    + wdField(M.periodLabel, wdSelect('period', M.periods, s.period))
    + wdGroup('Counter dimensions', wdSeg('dims', [['identity', 'Caller identity'], ['ip', 'Caller IP address']], s.dims, true))
    + (M.budget ? wdGroup('Overrides', wdSeg('override', [['off', 'None'], ['on', 'Batch job identity']], 'off')) : '');
  const body = `<div class="wd-body"><div class="wd-pane"><p class="wd-pane-title">Callers</p><div class="wd-window"><span data-r="wlabel"></span><span class="wd-window-bar"><span></span></span><b data-r="wleft"></b></div><p class="wd-shared" data-r="shared" hidden></p><div class="wd-callers">${QUOTA_CALLERS.map((c) => `
    <div class="wd-caller" data-caller="${c.id}"><div><div class="wd-caller-name"><span class="wd-avatar" style="--av:${c.av}" aria-hidden="true">${c.name.split(' ').map((w) => w[0]).join('')}</span>${c.name}<span class="wd-tag ov" data-r="ov" hidden>Override</span></div><div class="wd-caller-id" data-r="cid"></div></div>
    <button class="btn btn-secondary btn-sm" type="button" data-send="${c.id}">${IC.play}Send</button>
    <div class="wd-meter"><span class="wd-meter-bar"><span></span></span><span data-r="mval"></span></div></div>`).join('')}</div></div>
    <div class="wd-pane"><p class="wd-pane-title"><span>Gateway responses</span><button class="link-btn" type="button" data-burst>Burst from App A ×5</button></p><div class="wd-log" role="log" aria-label="Gateway responses" tabindex="0"></div></div></div>`;
  const foot = `<span>${IC.info}Simulated time: one ${M.rolling ? 'rolling window' : 'renewal period'} (${periodName().toLowerCase()}) runs in 20 seconds. Values are illustrative.</span><button class="btn btn-ghost btn-sm" type="button" data-reset>${IC.reset}Reset</button>`;
  el.innerHTML = wdShell({ icon: M.icon, title: M.title, desc: M.desc, controls, body, foot });
  const logEl = $('.wd-log', el);

  const callerKey = (c) => {
    if (M.budget && s.override && c.id === 'c') return 'ov:c';
    const parts = [];
    if (s.dims.includes('identity')) parts.push(c.ident);
    if (s.dims.includes('ip')) parts.push(c.ip);
    return parts.join('|') || 'shared';
  };
  const limitFor = (c) => (M.budget && s.override && c.id === 'c' ? ovAmount() : s.limit);
  const used = (key) => {
    const ct = counters.get(key);
    if (!ct) return 0;
    if (M.rolling) { const now = wdNow(); ct.entries = ct.entries.filter((e) => now - e.t < SIM_MS); return ct.entries.reduce((a, e) => a + e.v, 0); }
    return ct.used;
  };
  const add = (key, v) => {
    const ct = counters.get(key) || { entries: [], used: 0 };
    ct.entries.push({ t: wdNow(), v }); ct.used += v; counters.set(key, ct);
  };
  const toReal = (ms) => Math.max(1, Math.ceil((ms / SIM_MS) * periodSecs()));
  const fmtDur = (sec) => sec < 120 ? `${sec}s` : sec < 7200 ? `${Math.round(sec / 60)} min` : sec < 172800 ? `${Math.round(sec / 3600)} h` : `${Math.round(sec / 86400)} days`;
  const retryMs = (key) => {
    if (!M.rolling) return SIM_MS - (wdNow() - winStart);
    const ct = counters.get(key);
    return ct?.entries.length ? SIM_MS - (wdNow() - ct.entries[0].t) : 0;
  };

  function send(cid) {
    const c = QUOTA_CALLERS.find((x) => x.id === cid);
    const key = callerKey(c), lim = limitFor(c), u = used(key);
    let row;
    if (u >= lim) {
      const ra = toReal(retryMs(key));
      row = M.budget
        ? { code: 403, msg: `${c.name} blocked: budget exhausted`, hdr: `LlmCostQuotaExceeded · renews in ~${fmtDur(ra)}` }
        : { code: 429, msg: `${c.name} throttled`, hdr: `Retry-After: ${ra}` };
    } else {
      const v = M.cost(s);
      add(key, v);
      const left = Math.max(0, lim - u - v);
      row = M.budget
        ? { code: 200, msg: `${c.name} · ${M.fmt(v)} <small>estimated cost</small>`, hdr: `Remaining budget ${M.fmt(left)}${u + v > lim ? ` · overshoot ${M.fmt(u + v - lim)}` : ''}` }
        : mode === 'token-limit'
          ? { code: 200, msg: `${c.name} · ${M.fmt(v)} <small>tokens</small>`, hdr: `${M.fmt(left)} tokens left this period` }
          : { code: 200, msg: `${c.name} · 1 call <small>${M.fmt(u + 1)} of ${M.fmt(lim)} this period</small>`, hdr: '' };
    }
    log.unshift(row); log = log.slice(0, 30);
    renderLog(); paint();
  }
  function renderLog() {
    logEl.innerHTML = log.length ? log.map((r) => `<div class="wd-log-row"><span class="wd-code s${r.code}">${r.code}</span><span class="wd-log-msg">${r.msg}</span>${r.hdr ? `<span class="wd-log-hdr">${escHtml(r.hdr)}</span>` : ''}</div>`).join('')
      : '<p class="wd-log-empty">Press Send on a caller to make a request.</p>';
  }
  function paint() {
    const now = wdNow();
    if (!M.rolling && now - winStart >= SIM_MS) { winStart = now; counters = new Map(); }
    // Window indicator
    let p, left;
    if (M.rolling) {
      const oldest = Math.min(...[...counters.values()].flatMap((ct) => ct.entries.map((e) => e.t)).filter((t) => now - t < SIM_MS), Infinity);
      p = oldest === Infinity ? 0 : 1 - (now - oldest) / SIM_MS;
      left = oldest === Infinity ? '' : `${fmtDur(toReal(SIM_MS - (now - oldest)))}`;
      $('[data-r="wlabel"]', el).textContent = oldest === Infinity ? 'Rolling window: no recent usage' : 'Oldest usage frees up in';
    } else {
      p = (now - winStart) / SIM_MS;
      left = fmtDur(toReal(SIM_MS - (now - winStart)));
      $('[data-r="wlabel"]', el).textContent = 'Period renews in';
    }
    $('.wd-window-bar span', el).style.setProperty('--p', Math.max(0, Math.min(1, p)).toFixed(3));
    $('[data-r="wleft"]', el).textContent = left;
    // Callers
    const keys = QUOTA_CALLERS.map(callerKey);
    QUOTA_CALLERS.forEach((c, i) => {
      const row = $(`[data-caller="${c.id}"]`, el);
      const lim = limitFor(c), u = used(keys[i]), r = Math.min(1, u / lim);
      const m = $('.wd-meter', row);
      m.classList.toggle('warn', r >= 0.75 && r < 1); m.classList.toggle('full', r >= 1);
      $('.wd-meter-bar span', m).style.setProperty('--p', r.toFixed(3));
      $('[data-r="mval"]', row).textContent = `${M.fmt(u)} / ${M.fmt(lim)}`;
      row.classList.toggle('blocked', u >= lim);
      const ov = M.budget && s.override && c.id === 'c';
      $('[data-r="ov"]', row).hidden = !ov;
      $('[data-r="cid"]', row).textContent = [s.dims.includes('identity') || ov ? c.ident : null, s.dims.includes('ip') && !ov ? c.ip : null].filter(Boolean).join(' · ') || 'Shared counter';
    });
    const shared = $('[data-r="shared"]', el);
    const groups = {};
    keys.forEach((k, i) => (groups[k] = groups[k] || []).push(QUOTA_CALLERS[i].name));
    const multi = Object.values(groups).filter((g) => g.length > 1);
    shared.hidden = !multi.length;
    if (multi.length) shared.textContent = keys.every((k) => k === 'shared')
      ? 'No counter dimension selected: all callers share one counter.'
      : Object.entries(groups).filter(([, g]) => g.length > 1).map(([k, g]) => `${g.join(' and ')} share ${k === 'shared' ? 'one counter because no counter dimension is selected' : 'a counter because they call from the same NAT IP address'}.`).join(' ');
  }
  wdBindSeg(el, (seg, vals) => {
    if (seg === 'dims') s.dims = vals;
    if (seg === 'override') {
      s.override = vals[0] === 'on';
      // Caller IP address can't be a counter dimension while overrides exist.
      const ipBtn = $('[data-seg="dims"] [data-v="ip"]', el);
      ipBtn.disabled = s.override; ipBtn.title = s.override ? 'Caller IP address cannot be used while overrides exist' : '';
      if (s.override) { ipBtn.setAttribute('aria-pressed', 'false'); s.dims = s.dims.filter((d) => d !== 'ip'); }
    }
    reset();
  });
  $$('[data-k]', el).forEach((inp) => inp.addEventListener('change', () => {
    if (inp.dataset.k === 'limit') { const v = +inp.value; if (v > 0) s.limit = v; else inp.value = s.limit; } else s[inp.dataset.k] = inp.value;
    $('.wd-foot span', el).lastChild.textContent = `Simulated time: one ${M.rolling ? 'rolling window' : 'renewal period'} (${periodName().toLowerCase()}) runs in 20 seconds. Values are illustrative.`;
    reset();
  }));
  function reset() { counters = new Map(); winStart = wdNow(); log = []; renderLog(); paint(); }
  el.addEventListener('click', (e) => {
    const b = e.target.closest('[data-send]');
    if (b) return send(b.dataset.send);
    if (e.target.closest('[data-reset]')) return reset();
    if (e.target.closest('[data-burst]')) for (let i = 0; i < 5; i++) setTimeout(() => send('a'), i * 140);
  });
  renderLog(); paint();
  wdTicker(el, paint);
}
WIDGETS['token-limit'] = (el, c) => quotaWidget(el, c, 'token-limit');
WIDGETS['request-rate'] = (el, c) => quotaWidget(el, c, 'request-rate');
WIDGETS.budget = (el, c) => quotaWidget(el, c, 'budget');
