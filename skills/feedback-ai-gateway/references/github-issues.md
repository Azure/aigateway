# GitHub issue publication

Read this only when the user chooses issue sharing. Collection consent is not
publication approval. GitHub issues and attachments may be public.

## Draft and obtain approval

Require an inspected issue-mode ZIP built from semantically anonymized copies
with helper scrubbing. Never reuse an original/private bundle.

Prepare an anonymized title and body. Prefer the repository's applicable issue
template if available; otherwise use:

```markdown
Title: Azure AI Gateway feedback: <concise symptom>

## Expected behavior
<intended workflow and outcome>

## Actual behavior
<observed failure and impact>

## Reproduction
<minimal steps with neutral identifiers>

## Environment
<known agent, plugin, and CLI versions; mark unavailable fields>

## Session evidence
<included evidence and missing telemetry>
<reviewed anonymized ZIP to be attached in the browser>
```

Check the title, body, comments, filenames, and attachments for sensitive details.
Show the draft and the final ZIP path, explain the public-sharing risk, and ask
the user to review the archive and approve **that archive, title, body, and
`Azure/aigateway` destination**. If any approved artifact changes, obtain approval
again. Do not publish while review or approval is outstanding.

## Publish only as requested

**Browser handoff:** return
`https://github.com/Azure/aigateway/issues/new` and the approved description.
The user attaches the reviewed issue ZIP through GitHub's browser upload.

**Assistant-created issue:** only when requested and approved, save the approved
body to a local UTF-8 file and run:

```bash
gh issue create --repo Azure/aigateway \
  --title "$APPROVED_TITLE" \
  --body-file "$APPROVED_BODY_FILE"
```

Require an available, authenticated `gh`; otherwise use the browser handoff.
`gh issue create` does not attach local ZIPs. Return the created issue URL and
state that the reviewed ZIP still needs browser attachment. Do not report the
evidence as uploaded until it actually is.

If publication fails, report the error and retain the local ZIP. If attachment
limits or repository restrictions prevent upload, leave the archive local and
let the user choose a private channel. Never bypass these limits with raw log
comments, a gist, or a third-party file host.
