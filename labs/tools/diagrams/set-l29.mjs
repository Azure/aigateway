// Diagrams for lab 29. Exported functions return svgDoc(...) from ./lib.mjs; npm run diagrams writes them to assets/diagrams.
import { box, zone, pill, arrow, text, label, svgDoc } from './lib.mjs';

export const modelFailover = () => svgDoc('model-failover', {
  title: 'Failover and retry across the backend models of one alias',
  desc: 'A chat app sends model: chat-failover. The alias prefers gpt-5-mini-tiny at priority 0, a deployment with a capacity of 1 that soon returns 429. A failure rule on the alias matches the 429 with the CEL condition response.status_code == 429, retries the same backend 0 times, and switches the request to the next eligible backend model, gpt-6.1-sol at priority 1, which returns 200. The rule also excludes gpt-5-mini-tiny from later requests for 30 seconds. Maximum retries per request caps the extra sends at 3, so a request makes at most four sends. Without a matching rule, the client gets the 429.',
  h: 420,
  body: () => {
    let o = zone(16, 20, 210, 360, 'Clients', { ic: 'users', tone: 'azure' });
    o += box(28, 148, 186, 72, { t: 'Chat app', s: 'sends model:', s2: 'chat-failover', icon: 'app', tone: 'azure', mono: true });
    o += text(28, 336, 'The client never retries', 'dg-s');
    o += text(28, 354, 'and never changes the model.', 'dg-s');
    o += zone(252, 20, 344, 360, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(268, 56, 312, 64, { t: 'Alias: chat-failover', s: 'Priority 0 first, then priority 1', icon: 'route', accent: true });
    o += text(272, 152, 'FAILURE RULES · FIRST MATCH WINS', 'dg-cap');
    o += box(268, 164, 312, 76, { t: 'Rule 1: throttled', s: 'Retries 0 · exclude for 30 s', s2: 'response.status_code == 429', icon: 'filter', tone: 'amber', accent: true, mono: true });
    o += box(268, 256, 312, 64, { t: 'Maximum retries per request: 3', s: 'At most four sends for one request', icon: 'gauge', tone: 'violet' });
    o += text(272, 348, 'No matching rule: the error goes to the client.', 'dg-s');
    o += zone(622, 20, 322, 360, 'Backend models', { ic: 'models', tone: 'azure' });
    o += zone(634, 52, 298, 150, 'Priority 0 · preferred', { tone: 'red' });
    o += box(646, 88, 274, 64, { t: 'gpt-5-mini-tiny', s: 'Capacity 1 · soon returns 429', icon: 'models', tone: 'red', accent: true });
    o += pill(783, 166, 'Excluded for 30 s after a 429', { tone: 'amber', anchor: 'middle' });
    o += zone(634, 218, 298, 150, 'Priority 1 · backup', { tone: 'green' });
    o += box(646, 254, 274, 64, { t: 'gpt-6.1-sol', s: 'Healthy · serves the request', icon: 'models', tone: 'green', accent: true });
    o += pill(783, 332, '200 · x-ms-served-model names it', { tone: 'green', anchor: 'middle' });
    o += arrow('M216 184 C240 184 242 88 264 88', { tone: 'azure' });
    o += arrow('M582 80 C610 80 614 112 642 112', { tone: 'red' });
    o += arrow('M582 104 C616 104 610 280 642 280', { tone: 'green' });
    o += label(610, 72, '1 · 429');
    o += label(600, 214, '2 · 200');
    o += text(16, 404, 'The rule turns a 429 from the primary into a 200 from the backup, and keeps the primary out for 30 seconds.', 'dg-s');
    return o;
  },
});
