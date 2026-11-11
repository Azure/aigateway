# Diagnose a runtime request

Start with the exact gateway endpoint, model alias or MCP server/tool,
operation, client version, UTC time, HTTP/protocol error and safe request ID.
Never collect credentials or unredacted prompts, tool arguments or results for
diagnosis.

Check, in order:

1. **Destination:** correct gateway HTTPS origin, `/default/` workspace and
   published model operation or MCP path; no duplicated SDK suffix.
2. **Callable contract:** exact alias/tool name, request schema and advertised
   protocol. Do not substitute a backend model or upstream URL.
3. **Caller access:** selected gateway key or Entra runtime token, audience,
   tenant and asset-scoped runtime role. Keep ARM, runtime and backend identity
   separate.
4. **Outcome:** inspect HTTP status and parsed model/MCP result. HTTP 200 can
   contain a protocol error, failed stream or tool `isError`.
5. **Owner-only causes:** if client evidence is insufficient, request the
   specific missing role, policy, filter or backend-connection confirmation.
   Do not broaden identity, alter policy or retry a possibly side-effecting
   tool to make the error disappear.

## Recognize policy responses

| Policy or signal | Response | Next check |
| --- | --- | --- |
| Cost limit | `403 LlmCostQuotaExceeded` | Check the applicable cost policy and caller counter; this is not an RBAC failure. |
| Token or request-rate limit | `429` with `Retry-After` | Honor the delay. Correlate policy and backend evidence; status alone does not identify which limit rejected the request. |
| IP filter | `403` | Check the caller's actual egress IP against the effective filter; a 403 alone does not identify this policy. |
| Content-safety rejection | Often `400` | Inspect the returned error and trace to distinguish gateway enforcement from provider filtering; don't replay unchanged input. |
| Agent 365 tool threat protection | MCP `tools/call` returns HTTP `200` with `result.isError: true` | Read the exact denial code and correlation ID from `result._meta["com.microsoft.azure.ai.gateway/denial"]`. |

Tool-threat denial codes:

| Code | Meaning and response |
| --- | --- |
| `ToolEvaluationIdentityRequired` | No usable delegated caller token or required tenant. Use the approved user bearer-token flow; app-only tokens and keys cannot satisfy OBO. |
| `ToolEvaluationDenied` | The evaluator denied the call or result. Share the correlation ID with the security owner. |
| `ToolEvaluationInvalidRequest` | Evaluation input is invalid. Correct the request or ask the owner to investigate the policy input. |
| `ToolEvaluationRequestTooLarge` | Evaluation input exceeds the supported size. Reduce the relevant tool input/result. |
| `ToolEvaluationUnavailable` | Token exchange/evaluation failed, timed out, or returned no valid verdict. Share the correlation ID; after-invocation evaluation may have withheld a result after the tool ran, so don't automatically retry. |

For threat protection, a pre-invocation denial prevents execution; a
post-invocation denial withholds the result but cannot undo execution. Other
policy failures may not have a documented stable code. Use the observed
response and Monitoring/request trace instead of inferring a policy from HTTP
status.

See the current [policy overview](https://ai.gateway-df.azure.com/docs/policies/overview),
[rate-limit](https://ai.gateway-df.azure.com/docs/policies/request-rate-limit),
[IP-filter](https://ai.gateway-df.azure.com/docs/policies/ip-filter),
[cost-limit](https://ai.gateway-df.azure.com/docs/finops/overview#cost-limits),
and [tool threat protection](https://ai.gateway-df.azure.com/docs/policies/tool-threat-protection)
documentation for policy behavior and supported error details.

For other `401`/`403` responses, distinguish authentication, invocation
permission and backend denial. For `404`, check the published route and SDK URL
joining. For timeouts or partial streams, do not claim success or assume no
tool action occurred.

Report the observed failure layer, evidence, remaining uncertainty and the
smallest client fix or owner action. Do not claim telemetry or configuration
was inspected unless it actually was.
