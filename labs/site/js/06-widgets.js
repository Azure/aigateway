// Widgets: request lifecycle, alias retarget, alias routing, tool patterns, policy layers.
const LC_STAGES = [
  ['client', 'Client app', 'SDK or agent', 'app'],
  ['auth', 'Auth', 'key or Entra', 'key', 1],
  ['ip', 'IP filter', 'allow / deny', 'globe', 1],
  ['rate', 'Request rate', 'calls / window', 'filter', 1],
  ['tokens', 'Token limit', 'TPM / quota', 'gauge', 1],
  ['cost', 'Cost limit', 'budget', 'coins', 1],
  ['safety', 'Content safety', 'prompt', 'shield', 1],
  ['alias', 'Alias routing', 'alias → model', 'route', 1],
  ['backend', 'Backend model', 'managed identity', 'models'],
  ['screen', 'Response', 'screening', 'eye', 1],
  ['telemetry', 'Telemetry', 'Monitoring', 'chart', 1],
];
const LC_SCENARIOS = [
  { id: 'ok', label: 'Happy path', code: 200, dc: 'var(--success)', text: '<strong>200 OK.</strong> Every policy passed, the alias resolved to its backend model, and the gateway called it with its managed identity. Tokens, cost, and policy outcomes are recorded for Monitoring.' },
  { id: 'auth', label: 'Missing key', code: 401, fail: 'auth', dc: 'var(--danger)', text: '<strong>401 Unauthorized.</strong> No valid API key or Entra token. The gateway rejects the request before any policy runs or any backend is called.' },
  { id: 'ip', label: 'Blocked IP', code: 403, fail: 'ip', dc: 'var(--danger)', text: '<strong>403 Forbidden.</strong> The caller\'s address doesn\'t match the IP filter. Nothing reaches the model.' },
  { id: 'rate', label: 'Too many requests', code: 429, fail: 'rate', dc: 'var(--warning)', text: '<strong>429 Too Many Requests.</strong> The caller used all calls for this renewal period. The <code>Retry-After</code> header says when to try again.' },
  { id: 'tokens', label: 'Token limit hit', code: 429, fail: 'tokens', dc: 'var(--warning)', text: '<strong>429 Too Many Requests.</strong> The caller\'s token counter is spent for the window. Clients should back off using <code>Retry-After</code>.' },
  { id: 'cost', label: 'Over budget', code: 403, fail: 'cost', dc: 'var(--danger)', text: '<strong>403 <code>LlmCostQuotaExceeded</code>.</strong> Spend reached the cost limit for this renewal period, so the gateway stops forwarding requests until it renews.' },
  { id: 'safety', label: 'Harmful prompt', code: 400, fail: 'safety', dc: 'var(--warning)', text: '<strong>400 Bad Request.</strong> Content safety flagged the prompt at or above the configured severity. The model never sees it.' },
];
const LC_FOCUS = { auth: 'auth', ipFilter: 'ip', requestRate: 'rate', tokenLimit: 'tokens', costLimit: 'cost', contentSafety: 'safety', alias: 'alias', telemetry: 'telemetry', backend: 'backend' };

WIDGETS['request-lifecycle'] = (el, cfg) => {
  const focus = LC_FOCUS[cfg.focus] || null;
  let cur = LC_SCENARIOS.find((x) => x.fail === focus) || LC_SCENARIOS[0];
  let timer = null, played = false;
  const pills = `<div class="wd-scenarios" role="group" aria-label="Scenario">${LC_SCENARIOS.map((x) => `<button type="button" class="wd-scenario" data-sc="${x.id}" aria-pressed="${x === cur}" style="--dc:${x.dc}"><span class="wd-dot"></span>${x.label}</button>`).join('')}</div>`;
  const pipe = `<div class="wd-pipe">${LC_STAGES.map(([id, l, sub, ic, gw]) => `<div class="wd-stage${gw ? ' gw' : ''}${id === focus ? ' focus' : ''}" data-st="${id}"><span class="wd-node">${IC[ic]}</span><span class="wd-stage-label">${l}</span><span class="wd-stage-sub">${sub}</span></div>`).join('')}</div>`;
  const body = pills + pipe + `<div class="wd-zone"><span><i></i>Runs in the AI gateway</span></div><div class="wd-result" aria-live="polite"><span class="wd-code">…</span><p></p></div>`;
  const foot = `<span>${IC.info}Pick a scenario to follow one request. Stage order is simplified for illustration.</span><button class="btn btn-ghost btn-sm" type="button" data-replay>${IC.reset}Replay</button>`;
  el.innerHTML = wdShell({ icon: 'route', title: 'Follow a request through the gateway', desc: 'Every call is authenticated, checked against policies, routed by alias to a backend model, then logged. A blocked request never reaches the backend.', body, foot });
  const stages = $$('.wd-stage', el);
  const result = $('.wd-result', el);

  function play() {
    clearTimeout(timer);
    stages.forEach((s) => s.classList.remove('active', 'pass', 'fail', 'skip', 'reached'));
    $('.wd-code', result).className = 'wd-code'; $('.wd-code', result).textContent = '…';
    $('p', result).innerHTML = '<span class="muted">Request in flight…</span>';
    const failIdx = cur.fail ? stages.findIndex((s) => s.dataset.st === cur.fail) : -1;
    const tIdx = stages.length - 1;
    const seq = [];
    stages.forEach((s, i) => {
      if (failIdx >= 0 && i > failIdx && i < tIdx) return;
      seq.push(i);
    });
    const step = (k) => {
      const i = seq[k];
      if (k > 0) { const p = stages[seq[k - 1]]; p.classList.remove('active'); if (!p.classList.contains('fail')) p.classList.add('pass'); }
      if (i === undefined) return finish();
      const s = stages[i];
      s.classList.add('reached');
      if (i === failIdx) { s.classList.add('fail'); stages.forEach((x, j) => { if (j > failIdx && j < tIdx) x.classList.add('skip'); }); }
      else s.classList.add('active');
      timer = setTimeout(() => step(k + 1), reduceMotion ? 0 : i === failIdx ? 650 : 360);
    };
    const finish = () => {
      $('.wd-code', result).className = `wd-code s${cur.code}`;
      $('.wd-code', result).textContent = cur.code;
      $('p', result).innerHTML = cur.text;
    };
    step(0);
  }
  el.addEventListener('click', (e) => {
    const b = e.target.closest('[data-sc]');
    if (b) { cur = LC_SCENARIOS.find((x) => x.id === b.dataset.sc); $$('[data-sc]', el).forEach((x) => x.setAttribute('aria-pressed', x === b)); play(); }
    if (e.target.closest('[data-replay]')) play();
  });
  new IntersectionObserver(([en], io) => { if (en.isIntersecting && !played) { played = true; io.disconnect(); play(); } }, { threshold: 0.4 }).observe(el);
};

WIDGETS['alias-retarget'] = (el, cfg) => {
  const alias = cfg.alias || 'chat';
  const targets = cfg.targets || [
    { provider: 'Microsoft Foundry', model: 'gpt-5-mini', note: 'Lower cost', logo: 'microsoft-foundry' },
    { provider: 'Microsoft Foundry', model: 'gpt-6.1-sol', note: 'Higher quality', logo: 'microsoft-foundry' },
    { provider: 'Azure OpenAI', model: 'gpt-6-sol', note: 'Existing deployment', logo: 'azure-openai' },
  ];
  let sel = 0, moves = 0;
  const body = `<div class="wd-alias"><div class="wd-client"><pre>response = client.responses.create(
    model=<b>"${escHtml(alias)}"</b>,
    input="Summarize this ticket",
)</pre><p class="wd-client-cap">${IC.check}<span data-r="cap">Client code: unchanged</span></p></div>
    <div class="wd-alias-hub"><svg aria-hidden="true"><path data-in></path>${targets.map((_, i) => `<path data-p="${i}"></path>`).join('')}</svg><div class="wd-alias-chip"><small>Alias</small>${escHtml(alias)}</div></div>
    <div class="wd-targets" role="group" aria-label="Backend model for alias ${escHtml(alias)}">${targets.map((t, i) => `<button type="button" class="wd-target" data-t="${i}" aria-pressed="${i === sel}"><img src="${D.rel}labs/assets/providers/${t.logo}.png" alt="" width="22" height="22"><span><b>${escHtml(t.model)}</b><span>${escHtml(t.provider)} · ${escHtml(t.note)}</span></span></button>`).join('')}</div></div>`;
  const foot = `<span data-r="msg">${IC.info}Choose a different backend model. The alias name, client code, and alias policies stay the same.</span>`;
  el.innerHTML = wdShell({ icon: 'route', title: 'Retarget an alias', desc: `Clients call the alias <code>${escHtml(alias)}</code>, not a model. Point it at another backend model and every client follows on its next request.`, body, foot });
  const hub = $('.wd-alias-hub', el), svg = $('svg', hub);
  function draw() {
    const hr = hub.getBoundingClientRect();
    if (!hr.width) return;
    svg.setAttribute('viewBox', `0 0 ${hr.width} ${hr.height}`);
    const cy = hr.height / 2, w = hr.width;
    $('[data-in]', svg).setAttribute('d', `M0 ${cy} H${w / 2}`);
    $('[data-in]', svg).classList.add('on');
    $$('[data-t]', el).forEach((b, i) => {
      const r = b.getBoundingClientRect();
      const y = Math.max(4, Math.min(hr.height - 4, r.top + r.height / 2 - hr.top));
      const p = $(`[data-p="${i}"]`, svg);
      p.setAttribute('d', `M${w / 2} ${cy} C${w * 0.78} ${cy}, ${w * 0.7} ${y}, ${w} ${y}`);
      p.classList.toggle('on', i === sel);
    });
  }
  el.addEventListener('click', (e) => {
    const b = e.target.closest('[data-t]');
    if (!b || +b.dataset.t === sel) return;
    sel = +b.dataset.t; moves++;
    $$('[data-t]', el).forEach((x) => x.setAttribute('aria-pressed', +x.dataset.t === sel));
    const t = targets[sel];
    $('[data-r="msg"]', el).innerHTML = `${IC.check}Alias <code>${escHtml(alias)}</code> now routes to <strong>${escHtml(t.model)}</strong> (${escHtml(t.provider)}). Clients changed: 0. Alias policies kept: all. Retargets so far: ${moves}.`;
    $('[data-r="cap"]', el).textContent = `Client code: unchanged after ${moves} retarget${moves > 1 ? 's' : ''}`;
    draw();
  });
  new ResizeObserver(draw).observe(el);
  draw();
};

// Priority and weight routing: the lowest priority number wins, weights split traffic inside that tier.
WIDGETS['alias-routing'] = (el, cfg) => {
  const alias = cfg.alias || 'chat', N = 20;
  const COL = ['var(--cat-violet)', 'var(--cat-magenta)', 'var(--cat-azure)', 'var(--cat-cyan)', 'var(--cat-amber)'];
  const rows = (cfg.backends || [
    { model: 'gpt-5-mini', provider: 'Microsoft Foundry', logo: 'microsoft-foundry', priority: 0, weight: 80 },
    { model: 'gpt-6.1-sol', provider: 'Microsoft Foundry', logo: 'microsoft-foundry', priority: 0, weight: 20 },
    { model: 'gpt-6-sol', provider: 'Azure OpenAI', logo: 'azure-openai', priority: 1, weight: 1 },
  ]).map((b, i) => ({ ...b, priority: String(b.priority ?? 0), weight: String(b.weight ?? 1), c: COL[i % COL.length] }));
  const presets = cfg.presets || [
    ['canary', 'Canary 80/20', [[0, 80], [0, 20], [1, 1]]],
    ['ab', 'A/B 50/50', [[0, 50], [0, 50], [1, 1]]],
    ['prefer', 'Prefer by priority', [[0, 1], [1, 1], [2, 1]]],
  ];
  const bad = (v, k) => {
    const ok = /^\d+$/.test(String(v).trim()) && +v >= (k === 'weight' ? 1 : 0) && +v <= 100;
    return ok ? null : k === 'weight' ? 'Weight must be a whole number from 1 to 100.' : 'Priority must be a whole number from 0 to 100.';
  };
  const pct = (s) => (s > 0 && s < 0.001 ? '<0.1%' : `${+(s * 100).toFixed(1)}%`);
  const controls = wdGroup('Scenario', wdSeg('preset', presets.map(([v, l]) => [v, l]), presets[0][0]));
  const table = `<div class="wr-table" role="table" aria-label="Backend models of alias ${escHtml(alias)}"><div class="wr-row wr-head" role="row"><span role="columnheader">Backend model</span><span role="columnheader">Priority</span><span role="columnheader">Weight</span><span role="columnheader">Share within priority</span></div>`
    + rows.map((r, i) => `<div class="wr-row" role="row" data-i="${i}" style="--c:${r.c}"><span class="wr-model" role="cell"><i></i><img src="${D.rel}labs/assets/providers/${r.logo}.png" alt="" width="20" height="20"><span><b>${escHtml(r.model)}</b><small>${escHtml(r.provider)}</small></span></span>`
      + ['priority', 'weight'].map((k) => `<span role="cell"><input type="number" inputmode="numeric" step="1" min="${k === 'weight' ? 1 : 0}" max="100" data-k="${k}" data-i="${i}" value="${r[k]}" aria-label="${k === 'weight' ? 'Weight' : 'Priority'} for ${escHtml(r.model)}"></span>`).join('')
      + `<span class="wr-share" role="cell"><span class="wr-bar"><span></span></span><b data-r="share"></b><em data-r="tier"></em></span></div>`).join('') + '</div>';
  const body = `<div class="wr">${table}<p class="wr-err" role="alert" hidden></p>
    <div class="wr-run"><div><p class="wd-pane-title">Next ${N} requests with <code>"model": "${escHtml(alias)}"</code></p><div class="wr-dots" aria-hidden="true">${'<span></span>'.repeat(N)}</div></div><div class="wr-tally" aria-live="polite"></div></div></div>`;
  const foot = `<span>${IC.info}Shares match the alias settings. The gateway's exact request order can differ.</span><button class="btn btn-ghost btn-sm" type="button" data-send>${IC.play}Send ${N} requests</button>`;
  el.innerHTML = wdShell({ icon: 'route', title: 'Route one alias by priority and weight', desc: `Clients keep calling <code>${escHtml(alias)}</code>. The gateway uses the backend models with the lowest priority number, then splits traffic among them in proportion to their weights.`, controls, body, foot });
  const dots = $$('.wr-dots span', el);
  let timer = null;

  function plan() {
    const err = rows.flatMap((r) => [bad(r.priority, 'priority'), bad(r.weight, 'weight')]).find(Boolean);
    if (err) return { err };
    const top = Math.min(...rows.map((r) => +r.priority));
    const tier = rows.filter((r) => +r.priority === top);
    // Smooth weighted round robin: an even spread that converges on the exact weights.
    const tot = tier.reduce((a, r) => a + +r.weight, 0), cur = tier.map(() => 0), seq = [];
    for (let k = 0; k < N; k++) {
      let bi = 0;
      tier.forEach((r, i) => { cur[i] += +r.weight; if (cur[i] > cur[bi]) bi = i; });
      cur[bi] -= tot; seq.push(tier[bi]);
    }
    return { top, seq };
  }
  function render(animate) {
    clearTimeout(timer);
    const p = plan();
    $('.wr-err', el).hidden = !p.err;
    $('.wr-err', el).textContent = p.err || '';
    el.classList.toggle('wr-invalid', !!p.err);
    rows.forEach((r, i) => {
      const row = $(`.wr-row[data-i="${i}"]`, el);
      ['priority', 'weight'].forEach((k) => $(`[data-k="${k}"]`, row).setAttribute('aria-invalid', !!bad(r[k], k)));
      const same = rows.filter((x) => !bad(x.priority, 'priority') && x.priority.trim() === r.priority.trim());
      const sum = same.reduce((a, x) => a + (bad(x.weight, 'weight') ? 0 : +x.weight), 0);
      const share = p.err ? 0 : +r.weight / sum;
      const active = !p.err && +r.priority === p.top;
      row.classList.toggle('active', active);
      $('.wr-bar span', row).style.setProperty('--p', share);
      $('[data-r="share"]', row).textContent = p.err ? '--' : pct(share);
      $('[data-r="tier"]', row).textContent = p.err ? '' : active ? 'Preferred tier' : 'Lower preference';
    });
    if (p.err) { dots.forEach((d) => { d.style.removeProperty('--c'); d.className = ''; }); $('.wr-tally', el).innerHTML = ''; return; }
    const counts = new Map();
    const show = (k) => {
      if (k >= N) return;
      const r = p.seq[k];
      dots[k].style.setProperty('--c', r.c); dots[k].className = 'on'; dots[k].title = r.model;
      counts.set(r, (counts.get(r) || 0) + 1);
      $('.wr-tally', el).innerHTML = rows.map((x) => `<span style="--c:${x.c}"><i></i>${escHtml(x.model)}<b>${counts.get(x) || 0}</b></span>`).join('');
      if (animate && !reduceMotion) timer = setTimeout(() => show(k + 1), 70); else show(k + 1);
    };
    dots.forEach((d) => { d.className = ''; d.style.removeProperty('--c'); });
    show(0);
  }
  wdBindSeg(el, (seg, v) => {
    const ps = presets.find((x) => x[0] === v[0]);
    if (!ps) return;
    rows.forEach((r, i) => { const [pr, w] = ps[2][i] || [9, 1]; r.priority = String(pr); r.weight = String(w); $(`[data-k="priority"][data-i="${i}"]`, el).value = r.priority; $(`[data-k="weight"][data-i="${i}"]`, el).value = r.weight; });
    render(true);
  });
  $$('input[data-k]', el).forEach((inp) => inp.addEventListener('input', () => {
    rows[+inp.dataset.i][inp.dataset.k] = inp.value;
    $$('.wd-seg button', el).forEach((b) => b.setAttribute('aria-pressed', 'false'));
    render(false);
  }));
  $('[data-send]', el).addEventListener('click', () => render(true));
  render(false);
  new IntersectionObserver(([en], io) => { if (en.isIntersecting) { io.disconnect(); render(true); } }, { threshold: 0.4 }).observe(el);
};

const globRe = (g) => new RegExp(`^${g.trim().replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.')}$`);
const splitPats = (v) => (Array.isArray(v) ? v : String(v || '').split(/[,\n]/)).map((x) => x.trim()).filter(Boolean);
WIDGETS['tool-patterns'] = (el, cfg) => {
  const tools = cfg.tools || ['aigw-github_github_list_issues', 'aigw-github_github_get_issue', 'aigw-github_github_create_issue', 'aigw-github_github_delete_repository',
    'learn_microsoft_docs_search', 'learn_microsoft_docs_fetch', 'crm_get_customer', 'crm_update_customer', 'crm_delete_customer'];
  const s = { mode: 'patterns', allow: splitPats(cfg.allow || ['*']).join(', '), block: splitPats(cfg.block || ['*_delete_*']).join(', ') };
  const controls = wdGroup('Tool availability', wdSeg('mode', [['all', 'Allow all tools'], ['patterns', 'Use name patterns'], ['server', 'Block the MCP server']], s.mode))
    + wdField('Allowed patterns', `<input type="text" data-k="allow" value="${escHtml(s.allow)}" spellcheck="false" placeholder="aigw-github_github_*">`, 'grow')
    + wdField('Blocked tool patterns', `<input type="text" data-k="block" value="${escHtml(s.block)}" spellcheck="false" placeholder="*_delete_*">`, 'grow');
  const body = `<div class="wd-body"><div class="wd-pane"><p class="wd-pane-title">Backend tools</p><div class="wd-tools"></div><div class="wd-summary"></div></div><div class="wd-pane"><p class="wd-pane-title">What clients get from tools/list</p><div class="wd-client"><pre data-r="list"></pre></div><p class="wd-note">${IC.info} Use <code>*</code> for any characters and <code>?</code> for one. Blocked patterns win over allowed ones. Separate patterns with commas.</p></div></div>`;
  el.innerHTML = wdShell({ icon: 'tools', title: 'Try tool availability patterns', desc: 'Decide which backend tools an MCP server exposes. Names are namespaced per backend, so one pattern can cover a whole backend or a single verb.', controls, body });
  const list = $('.wd-tools', el);
  function evalAll() {
    const allow = splitPats(s.allow), block = splitPats(s.block);
    let ok = 0, bl = 0, hid = 0;
    const rows = tools.map((t) => {
      let cls = 'ok', why = 'Allowed', icon = IC.ok;
      const b = block.find((p) => { try { return globRe(p).test(t); } catch { return false; } });
      const a = allow.find((p) => { try { return globRe(p).test(t); } catch { return false; } });
      if (s.mode === 'server') { cls = 'blocked'; why = 'Server blocked'; icon = IC.lock; }
      else if (b) { cls = 'blocked'; why = `Blocked by ${b}`; icon = IC.x; }
      else if (s.mode === 'patterns' && !a) { cls = 'hidden-tool'; why = 'Not allowed'; icon = IC.minus; }
      else if (s.mode === 'patterns') why = `Allowed by ${a}`;
      cls === 'ok' ? ok++ : cls === 'blocked' ? bl++ : hid++;
      return { t, cls, why, icon };
    });
    list.innerHTML = rows.map((r) => `<div class="wd-tool ${r.cls}">${r.icon}<span class="wd-tool-name" title="${escHtml(r.t)}">${escHtml(r.t)}</span><span class="wd-tool-why">${escHtml(r.why)}</span></div>`).join('');
    $('.wd-summary', el).innerHTML = `<span><b>${ok}</b> available</span><span><b>${bl}</b> blocked</span><span><b>${hid}</b> not allowed</span>`;
    const vis = rows.filter((r) => r.cls === 'ok');
    $('[data-r="list"]', el).textContent = s.mode === 'server'
      ? 'HTTP 403\n// The MCP server is blocked.\n// No tools are reachable.'
      : `{\n  "tools": [${vis.map((r) => `\n    { "name": "${r.t}" }`).join(',')}${vis.length ? '\n  ' : ''}]\n}`;
    syncScroller($('[data-r="list"]', el));
    $$('[data-k]', el).forEach((i) => { i.disabled = s.mode === 'server' || (i.dataset.k === 'allow' && s.mode === 'all'); });
  }
  wdBindSeg(el, (seg, v) => { s.mode = v[0]; evalAll(); });
  $$('[data-k]', el).forEach((i) => i.addEventListener('input', () => { s[i.dataset.k] = i.value; evalAll(); }));
  evalAll();
};

WIDGETS['policy-layers'] = (el) => {
  const L = [
    { id: 'gw', name: 'Gateway', sub: 'All compatible assets, including future ones', icon: 'globe', c: 'var(--cat-azure)',
      pols: [['IP filter', 'filter', ['model', 'mcp']], ['Content safety', 'shield', ['model', 'mcp']], ['Cost limit', 'coins', ['model']]] },
    { id: 'chat', name: 'Alias chat', sub: 'Individual asset', icon: 'route', c: 'var(--cat-violet)', pols: [['Token rate limit', 'gauge', ['model']]] },
    { id: 'batch', name: 'Alias chat-batch', sub: 'Individual asset', icon: 'route', c: 'var(--cat-magenta)', pols: [['Token rate limit', 'gauge', ['model']], ['Cost limit', 'coins', ['model']]] },
    { id: 'model', name: 'Backend model gpt-5-mini', sub: 'Applies through every alias', icon: 'models', c: 'var(--cat-green)', pols: [['Request rate limit', 'filter', ['model']]] },
    { id: 'mcp', name: 'MCP server github-tools', sub: 'Individual asset', icon: 'tools', c: 'var(--cat-amber)', pols: [['Request rate limit', 'filter', ['mcp']], ['Agent 365 tool threat protection', 'shield', ['mcp']]] },
  ];
  const T = {
    chat: { label: 'Alias chat', kind: 'model', layers: ['gw', 'chat', 'model'], note: 'Both aliases point to the same backend model, so its request rate limit applies to each. Alias policies apply only to calls through that alias.' },
    batch: { label: 'Alias chat-batch', kind: 'model', layers: ['gw', 'batch', 'model'], note: 'Same backend model as chat, but different alias policies: a separate token limit and budget for batch traffic.' },
    mcp: { label: 'MCP tool call', kind: 'mcp', layers: ['gw', 'mcp'], note: 'Cost limit only applies to models, so the gateway-scope cost limit is skipped for tool calls. IP filter and content safety still apply.' },
  };
  let cur = 'chat';
  const controls = wdGroup('Send a request to', wdSeg('target', Object.entries(T).map(([k, v]) => [k, v.label]), cur));
  const body = `<div class="wd-body"><div class="wd-pane"><p class="wd-pane-title">Policy scopes</p><div class="wd-layers">${L.map((l) => `<div class="wd-layer" data-l="${l.id}" style="--lc:${l.c}"><div class="wd-layer-head">${IC[l.icon]}<span>${l.name}</span><small>${l.sub}</small></div><div class="wd-pols">${l.pols.map(([n, ic]) => `<span class="wd-pol">${IC[ic]}${n}</span>`).join('')}</div></div>`).join('')}</div></div>
    <div class="wd-pane"><p class="wd-pane-title">Policies evaluated for this request</p><div class="wd-eval"></div><p class="wd-note" data-r="note"></p></div></div>`;
  const foot = `<span>${IC.info}Every applicable policy is evaluated. If any one blocks, the request is rejected before the backend is called.</span>`;
  el.innerHTML = wdShell({ icon: 'layers', title: 'Which policies apply?', desc: 'Policies attach at gateway scope or to individual assets. Pick a request to see which layers take part.', controls, body, foot });
  function paint() {
    const t = T[cur];
    const rows = [];
    L.forEach((l) => {
      const on = t.layers.includes(l.id);
      const node = $(`[data-l="${l.id}"]`, el);
      node.classList.toggle('on', on); node.classList.toggle('off', !on);
      if (on) l.pols.forEach(([n, , kinds]) => { if (kinds.includes(t.kind)) rows.push(`<div class="wd-eval-row">${n}<small>${l.name}</small></div>`); });
    });
    $('.wd-eval', el).innerHTML = rows.join('');
    $('[data-r="note"]', el).textContent = t.note;
  }
  wdBindSeg(el, (seg, v) => { cur = v[0]; paint(); });
  paint();
};

// Streaming usage: what a streaming client receives versus what the gateway counts.
WIDGETS['stream-usage'] = (el, cfg) => {
  const LIMIT = cfg.limit || 1000, WIN = cfg.window || 30, alias = cfg.alias || 'gpt-5-mini-stream';
  const REPLY = cfg.reply || 'Streaming sends the reply in small chunks as the model writes it, so people see words right away instead of waiting for the full answer.';
  const words = REPLY.match(/\S+\s*/g);
  const fmt = (n) => n.toLocaleString('en-US');
  const controls = wdGroup('Client sets <code>stream_options.include_usage</code>', wdSeg('usage', [['off', 'Not set'], ['on', 'true']], 'off'));
  const body = `<div class="wd-body"><div class="wd-pane"><p class="wd-pane-title"><span>Client receives</span><span class="ws-status" data-r="status"></span></p>
    <code class="ws-req" data-r="req"></code><pre class="ws-sse" data-r="sse" tabindex="0" role="region" aria-label="Server-sent events the client receives"></pre>
    <div class="ws-reply"><span class="ws-label">Reply so far</span><p data-r="reply"></p></div><p class="ws-usage" data-r="usage" aria-live="polite"></p></div>
    <div class="wd-pane"><p class="wd-pane-title"><span>Gateway counts</span><button class="link-btn" type="button" data-burst>Send until throttled</button></p>
    <div class="ws-limit"><div class="ws-limit-head"><code>${escHtml(alias)}</code><span>Token limit: ${fmt(LIMIT)} per minute</span></div>
    <div class="wd-meter"><span class="wd-meter-bar"><span></span></span><b data-r="used"></b></div>
    <div class="wd-window"><span>Window</span><span class="wd-window-bar"><span></span></span><b data-r="left"></b></div></div>
    <div class="wd-log" role="log" aria-label="Responses" tabindex="0"></div></div></div>`;
  const foot = `<span>${IC.info}Simulated: one minute runs in ${WIN} seconds. Token counts are illustrative.</span><span class="ws-actions"><button class="btn btn-ghost btn-sm" type="button" data-reset>${IC.reset}Reset</button><button class="btn btn-primary btn-sm" type="button" data-send>${IC.play}Send a streaming request</button></span>`;
  el.innerHTML = wdShell({ icon: 'stream', title: 'Stream a reply and watch the gateway count it', desc: 'The client sees chunks as they arrive, and a usage chunk only when it asks for one. The gateway counts every stream either way, and a full token limit returns a JSON 429 before any stream starts.', controls, body, foot });
  const r = (k) => $(`[data-r="${k}"]`, el);
  const sse = r('sse'), logEl = $('.wd-log', el);
  let usage = false, used = 0, start = wdNow(), n = 0, busy = false, log = [];
  const left = () => Math.max(0, WIN - (wdNow() - start) / 1000);
  function roll() { if (left() <= 0) { used = 0; start = wdNow(); } }
  function paint() {
    roll();
    const p = Math.min(1, used / LIMIT), m = $('.wd-meter', el);
    $('.wd-meter-bar span', m).style.setProperty('--p', p);
    m.classList.toggle('warn', p >= 0.7 && p < 1); m.classList.toggle('full', p >= 1);
    r('used').textContent = `${fmt(used)} / ${fmt(LIMIT)}`;
    $('.wd-window-bar span', el).style.setProperty('--p', 1 - left() / WIN);
    r('left').textContent = `${Math.ceil(left())}s left`;
  }
  function paintLog() {
    logEl.innerHTML = log.length ? log.map((x) => `<div class="wd-log-row"><span class="wd-code s${x.code}">${x.code}</span><span class="wd-log-msg">${x.msg}</span><span class="wd-log-hdr">${escHtml(x.hdr)}</span></div>`).join('')
      : '<p class="wd-log-empty">Send a streaming request to see what the gateway counts.</p>';
  }
  function paintReq() {
    r('req').textContent = JSON.stringify({ model: alias, stream: true, ...(usage ? { stream_options: { include_usage: true } } : {}) });
  }
  function idle() {
    r('status').innerHTML = '';
    sse.innerHTML = '<span class="ws-l ws-k-hint">Press Send a streaming request.</span>';
    r('reply').textContent = ''; r('usage').className = 'ws-usage'; r('usage').textContent = '';
  }
  const line = (txt, kind) => { sse.insertAdjacentHTML('beforeend', `<span class="ws-l ws-k-${kind}">${escHtml(txt)}</span>`); sse.scrollTop = sse.scrollHeight; };
  const wait = (ms) => new Promise((res) => setTimeout(res, reduceMotion ? 0 : ms));
  async function send(fast = false) {
    if (busy) return false;
    paint(); n++;
    sse.innerHTML = ''; r('reply').textContent = '';
    const u = r('usage');
    if (used >= LIMIT) {
      const after = Math.max(1, Math.ceil(left()));
      r('status').innerHTML = '<span class="wd-code s429">429</span>application/json';
      ['HTTP/2 429', 'content-type: application/json', `retry-after: ${after}`, ''].forEach((t) => line(t, 'hdr'));
      line(`{ "statusCode": 429, "message": "Token limit is exceeded. Try again in ${after} seconds." }`, 'err');
      r('reply').innerHTML = '<span class="ws-none">No reply. The gateway rejected the request before streaming.</span>';
      u.className = 'ws-usage err'; u.textContent = `No stream started. Wait ${after} seconds (Retry-After), then try again.`;
      log.unshift({ code: 429, msg: `Request ${n} · <b>throttled</b> <small>before the stream</small>`, hdr: `JSON body, retry-after: ${after}` });
      paintLog();
      return false;
    }
    busy = true; el.classList.add('ws-busy');
    $$('[data-send], [data-burst]', el).forEach((b) => { b.disabled = true; });
    const withUsage = usage, prompt = 14 + Math.round(wdRand(0, 6)), completion = Math.round(wdRand(170, 240));
    const reasoning = completion - words.length - 2;
    r('status').innerHTML = '<span class="wd-code s200">200</span>text/event-stream';
    u.className = 'ws-usage'; u.textContent = 'Streaming…';
    $('.ws-reply', el).classList.add('live');
    const step = fast ? 8 : 70;
    line('data: {"choices":[],"prompt_filter_results":[…]}', 'filter'); await wait(step * 2);
    line('data: {"choices":[{"delta":{"role":"assistant","content":""}}]}', 'role'); await wait(step * 2);
    for (const w of words) {
      line(`data: {"choices":[{"delta":{"content":${JSON.stringify(w)}}}]}`, 'delta');
      r('reply').textContent += w;
      await wait(step);
    }
    line('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}', 'role'); await wait(step * 2);
    if (withUsage) { line(`data: {"choices":[],"usage":{"prompt_tokens":${prompt},"completion_tokens":${completion},"total_tokens":${prompt + completion}}}`, 'usage'); await wait(step * 2); }
    line('data: [DONE]', 'done');
    $('.ws-reply', el).classList.remove('live');
    roll(); used += prompt + completion;
    u.className = `ws-usage ${withUsage ? 'yes' : 'no'}`;
    u.innerHTML = withUsage
      ? `${IC.ok}<span>The client saw usage: <b>${prompt}</b> prompt + <b>${completion}</b> completion (${reasoning} reasoning) = <b>${prompt + completion}</b> tokens.</span>`
      : `${IC.minus}<span>No usage chunk reached the client. The gateway counted <b>${prompt + completion}</b> tokens anyway.</span>`;
    log.unshift({ code: 200, msg: `Request ${n} · <b>${prompt + completion}</b> tokens counted`, hdr: `stream finished, usage chunk to client: ${withUsage ? 'yes' : 'no'}` });
    paintLog(); paint();
    busy = false; el.classList.remove('ws-busy');
    $$('[data-send], [data-burst]', el).forEach((b) => { b.disabled = false; });
    return true;
  }
  wdBindSeg(el, (seg, v) => { usage = v[0] === 'on'; paintReq(); });
  $('[data-send]', el).addEventListener('click', () => send());
  $('[data-burst]', el).addEventListener('click', async () => { for (let i = 0; i < 12 && await send(true); i++); });
  $('[data-reset]', el).addEventListener('click', () => { if (busy) return; used = 0; start = wdNow(); n = 0; log = []; idle(); paintLog(); paint(); });
  paintReq(); idle(); paintLog(); paint();
  wdTicker(el, paint, 500);
};
