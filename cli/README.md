# Azure AI Gateway CLI: external dependency

The CLI is published and maintained through **[Azure/aigateway](https://github.com/Azure/aigateway)**.
This skill repository does not maintain a CLI implementation, local installer,
or copied quickstart.

- [Current installation guide and quickstart](https://github.com/Azure/aigateway/tree/main/cli)
- [Current command reference](https://github.com/Azure/aigateway/blob/main/cli/command-reference.md)
- [Published CLI releases and verified wheel assets](https://github.com/Azure/aigateway/releases)

Use the newest published `cli-v...` release, including public previews. GitHub's
`releases/latest` API omits previews; inspect the releases list instead. Install
the exact official wheel only after verifying its published SHA-256 and obtaining
approval for the tool change. Do not silently substitute an older release.

Check `az aigateway version` and the installed command's `--help`. Do not use
legacy `az ai-gateway` checkouts, local source builds, repacked wheels, or patched
installed modules as the CLI authority. Missing features must be resolved through
the upstream product or reported as unsupported, not invented locally.

The migration helper verifies release freshness, released-wheel provenance,
installed code, and reviewed new-RP command support. If a newer release is not
yet reviewed, update the capability profile and obtain fresh plan approvals;
do not continue with a stale CLI or auto-upgrade during an approved mutation.
