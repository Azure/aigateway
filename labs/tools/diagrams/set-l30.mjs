// Diagrams for lab 30. Exported functions return svgDoc(...) from ./lib.mjs; npm run diagrams writes them to assets/diagrams.
import { box, zone, pill, arrow, text, label, list, svgDoc } from './lib.mjs';

export const agentHooks = () => svgDoc('agent-hooks', {
  title: 'Agent hooks ask a decision service before and after each tool call',
  desc: 'An agent sends tools/call to the learn MCP server on AI Gateway. The agent hooks policy sends the tool name and arguments to a decision service before the call, and the tool result after it. The decision service is an Azure function behind App Service Authentication that accepts only the gateway\'s managed identity. It returns allow or deny. A deny before the call means the tool never runs. A deny after the call withholds the result, but the tool already ran. The caller gets HTTP 200 with isError: true, and with failClosed a hook that fails also blocks the call.',
  h: 476,
  body: () => {
    let o = zone(16, 20, 164, 290, 'MCP client', { ic: 'users', tone: 'azure' });
    o += box(26, 128, 146, 64, { t: 'Agent', s: 'calls a tool', icon: 'agent', tone: 'azure' });

    o += zone(204, 20, 456, 290, 'AI Gateway · learn MCP server', { gw: true, ic: 'sparkle' });
    o += box(220, 56, 214, 64, { t: 'Before tool call', s: 'pre_tool_call', icon: 'eye', tone: 'magenta', accent: true, mono: true });
    o += pill(360, 128, 'Deny: the tool never runs', { tone: 'red', anchor: 'middle' });
    o += box(430, 196, 214, 64, { t: 'After tool call', s: 'post_tool_call', icon: 'eye', tone: 'amber', accent: true, mono: true });
    o += pill(500, 268, 'Deny: result withheld', { tone: 'amber', anchor: 'middle' });

    o += zone(684, 20, 260, 290, 'Remote MCP server', { ic: 'globe', tone: 'amber' });
    o += box(696, 128, 236, 64, { t: 'Microsoft Learn', s: 'docs search, fetch, samples', icon: 'tools', tone: 'amber' });

    o += arrow('M170 150 C196 150 196 88 216 88', { tone: 'azure' });
    o += arrow('M436 88 C600 88 640 150 692 150', { tone: 'green' });
    o += arrow('M694 172 C672 172 672 228 648 228', { tone: 'amber' });
    o += arrow('M428 228 C300 228 200 174 172 174', { tone: 'azure' });

    o += zone(204, 334, 740, 108, '', { tone: 'green' });
    o += box(220, 352, 420, 72, { t: 'Decision service · Azure Functions', s: 'POST /api/tool-hook · returns allow or deny', s2: 'Easy Auth accepts only the gateway identity', icon: 'bolt', tone: 'green', accent: true });
    o += text(668, 360, 'RULES IN THIS LAB', 'dg-cap');
    o += list(668, 384, ['Blocked tool name: deny', 'Email address in the arguments: deny', 'Secret in the tool result: deny'], { tone: 'green', gap: 20 });

    o += arrow('M250 120 V348', { tone: 'magenta', dashed: true });
    o += arrow('M600 260 V348', { tone: 'amber', dashed: true });
    o += label(250, 326, 'tool name + arguments');
    o += label(600, 326, 'tool result');

    o += text(16, 466, 'A deny reaches the caller as HTTP 200 with isError: true. With failClosed, a hook that fails also blocks the call.', 'dg-s');
    return o;
  },
});
