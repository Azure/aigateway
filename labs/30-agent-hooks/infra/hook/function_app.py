"""Agent hooks decision service for Azure AI Gateway (lab 30).

The gateway posts an Agent Hooks AgentContext to /api/tool-hook before a tool runs (interception_point
pre_tool_call) and after the tool returns (post_tool_call). The function answers HTTP 200 with
{"decision": "allow" | "deny", "reason": "..."}.

App Service Authentication (Easy Auth) in front of the app rejects every request that doesn't carry a Microsoft Entra
token for this app from the gateway's managed identity, so the function itself allows anonymous calls.

Rules:
- BLOCKED_TOOLS (app setting): comma-separated tool name patterns that never run, for example *code_sample*
- Tool arguments that contain an email address or a secret-looking string are denied before the call.
- Tool results that contain a secret-looking string are withheld after the call.

The decision log has the tool name, the decision, the reason, and the gateway's request ID. It never has tool
arguments, results, or tokens.
"""
import fnmatch
import json
import logging
import os
import re

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

BLOCKED_TOOLS = [p.strip().lower() for p in os.environ.get("BLOCKED_TOOLS", "*code_sample*").split(",") if p.strip()]

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SECRETS = {
    "storage_account_key": re.compile(r"AccountKey=[A-Za-z0-9+/]{40,}={0,2}"),
    "sas_signature": re.compile(r"[?&]sig=[A-Za-z0-9%+/]{30,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "openai_style_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
}


def find_secret(text: str) -> str | None:
    """Return the name of the first secret pattern that matches the text, or None."""
    return next((name for name, pattern in SECRETS.items() if pattern.search(text)), None)


def before_call(context: dict) -> tuple[str, str]:
    """Decide whether the tool may run, from its name and arguments."""
    tool_call = context["tool_call"]
    name = str(tool_call.get("name", "")).lower()
    for pattern in BLOCKED_TOOLS:
        if fnmatch.fnmatchcase(name, pattern):
            return "deny", f"blocked_tool:{pattern}"

    args = json.dumps(tool_call.get("args") or {})
    if EMAIL.search(args):
        return "deny", "personal_data:email_address"
    secret = find_secret(args)
    if secret:
        return "deny", f"secret_in_arguments:{secret}"
    return "allow", "policy_satisfied"


def after_call(context: dict) -> tuple[str, str]:
    """Decide whether the caller may see the tool result."""
    # The gateway sends the MCP tool result in target; the Agent Hooks spec also defines tool_result.
    result = json.dumps([context.get("target"), context.get("tool_result")])
    secret = find_secret(result)
    if secret:
        return "deny", f"secret_in_result:{secret}"
    return "allow", "policy_satisfied"


@app.route(route="tool-hook", methods=["POST"])
def tool_hook(req: func.HttpRequest) -> func.HttpResponse:
    try:
        context = req.get_json()
    except ValueError:
        context = None
    if not isinstance(context, dict) or not isinstance(context.get("tool_call"), dict):
        context = {}
        decision, reason = "deny", "invalid_context"
    elif context.get("interception_point") == "pre_tool_call":
        decision, reason = before_call(context)
    elif context.get("interception_point") == "post_tool_call":
        decision, reason = after_call(context)
    else:
        decision, reason = "deny", "unsupported_interception_point"

    logging.info(
        "agent-hook point=%s tool=%s decision=%s reason=%s request_id=%s caller=%s policy=%s",
        context.get("interception_point"), (context.get("tool_call") or {}).get("name"), decision, reason,
        context.get("request_id"), req.headers.get("x-ms-client-principal-id", "none"),
        req.headers.get("x-hook-policy", "none"),
    )
    return func.HttpResponse(json.dumps({"decision": decision, "reason": reason}),
                             status_code=200, mimetype="application/json")
