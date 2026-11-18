"""Demo MCP server that only answers calls made through Azure AI Gateway as the signed-in user.

Adapted for the Azure AI Gateway labs from https://github.com/kostapetan/ai-gateway-end-to-end by Kosta Petan.

The server accepts a Microsoft Entra ID v2 access token only when:
  * the tenant issued it (iss),
  * it was issued for this backend's app registration (aud is the backend's client ID),
  * it carries the backend's delegated scope (scp), and
  * the token exchange app requested it (azp), which is what the gateway uses for the on-behalf-of exchange.

So the tools are reachable only along one path: MCP client -> Azure AI Gateway -> on-behalf-of exchange -> here.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import uvicorn
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_access_token
from starlette.requests import Request
from starlette.responses import JSONResponse

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("obo-demo")

TENANT_ID = os.environ["AZURE_TENANT_ID"]
BACKEND_CLIENT_ID = os.environ["BACKEND_CLIENT_ID"]
REQUIRED_SCOPE = os.getenv("REQUIRED_SCOPE", "user_impersonation")
ALLOWED_CLIENT_IDS = {c.strip().lower() for c in os.getenv("ALLOWED_CLIENT_IDS", "").split(",") if c.strip()}
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"


class OnBehalfOfVerifier(JWTVerifier):
    """Validates the token's signature, issuer, audience, and scope, then checks which app requested it."""

    async def verify_token(self, token: str):  # type: ignore[override]
        access_token = await super().verify_token(token)
        if access_token is None:
            return None
        claims = access_token.claims
        client_app = str(claims.get("azp", "")).lower()
        if ALLOWED_CLIENT_IDS and client_app not in ALLOWED_CLIENT_IDS:
            log.warning("Rejected a token that app %s requested: only the token exchange app may call", client_app)
            return None
        log.info("Call from user %s through app %s with scope %s", claims.get("oid"), client_app, claims.get("scp"))
        return access_token


mcp = FastMCP(
    name="obo-demo",
    instructions="Demo tools behind Azure AI Gateway. Call whoami to see the user that the gateway signed in as.",
    auth=OnBehalfOfVerifier(
        jwks_uri=f"{AUTHORITY}/discovery/v2.0/keys",
        issuer=f"{AUTHORITY}/v2.0",
        # A v2 access token's audience is the backend's client ID, not its api:// URI.
        audience=BACKEND_CLIENT_ID,
        required_scopes=[REQUIRED_SCOPE],
    ),
)

READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}


@mcp.tool(annotations=READ_ONLY)
def whoami() -> dict[str, Any]:
    """Return who the backend sees as the caller, read from the access token that the gateway sent."""
    token = get_access_token()
    claims = token.claims if token else {}
    expires = claims.get("exp")
    return {
        "name": claims.get("name"),
        "username": claims.get("preferred_username") or claims.get("upn"),
        "object_id": claims.get("oid"),
        "tenant_id": claims.get("tid"),
        "audience": claims.get("aud"),
        "client_app_id": claims.get("azp"),
        "scopes": claims.get("scp"),
        "issuer": claims.get("iss"),
        "token_version": claims.get("ver"),
        "expires_utc": datetime.fromtimestamp(int(expires), tz=timezone.utc).isoformat() if expires else None,
    }


@mcp.tool(annotations=READ_ONLY)
def echo(message: str) -> str:
    """Return the message, prefixed with the caller's display name."""
    token = get_access_token()
    name = (token.claims.get("name") if token else None) or "Someone"
    return f"{name} said: {message}"


@mcp.tool(annotations=READ_ONLY)
def get_server_time() -> str:
    """Return the backend's current time in UTC (ISO 8601)."""
    return datetime.now(timezone.utc).isoformat()


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


# Stateless JSON responses: no session affinity behind the gateway, and the app can scale out.
app = mcp.http_app(path="/mcp", stateless_http=True, json_response=True)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")), proxy_headers=True, forwarded_allow_ips="*")
