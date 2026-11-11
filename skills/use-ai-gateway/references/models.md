# Call a model

Use a complete supplied operation URL when available. Otherwise, when
authorized, read the selected alias and its advertised `supportedEndpoints`.
The request's `model` is the exact `properties.aliasName`. Never substitute a backend deployment.

## Build the operation URL

For an advertised operation path:

```text
<runtime-origin>/default/models<supportedEndpoint>
```

The path includes its provider prefix, for example
`/openai/v1/responses`. Keep `/default/`, preserve that prefix, and join with
one slash. Use a published full operation URL as-is after checking that its
HTTPS origin belongs to the selected gateway.

Match the operation to the request shape:

| Operation | Request shape |
| --- | --- |
| OpenAI Chat Completions | `model`, `messages` |
| OpenAI Responses | `model`, `input` |
| Anthropic Messages | `model`, `messages`, required `max_tokens`, `anthropic-version: 2023-06-01` |
| Embeddings | `model`, `input`; consume returned vectors |
| Other | Verify gateway and alias support and the current operation schema before coding |

Provider or SDK support alone does not prove that the gateway publishes an
operation or that the caller can invoke it. If capability or API format is
unknown, check the selected alias metadata or current gateway docs; otherwise
ask the owner. Do not invent a route or call the provider directly.

## Integrate in the existing project

Use the project's language, dependencies and error-handling conventions. For
an advertised `/openai/v1/...` operation, the OpenAI SDK base URL is
`<runtime-origin>/default/models/openai/v1`; the SDK appends the operation
path. Check the installed SDK's URL-joining behavior and preserve the exact
published URL. Use HTTP when an SDK duplicates or removes a required path
segment. Anthropic clients must send the gateway bearer header rather than
their provider-key header.

Read credentials from the configured secret binding. Keep request size,
timeout and retries bounded. Surface HTTP errors and protocol-level failures;
for streaming APIs, require a completed response rather than treating an open
HTTP connection as success. Test with one approved, non-sensitive request and
report the actual result.
