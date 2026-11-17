// Diagrams for lab 33. Exported functions return svgDoc(...) from ./lib.mjs; npm run diagrams writes them to assets/diagrams.
import { box, zone, pill, arrow, text, label, list, svgDoc } from './lib.mjs';

export const copilotObo = () => svgDoc('copilot-obo', {
  title: 'Microsoft 365 Copilot calls MCP tools through AI Gateway as the signed-in user',
  desc: 'Copilot Cowork signs the user in through a connector and sends token 1, for AI Gateway with the Data.All scope, to the obo-demo MCP server. The gateway checks the scope and the user\'s AI Gateway Tools User role, then exchanges the token with Microsoft Entra ID on behalf of the user. It signs in as the token exchange app with its user-assigned managed identity, whose federated credential replaces a client secret, and gets token 4, for the backend app. Container Apps authentication accepts only tokens for the backend app, and the MCP server on Azure Container Apps runs the tool for the same user.',
  h: 380,
  body: () => {
    let o = zone(16, 20, 204, 270, 'Microsoft 365', { ic: 'users', tone: 'azure' });
    o += box(28, 60, 180, 64, { t: 'Copilot Cowork', s: 'signed in as you', icon: 'user', tone: 'azure' });
    o += box(28, 196, 180, 64, { t: 'Connector', s: 'OAuth 2.0 sign-in', icon: 'plug', tone: 'azure' });
    o += arrow('M118 124 V192', { tone: 'azure' });

    o += zone(236, 20, 448, 160, 'AI Gateway · obo-demo MCP server', { gw: true, ic: 'sparkle' });
    o += box(252, 60, 192, 72, { t: 'Check the caller', s: 'Data.All scope', s2: 'Tools User role', icon: 'shield', tone: 'magenta', accent: true });
    o += pill(348, 144, '401 or 403 without them', { tone: 'red', anchor: 'middle' });
    o += box(460, 60, 208, 72, { t: 'Exchange the token', s: 'on behalf of the user', s2: 'with managed identity', icon: 'key', tone: 'violet', accent: true });
    o += arrow('M444 96 H456', { tone: 'magenta' });

    o += arrow('M208 228 C230 228 230 96 248 96', { tone: 'azure' });
    o += label(238, 198, 'token 1', { anchor: 'start' });

    o += zone(724, 20, 220, 270, 'Azure Container Apps', { ic: 'cloud', tone: 'amber' });
    o += box(736, 60, 196, 64, { t: 'Authentication', s: 'backend tokens only', icon: 'lock', tone: 'amber' });
    o += pill(862, 136, 'Other tokens: 401', { tone: 'red', anchor: 'middle' });
    o += box(736, 196, 196, 72, { t: 'MCP server', s: 'whoami, echo', s2: 'get_server_time', icon: 'tools', tone: 'amber', mono: 'all' });
    o += arrow('M770 124 V192', { tone: 'amber' });

    o += arrow('M668 92 H732', { tone: 'green' });
    o += label(700, 82, 'token 4');

    o += zone(236, 212, 448, 150, 'Microsoft Entra ID', { ic: 'key', tone: 'green' });
    o += text(252, 256, 'TOKENS', 'dg-cap');
    o += list(252, 280, ['1 · for AI Gateway', '2 · federation token', '3 · identity assertion', '4 · for the backend app'], { tone: 'green', gap: 22 });
    o += box(460, 252, 208, 72, { t: 'Token exchange app', s: 'no client secret', s2: 'federated credential', icon: 'key', tone: 'green', accent: true });

    o += arrow('M520 132 V248', { tone: 'violet', dashed: true });
    o += arrow('M608 252 V136', { tone: 'green', dashed: true });
    o += label(512, 200, 'token 1 + assertion', { anchor: 'end' });
    o += label(616, 200, 'token 4', { anchor: 'start' });
    return o;
  },
});
