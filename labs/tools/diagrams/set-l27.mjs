// Diagrams for lab 27. Exported functions return svgDoc(...) from ./lib.mjs; npm run diagrams writes them to assets/diagrams.
import { box, zone, pill, arrow, text, svgDoc } from './lib.mjs';

export const conditionalRouting = () => svgDoc('conditional-routing', {
  title: 'Backend conditions and session affinity on one alias',
  desc: 'Three clients call the alias chat: a research tool that sends the header x-workload: research, a chat app that sends a session-id header, and a batch job with no extra headers. For each request the gateway first keeps only the backend models whose when condition is true, then applies session affinity, priority, and weight, in the order that selectionOrder sets. gpt-6.1-sol has priority 0 and a condition on x-workload: research, so only research requests reach it. gpt-5-mini has priority 1 and no condition, so every other request falls through to it. With session affinity, requests with the same session key go to the same backend model, and weights are skipped.',
  h: 420,
  body: () => {
    let o = zone(16, 20, 240, 360, 'Clients', { ic: 'users', tone: 'azure' });
    o += box(28, 60, 216, 64, { t: 'Research tool', s: 'model: chat', s2: 'x-workload: research', icon: 'agent', tone: 'azure', mono: 'all' });
    o += box(28, 148, 216, 64, { t: 'Chat app', s: 'model: chat', s2: 'session-id: alpha', icon: 'app', tone: 'azure', mono: 'all' });
    o += box(28, 236, 216, 64, { t: 'Batch job', s: 'model: chat', s2: 'no extra headers', icon: 'terminal', tone: 'azure', mono: 'all' });
    o += text(28, 336, 'Clients always send model: chat.', 'dg-s');
    o += text(28, 354, 'Headers and keys steer the request.', 'dg-s');
    o += zone(284, 20, 372, 360, 'AI Gateway · alias chat', { gw: true, ic: 'sparkle' });
    o += box(300, 56, 340, 56, { t: '1 · Conditions', s: 'Keep the backend models whose when', s2: 'expression is true for this request', icon: 'filter', tone: 'cyan', accent: true });
    o += box(300, 128, 340, 56, { t: '2 · Session affinity', s: 'The same session key goes to', s2: 'the same backend model', icon: 'key', tone: 'magenta', accent: true });
    o += box(300, 200, 340, 56, { t: '3 · Priority', s: 'The lowest priority number wins', icon: 'layers', tone: 'violet', accent: true });
    o += box(300, 272, 340, 56, { t: '4 · Weight', s: 'Splits traffic within a priority,', s2: 'unless affinity already chose', icon: 'gauge', tone: 'violet', accent: true });
    o += arrow('M470 112 V124', { tone: 'cyan', flow: false });
    o += arrow('M470 184 V196', { tone: 'magenta', flow: false });
    o += arrow('M470 256 V268', { tone: 'violet', flow: false });
    o += pill(470, 344, 'selectionOrder sets whether 2 or 3 runs first', { tone: 'magenta', anchor: 'middle' });
    o += zone(692, 20, 252, 360, 'Backend models', { ic: 'models', tone: 'azure' });
    o += box(704, 92, 228, 76, { t: 'gpt-6.1-sol', s: 'Priority 0 · condition', s2: 'x-workload: research', icon: 'models', tone: 'magenta', accent: true, mono: true });
    o += box(704, 232, 228, 76, { t: 'gpt-5-mini', s: 'Priority 1', s2: 'Always included', icon: 'models', tone: 'violet', accent: true });
    o += text(708, 336, 'Research requests reach gpt-6.1-sol.', 'dg-s');
    o += text(708, 354, 'All other requests fall through.', 'dg-s');
    o += arrow('M246 92 C272 92 274 78 296 78', { tone: 'azure' });
    o += arrow('M246 180 C276 180 270 86 296 86', { tone: 'azure' });
    o += arrow('M246 268 C280 268 268 94 296 94', { tone: 'azure' });
    o += arrow('M642 292 C676 292 672 130 700 130', { tone: 'magenta' });
    o += arrow('M642 308 C676 308 672 270 700 270', { tone: 'violet' });
    o += text(16, 406, 'Conditions decide which backend models may serve a request. Affinity, priority, and weight then pick one of them.', 'dg-s');
    return o;
  },
});
