// Diagrams for lab 32. Exported functions return svgDoc(...) from ./lib.mjs; npm run diagrams writes them to assets/diagrams.
import { box, zone, pill, pillW, pills, arrow, text, svgDoc } from './lib.mjs';

export const foundryConnection = () => svgDoc('foundry-connection', {
  title: 'A Microsoft Foundry project calls gateway models through a gateway connection',
  desc: 'The app team\'s Foundry project has a gateway connection and no model deployments. The playground, a prompt agent, and code call the model by its Foundry name, gateway/alias. Foundry calls the gateway with the project\'s managed identity. The gateway checks the AI Gateway Models User role on its default workspace, applies the token limit per identity, and routes the alias to the backend model in the platform team\'s Foundry resource. When the limit is reached, Foundry returns rate_limit_exceeded with the gateway\'s message inside.',
  h: 432,
  body: () => {
    let o = zone(16, 20, 470, 296, 'App team\'s Foundry project', { ic: 'cloud', tone: 'cyan' });
    o += box(28, 56, 200, 64, { t: 'Playground', s: 'Chat with the model', icon: 'app', tone: 'cyan' });
    o += box(28, 140, 200, 64, { t: 'Prompt agent', s: 'Foundry Agent Service', icon: 'agent', tone: 'cyan' });
    o += box(28, 224, 200, 64, { t: 'Your code', s: 'OpenAI SDK, Responses', icon: 'code', tone: 'cyan' });
    o += box(254, 118, 222, 104, { t: 'Gateway connection', s: 'Project managed identity', s2: 'No deployments, no keys', icon: 'plug', tone: 'amber', accent: true });
    o += arrow('M228 88 C244 88 238 146 250 146', { tone: 'cyan' });
    o += arrow('M228 172 H250', { tone: 'cyan' });
    o += arrow('M228 256 C244 256 238 198 250 198', { tone: 'cyan' });

    o += zone(510, 20, 262, 296, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(522, 56, 238, 72, { t: 'Check the identity', s: 'Entra token, not a key', s2: 'AI Gateway Models User role', icon: 'key', accent: true });
    o += box(522, 148, 238, 72, { t: 'Alias gpt-5-mini', s: 'Token limit per identity', s2: '429 with Retry-After', icon: 'gauge', tone: 'magenta', accent: true });
    o += pills(522, 244, ['Usage', 'Logs', 'Budgets'], { tone: 'green', maxW: 238 });
    o += arrow('M478 158 C500 158 496 92 518 92', { tone: 'amber' });
    o += arrow('M641 128 V144', { tone: 'violet', flow: false });
    o += arrow('M520 196 C500 196 500 190 480 190', { tone: 'red', dashed: true });

    o += zone(792, 20, 152, 296, 'Backend', { ic: 'models', tone: 'azure' });
    o += box(802, 148, 132, 72, { t: 'Foundry', s: 'gpt-5-mini', icon: 'models', tone: 'azure' });
    o += arrow('M762 184 H798', { tone: 'azure' });

    o += text(32, 348, 'WHAT EACH SIDE SEES', 'dg-cap');
    let x = 32;
    [['model: aigw/gpt-5-mini', 'cyan', true, 'Foundry name: connection/alias'], ['AI Gateway Models User', 'violet', false, 'on the default workspace'], ['rate_limit_exceeded', 'red', true, 'gateway message inside']].forEach(([l, tone, mono, note]) => {
      const w = Math.max(pillW(l, mono), 220);
      o += pill(x, 360, l, { tone, w, mono });
      o += text(x + w / 2, 400, note, 'dg-s', 'middle');
      x += w + 64;
    });
    o += text(16, 424, 'The project borrows the gateway\'s models: the platform team keeps the deployments, the keys, and the limits.', 'dg-s');
    return o;
  },
});
