# Diagnose the request, not just the HTTP status

Use this reference for an unexpected model choice, missing or blocked tools,
latency, usage surprises, authentication failures or other runtime errors.
It supplements normal discovery/integration; do not query monitoring or replay
requests automatically for an ordinary catalog request.

## Runtime-only diagnosis remains useful

Gateway management access is not required to check a supplied endpoint,
callable name, request format, credential method or sanitized runtime error.
First inspect the local client configuration: HTTPS origin, `/default/`, exact
operation path, one correct SDK suffix, body model name, chosen runtime
credential binding, protocol and completion/error handling.

If the user cannot read ARM resources, skip alias/server/key/policy enumeration.
Continue with these checks, the returned code and behavior, safe correlation
metadata, and the published connection contract. State which routing, policy or
upstream explanations remain hypotheses. Do not request elevated management
access as a prerequisite or guess hidden configuration from a status alone.

A supplied monitoring link/resource can be used if the user separately has
query permission, even without gateway management permission. Without telemetry
access too, finish with a precise redacted client-side diagnosis or owner
handoff; do not pretend trace retrieval or configuration inspection occurred.

## 1. Capture the smallest useful incident

Record a redacted diagnostic envelope:

- UTC time/window, supplied runtime endpoint and gateway/workspace identity when
  known, callable alias or MCP server/tool, operation/protocol, and client/SDK version.
- Authentication method and intended caller context, never the token/key.
- HTTP status and parsed, sanitized provider/gateway or JSON-RPC error code.
  For streams, include whether the failure occurred after HTTP acceptance.
- Available safe request/correlation/trace identifiers and any Retry-After
  value. Use only allowlisted response metadata; do not dump all headers,
  raw exception objects or request/response bodies.
- MCP negotiated version and whether a session was established, without
  retaining a session credential. For model calls, retain any reported model
  identity separately from the requested alias.

An SDK request ID, a provider response ID and a distributed trace ID are not
interchangeable. Do not promise that every gateway returns a trace ID. If none
is available, use time, asset and authorized caller filters to locate an
existing trace. Do not collect prompts, tool arguments, JWTs, full user claims,
backend credentials or unredacted payloads merely for correlation.

Inspect HTTP, protocol and application outcomes separately. HTTP 200 can contain
an OpenAI Responses `response.failed`/`error` event, an Anthropic stream error,
a Chat Completions error payload, an MCP JSON-RPC error, or a tool result with
`isError: true`. A connection closing without the expected result is not proof
that the operation succeeded or never executed.

## 2. Establish the failed access/processing layer

| Layer | Appropriate identity and evidence |
| --- | --- |
| Management metadata | The caller's ARM read permissions on the selected resources; use Azure CLI/ARM authentication, not a runtime key. |
| Gateway runtime | The explicitly selected gateway key or Entra runtime token. Delegated apps use `https://azure-api.net/aigateway/Data.All`; workload identities use `https://azure-api.net/aigateway/.default`. Check the endpoint-specific header in [authentication](authentication.md), tenant, expiry, consent and runtime role/scope separately. |
| Gateway to backend | Existing configured backend key, managed identity or user connection/token exchange. Management access or the caller's gateway key does not establish upstream authorization. |
| Observability store | Independent read/query permission on the existing Azure Monitor workspace or custom destination. Gateway control-plane access does not automatically grant it. |

Keep the chosen credential identity fixed while diagnosing. A new key, broader
token, role grant or provider-direct call would change the security context
rather than explain the failing request. Do not carry out those changes.

Classify the failure using actual response/error and configuration evidence:

| Symptom | Evidence to inspect and safe next step |
| --- | --- |
| `unknown_model` or unsupported operation | Exact callable alias versus management/backend names; endpoint suffix and SDK joining; aliases and capability support. Do not "fix" a working alias by substituting a deployment. |
| 400 / input rejection | Protocol/schema, model-specific parameters, no eligible router model, condition/session expression errors, prohibited overrides, auto-selection text/state restrictions, and content-safety details. Not every 400 is a client serialization bug. |
| 401 | Selected runtime host and bearer header, token audience/tenant/expiry or current key. Keep ARM, runtime and backend tokens separate. |
| 403 | Error code and stage: runtime role/scope, IP restrictions, blocked server/tool, cost budget, policy or backend denial. `LlmCostQuotaExceeded` is not fixed by granting an invocation role. |
| 404 | Correct management/root API version or runtime route, `/default/`, provider prefix, resource identity, session handling and duplicated/missing SDK suffixes. |
| 429 | Gateway policy versus backend quota, counter dimension and safe Retry-After. Only retry with bounded backoff when appropriate; do not rotate identity to evade limits. |
| Missing tools | Server allowlist/blocked state, per-backend namespace, actual paginated inventory, compatible MCP version, caller access and upstream connection. A block can deny invocation while leaving discovery visible. |
| Slow/empty reply, timeout, 5xx or partial stream | Correlate routing attempts, policy evaluation, provider latency and protocol completion. Determine whether any backend/tool action happened before considering a retry. |

Do not infer the layer from status alone. Use the smallest relevant permitted
configuration reads from the asset-selection reference. A client with no
management permission can still use its supplied runtime contract and client
evidence; request only the missing owner confirmation.

## 3. Inspect telemetry when useful

Follow [Application Insights and OpenTelemetry](telemetry.md) when existing
trace evidence can resolve the question and the caller has query access.
Gateway management access is not a prerequisite for a known monitoring destination.

## 4. Close the evidence loop

Explain the observed failure boundary, the supporting evidence, confidence
and any remaining unknown. Recommend the smallest client fix consistent with
the chosen asset contract. Separate client fixes from owner actions such as
changing filters/policies, granting access or correcting backend connectivity.
Do not carry out the latter through this skill.

When no trace is found, check the selected destination, time range, ingestion
delay, retention/sampling/export gaps and query permission. Trace absence does
not prove that no request or tool execution occurred. Do not turn on payload
logging or repeatedly replay a potentially side-effecting call to compensate.

Provide a concise escalation packet if blocked: runtime endpoint, gateway/workspace
identity when known, asset and
operation, UTC window, safe correlation IDs, auth method, sanitized error/stage,
relevant configured constraints, permitted read coverage, and the precise
missing read or owner decision. Keep keys, tokens, payloads and private tool
results out of the packet.
