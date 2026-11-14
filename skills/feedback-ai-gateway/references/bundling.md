# Anonymize summary and recovery

## Resolve paths once

Set `SKILL_DIR` to the absolute **installed skill directory**, not a directory
guessed inside the user's project. The examples use `python3`; substitute an
existing Python 3.10+ executable if the host uses another name. If none exists,
report the prerequisite rather than installing it without permission.

Set `SUMMARY_FILE` to the approved session summary (friction, tasks, outcomes)
and `OUTPUT_FILE` to a new path in the approved protected directory.
Quote all paths. Do not pass secret values in shell arguments.

## Run the helper

```bash
python3 "$SKILL_DIR/scripts/feedback.py" \
  --summary-file "$SUMMARY_FILE" \
  --output "$OUTPUT_FILE"
```

Add optional `--sensitive-values-file "$VALUES_FILE"` with a protected UTF-8
JSON array of additional literal strings to replace:

```bash
python3 "$SKILL_DIR/scripts/feedback.py" \
  --summary-file "$SUMMARY_FILE" \
  --sensitive-values-file "$VALUES_FILE" \
  --output "$OUTPUT_FILE"
```

The values file is not included in the output. Keep it local and delete after use.

The scrubber replaces common credential forms, URLs, emails, IDs, IP addresses,
and local paths with consistent tokens. It does not understand all identities
or secret formats; semantic review remains mandatory.

## Verify the artifact

The helper prints the anonymized file path, the count of sensitive values masked,
and a reminder that automated scrubbing is not a guarantee. It performs no upload.

Inspect the output file for remaining secrets and identities by reading it in
full. Look for:
- Customer or project names that survived scrubbing
- Code patterns that identify business logic
- Resource hierarchies or correlation patterns
- Unusual secret formats the regex did not catch

Do not treat the file format check as a privacy check.

## Recover without bypassing safeguards

| Failure | Required action |
| --- | --- |
| Existing output | Choose a new output path; never overwrite the existing file. |
| Non-UTF-8, binary, directory, or symlink input | Obtain an approved regular UTF-8 summary file. |
| More than 20 MiB | Ask for a narrower selection or an explicitly approved partial summary. |
| Missing path or permission failure | Confirm the selected path/access with the user; do not scan unrelated stores. |
| Invalid sensitive-values file | Use a JSON array of nonempty strings; keep it local. |
| Sensitive content in final output | Edit the file by hand, re-run the helper with updated `--sensitive-values-file`, and verify again. |
