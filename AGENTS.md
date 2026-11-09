# AGENTS.md

Guidance for coding agents (GitHub Copilot, Claude Code, Codex, Cursor, and others) working in this repository.

## Repository map

| Path | What it is | Edit? |
|---|---|---|
| `labs/` | The Azure AI Gateway hands-on labs: one folder per lab (`NN-slug/README.md`, `infra/`, optional notebook, plus the unnumbered `quickstart/`), the site engine (`site/`, `build.mjs`), tools, shared assets, and the `azure-ai-gateway-labs` agent skill | Yes. Read [`labs/AUTHORING.md`](labs/AUTHORING.md) first |
| `labs/RELEASE-NOTES.md` | The labs release notes, one section per [product release](https://ai.gateway.azure.com/docs/) | Yes |
| `docs/` | The generated labs site, ignored by git. On `main`, `.github/workflows/labs-pages.yml` builds it from `labs/` and publishes it to GitHub Pages | Never. `npm run build` writes it |
| `skills/`, `commands/`, `.claude-plugin/`, `.cursor-plugin/`, `.github/plugin/`, `gemini-extension.json` | The coding-agent plugin: developer integration, gateway administration, capability-gated migration, and local feedback packaging | Only when asked |
| `cli/` | Installation guidance and the command reference for the published `az aigateway` CLI extension | Only when asked |
| `samples/` | The samples catalog | Only when asked |

## Labs essentials

Run these from `labs/` (Node.js 20 or later):

```bash
npm install
npm run releases   # product releases, and which ones labs/RELEASE-NOTES.md doesn't cover yet
npm run sync       # refresh the generated GitHub navigation in the READMEs and the skill catalog
npm run build      # sync, then write ../docs
npm run check      # strict build: must finish with zero warnings before you commit
npm run serve      # preview at http://localhost:4173/aigateway/
npm run deploy:swa # optional: publish to the swa-ai-gateway-labs Static Web App in rg-ai-gateway-labs
```

- Each lab's `README.md` is the single source of truth for the site, GitHub, and the agent skill. Never edit
  `docs/`, the `<!-- gh:begin -->` … `<!-- gh:end -->` regions, or lines that end with `<!-- gh -->`.
- Follow [`labs/AUTHORING.md`](labs/AUTHORING.md) for the metadata, lab anatomy, tracks, directives, writing
  style, Bicep, runtime calls, notebooks, and release notes.
- Never invent portal labels, CLI flags, JSON fields, or outputs. Verify every step on a live gateway first: the
  labs create the `Microsoft.ApiManagement/aigateways` resource type with API version `2025-09-01-preview`.
- Never print, commit, or screenshot keys, tokens, or connection strings. Delete the Azure resources you create to
  verify a change.
- Commit only the sources under `labs/`. `docs/` is ignored by git; the **Publish labs site** workflow builds it.

## Update the labs

When the user asks to **update the labs** (or to check for new AI Gateway releases, or to align the labs with the
latest release), follow these steps.

### 1. Find the new product releases

```bash
cd labs
npm run releases
```

The tool reads the changelog from <https://ai.gateway.azure.com/docs/> and marks every release that
`RELEASE-NOTES.md` doesn't cover yet with ✗. For each one it prints the changelog entry and the full release page,
including the product docs links and the URLs of the product screenshots. The docs site is a single-page app, so
fetching a docs URL directly returns no content; use the tool instead:

- `npm run releases -- --page /docs/<page>` prints any product docs page, and `-- --pages` lists them.
- `npm run releases -- --save-bundle /tmp/aigw-docs.js` saves the docs bundle. Search it for the exact portal
  labels, hints, and error messages of a feature, for example
  `grep -o '.\{100\}Supported MCP versions.\{200\}' /tmp/aigw-docs.js`.

If every release is covered, say so. Then only refresh what the user asked for, such as changed portal labels or
newer models.

### 2. Map every change to a lab

For each product change, search the labs (`grep -il "<feature>" labs/[0-9][0-9]-*/README.md labs/quickstart/README.md`) and
`labs/catalog.json`, and choose one action:

| Status | When | What to do |
|---|---|---|
| ✅ Covered | A lab already teaches it as released | Nothing, beyond checking that the labels still match |
| ✏️ Update | It extends or changes a feature that a lab teaches: a new option, a new wizard step, a renamed label | Update every affected track (portal, CLI, REST, Bicep, code, notebook), the checkpoints, the lab's section in `labs/TROUBLESHOOTING.md`, next steps, and the metadata (`duration`, `tags`, `objectives`) |
| 🆕 New lab | A new use case with its own outcome and at least 15 minutes of hands-on work | Use the next free number, follow the lab anatomy in `AUTHORING.md`, and add it to `catalog.json` (`paths`, `usecases`, `shortTitles`). Add a diagram in `labs/tools/diagrams/` and, when it helps, a widget |
| ➖ Not covered | It can't be practiced, or it's too minor for a lab | Say so in the release notes |

Show the user the mapping as a table and confirm it before you write, unless they asked you to go ahead.

### 3. Verify on a live gateway

Deploy a throwaway gateway with [lab 01's Bicep](labs/01-provision-gateway/infra/gateway.bicep), plus what the
labs need (for example a Foundry account with the lab models), or run `azd up` in the lab's folder. Then run every new or changed step: CLI and REST
calls, `az bicep build` and a real deployment of each changed template, scripts, code samples, and notebooks.
Use the real outputs and error messages in the checkpoints and in the lab's section of
[`labs/TROUBLESHOOTING.md`](labs/TROUBLESHOOTING.md). Check portal steps in the live portal at
<https://ai.gateway.azure.com> and capture new screenshots into `labs/assets/screens/`.

### 4. Write the release notes

Add a `## <Month D, YYYY>` section at the top of `labs/RELEASE-NOTES.md`, as described in
[Release notes](labs/AUTHORING.md#release-notes):

- An `### <title>` heading that matches the product changelog title.
- A one-sentence summary and a link to `https://ai.gateway.azure.com/docs/releases/<YYYY-MM-DD>`.
- The mapping table, linking to the lab sections.
- The date added to the `**Releases:**` jump line.

`npm run releases -- --check` must then exit with code 0.

### 5. Update the references

- `labs/README.md`: hand-written text that mentions the labs.
- The root `README.md`: the lab count and the use-case list.
- `labs/quickstart/`: when provisioning, the portal flow, the default model, or the runtime URL changes, update its
  portal, Azure CLI, and Bicep + azd tracks (keep them paste-ready for Cloud Shell once the **One-time setup** card
  is done), its azd template (`azure.yaml` and `infra/`, which the track runs from `labs/quickstart` in the clone of
  the repo; test it with `azd up` and `azd down --purge --force`), and the condensed output of a real CLI run that
  the home page shows (`homePage` in `labs/site/templates.mjs`).
- `labs/AUTHORING.md`: the lists of screens, diagrams, and widgets.
- `labs/skills/azure-ai-gateway-labs/SKILL.md`: the hand-written facts, when runtime behavior or lab conventions
  change. `npm run sync` regenerates its catalog.

### 6. Build, check, and ship

1. Run `npm run sync && npm run build && npm run check`, and fix every warning.
2. Preview with `npm run serve`. Check the release notes page, the **What's new** pill on the home page, and each
   changed lab in light and dark themes and at mobile width.
3. Commit `labs/` and the root `README.md` with a message that names the product release, then push. Once the
   change merges to `main`, the **Publish labs site** workflow builds the site and publishes it to GitHub Pages.
4. If the user publishes the Static Web App, run `npm run deploy:swa` and open `/release-notes/` on it.
5. Delete the verification resources (gateways, the connector gateways that the portal creates with them, and
   Foundry accounts, purging soft-deleted ones) and their deployment history.

Finish with a short report: the releases handled, the labs added or updated, and any product change that no lab
covers yet.
