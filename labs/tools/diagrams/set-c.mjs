import { box, zone, pills, pill, arrow, text, svgDoc } from './lib.mjs';

export const enterpriseReference = () => svgDoc('enterprise-reference', {
  title: 'Enterprise reference deployment for Azure AI Gateway',
  desc: 'GitHub Actions signs in with OpenID Connect, previews main.bicep with what-if, deploys dev and then prod, applies gateway-wide baselines, and runs a smoke test. One subscription-scope template creates two resource groups. The gateway group holds the AI Gateway with the chat alias, a Foundry model provider that uses the managed identity, the learn MCP server, per-app API keys, and Application Insights with Log Analytics. The Foundry group holds a Foundry account with key authentication disabled and the gpt-5-mini deployment. The gateway identity has the Foundry User role.',
  h: 468,
  body: () => {
    let o = zone(16, 16, 928, 104, 'Delivery · GitHub Actions with OpenID Connect', { ic: 'terminal', tone: 'cyan' });
    const steps = [
      ['Sign in with OIDC', 'Federated credential', 'lock'],
      ['Preview', 'what-if on main.bicep', 'eye'],
      ['Deploy', 'dev, then prod', 'layers'],
      ['Baseline + test', 'Merge, then verify', 'check'],
    ];
    steps.forEach(([t, s, ic], i) => {
      const x = 32 + i * 231;
      o += box(x, 44, 203, 60, { t, s, icon: ic, tone: 'cyan', accent: i === 2 });
    });
    o += zone(16, 146, 640, 288, '…-gateway resource group', { ic: 'grid', tone: 'azure' });
    o += zone(672, 146, 272, 288, 'Foundry resource group', { ic: 'grid', tone: 'violet' });
    o += box(32, 216, 164, 60, { t: 'App Insights', s: 'Dashboards', icon: 'chart', tone: 'green', accent: true });
    o += box(32, 286, 164, 60, { t: 'Workspace', s: 'Log Analytics', icon: 'doc', tone: 'green' });
    o += pill(32, 386, 'Connect in portal', { tone: 'green' });
    o += zone(228, 182, 412, 236, 'AI Gateway · aigateways', { gw: true, ic: 'sparkle' });
    o += box(240, 216, 190, 60, { t: 'Alias: chat', s: 'Token limit, safety', icon: 'route', tone: 'violet', accent: true });
    o += box(438, 216, 190, 60, { t: 'Model provider', s: 'Managed identity', icon: 'models', tone: 'violet' });
    o += box(240, 286, 190, 60, { t: 'MCP: learn', s: 'Learn docs tools', icon: 'tools', tone: 'amber' });
    o += box(438, 286, 190, 60, { t: 'API keys', s: 'web-chat, batch-jobs', icon: 'key', tone: 'amber' });
    o += text(244, 376, 'GATEWAY SCOPE BASELINE (SCRIPT)', 'dg-cap');
    o += pills(240, 386, ['Request rate limit', 'Cost limit'], { tone: 'magenta' });
    o += box(688, 216, 240, 60, { t: 'Foundry account', s: 'Key auth disabled', icon: 'cloud', tone: 'violet', accent: true });
    o += box(688, 286, 240, 60, { t: 'gpt-5-mini', s: 'Model deployment', icon: 'models', tone: 'violet' });
    o += text(692, 376, 'GATEWAY IDENTITY HAS', 'dg-cap');
    o += pill(688, 386, 'Foundry User role', { tone: 'violet' });
    // Arrows last so they sit above zones.
    [235, 466, 697].forEach((x) => { o += arrow(`M${x} 74 H${x + 24}`, { tone: 'cyan' }); });
    o += arrow('M560 104 V144', { tone: 'cyan' });
    o += arrow('M640 104 C640 126 808 122 808 144', { tone: 'cyan' });
    o += arrow('M228 246 H200', { tone: 'green' });
    o += arrow('M628 246 H686', { tone: 'violet' });
    o += text(16, 458, 'One subscription-scope main.bicep composes the modules. No module outputs a secret.', 'dg-s');
    return o;
  },
});

export const githubCopilotByok = () => svgDoc('github-copilot-byok', {
  title: 'GitHub Copilot with models and tools from Azure AI Gateway',
  desc: 'The GitHub Copilot app, Copilot CLI, Copilot SDK, and Copilot in VS Code each add the gateway as a bring-your-own-key model provider and the gateway learn MCP server as a tool server. They call the gpt-6.1-sol alias on the gateway OpenAI v1 endpoint with the Responses API, and the learn MCP endpoint, both with the github-copilot API key: as a bearer token for models and in the api-key header for MCP. The gateway applies a per-caller token limit, records usage for Monitoring, calls the gpt-6.1-sol deployment in Microsoft Foundry with its managed identity, and calls the public Microsoft Learn MCP server.',
  h: 486,
  body: () => {
    let o = zone(16, 20, 276, 372, 'GitHub Copilot', { ic: 'sparkle', tone: 'azure' });
    const clients = [
      ['Copilot app', 'Model provider · MCP', 'app'],
      ['Copilot CLI', 'Env variables · mcp add', 'terminal'],
      ['Copilot SDK', 'provider · mcpServers', 'doc'],
      ['VS Code', 'Custom Endpoint · mcp.json', 'layers'],
    ];
    clients.forEach(([t, s, ic], i) => {
      const y = 52 + i * 82;
      o += box(28, y, 252, 64, { t, s, icon: ic, tone: 'azure', accent: i === 1 });
    });
    o += zone(330, 20, 330, 372, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(346, 52, 298, 80, { t: 'Alias: gpt-6.1-sol', s: 'OpenAI v1 · Responses API', s2: '/default/models/openai/v1', icon: 'route', accent: true, mono: true });
    o += box(346, 146, 298, 80, { t: 'MCP server: learn', s: '3 Microsoft Learn tools', s2: '/default/toolservers/learn/mcp', icon: 'tools', tone: 'green', accent: true, mono: true });
    o += box(346, 240, 298, 64, { t: 'API key: github-copilot', s: 'One key for models and tools', icon: 'key', tone: 'amber' });
    o += text(350, 326, 'APPLIED ON EVERY CALL', 'dg-cap');
    o += pills(346, 336, ['Token limit per caller', 'Usage by key', 'Monitoring'], { tone: 'magenta', maxW: 298 });
    o += zone(698, 20, 246, 184, 'Microsoft Foundry', { ic: 'cloud', tone: 'cyan' });
    o += box(712, 52, 218, 80, { t: 'gpt-6.1-sol', s: 'Model deployment', s2: 'GlobalStandard', icon: 'models', tone: 'cyan', accent: true });
    o += text(716, 160, 'GATEWAY SIGNS IN WITH', 'dg-cap');
    o += pill(712, 170, 'Managed identity', { tone: 'cyan' });
    o += zone(698, 220, 246, 172, 'Microsoft Learn', { ic: 'doc', tone: 'green' });
    o += box(712, 252, 218, 80, { t: 'Learn MCP server', s: 'Public documentation', s2: 'learn.microsoft.com', icon: 'tools', tone: 'green', mono: true });
    o += text(716, 356, 'BACKEND AUTHENTICATION', 'dg-cap');
    o += pill(712, 364, 'None', { tone: 'green' });
    clients.forEach((_, i) => {
      const c = 84 + i * 82;
      o += arrow(`M282 ${c} C312 ${c} 312 92 342 92`, { tone: 'azure' });
      o += arrow(`M282 ${c} C312 ${c} 312 186 342 186`, { tone: 'green', flow: false, dashed: true });
    });
    o += arrow('M646 92 H708', { tone: 'violet' });
    o += arrow('M646 186 C678 186 678 292 708 292', { tone: 'green' });
    o += text(16, 424, 'Models', 'dg-s') + text(84, 424, 'https://<gateway-host>/default/models/openai/v1', 'dg-m') + text(500, 424, 'Key as', 'dg-s') + text(552, 424, 'Authorization: Bearer', 'dg-m');
    o += text(16, 446, 'Tools', 'dg-s') + text(84, 446, 'https://<gateway-host>/default/toolservers/learn/mcp', 'dg-m') + text(500, 446, 'Key as', 'dg-s') + text(552, 446, 'api-key header', 'dg-m');
    o += text(16, 468, 'Model', 'dg-s') + text(84, 468, 'gpt-6.1-sol', 'dg-m') + text(190, 468, 'Wire API', 'dg-s') + text(250, 468, 'responses', 'dg-m') + text(340, 468, 'Key', 'dg-s') + text(372, 468, 'github-copilot', 'dg-m');
    return o;
  },
});

export const copilotAppProvider = () => svgDoc('copilot-app-provider', {
  title: 'Add AI Gateway as a model provider in the GitHub Copilot app',
  desc: 'An illustration, not a screenshot. Open app settings and select Model providers, then Add provider. Choose Any OpenAI-compatible HTTP endpoint, enter a display name, the gateway base URL ending in /default/models/openai/v1, and the github-copilot API key. Choose the Responses wire API if the form offers it, add gpt-6.1-sol as a model by hand because the gateway does not list models, then pick gpt-6.1-sol in the model picker.',
  h: 470,
  body: () => {
    let o = zone(16, 16, 928, 108, 'In the GitHub Copilot app', { ic: 'app', tone: 'azure' });
    const steps = [
      ['App settings', 'Model providers', 'grid', false],
      ['Add provider', 'OpenAI-compatible', 'plug', false],
      ['Provider details', 'Base URL and API key', 'key', true],
      ['Pick the model', 'gpt-6.1-sol', 'check', false],
    ];
    steps.forEach(([t, s, ic, accent], i) => {
      o += box(32 + i * 231, 46, 203, 62, { t, s, icon: ic, tone: 'azure', accent, mono: i === 3 });
    });
    [235, 466, 697].forEach((x) => { o += arrow(`M${x} 77 H${x + 24}`, { tone: 'azure' }); });
    o += zone(16, 146, 928, 284, 'Provider details · illustration, not a screenshot', { gw: true, ic: 'doc' });
    const rows = [
      ['Provider', 'Any OpenAI-compatible HTTP endpoint', false],
      ['Display name', 'AI Gateway', false],
      ['Base URL', 'https://<gateway-host>/default/models/openai/v1', true],
      ['API key', '••••••••••••••••  the github-copilot key, kept in the system credential store', false],
      ['Wire API', 'Responses, if the form offers it', false],
      ['Model', 'gpt-6.1-sol, added by hand: the gateway has no /models list', false],
    ];
    rows.forEach(([lbl, val, mono], i) => {
      const y = 196 + i * 38;
      o += text(40, y, lbl, 'dg-t', 'start', ' style="font-size:13px"');
      o += `<rect class="dg-bar" x="176" y="${y - 19}" width="744" height="28" rx="6"/>`;
      o += text(188, y, val, mono ? 'dg-m' : 'dg-s', 'start', mono ? '' : ' style="fill:var(--dg-text)"');
    });
    o += text(16, 458, 'Field names vary by app version. The app stores the key in the system credential store and never shows it again.', 'dg-s');
    return o;
  },
});
