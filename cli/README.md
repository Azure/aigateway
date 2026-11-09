# Azure AI Gateway CLI: external dependency

The CLI is published and maintained through **[Azure/aigateway](https://github.com/Azure/aigateway)**.
The plugin uses the released CLI as a dependency; it does not maintain a local
implementation, installer, or copied quickstart.

- [Hosted installation guide and CLI quickstart](https://ai.gateway-df.azure.com/docs/quickstarts/cli)
- [Current command reference](https://github.com/Azure/aigateway/blob/main/cli/command-reference.md)
- [Published CLI releases and verified wheel assets](https://github.com/Azure/aigateway/releases)

For requested setup/upgrade, resolve the newest published `cli-v...` release,
including public previews. GitHub's
`releases/latest` API omits previews; inspect the releases list instead. Install
the exact official wheel only after verifying its published SHA-256 and obtaining
approval for the tool change. Do not silently substitute an older release.

Ordinary management tasks reuse `az aigateway version` for the working context
and inspect only the needed command's `--help`; no recurring release lookup is
required. A complete runtime-only integration needs neither CLI nor management
sign-in. Check the selected gateway's published runtime header/model contract,
not CLI version alone. Do not use
legacy `az ai-gateway` checkouts, local source builds, repacked wheels, or patched
installed modules as the CLI authority. Missing features must be resolved through
the upstream product or reported as unsupported, not invented locally.

The migration helper verifies release freshness, released-wheel provenance,
installed code, and reviewed new-RP command support. If a newer release is not
yet reviewed, update the capability profile and obtain fresh plan approvals;
do not continue with a stale CLI or auto-upgrade during an approved mutation.
