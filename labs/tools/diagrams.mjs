// Generates the themable SVG diagrams in labs/assets/diagrams. Run: npm run diagrams
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { warnings } from './diagrams/lib.mjs';
import * as setA from './diagrams/set-a.mjs';
import * as setB from './diagrams/set-b.mjs';
import * as setC from './diagrams/set-c.mjs';

const out = join(dirname(fileURLToPath(import.meta.url)), '..', 'assets', 'diagrams');
await mkdir(out, { recursive: true });
const all = { ...setA, ...setB, ...setC };
for (const make of Object.values(all)) {
  const svg = make();
  const file = svg.match(/data-name="([\w-]+)"/)[1];
  await writeFile(join(out, `${file}.svg`), svg);
  console.log(`  ✓ ${file}.svg  ${(svg.length / 1024).toFixed(1)} KB`);
}
if (warnings.length) {
  console.log(`\n${warnings.length} possible text overflow(s):`);
  for (const w of warnings) console.log(`  ! ${w}`);
}
