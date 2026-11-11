# Discover and call models

Read the discovery section only when the callable contract is missing. For an
exact known endpoint/model/protocol, go to the usage section. Resolve missing
gateway identity with [connection](connection.md); use its ARM API versions and
pagination rules for management reads.

## Discover the callable contract

The following inventory steps apply only to permitted management reads. For
runtime-only users, keep the supplied callable name and published operation;
apply the URL/protocol rules without claiming a gateway-wide model inventory.

Distinguish a **published alias** from its **backend model registration**:

- When alias listing succeeds, aliases are the published model surface,
  including when the list is empty. The request's `model` is
  `properties.aliasName`, falling back to the alias resource `name` only when
  the callable name is absent. Preserve punctuation and casing. Do not
  substitute the backend deployment name or the alias's management ID.
- A denied, failed or unsupported alias read is not permission to call a
  registered backend model instead. Preserve the missing-inventory boundary
  and obtain the published callable contract from the owner. If existing
  evidence identifies a deprecated resource, follow the migration handoff in
  [connection](connection.md) rather than trying an obsolete direct-model path.

Read the selected asset's advertised `supportedEndpoints`. For an alias, use
its native capability metadata where available; otherwise resolve its
`backendModels[].resourceId` against authorized backend-model reads. A
multi-backend alias can only be assumed to support operations shared by all
resolved backends. Missing permissions, unresolved targets, or unknown
capabilities remain explicit gaps, not an assumed Chat Completions endpoint.
Validate backend resource references against the selected gateway and workspace
before following them; do not send management requests to an unrelated resource.

Build a model operation URL as:

```text
<runtime-origin>/default/models<supportedEndpoint>
```

The advertised path already contains its provider prefix, for example
`/openai/v1/responses` or `/anthropic/v1/messages`. Preserve that prefix; do not
append it twice, replace it with a provider URL, or drop `/default/`. Accept
only operation paths belonging to the selected gateway, joining with exactly
one slash. If native `gatewayEndpoints` metadata supplies the selected
operation's full URL, validate its origin and workspace before using it.
A copied full endpoint is already complete.

| Endpoint suffix | Integration and request shape |
| --- | --- |
| `/chat/completions` | OpenAI Chat Completions: `model`, `messages`. |
| `/responses` | OpenAI Responses: `model`, `input`. |
| `/messages` | Anthropic Messages: `model`, `messages`, required `max_tokens`, and `anthropic-version: 2023-06-01`. |
| `/embeddings` | OpenAI embeddings: `model`, `input`; return vectors rather than chat text. |
| Other operations | Require both current gateway documentation and selected-asset capability evidence before using that operation's client/schema. Provider support alone is not enough. |

### Distinguish model capabilities from gateway API support

There are three checks: the model supports the capability, the gateway exposes
that operation, and this caller can invoke the published asset. A provider SDK
method or a registered model is not evidence that all three hold.

Image-generation endpoints such as `/images/generations` are not currently
supported by the gateway. Image input on a supported multimodal operation does
not establish image-generation support. Re-check the current
[Azure AI Gateway documentation](https://ai.gateway.azure.com/docs/) and the
selected asset's operation metadata before treating a previously unavailable
operation as supported. If documentation is inaccessible, keep support
unverified rather than inventing a route or trying provider paths.

For an unavailable operation, explain whether the gap is gateway support, the
selected alias/model's capabilities, publication or permission. Offer an
existing supported asset/operation when it meets the task; an owner may need
to supply a suitable contract. Do not bypass the gateway or substitute a
backend deployment for a published alias.

For SDKs, remove only the operation suffix the chosen SDK itself appends.
OpenAI clients commonly use `<origin>/default/models/openai/v1`. Anthropic SDK
URL-joining conventions differ: verify the chosen version's behavior so the
result is exactly the advertised Messages URL, with neither a missing nor a
duplicated `/v1`. Prefer an exact-URL HTTP request if the SDK cannot represent
the route correctly.

For shortlisted aliases, use permitted non-secret reads to explain the map
from callable alias to candidate registrations, deployments and providers.
Interpret conditions, actual `selectionOrder`, priorities/weights, selector
models and session/state requirements using [asset selection](asset-selection.md).
Explain how these affect the user's choice; configuration does not prove which
backend handled a particular request.

Keep routing and governance server-side. Do not bypass an alias, assume portable
provider-stored state, or add overrides implicitly. Any requested
`auto_model_selection` override must be allowed by the alias, use eligible
selector names and match the operation. Unsupported/unauthorized overrides fail
rather than being silently dropped.

## Call the selected operation

Establish [runtime authentication](authentication.md) and follow the main skill's
live-use approval boundary. An example in this file is not authorization to
send a request. Preserve a supplied full operation URL; derive an SDK base only
by removing the suffix that SDK appends.

Generate the smallest client for the selected operation, not a chat client for
every model. For OpenAI-compatible operations, use `openai` in Python or
`openai` in TypeScript with the derived `base_url`/`baseURL`, exact callable
model name, and selected runtime credential. The SDK's `api_key` parameter sends
the credential as `Authorization: Bearer`; the same gateway header applies to
raw model requests. See [authentication](authentication.md).

For example, this is a **Chat Completions-only** Python integration:

```python
import os

from openai import APIConnectionError, APIStatusError, OpenAI

mode = os.environ["AI_GATEWAY_AUTH"]
credential_names = {"entra": "AI_GATEWAY_TOKEN", "key": "AI_GATEWAY_API_KEY"}
if mode not in credential_names:
    raise ValueError("AI_GATEWAY_AUTH must be entra or key")
credential = os.environ[credential_names[mode]]
if not credential.strip():
    raise ValueError("The selected gateway credential is empty")

try:
    with OpenAI(
        base_url=os.environ["AI_GATEWAY_MODEL_BASE_URL"],
        api_key=credential,
        timeout=30.0,
        max_retries=0,
    ) as client:
        reply = client.chat.completions.create(
            model=os.environ["AI_GATEWAY_MODEL"],
            messages=[{"role": "user", "content": "Reply with a short greeting."}],
        )
        if not reply.choices or not reply.choices[0].message.content:
            raise SystemExit("Gateway returned no text; the model response is unverified.")
        print(reply.choices[0].message.content)
except APIStatusError as error:
    raise SystemExit(
        f"Gateway request failed with HTTP {error.status_code}; "
        "check authentication, permissions, model protocol, and quota."
    ) from None
except APIConnectionError:
    raise SystemExit("Gateway connection failed; check endpoint and network access.") from None
```

`AI_GATEWAY_MODEL_BASE_URL` is an SDK base, not the full operation endpoint.
For Responses use `client.responses.create(model=..., input=...)`; for
embeddings use `client.embeddings.create(model=..., input=...)` and inspect the
returned vectors. Messages requires the Anthropic request shape and version
header. An Anthropic SDK's default `x-api-key` is not the gateway's bearer
credential: configure `Authorization: Bearer` through the SDK's supported
headers or bearer option without sending provider secrets. If the SDK cannot
send the required header, use an exact-URL HTTP request. Verify streaming and
function-calling support before enabling them.
Only use generation limits accepted by the selected model; do not assume all
Chat Completions models accept `max_tokens`.

Keep gateway keys and tokens on a trusted backend, never in browser bundles,
public configuration, URLs, or prompts. If a browser app needs gateway access,
use its existing authenticated backend or an approved delegated identity flow;
do not expose a shared key or disable CORS/authentication.
