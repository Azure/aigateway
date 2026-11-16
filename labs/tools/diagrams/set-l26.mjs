// Diagrams for lab 26. Exported functions return svgDoc(...) from ./lib.mjs; npm run diagrams writes them to assets/diagrams.
import { box, zone, pill, pillW, pills, arrow, list, text, svgDoc } from './lib.mjs';

export const embeddings = () => svgDoc('embeddings', {
  title: 'Embedding models through Azure AI Gateway',
  desc: 'An ingestion job and a RAG app call the same gateway URL with the same API key or Entra token. The gateway authenticates the caller and resolves the alias in the model field: text-embedding-3-small accepts only the embeddings endpoint, and gpt-5-mini accepts Chat Completions and Responses. It applies the alias and model policies, such as a token limit of 2,000 tokens per minute per caller on the embedding model, records usage, and forwards the request through the Foundry provider to one of two deployments: text-embedding-3-small, which returns vectors of 1,536 numbers, or gpt-5-mini. The mini RAG app embeds the articles, embeds the question, ranks the articles by cosine similarity in the app, and asks gpt-5-mini to answer from the best match.',
  h: 450,
  body: () => {
    let o = zone(16, 20, 210, 300, 'Callers', { ic: 'users', tone: 'azure' });
    o += box(28, 62, 186, 64, { t: 'Ingestion job', s: 'Embeds articles', s2: 'in batches', icon: 'doc', tone: 'azure' });
    o += box(28, 150, 186, 64, { t: 'RAG app', s: 'Embeds questions', s2: 'and answers them', icon: 'app', tone: 'azure' });
    o += list(30, 250, ['One gateway URL', 'One key for both models', 'OpenAI SDK or curl'], { tone: 'azure' });
    o += zone(262, 20, 400, 300, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(278, 54, 368, 62, { t: 'Authenticate the caller', s: 'API key or Microsoft Entra token', s2: 'POST …/models/openai/v1/embeddings', icon: 'key', accent: true, mono: true });
    o += box(278, 126, 368, 62, { t: 'Resolve the alias', s: 'text-embedding-3-small → /openai/v1/embeddings', s2: 'gpt-5-mini → /openai/v1/chat/completions', icon: 'route', tone: 'violet', accent: true });
    o += box(278, 198, 368, 62, { t: 'Apply the policies', s: 'Token limit: 2,000 tokens per minute per caller', s2: 'Usage and telemetry for every request', icon: 'gauge', tone: 'magenta', accent: true });
    o += pills(278, 280, ['Provider foundry-models', '429 with Retry-After'], { tone: 'green' });
    o += zone(698, 20, 246, 300, 'Microsoft Foundry', { ic: 'cloud', tone: 'amber' });
    o += list(712, 70, ['Two deployments, one account', 'Gateway uses managed identity'], { tone: 'amber' });
    o += box(710, 126, 222, 62, { t: 'Embedding model', s: 'Vectors of 1,536 numbers', s2: 'text-embedding-3-small', icon: 'models', tone: 'amber', mono: true });
    o += box(710, 198, 222, 62, { t: 'Chat model', s: 'Answers from the articles', s2: 'gpt-5-mini', icon: 'models', tone: 'amber', mono: true });
    o += arrow('M216 94 C244 94 246 80 274 80', { tone: 'azure' });
    o += arrow('M216 182 C248 182 244 92 274 92', { tone: 'azure' });
    o += arrow('M462 116 V124', { tone: 'violet', flow: false });
    o += arrow('M462 188 V196', { tone: 'violet', flow: false });
    o += arrow('M648 220 C676 220 680 157 706 157', { tone: 'amber' });
    o += arrow('M648 238 C672 238 682 229 706 229', { tone: 'amber' });
    o += text(32, 352, 'MINI RAG: THE SAME GATEWAY URL AND KEY FOR EVERY STEP', 'dg-cap');
    let x = 32;
    const steps = [
      ['1 · Embed the articles', 'azure', '8 articles, 216 tokens'],
      ['2 · Embed the question', 'azure', 'One vector, 1,536 numbers'],
      ['3 · Rank by cosine similarity', 'violet', 'In the app: best match 0.70'],
      ['4 · Answer with gpt-5-mini', 'green', 'Cites [laptop-repair]'],
    ];
    steps.forEach(([l, tone, note], i) => {
      const w = Math.max(pillW(l), 176);
      o += pill(x, 364, l, { tone, w });
      o += text(x + w / 2, 404, note, 'dg-s', 'middle');
      if (i < steps.length - 1) o += arrow(`M${x + w + 6} 375 H${x + w + 34}`, { tone: 'violet', flow: false });
      x += w + 40;
    });
    o += text(32, 436, 'The app ranks the vectors itself. The gateway sees embeddings calls and one chat call, and counts the tokens of each.', 'dg-s');
    return o;
  },
});
