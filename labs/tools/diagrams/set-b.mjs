import { box, node, zone, pill, pills, arrow, label, list, text, icon, bar, svgDoc } from './lib.mjs';

export const observability = () => svgDoc('observability', {
  title: 'Observability with OpenTelemetry',
  desc: 'The gateway emits OpenTelemetry metrics, logs and traces for model calls, tool calls and policy decisions. Signals go to Application Insights, which powers the built-in Monitoring dashboard, or to any OTLP endpoint.',
  h: 420,
  body: () => {
    let o = zone(16, 20, 290, 340, 'AI Gateway', { gw: true, ic: 'sparkle' });
    [['models', 'Model calls', 'Tokens, latency, estimated cost', 'azure'], ['tools', 'Tool calls', 'tools/list and tools/call', 'amber'], ['shield', 'Policy decisions', 'Allowed, blocked, and why', 'magenta']].forEach(([ic, t, s, tone], i) => {
      const y = 56 + i * 96;
      o += box(28, y, 266, 72, { t, s, icon: ic, tone });
      o += arrow(`M296 ${y + 36} C326 ${y + 36} 326 ${88 + i * 96} 358 ${88 + i * 96}`, { tone: 'green' });
    });
    o += zone(346, 20, 250, 340, 'OpenTelemetry (OTLP)', { ic: 'chart', tone: 'green' });
    [['chart', 'Metrics', 'Token usage and cost'], ['doc', 'Logs', 'Requests and outcomes'], ['layers', 'Traces', 'Policy spans per request']].forEach(([ic, t, s], i) => {
      const y = 56 + i * 96;
      o += box(362, y, 218, 72, { t, s, icon: ic, tone: 'green', accent: true });
    });
    o += arrow('M582 92 C614 92 614 98 646 98', { tone: 'green' }) + arrow('M582 188 C614 188 614 98 646 98', { tone: 'green' }) + arrow('M582 284 C614 284 614 98 646 98', { tone: 'green' });
    o += arrow('M582 284 C614 284 614 300 646 300', { tone: 'green' });
    o += zone(636, 20, 308, 340, 'Destinations', { ic: 'cloud', tone: 'azure' });
    o += box(652, 56, 276, 84, { t: 'Application Insights', s: 'Powers the built-in', s2: 'Monitoring dashboard', icon: 'chart', tone: 'azure', accent: true });
    o += text(656, 166, 'DASHBOARD TABS', 'dg-cap');
    o += pills(652, 176, ['Overview', 'Models', 'Tools', 'Policies', 'Traces'], { tone: 'azure', maxW: 276 });
    o += box(652, 268, 276, 64, { t: 'Any OTLP endpoint', s: 'Your observability backend', icon: 'globe', tone: 'azure' });
    o += text(16, 386, 'Token metric', 'dg-s') + text(100, 386, 'gen_ai_client_token_usage', 'dg-m');
    o += text(16, 408, 'Claim attribute', 'dg-s') + text(116, 408, 'azure.ai_gateway.identity.claims.<claim>', 'dg-m');
    return o;
  },
});

export const privateNetworking = () => svgDoc('private-networking', {
  title: 'Private networking for Azure AI Gateway',
  desc: 'Clients reach the gateway on its public endpoint, protected by API keys or Microsoft Entra ID and an IP filter policy. Inbound private endpoints and disabling public network access are not available for the aigateways resource yet. Outbound, private routing chosen when you create the gateway joins it to an integration subnet of at least /27 delegated to Microsoft.App/environments, so it reaches a Foundry account with public access disabled through a private endpoint and private DNS zones.',
  h: 430,
  body: () => {
    let o = zone(16, 20, 230, 330, 'Clients', { ic: 'users', tone: 'azure' });
    o += box(28, 56, 206, 72, { t: 'App or agent', s: 'Calls the gateway host', icon: 'app', tone: 'azure' });
    o += box(28, 150, 206, 72, { t: 'Caller credential', s: 'API key or Entra token', icon: 'key', tone: 'azure' });
    o += `<path class="dg-ghost" d="M131 130 V148"/>`;
    o += zone(276, 20, 330, 330, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(292, 56, 298, 72, { t: 'Inbound', s: 'Public endpoint', s2: '*.ai.gateway.azure.com', icon: 'globe', accent: true, mono: true });
    o += pills(292, 140, ['Keys or Entra ID', 'IP filter policy'], { tone: 'violet' });
    o += pill(292, 174, 'Private frontend: not yet', { tone: 'amber' });
    o += box(292, 252, 298, 72, { t: 'Outbound', s: 'Private routing, set at creation', s2: 'backend.subnet.id', icon: 'network', tone: 'green', accent: true, mono: true });
    o += arrow('M236 92 H288', { tone: 'azure' });
    o += zone(636, 20, 308, 330, 'Your virtual network', { ic: 'network', tone: 'green' });
    o += text(652, 60, 'Integration subnet: /27 or larger,', 'dg-s') + text(652, 78, 'delegated to Microsoft.App/environments', 'dg-m');
    o += box(648, 96, 284, 64, { t: 'Private DNS zones', s: 'privatelink.*.azure.com', icon: 'dns', tone: 'green', mono: true });
    o += `<path class="dg-ghost" d="M790 162 V180"/>`;
    o += box(648, 182, 284, 64, { t: 'Private endpoint', s: 'groupId: account', icon: 'plug', tone: 'green', accent: true, mono: true });
    o += arrow('M790 248 V266', { tone: 'green' });
    o += box(648, 268, 284, 64, { t: 'Microsoft Foundry', s: 'Public network access disabled', icon: 'models', tone: 'cyan' });
    o += arrow('M592 288 C620 288 620 214 644 214', { tone: 'green' });
    o += `<g class="tn-amber">${icon('lock', 16, 372, 20)}</g>` + text(44, 387, 'Inbound private endpoints and turning off public network access aren\'t available for aigateways yet.', 'dg-s');
    o += `<g class="tn-amber">${icon('dns', 16, 400, 20)}</g>` + text(44, 415, 'DNS is the common pitfall: the gateway must resolve Foundry to its private endpoint IP.', 'dg-s');
    return o;
  },
});

export const hostedAgent = () => svgDoc('hosted-agent', {
  title: 'Foundry hosted agent behind Azure AI Gateway',
  desc: 'azd runs the agent locally and deploys it to Microsoft Foundry Hosted Agents. The agent has no model deployment, no direct tool access, and no keys: it calls a model alias through the AI gateway with its own Microsoft Entra Agent ID, and reaches the Microsoft Learn MCP server through a Foundry toolbox that signs in with the project\'s managed identity. The gateway authorizes both identities with the AI Gateway User role, applies policies, and forwards to Foundry models and Microsoft Learn.',
  h: 400,
  body: () => {
    let o = zone(16, 20, 220, 340, 'You', { ic: 'user', tone: 'azure' });
    o += box(28, 56, 196, 72, { t: 'Run locally', s: 'azd ai agent run', icon: 'terminal', tone: 'azure' });
    o += box(28, 150, 196, 72, { t: 'Deploy', s: 'azd deploy', icon: 'terminal', tone: 'azure', accent: true });
    o += box(28, 244, 196, 72, { t: 'Invoke', s: 'azd ai agent invoke', icon: 'user', tone: 'azure' });
    o += zone(266, 20, 200, 340, 'Microsoft Foundry', { ic: 'cloud', tone: 'cyan' });
    o += box(278, 56, 176, 100, { t: 'Hosted agent', s: 'Agent Framework', s2: 'Entra Agent ID', icon: 'agent', tone: 'cyan', accent: true });
    o += box(278, 196, 176, 72, { t: 'Toolbox', s: 'Project identity', icon: 'tools', tone: 'amber' });
    o += arrow('M226 92 H274', { tone: 'azure', dashed: true });
    o += arrow('M226 186 C250 186 250 122 274 122', { tone: 'azure' });
    o += arrow('M226 280 C256 280 256 142 274 142', { tone: 'azure' });
    o += arrow('M366 156 V192', { tone: 'amber' });
    o += zone(496, 20, 240, 340, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(510, 70, 212, 72, { t: 'Model alias', s: 'Bearer: agent token', icon: 'route', accent: true });
    o += box(510, 166, 212, 72, { t: 'MCP server: learn', s: 'Bearer: project token', icon: 'tools', tone: 'amber', accent: true });
    o += pills(510, 262, ['AI Gateway User', 'Token limits', 'Monitoring'], { tone: 'magenta', maxW: 212 });
    o += arrow('M456 106 H506') + arrow('M456 232 C484 232 480 202 506 202', { tone: 'amber' });
    o += zone(766, 20, 178, 340, 'Backends', { ic: 'models', tone: 'azure' });
    o += box(778, 70, 154, 72, { t: 'Foundry', s: 'models', icon: 'models', tone: 'azure' });
    o += box(778, 166, 154, 72, { t: 'Learn MCP', s: 'Public server', icon: 'globe', tone: 'amber' });
    o += arrow('M724 106 H774', { tone: 'azure' }) + arrow('M724 202 H774', { tone: 'amber' });
    o += text(16, 388, 'No keys: the gateway authorizes the agent and the project by their Entra identities, so their limits and telemetry stay separate.', 'dg-s');
    return o;
  },
});

export const agent365 = () => svgDoc('agent-365', {
  title: 'Govern MCP servers with Microsoft Agent 365',
  desc: 'The Microsoft 365 admin center inventories API Management gateways and MCP servers. Admins block or unblock MCP servers, and block individual tools when the server has a static allow list. The gateway enforces the decisions for agents and sends runtime signals back for audit.',
  h: 400,
  body: () => {
    let o = zone(16, 20, 290, 340, 'Microsoft 365 admin center', { ic: 'm365', tone: 'azure' });
    o += box(28, 56, 266, 72, { t: 'Inventory', s: 'API Management gateways', s2: 'and MCP servers', icon: 'grid', tone: 'azure' });
    o += box(28, 148, 266, 72, { t: 'Block or unblock', s: 'Whole MCP servers', icon: 'block', tone: 'red', accent: true });
    o += box(28, 240, 266, 84, { t: 'Block individual tools', s: 'Requires a static allow list', s2: 'on the MCP server', icon: 'filter', tone: 'red' });
    o += zone(350, 20, 290, 340, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(366, 56, 258, 72, { t: 'MCP server: github-tools', s: 'Allowed tools only', icon: 'tools', tone: 'amber', accent: true });
    o += box(366, 148, 258, 72, { t: 'MCP server: crm-tools', s: 'Blocked by admin', icon: 'block', tone: 'red' });
    o += box(366, 240, 258, 84, { t: 'Tool threat protection', s: 'Defender and Purview', s2: 'before and after tool calls', icon: 'shield', tone: 'magenta' });
    o += arrow('M296 184 H362', { tone: 'red' }) + arrow('M296 282 C330 282 330 92 362 92', { tone: 'red' });
    o += arrow('M366 312 C336 312 330 342 296 342', { tone: 'green', dashed: true });
    o += label(206, 346, 'Runtime signals for audit', { cls: 'dg-s' });
    o += zone(684, 20, 260, 340, 'Agents', { ic: 'agent', tone: 'cyan' });
    [['agent', 'Copilot agents', 'Built in Microsoft 365'], ['cloud', 'Hosted agents', 'Microsoft Foundry'], ['terminal', 'Coding agents', 'IDEs and CLIs']].forEach(([ic, t, s], i) => {
      const y = 56 + i * 92;
      o += box(696, y, 236, 72, { t, s, icon: ic, tone: 'cyan' });
      o += arrow(`M694 ${y + 36} C664 ${y + 36} 664 ${92 + Math.min(i, 1) * 92} 628 ${92 + Math.min(i, 1) * 92}`, { tone: 'cyan' });
    });
    o += text(16, 388, 'Decisions made by Microsoft 365 admins are enforced by the gateway on every tool call.', 'dg-s');
    return o;
  },
});

export const threatProtection = () => svgDoc('threat-protection', {
  title: 'Agent 365 tool threat protection',
  desc: 'An agent calls an MCP tool with a delegated Microsoft Entra token. Before invocation, Microsoft Defender and Microsoft Purview check the tool input for malicious content, prompt injection and sensitive data. If blocked, the tool never runs. After invocation they check the tool result. A denial after invocation withholds the result, but the tool already ran.',
  h: 430,
  body: () => {
    let o = zone(120, 16, 660, 370, 'AI Gateway · MCP server', { gw: true, ic: 'sparkle' });
    o += node(56, 130, 'agent', 'Agent', { tone: 'cyan', sub: 'calls a tool', accent: false });
    o += node(240, 60, 'key', 'Entra token', { sub: 'delegated (OBO)' });
    o += node(450, 60, 'eye', 'Before invocation', { tone: 'magenta', sub: 'checks tool input' });
    o += node(880, 150, 'tools', 'MCP tool', { tone: 'amber', sub: 'runs the call', accent: false });
    o += node(620, 230, 'eye', 'After invocation', { tone: 'magenta', sub: 'checks tool result' });
    o += arrow('M86 150 C140 150 160 88 208 88', { tone: 'cyan' }) + arrow('M270 88 H418');
    o += arrow('M480 88 C720 88 800 120 850 160', { tone: 'amber' });
    o += arrow('M850 192 C780 250 720 258 652 258', { tone: 'amber' });
    o += arrow('M588 258 C320 258 160 172 90 172', { tone: 'cyan' });
    o += pill(240, 164, 'App-only tokens not supported', { tone: 'violet', anchor: 'middle' });
    o += pill(450, 164, 'Deny: tool never runs', { tone: 'red', anchor: 'middle' });
    o += pill(620, 330, 'Deny: result withheld, tool already ran', { tone: 'amber', anchor: 'middle' });
    o += text(150, 296, 'DEFENDER + PURVIEW CHECK FOR', 'dg-cap');
    o += list(150, 320, ['Malicious content', 'Prompt injection', 'Sensitive data'], { tone: 'magenta', gap: 20 });
    o += text(16, 414, 'Choose before, after, or both. Do not auto-retry after a post-invocation denial: the side effect already happened.', 'dg-s');
    return o;
  },
});

export const tokenLimits = () => svgDoc('token-limits', {
  title: 'Token limits give each caller its own allowance',
  desc: 'A token limit of 1,000 tokens per minute with the Caller identity counter keeps a separate counter for each caller. App A and the batch job are under the limit, so their requests are forwarded to the model and get 200. App B exhausted its counter and gets 429 with Retry-After, without the backend being called.',
  h: 410,
  body: () => {
    let o = zone(16, 20, 210, 340, 'Callers', { ic: 'users', tone: 'azure' });
    o += zone(260, 20, 440, 340, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(276, 56, 408, 64, { t: 'Token limit · 1,000 tokens per minute', s: 'Counter dimension: Caller identity', icon: 'gauge', accent: true });
    o += zone(734, 20, 210, 340, 'Responses', { ic: 'doc', tone: 'green' });
    const rows = [['app', 'App A', 420, 'green', '200 OK', 'Forwarded to model'], ['app', 'App B', 1000, 'red', '429 Too Many', 'Retry-After: 18'], ['server', 'Batch job', 760, 'amber', '200 OK', 'Forwarded to model']];
    rows.forEach(([ic, n, used, tone, st, hdr], i) => {
      const y = 140 + i * 72;
      o += box(28, y, 186, 56, { t: n, s: i === 2 ? 'Managed identity' : 'API key', icon: ic, tone: 'azure' });
      o += arrow(`M216 ${y + 28} H272`, { tone: 'azure' });
      o += text(286, y + 22, `${n} counter`, 'dg-t', 'start', ' style="font-size:12.5px"') + text(668, y + 22, `${used.toLocaleString('en-US')} / 1,000`, 'dg-m', 'end');
      o += bar(286, y + 32, 382, used / 1000, { tone, h: 10 });
      o += arrow(`M690 ${y + 28} H742`, { tone: tone === 'red' ? 'red' : 'green' });
      o += pill(746, y + 4, st, { tone: tone === 'red' ? 'red' : 'green' });
      o += text(748, y + 46, hdr, 'dg-m');
    });
    o += text(16, 394, 'Each caller is counted separately. The backend is never called for a 429.', 'dg-s');
    return o;
  },
});
