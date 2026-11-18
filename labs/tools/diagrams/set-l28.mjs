// Diagrams for lab 28. Exported functions return svgDoc(...) from ./lib.mjs; npm run diagrams writes them to assets/diagrams.
import { box, zone, pill, arrow, text, svgDoc } from './lib.mjs';

export const autoModelSelection = () => svgDoc('auto-model-selection', {
  title: 'Auto model selection on one alias',
  desc: 'Three clients call the alias auto: one sends a simple prompt, one sends a hard prompt, and one adds an auto_model_selection override that asks for the quality objective. For each request the gateway follows selectionOrder: priority first, so only the backend models with the lowest priority number stay in the pool, then auto model selection. It takes the alias objective, Balanced, Cost, or Quality, or the caller\'s objective when the alias allows that override, and Model Router scores the prompt for each model in the pool by its selectorModelName. The gateway calls the model it picks and names it in the x-ms-served-model response header. gpt-5-mini is the lower-cost model, and gpt-5.5 is the higher-quality model.',
  h: 420,
  body: () => {
    let o = zone(16, 20, 240, 360, 'Clients', { ic: 'users', tone: 'azure' });
    o += box(28, 60, 216, 64, { t: 'Simple prompt', s: 'Is 17 a prime number?', s2: 'model: auto', icon: 'app', tone: 'azure', mono: true });
    o += box(28, 148, 216, 64, { t: 'Hard prompt', s: 'Prove √2 is irrational', s2: 'model: auto', icon: 'agent', tone: 'azure', mono: true });
    o += box(28, 236, 216, 64, { t: 'Caller override', s: 'auto_model_selection', s2: 'objective: quality', icon: 'terminal', tone: 'azure', mono: 'all' });
    o += text(28, 336, 'Clients always send model: auto.', 'dg-s');
    o += text(28, 354, 'The gateway picks the model.', 'dg-s');
    o += zone(284, 20, 372, 360, 'AI Gateway · alias auto', { gw: true, ic: 'sparkle' });
    o += box(300, 56, 340, 56, { t: '1 · Priority', s: 'Only the backend models with the', s2: 'lowest priority number stay', icon: 'layers', tone: 'violet', accent: true });
    o += box(300, 128, 340, 56, { t: '2 · Objective', s: 'Balanced, Cost, or Quality from the', s2: 'alias, or the caller if it\'s allowed', icon: 'gauge', tone: 'cyan', accent: true });
    o += box(300, 200, 340, 56, { t: '3 · Model Router', s: 'Scores the prompt for each model', s2: 'by its selectorModelName', icon: 'sparkle', tone: 'magenta', accent: true });
    o += box(300, 272, 340, 56, { t: '4 · Call the model', s: 'The response names it in', s2: 'x-ms-served-model', icon: 'route', tone: 'violet', accent: true, mono: true });
    o += arrow('M470 112 V124', { tone: 'violet', flow: false });
    o += arrow('M470 184 V196', { tone: 'cyan', flow: false });
    o += arrow('M470 256 V268', { tone: 'magenta', flow: false });
    o += pill(470, 344, 'selectionOrder: priority, then autoModelSelection', { tone: 'magenta', anchor: 'middle' });
    o += zone(692, 20, 252, 360, 'Backend models', { ic: 'models', tone: 'azure' });
    o += box(704, 92, 228, 76, { t: 'gpt-5-mini', s: 'Lower cost, faster', s2: 'selector: gpt-5-mini', icon: 'models', tone: 'violet', accent: true, mono: true });
    o += box(704, 232, 228, 76, { t: 'gpt-5.5', s: 'Higher quality and cost', s2: 'selector: gpt-5.5', icon: 'models', tone: 'magenta', accent: true, mono: true });
    o += text(708, 336, 'Cost leans to gpt-5-mini.', 'dg-s');
    o += text(708, 354, 'Quality leans to gpt-5.5.', 'dg-s');
    o += arrow('M246 92 C272 92 274 78 296 78', { tone: 'azure' });
    o += arrow('M246 180 C276 180 270 86 296 86', { tone: 'azure' });
    o += arrow('M246 268 C280 268 268 94 296 94', { tone: 'azure' });
    o += arrow('M642 292 C676 292 672 130 700 130', { tone: 'violet' });
    o += arrow('M642 308 C676 308 672 270 700 270', { tone: 'magenta' });
    o += text(16, 406, 'Priority picks the tier. Model Router picks one model in it for each prompt, as the objective asks.', 'dg-s');
    return o;
  },
});
