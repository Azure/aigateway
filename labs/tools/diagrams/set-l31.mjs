// Diagrams for lab 31. Exported functions return svgDoc(...) from ./lib.mjs; npm run diagrams writes them to assets/diagrams.
import { box, zone, pill, pillW, pills, arrow, list, text, svgDoc } from './lib.mjs';

export const jevDecisions = () => svgDoc('jev-decisions', {
  title: 'Jev decision models through Azure AI Gateway',
  desc: 'An app or the TypeSafe SDK sends a System One request to the gateway with a gateway API key or an Entra token and the alias ticket-triage as the model. The gateway authenticates the caller, applies the alias policies such as a request rate limit or a token limit, and forwards the request through the Custom provider typesafe, which adds the TypeSafe key in one Authorization header. The Jev model reads the state and returns a typed answer for every question: a probability for a noul, a choice with its confidence and probabilities, and a score on a scale. The gateway records the usage for limits and telemetry.',
  h: 450,
  body: () => {
    let o = zone(16, 20, 210, 300, 'Callers', { ic: 'users', tone: 'azure' });
    o += box(28, 62, 186, 64, { t: 'Triage app', s: 'curl or requests', icon: 'app', tone: 'azure' });
    o += box(28, 150, 186, 64, { t: 'TypeSafe SDK', s: 'compression off', icon: 'code', tone: 'azure' });
    o += list(30, 250, ['Gateway key or Entra token', 'model: ticket-triage', 'No TypeSafe key in the app'], { tone: 'azure' });
    o += zone(262, 20, 400, 300, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(278, 54, 368, 62, { t: 'Authenticate the caller', s: 'API key or Microsoft Entra token', s2: 'POST …/models/typesafe/v1/systemone', icon: 'key', accent: true, mono: true });
    o += box(278, 126, 368, 62, { t: 'Alias ticket-triage', s: 'Request rate limit: 5 per minute per caller', s2: 'Token limits count decision tokens too', icon: 'gauge', tone: 'magenta', accent: true });
    o += box(278, 198, 368, 62, { t: 'Custom provider typesafe', s: 'Adds Authorization: Bearer <TypeSafe key>', s2: 'Model jev-latest, typesafe/v1/systemone', icon: 'plug', tone: 'violet' });
    o += pills(278, 280, ['Usage', 'Telemetry', '429 with Retry-After'], { tone: 'green' });
    o += zone(698, 20, 246, 300, 'TypeSafe', { ic: 'cloud', tone: 'amber' });
    o += box(710, 118, 222, 76, { t: 'Jev decision model', s: 'Model jev-latest', s2: 'api.typesafe.ai', icon: 'models', tone: 'amber', mono: true });
    o += list(712, 232, ['Reads the state', 'Answers typed questions', 'Returns probabilities'], { tone: 'amber' });
    o += arrow('M216 94 C244 94 246 84 274 84', { tone: 'azure' });
    o += arrow('M216 182 C248 182 244 96 274 96', { tone: 'azure' });
    o += arrow('M462 116 V124', { tone: 'violet', flow: false });
    o += arrow('M462 188 V196', { tone: 'violet', flow: false });
    o += arrow('M648 220 C676 220 680 146 706 146', { tone: 'amber' });
    o += arrow('M708 172 C680 172 678 244 650 244', { tone: 'green' });
    o += text(32, 352, 'ONE REQUEST: THE TICKET AS STATE, THREE TYPED QUESTIONS', 'dg-cap');
    let x = 32;
    [['state: ticket', 'azure', 'subject, message, plan'], ['urgent · noul', 'violet', 'probability of yes: 0.93'], ['team · choice', 'violet', 'billing, confidence 1.00'], ['frustration · score', 'violet', '1 on a 0–2 scale']].forEach(([l, tone, note]) => {
      const w = Math.max(pillW(l, true), 176);
      o += pill(x, 364, l, { tone, w, mono: true });
      o += text(x + w / 2, 404, note, 'dg-s', 'middle');
      x += w + 46;
    });
    o += text(32, 436, 'Typed answers with probabilities, in about half a second: no prompt parsing, no free-form text to validate.', 'dg-s');
    return o;
  },
});
