---
description: Anonymize a session transcript summary for product feedback. Returns an anonymized file; no uploads or GitHub publishing.
argument-hint: [summary-file-path] [output-directory]
---

# /aigateway:feedback

Follow `skills/feedback-ai-gateway/SKILL.md` and its bundled local Python helper.
Resolve `$ARGUMENTS` into the selected summary file and output directory.
Obtain consent before reading the summary file. Verify that the file is a
summary (friction, tasks, outcomes) and not a full transcript. Never accept
full session histories or conversation exports.
Return an anonymized summary file to the user; never upload automatically.
Do not suggest or facilitate sharing to GitHub, email, or any other service.
All sharing decisions belong to the user.
