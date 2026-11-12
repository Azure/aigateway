"""Ask an MCP server what tools it exposes.

APIM stores no tool names for a passthrough server -- it proxies ``tools/list``
to the upstream -- so the only way to know them is to ask at runtime. That makes
this the MCP counterpart of ``resolve-models``: opt-in, credential-aware, and
explicit about which route it took.

**The route changes the answer.** Called through the APIM gateway, the list is
what callers actually see, because the API's policies run. Called directly at
the upstream, those policies are bypassed, so the list can be larger than what
the gateway exposes. Both are recorded, never conflated.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from .arm import ArmClient
from .resolve import ResolveError, resolve_secret

PROTOCOL_VERSION = "2025-06-18"

# Injected so tests never reach the network.
Caller = Callable[[str, dict, dict], dict]


@dataclass
class Discovery:
    asset_id: str
    route: str = "none"  # gateway | upstream | none
    url: str | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    status: str = "pending"  # discovered | needsAuthorization | unsupported | failed
    detail: str = ""
    bypassedPolicy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "assetId": self.asset_id,
            "route": self.route,
            "url": self.url,
            "tools": self.tools,
            "status": self.status,
            "detail": self.detail,
            "bypassedPolicy": self.bypassedPolicy,
        }


# ------------------------------------------------------------------ protocol


def _parse(body: str, content_type: str) -> dict[str, Any]:
    """Read a JSON-RPC reply from either a JSON body or an SSE stream.

    A streamable-HTTP server may answer either way for the same request; the
    live servers tested answer POSTs with ``text/event-stream``.
    """
    if "text/event-stream" in (content_type or ""):
        for line in body.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload:
                    return json.loads(payload)
        raise ResolveError("the server returned an event stream with no data frame")
    return json.loads(body)


def call(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    *,
    timeout: int = 30,
    hops: int = 3,
) -> tuple[dict[str, Any] | None, dict[str, str], str]:
    """One JSON-RPC round trip over streamable HTTP.

    307 and 308 are followed with the method and body intact, which urllib will
    not do for a POST. MCP endpoints redirect for mundane reasons -- a missing
    trailing slash is the common one -- and treating that as a failure reports a
    reachable server as unreachable.

    Returns the reply, the response headers, and the final URL. The headers carry
    ``Mcp-Session-Id`` on a stateful server, which later requests must echo back.
    """
    for _hop in range(hops + 1):
        request = urllib.request.Request(url, method="POST", data=json.dumps(payload).encode("utf-8"))
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json, text/event-stream")
        request.add_header("MCP-Protocol-Version", PROTOCOL_VERSION)
        for name, value in headers.items():
            request.add_header(name, value)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                response_headers = {k.lower(): v for k, v in dict(response.headers).items()}
                if response.status == 202 or not body.strip():
                    return None, response_headers, url  # a notification has no reply
                return _parse(body, response.headers.get("content-type", "")), response_headers, url
        except urllib.error.HTTPError as exc:
            location = (exc.headers or {}).get("Location")
            if exc.code in {307, 308} and location:
                url = urllib.parse.urljoin(url, location)
                continue
            detail = exc.read().decode("utf-8", errors="replace").strip()[:200]
            raise ResolveError(f"{url} returned {exc.code}{': ' + detail if detail else ''}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
            raise ResolveError(f"{url} could not be reached: {exc}") from exc
    raise ResolveError(f"{url} redirected more than {hops} times")


def list_tools(url: str, headers: dict[str, str], *, timeout: int = 30) -> list[dict[str, Any]]:
    """Handshake, then ask for the tool list.

    A stateful server (FastMCP among them) issues an ``Mcp-Session-Id`` on
    initialize and rejects everything after it without one, and expects the
    ``notifications/initialized`` acknowledgement before serving requests.
    Skipping either reports a working server as a 400.
    """
    session = dict(headers)
    _reply, response_headers, url = call(url, session, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "apim-import", "version": "0.1"},
        },
    }, timeout=timeout)

    session_id = response_headers.get("mcp-session-id")
    if session_id:
        session["Mcp-Session-Id"] = session_id
        # Stateful servers expect the handshake to be acknowledged.
        try:
            call(url, session, {"jsonrpc": "2.0", "method": "notifications/initialized"},
                 timeout=timeout)
        except ResolveError:
            pass  # not every server requires or accepts it

    reply, _headers, _url = call(
        url, session, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        timeout=timeout,
    )
    if not reply:
        raise ResolveError("tools/list returned no reply")
    if "error" in reply:
        raise ResolveError(f"tools/list failed: {reply['error'].get('message')}")
    tools = (reply.get("result") or {}).get("tools") or []
    return [
        {"name": tool.get("name"), "description": (tool.get("description") or "")[:200]}
        for tool in tools if isinstance(tool, dict) and tool.get("name")
    ]


# --------------------------------------------------------------- orchestration


def discoverable(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    """Servers whose tool list only exists at runtime."""
    return [
        server
        for server in (inventory.get("assets") or {}).get("mcpServers") or []
        if (server.get("toolDiscovery") or {}).get("status") == "runtimeOnly"
        and server.get("pattern") != "unconfigured"
    ]


def gateway_url(inventory: dict[str, Any], server: dict[str, Any]) -> str | None:
    """Where a caller reaches this server today."""
    base = ((inventory.get("service") or {}).get("gatewayUrl") or "").rstrip("/")
    path = (server.get("source") or {}).get("path")
    if not base or not path:
        return None
    suffix = (server.get("upstream") or [{}])[0].get("mcpPath") or "/mcp"
    return f"{base}/{path.strip('/')}{suffix}"


def upstream_url(server: dict[str, Any]) -> str | None:
    upstream = (server.get("upstream") or [{}])[0]
    url = upstream.get("url")
    if not url:
        return None
    if upstream.get("transport") not in {"streamableHttp", None}:
        return None
    return url.rstrip("/") + (upstream.get("mcpPath") or "/mcp")


def _subscription_key_ref(inventory: dict[str, Any], server: dict[str, Any]) -> str | None:
    """A subscription key whose scope covers this API."""
    for entry in (server.get("access") or {}).get("subscriptions") or []:
        subscription = next(
            (s for s in (inventory.get("shared") or {}).get("subscriptions") or []
             if s["id"] == entry["id"]), None
        )
        if subscription and subscription.get("secretRef"):
            return subscription["secretRef"]
    return None


def discover_tools(
    inventory: dict[str, Any],
    *,
    client: ArmClient | None = None,
    allow: set[str] | None = None,
    route: str = "auto",
    caller: Caller | None = None,
) -> list[Discovery]:
    """List tools for the authorized servers and write them into the inventory.

    ``route`` is ``gateway``, ``upstream`` or ``auto``. ``auto`` prefers the
    gateway, because that is the list callers actually see, and falls back to the
    upstream when the gateway refuses -- recording that policies were bypassed.
    """
    allow = allow or set()
    caller = caller or (lambda url, headers, _server: {"tools": list_tools(url, headers)})
    secrets_by_id = {entry["id"]: entry for entry in inventory.get("secrets") or []}
    results: list[Discovery] = []

    for server in discoverable(inventory):
        result = Discovery(asset_id=server["id"])
        if not ("all" in allow or server["id"] in allow):
            result.status = "needsAuthorization"
            result.detail = "Listing tools calls the server; not authorized."
            results.append(result)
            continue

        attempts: list[tuple[str, str | None]] = []
        if route in {"auto", "gateway"}:
            attempts.append(("gateway", gateway_url(inventory, server)))
        if route in {"auto", "upstream"}:
            attempts.append(("upstream", upstream_url(server)))

        errors = []
        for name, url in attempts:
            if not url:
                errors.append(f"{name}: no usable URL")
                continue
            headers: dict[str, str] = {}
            if name == "gateway":
                ref_id = _subscription_key_ref(inventory, server)
                if (server.get("access") or {}).get("subscriptionRequired") and not ref_id:
                    errors.append("gateway: the API needs a subscription key and none covers it")
                    continue
                if ref_id and client and ref_id in secrets_by_id:
                    try:
                        header = ((server.get("access") or {}).get("subscriptionKeyParameterNames")
                                  or {}).get("header") or "Ocp-Apim-Subscription-Key"
                        headers[header] = resolve_secret(client, secrets_by_id[ref_id])
                    except ResolveError as exc:
                        errors.append(f"gateway: {exc}")
                        continue
            try:
                payload = caller(url, headers, server)
            except ResolveError as exc:
                errors.append(f"{name}: {exc}")
                continue
            result.route = name
            result.url = url
            result.tools = payload.get("tools") or []
            result.status = "discovered"
            result.bypassedPolicy = name == "upstream"
            result.detail = f"{len(result.tools)} tools"
            if result.bypassedPolicy:
                result.detail += "; called the upstream directly, so APIM policies did not run"
            break
        else:
            result.status = "failed"
            result.detail = "; ".join(errors) or "no route available"

        if result.status == "discovered":
            _apply(server, result)
        results.append(result)

    return results


def _apply(server: dict[str, Any], result: Discovery) -> None:
    server["tools"] = [
        {"name": tool["name"], "description": tool.get("description"),
         "origin": "upstreamRuntime", "hasToolPolicy": False}
        for tool in result.tools
    ]
    server["toolCount"] = len(result.tools)
    server["toolDiscovery"] = {
        "status": "complete",
        "source": "gatewayRuntime" if result.route == "gateway" else "upstreamRuntime",
        "url": result.url,
        "discoveredCount": len(result.tools),
        # The distinction matters: an upstream list can be larger than what the
        # gateway exposes, because the API's policies did not run.
        "policiesApplied": result.route == "gateway",
        "note": result.detail,
    }
