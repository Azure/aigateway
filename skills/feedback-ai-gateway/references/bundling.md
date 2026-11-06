# Bundle commands and recovery

## Resolve paths once

Set `SKILL_DIR` to the absolute **installed skill directory**, not a directory
guessed inside the user's project. The examples use `python3`; substitute an
existing Python 3.10+ executable if the host uses another name. If none exists,
report the prerequisite rather than installing it without permission.

Set `SESSION_FILE` to the approved export or prepared copy and `OUTPUT_ZIP` to a
new `.zip` path in the approved protected directory. Quote all paths.
Do not pass secret values in shell arguments.

## Run the helper

**Private, original content:**

```bash
python3 "$SKILL_DIR/scripts/feedback.py" \
  --agent copilot --sharing private \
  --session-file "$SESSION_FILE" \
  --output "$OUTPUT_ZIP"
```

**Private, anonymized content:** use prepared anonymized copies and add
`--anonymize` to the private command.

**GitHub issue:** use prepared semantically anonymized copies, never the originals.

```bash
python3 "$SKILL_DIR/scripts/feedback.py" \
  --agent claude --sharing issue --anonymize \
  --session-file "$SESSION_FILE" \
  --output "$OUTPUT_ZIP"
```

Use the actual host's `--agent`: `copilot`, `claude`, `gemini`, `cursor`, or `other`.
Repeat `--session-file` for parts of the same selected session.
Add repeatable `--context-file` arguments only for approved diagnostics, prepared
under the same privacy mode. Do not include an unrelated session as context.

For anonymized modes, optional `--sensitive-values-file "$VALUES_FILE"` accepts a
protected UTF-8 JSON array of additional literal strings to replace. This file
and the replacement mapping are not automatically included in the archive.
Never select the values file as session or context evidence.

The scrubber replaces common credential forms, URLs, emails, IDs, IP addresses,
and local paths with consistent tokens. It does not understand all identities
or secret formats; semantic review remains mandatory.

## Verify the artifact

The helper prints the local ZIP path and performs no upload. It creates:

- `session-001.txt`, etc.: selected exports, original or scrubbed.
- `context-001.txt`, etc.: optional selected diagnostics.
- `manifest.json`: mode, agent, creation time, file sizes and SHA-256 digests.
- `REVIEW.txt`: sharing precautions.

Source basenames and paths are not used as archive member names; they may still
appear inside original or insufficiently anonymized content.

Run the standard-library integrity check:

```bash
python3 -m zipfile -t "$OUTPUT_ZIP"
```

Then inspect the member list, manifest, and every member's contents locally.
Confirm the mode, approved scope, expected evidence, and anonymization status.
Do not treat the integrity check as a privacy check.

## Recover without bypassing safeguards

| Failure | Required action |
| --- | --- |
| Existing output | Choose a new output path; never overwrite the existing archive. |
| Non-UTF-8, binary, directory, or symlink input | Obtain an approved regular UTF-8 text, Markdown, JSON, or JSONL export. |
| More than 20 MiB per file or 50 MiB total | Ask for a narrower selection or an explicitly approved partial export; record omissions. |
| Missing path or permission failure | Confirm the selected paths/access with the user; do not scan unrelated stores. |
| Invalid sensitive-values file | Use a JSON array of nonempty strings with `--anonymize`; keep it local. |
| Missing `--anonymize` for issue mode | Prepare anonymized copies and rerun with both `--sharing issue --anonymize`. |
| Sensitive content in final ZIP | Correct copies, rebuild to a new filename, and review the new archive again. |
