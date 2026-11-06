// The one-time tasks of the Setup guide (labs/SETUP.md) that readers can mark done.
//
// A lab lists the tasks it needs with <!-- setup: tools sign-in extension clone -->. The site renders a checklist
// that hides the tasks the reader already marked done, and GitHub gets a generated line of links (see github.mjs).
// A step that does a task itself can carry <!-- setup-done: extension -->: marking the step
// done marks the task done too. Titles and "when you need it" text come from the task table at the top of SETUP.md.
import fs from 'node:fs';

export const SETUP_TASKS = [
  { key: 'permissions', id: 'check-your-subscription-and-permissions' },
  { key: 'tools', id: 'choose-where-to-run-commands' },
  { key: 'sign-in', id: 'sign-in-to-azure' },
  { key: 'extension', id: 'install-the-aigateway-extension' },
  { key: 'providers', id: 'register-the-resource-providers' },
  { key: 'regions', id: 'find-the-available-regions' },
  { key: 'clone', id: 'clone-the-labs-repo' },
];
// Sections that the Setup guide panel shows as reference, without a done state.
export const SETUP_REFS = [{ key: 'azd', id: 'deploy-a-lab-with-azd' }];

export const SETUP_RE = /^<!--\s*setup:\s*([\w\s-]+?)\s*-->[ \t]*$/gm;
export const SETUP_DONE_RE = /<!--\s*setup-done:\s*([\w\s-]+?)\s*-->/g;

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
export const inlineMd = (s) => esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
export const plainMd = (s) => String(s).replace(/[`*]/g, '');

// Reads the titles and the "When you need it" text of every task from the table in SETUP.md.
export function readSetupTasks(file) {
  const source = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
  const rows = new Map([...source.matchAll(/^\|\s*\[([^\]]+)\]\(#([\w-]+)\)\s*\|\s*(.+?)\s*\|\s*$/gm)]
    .map((m) => [m[2], { title: m[1], when: m[3] }]));
  const info = (t, check) => ({ ...t, check, title: rows.get(t.id)?.title || t.id, when: rows.get(t.id)?.when || '' });
  return [...SETUP_TASKS.map((t) => info(t, true)), ...SETUP_REFS.map((t) => info(t, false))];
}

// Parses the task keys of a directive, and reports the unknown ones.
export function setupKeys(list, tasks) {
  const keys = list.trim().split(/\s+/);
  const unknown = keys.filter((k) => !tasks.some((t) => t.key === k && t.check));
  return { tasks: keys.map((k) => tasks.find((t) => t.key === k && t.check)).filter(Boolean), unknown };
}
