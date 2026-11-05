import { box, node, zone, pill, pillW, pills, arrow, label, list, text, icon, svgDoc } from './lib.mjs';

export const architecture = () => svgDoc('architecture', {
  title: 'Azure AI Gateway architecture',
  desc: 'Apps, agents, coding agents and hosted agents call one AI gateway. The gateway authenticates callers, routes model calls through aliases to model providers, federates tools from MCP servers, OpenAPI specs, connectors and Foundry Toolbox, applies policies, and emits OpenTelemetry.',
  h: 450,
  body: () => {
    let o = zone(16, 20, 230, 410, 'Clients', { ic: 'users' });
    const clients = [['app', 'Apps & services', 'OpenAI-compatible SDKs'], ['agent', 'AI agents', 'Any agent framework'], ['terminal', 'Coding agents', 'Copilot, Claude Code'], ['cloud', 'Hosted agents', 'Microsoft Foundry']];
    clients.forEach(([ic, t, s], i) => { const y = 60 + i * 90; o += box(28, y, 206, 76, { t, s, icon: ic, tone: 'azure' }) + arrow(`M236 ${y + 38} H286`, { tone: 'azure' }); });
    o += zone(290, 20, 380, 410, 'Azure AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(302, 56, 356, 56, { t: 'Access', s: 'API keys · Microsoft Entra ID', icon: 'key' });
    o += box(302, 124, 174, 88, { t: 'Models', s: 'Stable aliases', s2: 'Any provider', icon: 'models', tone: 'azure' });
    o += box(484, 124, 174, 88, { t: 'MCP servers', s: 'Federated tools', s2: 'Tool availability', icon: 'tools', tone: 'amber' });
    o += box(302, 224, 356, 52, { t: 'Policies', s: 'Gateway scope or individual assets', icon: 'shield', tone: 'magenta' });
    o += pills(302, 284, ['Token limits', 'Request rate', 'Cost limit', 'Content safety', 'IP filter', 'Threat protection'], { tone: 'magenta', maxW: 356 });
    o += box(302, 346, 356, 60, { t: 'Observability', s: 'OpenTelemetry metrics, logs, and traces', icon: 'chart', tone: 'green' });
    o += zone(714, 20, 230, 220, 'Model providers', { ic: 'models', tone: 'azure' });
    o += list(732, 64, ['Microsoft Foundry', 'Azure OpenAI', 'OpenAI', 'Anthropic', 'AWS Bedrock', 'Google Vertex AI', 'Custom endpoints'], { tone: 'azure', gap: 23, cls: 'dg-t' });
    o += zone(714, 252, 230, 178, 'Tool sources', { ic: 'tools', tone: 'amber' });
    o += list(732, 296, ['Remote MCP servers', 'OpenAPI specifications', 'Built-in connectors', 'Foundry Toolbox'], { tone: 'amber', gap: 25, cls: 'dg-t' });
    o += arrow('M672 130 H710', { tone: 'azure' }) + arrow('M672 341 H710', { tone: 'amber' });
    return o;
  },
});

export const provisioning = () => svgDoc('provisioning', {
  title: 'What provisioning an AI Gateway creates',
  desc: 'You choose a name, a resource group, and a region where AI Gateway is available. Azure creates the AI Gateway in the Standard SKU, with a system-assigned managed identity. There is no capacity or publisher to set. You get a runtime URL, a default workspace for model and MCP routes, and the AI Gateway portal.',
  h: 356,
  body: () => {
    let o = zone(16, 20, 220, 316, 'You choose', { ic: 'user', tone: 'azure' });
    [['Name', 'Up to 24 characters', 'Globally unique', 'doc'], ['Resource group', 'New or existing', 'Holds the gateway', 'layers'], ['Region', 'Any available region', 'List it with the CLI', 'globe']]
      .forEach(([t, s, s2, ic], i) => { o += box(28, 56 + i * 96, 196, 72, { t, s, s2, icon: ic, tone: 'azure' }); });
    o += zone(270, 20, 340, 316, 'Azure creates', { gw: true, ic: 'sparkle' });
    o += box(282, 56, 316, 72, { t: 'AI Gateway', s: 'Standard SKU, the default', s2: 'Microsoft.ApiManagement/aigateways', icon: 'sparkle', mono: true, accent: true });
    o += box(282, 152, 316, 72, { t: 'Managed identity', s: 'System-assigned, on by default', s2: 'Calls backends without keys', icon: 'key', tone: 'green' });
    o += box(282, 248, 316, 72, { t: 'Nothing to size', s: 'No capacity or publisher to set', s2: 'Ready in a few minutes', icon: 'clock' });
    o += zone(644, 20, 300, 316, 'You get', { ic: 'check', tone: 'green' });
    o += box(656, 56, 276, 72, { t: 'Runtime URL', s: 'https://<gateway>.eastus2-01', s2: '.ai.gateway.azure.com', icon: 'globe', tone: 'green', mono: 'all' });
    o += box(656, 152, 276, 72, { t: 'Default workspace', s: '/default/models/…', s2: '/default/toolservers/…', icon: 'grid', tone: 'green', mono: 'all' });
    o += box(656, 248, 276, 72, { t: 'AI Gateway portal', s: 'Home shows a setup guide', s2: 'ai.gateway.azure.com', icon: 'app', tone: 'green', mono: true });
    o += arrow('M236 188 H266', { tone: 'azure' }) + arrow('M610 188 H640', { tone: 'green' });
    return o;
  },
});

export const quickstart = () => svgDoc('quickstart', {
  title: 'Azure AI Gateway quick start',
  desc: 'Step 1: in the AI Gateway portal, with the Azure CLI in Azure Cloud Shell, or with a Bicep template and azd up, you create an AI Gateway, a Foundry model deployment, a Foundry model provider that signs in with the gateway managed identity, an alias, and a runtime API key. Step 2: your app sends a request with the key to the gateway runtime URL. The gateway checks the key, routes the alias to the backend model, and calls Foundry with its managed identity. Without a key the gateway returns 401 and the request never reaches Foundry.',
  h: 468,
  body: () => {
    let o = zone(16, 20, 928, 192, '1 · Set up once · portal, Azure CLI, or azd', { ic: 'clock', tone: 'azure' });
    o += box(32, 52, 260, 44, { t: 'AI Gateway portal', s: 'ai.gateway.azure.com', icon: 'globe', tone: 'azure', mono: 'all' });
    o += box(32, 104, 260, 44, { t: 'Azure CLI', s: 'paste into Azure Cloud Shell', icon: 'terminal', tone: 'azure' });
    o += box(32, 156, 260, 44, { t: 'Bicep + azd', s: 'one azd up, Cloud Shell or local', icon: 'code', tone: 'azure' });
    [74, 126, 178].forEach((y) => { o += arrow(`M294 ${y} C312 ${y} 310 114 326 114`, { tone: 'azure' }); });
    [['sparkle', 'AI Gateway', 'Standard SKU'], ['models', 'Foundry model', 'gpt-5-mini'], ['plug', 'Provider', 'managed identity'], ['route', 'Alias', 'gpt-5-mini'], ['key', 'Runtime key', 'app-first-call']]
      .forEach(([ic, l, sub], i) => { o += node(360 + i * 135, 86, ic, l, { sub, tone: i === 1 ? 'azure' : 'violet' }); });
    o += zone(16, 228, 928, 224, '2 · Call the model · seconds', { ic: 'bolt', tone: 'violet' });
    o += node(90, 312, 'app', 'Your app', { tone: 'azure', sub: 'curl or OpenAI SDK', accent: false });
    o += zone(176, 264, 560, 172, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += node(276, 312, 'key', 'Check the key', { sub: 'api-key header' });
    o += node(456, 312, 'route', 'Route the alias', { sub: 'gpt-5-mini → model' });
    o += node(636, 312, 'lock', 'Managed identity', { sub: 'Foundry User role' });
    o += node(860, 312, 'models', 'Foundry', { tone: 'azure', sub: 'gpt-5-mini deployment', accent: false });
    o += arrow('M120 340 H244', { tone: 'azure' }) + arrow('M306 340 H424') + arrow('M486 340 H604') + arrow('M666 340 H828', { tone: 'azure' });
    o += label(182, 332, 'POST + key') + label(747, 332, 'Entra token');
    o += pill(276, 406, '401 without a key', { tone: 'red', anchor: 'middle' });
    o += pill(860, 406, '200 · the reply', { tone: 'green', anchor: 'middle' });
    return o;
  },
});

export const createGateway = () => svgDoc('create-gateway', {
  title: 'What to choose in Create AI gateway',
  desc: 'Basics: a globally unique name of 24 characters or fewer, a subscription where you can create API Management and connector gateways, a new or existing resource group, and a region where AI Gateway is available. Advanced: keep the system-assigned managed identity enabled, public network access enabled, and public routing. Private routing is for virtual network backends, and you can also add it later under Networking. Then select Create gateway; provisioning takes a few minutes and Home opens with a setup guide.',
  h: 424,
  body: () => {
    const row = (x, y, lbl, chips, help) => {
      let r = text(x, y, lbl, 'dg-t'), cx = x;
      for (const [c, tone, mono] of chips) { const w = pillW(c, mono); r += pill(cx, y + 10, c, { tone, mono, w }); cx += w + 6; }
      return r + text(chips.length ? cx + 6 : x, y + 26, help, 'dg-s');
    };
    let o = zone(16, 20, 456, 304, 'Basics', { ic: 'doc', tone: 'azure' });
    o += row(36, 74, 'Name', [['<gateway>', 'azure', true]], 'Globally unique, 24 characters or fewer');
    o += row(36, 140, 'Subscription', [], 'Needs write access to API Management and connector gateways');
    o += row(36, 206, 'Resource group', [['New', 'azure'], ['Existing', 'azure']], 'Holds the gateway');
    o += row(36, 272, 'Region', [], 'One where AI Gateway is available, as listed by the CLI');
    o += zone(488, 20, 456, 304, 'Advanced · keep the defaults', { ic: 'shield', tone: 'green' });
    o += row(508, 74, 'System-assigned managed identity', [['Enabled', 'green']], 'The gateway uses it to call Foundry');
    o += row(508, 140, 'Public network access', [['Enabled', 'green']], 'Apps reach the runtime URL over HTTPS');
    o += row(508, 206, 'Routing', [['Public routing', 'green'], ['Private routing', 'amber']], 'Private: creation only');
    o += text(508, 276, 'Private routing reaches backends in a virtual network.', 'dg-s') + text(508, 294, 'Lab 18 covers it.', 'dg-s');
    o += box(16, 348, 284, 56, { t: 'Create gateway', s: 'Select it to start', icon: 'check', accent: true });
    o += box(338, 348, 284, 56, { t: 'Provisioning', s: 'A few minutes, often less', icon: 'clock', tone: 'azure' });
    o += box(660, 348, 284, 56, { t: 'Home', s: 'Opens with a setup guide', icon: 'app', tone: 'green' });
    o += arrow('M300 376 H334') + arrow('M622 376 H656', { tone: 'azure' });
    return o;
  },
});

export const requestLifecycle = () => svgDoc('request-lifecycle', {
  title: 'Request lifecycle through Azure AI Gateway',
  desc: 'A request is authenticated, checked by IP filter, rate and token limits, cost limit and content safety, then routed by alias to a backend model using the gateway managed identity. The response is screened and telemetry is recorded. A blocked request returns 401, 403, 429 or 400 and never reaches the backend.',
  h: 360,
  body: () => {
    let o = zone(120, 16, 640, 308, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += node(56, 130, 'app', 'Client', { tone: 'azure', sub: 'app or agent', accent: false });
    const req = [['key', 'Authenticate', 'key or Entra', '401', 'red'], ['globe', 'IP filter', 'allow · deny', '403', 'red'], ['gauge', 'Limits', 'rate · tokens', '429', 'amber'], ['coins', 'Cost limit', 'budget', '403', 'red'], ['shield', 'Content safety', 'prompt', '400', 'amber'], ['route', 'Alias routing', 'alias → model']];
    req.forEach(([ic, l, sub, code, tone], i) => {
      const cx = 180 + i * 96;
      o += node(cx, 60, ic, l, { sub, tone: 'violet' });
      if (code) o += pill(cx, 162, code, { tone, anchor: 'middle', w: 44 });
      if (i < req.length - 1) o += arrow(`M${cx + 31} 88 H${cx + 65}`);
    });
    o += arrow('M86 150 C118 150 118 88 148 88');
    o += node(868, 130, 'models', 'Backend model', { tone: 'azure', sub: 'managed identity', accent: false });
    o += arrow('M692 88 C790 88 800 150 836 150', { tone: 'azure' });
    o += node(640, 212, 'shield', 'Content safety', { tone: 'green', sub: 'response' });
    o += node(440, 212, 'chart', 'Telemetry', { tone: 'green', sub: 'tokens · cost · traces' });
    o += arrow('M838 172 C790 172 770 240 672 240', { tone: 'green' });
    o += arrow('M608 240 H472', { tone: 'green' });
    o += arrow('M408 240 C250 240 130 176 90 172', { tone: 'green' });
    o += text(440, 350, 'Blocked requests stop at the failing policy and never reach the backend.', 'dg-s', 'middle');
    return o;
  },
});

export const aliases = () => svgDoc('aliases', {
  title: 'Model aliases decouple clients from backend models',
  desc: 'Clients call stable aliases such as chat, chat-batch and reasoning. Each alias points to a backend model and carries its own policies. Two aliases can share a backend model. Retargeting an alias to another backend model needs no client change.',
  h: 420,
  body: () => {
    let o = zone(16, 20, 214, 360, 'Clients', { ic: 'users', tone: 'azure' });
    o += zone(290, 20, 280, 360, 'Aliases', { gw: true, ic: 'route' });
    o += zone(636, 20, 308, 360, 'Backend models', { ic: 'models', tone: 'azure' });
    const rows = [
      ['app', 'Chat app', 'model: chat', 'chat', 'Token rate limit', 'gpt-5-mini', 'Microsoft Foundry'],
      ['server', 'Batch job', 'model: chat-batch', 'chat-batch', 'Token rate limit · Cost limit', 'gpt-6.1-sol', 'Microsoft Foundry'],
      ['agent', 'Research agent', 'model: reasoning', 'reasoning', 'Content safety', 'claude-sonnet-5-5', 'Microsoft Foundry'],
    ];
    rows.forEach(([ic, c, call, a, pol, m, prov], i) => {
      const y = 60 + i * 110;
      o += box(28, y, 190, 60, { t: c, s: call, icon: ic, tone: 'azure', mono: true });
      o += arrow(`M220 ${y + 30} H302`);
      o += box(306, y - 2, 248, 64, { t: a, s: pol, icon: 'route', accent: true });
      o += box(652, y, 276, 60, { t: m, s: prov, icon: 'models', tone: 'azure' });
    });
    o += arrow('M556 90 C600 90 610 86 648 86', { tone: 'violet' });
    o += arrow('M556 200 C606 200 606 98 648 98', { tone: 'magenta' });
    o += arrow('M556 310 C600 310 610 310 648 310', { tone: 'cyan' });
    o += arrow('M556 96 C606 104 606 196 648 196', { tone: 'violet', dashed: true });
    o += label(604, 150, 'retarget', { cls: 'dg-m' });
    o += text(16, 404, 'Dashed: retarget chat to gpt-6.1-sol. Clients keep sending model: chat, and the alias keeps its policies.', 'dg-s');
    return o;
  },
});

export const aliasRouting = () => svgDoc('alias-routing', {
  title: 'Priority and weighted routing behind one alias',
  desc: 'Clients keep calling the alias chat. The alias lists several backend models, each with a priority and a weight. The gateway picks the lowest priority number, then splits traffic among the backend models at that priority in proportion to their weights: gpt-5-mini with weight 80 gets 80 percent and the gpt-6.1-sol canary with weight 20 gets 20 percent. A backend model at priority 1 is a lower preference.',
  h: 420,
  body: () => {
    let o = zone(16, 20, 200, 360, 'Clients', { ic: 'users', tone: 'azure' });
    o += box(28, 96, 176, 60, { t: 'Chat app', s: 'model: chat', icon: 'app', tone: 'azure', mono: true });
    o += box(28, 236, 176, 60, { t: 'Support agent', s: 'model: chat', icon: 'agent', tone: 'azure', mono: true });
    o += zone(252, 20, 312, 360, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(268, 60, 280, 64, { t: 'Alias: chat', s: 'Lowest priority first,', s2: 'then split by weight', icon: 'route', accent: true });
    o += text(272, 162, 'SHARE WITHIN PRIORITY 0', 'dg-cap');
    [['gpt-5-mini', 0.8, '80%', 'violet', 190], ['gpt-6.1-sol', 0.2, '20%', 'magenta', 240]].forEach(([m, r, pct, tone, y]) => {
      o += text(272, y, m, 'dg-m');
      o += `<g class="tn-${tone}"><rect class="dg-bar" x="272" y="${y + 8}" width="214" height="10" rx="5"/><rect class="dg-bar-fill" x="272" y="${y + 8}" width="${Math.round(214 * r)}" height="10" rx="5"/></g>`;
      o += text(548, y + 18, pct, 'dg-t', 'end');
    });
    o += text(272, 300, 'share = weight ÷ sum of the weights', 'dg-s');
    o += text(272, 318, 'at the same priority', 'dg-s');
    o += text(272, 346, '80 ÷ (80 + 20) = 80%', 'dg-m');
    o += zone(600, 20, 344, 360, 'Backend models', { ic: 'models', tone: 'azure' });
    o += zone(612, 52, 320, 196, 'Priority 0 · preferred', { tone: 'violet' });
    o += box(624, 88, 296, 64, { t: 'gpt-5-mini', s: 'Weight 80 · 80% of requests', icon: 'models', tone: 'violet', accent: true });
    o += box(624, 166, 296, 64, { t: 'gpt-6.1-sol', s: 'Weight 20 · 20% (canary)', icon: 'models', tone: 'magenta', accent: true });
    o += zone(612, 262, 320, 106, 'Priority 1 · lower preference', { tone: 'azure' });
    o += box(624, 296, 296, 60, { t: 'gpt-6-sol', s: 'Azure OpenAI · weight 1', icon: 'models', tone: 'azure' });
    o += arrow('M206 126 C232 126 240 92 264 92', { tone: 'azure' });
    o += arrow('M206 266 C240 266 236 100 264 100', { tone: 'azure' });
    o += arrow('M550 88 C582 88 592 120 620 120', { tone: 'violet' });
    o += arrow('M550 98 C586 98 590 198 620 198', { tone: 'magenta' });
    o += arrow('M550 108 C580 120 596 326 620 326', { tone: 'azure', dashed: true });
    o += text(16, 404, 'Clients never change: they send model: chat. Change priorities and weights on the alias to shift traffic.', 'dg-s');
    return o;
  },
});

export const streamingUsage = () => svgDoc('streaming-usage', {
  title: 'Streamed responses through Azure AI Gateway',
  desc: 'A client sends stream: true. The gateway checks token, cost and request limits before the stream starts and returns a JSON 429 when a limit is full. It then relays server-sent event chunks from the model as they arrive and captures token usage for counters, cost limits and Monitoring, whether or not the client set include_usage. A Chat Completions stream carries a prompt filter chunk, a role chunk, content deltas, a finish chunk, a usage chunk when include_usage is set, and [DONE].',
  h: 440,
  body: () => {
    let o = zone(16, 20, 200, 290, 'Clients', { ic: 'users', tone: 'azure' });
    o += box(28, 70, 176, 60, { t: 'Your app', s: 'stream: true', icon: 'app', tone: 'azure', mono: true });
    o += box(28, 190, 176, 60, { t: 'Agent', s: 'Responses API', icon: 'agent', tone: 'azure' });
    o += list(28, 280, ['Reads data: lines', 'Stops at [DONE]'], { tone: 'azure' });
    o += zone(252, 20, 400, 290, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(268, 54, 368, 62, { t: 'Check limits before the stream', s: 'Token limit, cost limit, request rate', s2: 'Full: a JSON 429, no stream starts', icon: 'gauge', accent: true });
    o += box(268, 126, 368, 62, { t: 'Relay chunks as they arrive', s: 'text/event-stream, no buffering', icon: 'bolt', tone: 'azure' });
    o += box(268, 198, 368, 62, { t: 'Capture usage from every stream', s: 'Prompt and completion tokens,', s2: 'with or without include_usage', icon: 'chart', tone: 'green', accent: true });
    o += pills(268, 274, ['Token counters', 'Cost limits', 'Monitoring'], { tone: 'green' });
    o += zone(688, 20, 256, 290, 'Model', { ic: 'models', tone: 'azure' });
    o += box(700, 120, 232, 76, { t: 'Foundry model', s: 'gpt-5-mini', s2: 'Streams tokens as made', icon: 'models', tone: 'violet' });
    o += list(700, 232, ['Tokens as data: chunks', 'Usage in the final chunk', 'Responses: response.completed'], { tone: 'violet' });
    o += arrow('M206 96 C236 96 236 80 264 80', { tone: 'azure' });
    o += arrow('M206 216 C240 216 236 90 264 90', { tone: 'azure' });
    o += arrow('M638 85 C668 85 668 140 696 140', { tone: 'violet' });
    o += arrow('M698 176 C668 176 668 157 640 157', { tone: 'green' });
    o += arrow('M266 152 C238 152 236 112 208 112', { tone: 'green' });
    o += arrow('M266 162 C238 162 236 232 208 232', { tone: 'green' });
    o += text(32, 340, 'WHAT A CHAT COMPLETIONS STREAM CARRIES, IN ORDER', 'dg-cap');
    let x = 32;
    [['prompt filter', 'amber', 'empty choices'], ['role', 'azure'], ['delta', 'violet'], ['delta', 'violet'], ['…', 'violet'], ['finish_reason: stop', 'violet'], ['usage', 'green', 'empty choices, only with include_usage'], ['[DONE]', 'azure']].forEach(([l, tone, note]) => {
      const w = pillW(l, true);
      o += pill(x, 352, l, { tone, w, mono: true });
      if (note) o += text(x + w / 2, 394, note, 'dg-s', 'middle');
      x += w + 10;
    });
    o += text(32, 428, 'The gateway counts every stream. Limits apply to the next request: a stream that started finishes.', 'dg-s');
    return o;
  },
});

export const mcpFederation = () => svgDoc('mcp-federation', {
  title: 'MCP tool federation through Azure AI Gateway',
  desc: 'MCP clients connect to one MCP server endpoint on the gateway. The server federates tools from remote MCP servers, OpenAPI specifications, built-in connectors and Foundry Toolbox. Tool names are namespaced per backend, tool availability rules decide which tools clients see, and policies apply to every call.',
  h: 420,
  body: () => {
    let o = zone(16, 20, 214, 380, 'MCP clients', { ic: 'users', tone: 'azure' });
    [['agent', 'AI agents', 'Agent Framework'], ['terminal', 'Coding agents', 'IDEs and CLIs'], ['cloud', 'Hosted agents', 'Microsoft Foundry'], ['app', 'Your apps', 'Any MCP client']].forEach(([ic, t, s], i) => {
      const y = 60 + i * 86;
      o += box(28, y, 190, 64, { t, s, icon: ic, tone: 'azure' });
    });
    o += zone(270, 20, 400, 380, 'AI Gateway', { gw: true, ic: 'sparkle' });
    [60, 146, 232, 318].forEach((y) => { o += arrow(`M220 ${y + 32} C252 ${y + 32} 252 95 282 95`, { tone: 'azure' }); });
    o += box(286, 56, 368, 78, { t: 'MCP server: github-tools', s: 'One endpoint, one key or Entra token', s2: '/default/toolservers/github-tools/mcp', icon: 'tools', accent: true, mono: true });
    o += box(286, 148, 368, 64, { t: 'Tool availability', s: 'Allow all · exact list · patterns · block', icon: 'filter', tone: 'amber' });
    o += box(286, 226, 368, 78, { t: 'Policies', s: 'IP filter · request rate · content safety', s2: 'Agent 365 tool threat protection', icon: 'shield', tone: 'magenta' });
    o += text(290, 332, 'Tools are namespaced per backend:', 'dg-s');
    o += text(290, 354, 'aigw-github_github_list_issues', 'dg-m') + text(290, 374, 'learn_microsoft_docs_search', 'dg-m');
    o += zone(714, 20, 230, 380, 'Tool sources', { ic: 'tools', tone: 'amber' });
    [['globe', 'Remote MCP server', 'SSE or Streamable HTTP'], ['doc', 'OpenAPI spec', 'Operations as tools'], ['plug', 'Connector', 'Microsoft 365, GitHub'], ['toolbox', 'Foundry Toolbox', 'Tools from Foundry']].forEach(([ic, t, s], i) => {
      const y = 60 + i * 86;
      o += box(726, y, 206, 64, { t, s, icon: ic, tone: 'amber' });
      o += arrow(`M672 210 C700 210 694 ${y + 32} 722 ${y + 32}`, { tone: 'amber' });
    });
    return o;
  },
});

export const policyScopes = () => svgDoc('policy-scopes', {
  title: 'Policy scopes in Azure AI Gateway',
  desc: 'Gateway-scope policies apply to all compatible assets, including assets added later. Individual-asset policies attach to a backend model, an alias or an MCP server. Every applicable policy is evaluated for a request.',
  h: 440,
  body: () => {
    let o = zone(16, 16, 928, 408, 'Gateway scope · applies to all compatible assets, including future ones', { gw: true, ic: 'globe' });
    o += pills(32, 48, [['Content safety', 'azure'], ['IP filter', 'azure'], ['Cost limit', 'azure']]);
    const cols = [
      ['Models', 'models', [['gpt-5-mini', 'Backend model', ['Request rate']]], 'Applies through every alias'],
      ['Aliases', 'route', [['chat', '→ gpt-5-mini', ['Token rate limit']], ['chat-batch', '→ gpt-5-mini', ['Token rate limit', 'Cost limit']]]],
      ['MCP servers', 'tools', [['github-tools', 'MCP server', ['Request rate', 'Threat protection']]]],
    ];
    const tones = ['green', 'violet', 'amber'];
    cols.forEach(([name, ic, assets, note], i) => {
      const x = 32 + i * 226, cx = x + 107;
      o += arrow(`M${cx} 76 V96`, { tone: 'azure' });
      o += zone(x, 100, 214, 300, name, { ic, tone: tones[i] });
      assets.forEach(([t, s, pols], j) => {
        const y = 138 + j * 128;
        o += box(x + 12, y, 190, 56, { t, s, icon: ic, tone: tones[i] });
        o += pills(x + 12, y + 64, pols, { tone: tones[i], maxW: 190 });
      });
      if (note) o += text(x + 14, 258, note, 'dg-s');
    });
    const fx = 710;
    o += arrow(`M${fx + 107} 76 V96`, { tone: 'azure' });
    o += `<rect class="dg-ghost" x="${fx}" y="100" width="214" height="300" rx="16"/>` + `<g class="tn-violet">${icon('sparkle', fx + 16, 110, 16)}</g>` + text(fx + 38, 123, 'FUTURE ASSETS', 'dg-cap');
    o += `<rect class="dg-ghost" x="${fx + 12}" y="138" width="190" height="56" rx="10"/>` + text(fx + 26, 162, 'New model or server', 'dg-t') + text(fx + 26, 180, 'Inherits gateway policies', 'dg-s');
    o += text(32, 416, 'Every applicable policy is evaluated for each request. Any one of them can block it.', 'dg-s');
    return o;
  },
});

export const identityBoundaries = () => svgDoc('identity-boundaries', {
  title: 'Identity boundaries in Azure AI Gateway',
  desc: 'Inbound, callers authenticate to the gateway with an API key or a Microsoft Entra token that carries an AI Gateway data-plane role. Outbound, the gateway calls backends with its own managed identity, or a provider API key it stores. Callers never receive backend credentials.',
  h: 360,
  body: () => {
    let o = pill(286, 10, 'Inbound: who is calling?', { tone: 'azure', anchor: 'middle' }) + pill(674, 10, 'Outbound: the gateway identity', { tone: 'green', anchor: 'middle' });
    o += `<path class="dg-ghost" d="M286 38 V324 M674 38 V324"/>`;
    o += zone(16, 44, 250, 280, 'Callers', { ic: 'users', tone: 'azure' });
    [['key', 'App with API key', 'api-key header'], ['user', 'User or agent', 'Entra token (delegated)'], ['cloud', 'Workload', 'Managed identity token']].forEach(([ic, t, s], i) => {
      const y = 82 + i * 80;
      o += box(28, y, 226, 64, { t, s, icon: ic, tone: 'azure' });
    });
    o += zone(306, 44, 348, 280, 'AI Gateway', { gw: true, ic: 'sparkle' });
    [82, 162, 242].forEach((y) => { o += arrow(`M256 ${y + 32} C290 ${y + 32} 292 124 318 124`, { tone: 'azure' }); });
    o += box(322, 82, 316, 84, { t: 'Inbound check', s: 'Valid key, or an Entra token with', s2: 'an AI Gateway data-plane role', icon: 'lock', accent: true });
    o += pills(322, 176, ['AI Gateway User', 'Models User', 'Tools User'], { tone: 'violet', maxW: 316 });
    o += box(322, 236, 316, 76, { t: 'Outbound identity', s: 'System- or user-assigned', s2: 'managed identity', icon: 'key', tone: 'green', accent: true });
    o += zone(694, 44, 250, 280, 'Backends', { ic: 'models', tone: 'green' });
    o += box(706, 82, 226, 84, { t: 'Microsoft Foundry', s: 'Managed identity with the', s2: 'Foundry User role', icon: 'models', tone: 'green' });
    o += box(706, 184, 226, 84, { t: 'Other providers', s: 'Provider API key', s2: 'stored by the gateway', icon: 'globe', tone: 'green' });
    o += arrow('M640 274 C672 274 672 124 702 124', { tone: 'green' }) + arrow('M640 274 C672 274 672 226 702 226', { tone: 'green' });
    o += text(16, 350, 'Callers never receive backend credentials. Each side is authorized separately.', 'dg-s');
    return o;
  },
});
