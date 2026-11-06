---
description: Package one selected coding-agent session into a local feedback ZIP; require anonymization and review before GitHub issue sharing.
argument-hint: [session-export-path] [private|issue]
---

# /aigateway:feedback

Follow `skills/feedback-ai-gateway/SKILL.md` and its bundled local Python helper.
Resolve `$ARGUMENTS` into the selected session/export and sharing preference.
Obtain consent before collecting the session and any optional diagnostics.
Support Copilot, Claude, Gemini, Cursor, or another host's supported session export;
report unavailable telemetry rather than inventing it or reading unrelated sessions.
Return a local ZIP to the user; never upload automatically.
Private handoff may retain original content if the user chooses.
GitHub issue sharing always requires semantic anonymization, helper scrubbing,
review of the final archive/title/body, and explicit publication approval.
Do not attach raw/private bundles or claim that `gh issue create` uploads ZIPs.
