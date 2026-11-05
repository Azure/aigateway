"""Shared helpers for the Azure AI Gateway lab notebooks.

Every notebook starts the same way:

    import sys; sys.path.insert(0, "../shared")
    import utils

    lab = utils.Lab("02-first-model-call")

`Lab` reads your Azure CLI sign-in and the shared defaults, so every notebook finds the same gateway. It deploys the
lab's own Bicep files with `az deployment group create`, the same command as the lab's Bicep track, and calls Azure
Resource Manager for the few reads and deletes that a deployment doesn't cover. Keys and tokens stay in memory:
nothing here prints or saves them.

Override the defaults with environment variables before you start the kernel:

    AIGW_LOCATION                 eastus2, or another region where AI Gateway is available
    AIGW_RESOURCE_GROUP           rg-ai-gateway-labs
    AIGW_GATEWAY_NAME             aigw-labs-<6 characters of the SHA-1 of the subscription ID>
    AIGW_FOUNDRY_ACCOUNT          an existing Foundry account to reuse, instead of aigwlabs<8 characters>
    AIGW_FOUNDRY_RESOURCE_GROUP   the Foundry account's resource group (default: AIGW_RESOURCE_GROUP)
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from azure.identity import AzureCliCredential

ARM = "https://management.azure.com"
AIGW_API = "2025-09-01-preview"         # Microsoft.ApiManagement/aigateways and its child resources
COGNITIVE_API = "2025-04-01-preview"    # Microsoft.CognitiveServices (Foundry)
RESOURCES_API = "2021-04-01"            # resource groups, resource providers, and deployments
ROLES_API = "2022-04-01"                # Microsoft.Authorization/roleAssignments
AIGW_SCOPE = "https://azure-api.net/aigateway/.default"   # Microsoft Entra token scope for gateway callers

ROLES = {   # AI Gateway data-plane roles: role ID -> name
    "caad7a21-134e-43f4-a550-c5ffc17e051c": "AI Gateway User",
    "a6b68e3d-a1f0-4c60-8678-237c050cf4ea": "AI Gateway Models User",
    "dce03f8d-857f-4e40-a90d-67770fa6ecd2": "AI Gateway Tools User",
}

_NOISE = ("BCP081", "A new Bicep release is available", "az bicep upgrade")


def az(*args: str, check: bool = True):
    """Run an Azure CLI command and return its JSON output, or None when it prints nothing."""
    executable = shutil.which("az") or shutil.which("az.cmd")
    if not executable:
        sys.exit("❌ Azure CLI not found. Install it from https://aka.ms/azcli, then restart the kernel.")
    result = subprocess.run([executable, *args, "--only-show-errors", "-o", "json"], capture_output=True, text=True)
    if result.returncode != 0:
        if not check:
            return None
        errors = [line for line in result.stderr.splitlines() if line.strip() and not any(n in line for n in _NOISE)]
        raise RuntimeError(f"az {' '.join(args[:3])} failed:\n" + "\n".join(errors))
    return json.loads(result.stdout) if result.stdout.strip() else None


def gateway_regions() -> list[str]:
    """The --location names of the regions where AI Gateway is available. The list grows over time."""
    display_names = az("provider", "show", "--namespace", "Microsoft.ApiManagement", "--query",
                       "resourceTypes[?resourceType=='aigateways'].locations | [0]", check=False) or []
    locations = az("account", "list-locations", "--query", "[].{name:name, displayName:displayName}",
                   check=False) or []
    return [location["name"] for location in locations if location["displayName"] in display_names]


class Lab:
    """Settings and Azure helpers for one lab notebook."""

    def __init__(self, name: str, needs_gateway: bool = True):
        account = az("account", "show", check=False)
        if not account:
            sys.exit("❌ Not signed in to Azure. Run `az login`, then rerun this cell.")
        self.name = name
        self.subscription_id = account["id"]
        self.tenant_id = account["tenantId"]
        self.user = account["user"]["name"]
        suffix = hashlib.sha1(self.subscription_id.encode()).hexdigest()   # stable for each subscription

        self.location = os.environ.get("AIGW_LOCATION") or "eastus2"
        self.resource_group = os.environ.get("AIGW_RESOURCE_GROUP") or "rg-ai-gateway-labs"
        self.gateway_name = os.environ.get("AIGW_GATEWAY_NAME") or f"aigw-labs-{suffix[:6]}"
        self.own_foundry_account = bool(os.environ.get("AIGW_FOUNDRY_ACCOUNT"))
        self.foundry_account = os.environ.get("AIGW_FOUNDRY_ACCOUNT") or f"aigwlabs{suffix[:8]}"
        self.foundry_resource_group = os.environ.get("AIGW_FOUNDRY_RESOURCE_GROUP") or self.resource_group
        self.tags = {"lab": name, "workload": "ai-gateway-labs"}

        regions = gateway_regions()
        if regions and self.location not in regions:
            sys.exit(f"❌ AI Gateway isn't available in {self.location}. "
                     f"Set AIGW_LOCATION to one of: {', '.join(regions)}.")
        if not re.fullmatch(r"[A-Za-z]([A-Za-z0-9-]{0,22}[A-Za-z0-9])?", self.gateway_name):
            sys.exit("❌ Gateway names use 1 to 24 letters, digits, or hyphens, and start with a letter.")

        subscription = f"/subscriptions/{self.subscription_id}"
        self.gateway_id = (f"{subscription}/resourceGroups/{self.resource_group}"
                           f"/providers/Microsoft.ApiManagement/aigateways/{self.gateway_name}")
        self.workspace_id = f"{self.gateway_id}/workspaces/default"   # models, aliases, and tool servers live here
        self.foundry_id = (f"{subscription}/resourceGroups/{self.foundry_resource_group}"
                           f"/providers/Microsoft.CognitiveServices/accounts/{self.foundry_account}")

        self.credential = AzureCliCredential()   # every client reuses your az login
        self._tokens = {}
        self.gateway = None
        self.gateway_url = None
        if needs_gateway:
            self.gateway = self.arm("GET", self.gateway_id)
            if not self.gateway or self.gateway["properties"].get("provisioningState") != "Succeeded":
                sys.exit(f"❌ Gateway {self.gateway_name} not found in {self.resource_group}. "
                         "Run 01-provision-gateway.ipynb first.")
            self.gateway_url = "https://" + self.gateway["properties"]["frontend"]["defaultHostname"]

        print(f"🧪 Lab:            {name}")
        print(f"👤 User:           {self.user}")
        print(f"🔑 Subscription:   {account['name']} ({self.subscription_id})")
        print(f"🌍 Region:         {self.location}")
        print(f"📁 Resource group: {self.resource_group}")
        print(f"🚪 Gateway:        {self.gateway_name}")
        if self.gateway_url:
            print(f"🌐 Runtime URL:    {self.gateway_url}")

    # Azure Resource Manager -------------------------------------------------------------------------------------

    def token(self, scope: str = f"{ARM}/.default") -> str:
        """Return a cached Microsoft Entra access token for the scope. Never print it."""
        cached = self._tokens.get(scope)
        if cached is None or cached.expires_on - time.time() < 300:
            cached = self._tokens[scope] = self.credential.get_token(scope)
        return cached.token

    def arm(self, method: str, path: str, body=None, api_version: str = AIGW_API, params=None):
        """Call Azure Resource Manager and return the JSON body, or None when a GET or DELETE finds nothing."""
        response = requests.request(method, ARM + path, json=body, timeout=120,
                                    params={"api-version": api_version, **(params or {})},
                                    headers={"Authorization": f"Bearer {self.token()}"})
        if response.status_code == 404 and method in ("GET", "DELETE"):
            return None
        if not response.ok:
            raise RuntimeError(f"{method} {path} -> {response.status_code}: {response.text[:1000]}")
        return response.json() if response.content else {}

    def require(self, path: str, hint: str, api_version: str = AIGW_API):
        """Return the resource at path, or stop the notebook with a hint when it doesn't exist."""
        resource = self.arm("GET", path, api_version=api_version)
        if resource is None:
            sys.exit(f"❌ {path.rsplit('/', 2)[-2]}/{path.rsplit('/', 1)[-1]} not found. {hint}")
        return resource

    def delete(self, path: str, api_version: str = AIGW_API, wait: bool = False):
        """Delete a resource. With wait=True, poll until it's gone (gateways take about 10 minutes)."""
        name = path.rsplit("/", 1)[-1]
        if self.arm("DELETE", path, api_version=api_version) is None:
            print(f"♻️ {name} was already deleted")
            return
        while wait and self.arm("GET", path, api_version=api_version):
            print(f"⏳ Deleting {name}...")
            time.sleep(30)
        print(f"🗑️ Deleted {name}")

    def delete_foundry_account(self):
        """Delete the lab's Foundry account, then purge it so the name is free again and nothing is billed."""
        if self.own_foundry_account:
            print(f"ℹ️ Kept {self.foundry_account}: you brought it with AIGW_FOUNDRY_ACCOUNT")
            return
        self.delete(self.foundry_id, api_version=COGNITIVE_API)
        deleted = (f"/subscriptions/{self.subscription_id}/providers/Microsoft.CognitiveServices"
                   f"/locations/{self.location}/resourceGroups/{self.foundry_resource_group}"
                   f"/deletedAccounts/{self.foundry_account}")
        for _ in range(30):   # the soft-deleted account takes a few seconds to appear
            if self.arm("GET", deleted, api_version=COGNITIVE_API):
                self.arm("DELETE", deleted, api_version=COGNITIVE_API)
                print(f"🚮 Purged {self.foundry_account}")
                return
            time.sleep(10)
        print(f"🚨 {self.foundry_account} isn't in the soft-deleted list yet. Purge it later in the Azure portal.")

    def register_providers(self, *namespaces: str):
        """Register resource providers once per subscription. Registration takes a minute or two."""
        for namespace in namespaces:
            path = f"/subscriptions/{self.subscription_id}/providers/{namespace}"
            state = self.arm("GET", path, api_version=RESOURCES_API)["registrationState"]
            if state == "Registered":
                print(f"♻️ {namespace} is registered")
                continue
            print(f"📦 Registering {namespace} ({state})")
            self.arm("POST", f"{path}/register", api_version=RESOURCES_API)
            for _ in range(60):
                state = self.arm("GET", path, api_version=RESOURCES_API)["registrationState"]
                if state == "Registered":
                    break
                time.sleep(10)
            assert state == "Registered", f"{namespace} is {state}"
            print(f"✅ {namespace} registered")

    def create_resource_group(self, name: str | None = None):
        """Create the resource group, tagged for clean-up, unless it exists."""
        name = name or self.resource_group
        path = f"/subscriptions/{self.subscription_id}/resourcegroups/{name}"
        group = self.arm("GET", path, api_version=RESOURCES_API)
        if group:
            print(f"♻️ Resource group {name} exists in {group['location']}")
        else:
            self.arm("PUT", path, {"location": self.location, "tags": self.tags}, api_version=RESOURCES_API)
            print(f"✅ Created resource group {name} in {self.location}")

    # Bicep deployments -----------------------------------------------------------------------------------------

    def deploy(self, template: str, resource_group: str | None = None, timeout_minutes: int = 30, **parameters):
        """Deploy a Bicep file with `az deployment group create` and return its outputs as a dict.

        Pass the template's parameters as keyword arguments. The cell shows progress while Azure Resource Manager
        creates the resources, and the error details if the deployment fails. Deployments are idempotent: running
        the cell again updates the same resources.
        """
        template_path = Path(template)
        if not template_path.exists():
            raise FileNotFoundError(f"{template} not found. Run the notebook from its lab folder.")
        group = resource_group or self.resource_group
        name = f"{self.name}-{template_path.stem}"[:64]
        parameter_file = {
            "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
            "contentVersion": "1.0.0.0",
            "parameters": {key: {"value": value} for key, value in parameters.items()},
        }
        with tempfile.NamedTemporaryFile("w", suffix=".parameters.json", delete=False) as file:
            json.dump(parameter_file, file)
        print(f"🚀 Deploying {template_path.as_posix()} to {group}")
        start = time.time()
        try:
            az("deployment", "group", "create", "-g", group, "-n", name, "-f", str(template_path),
               "-p", f"@{file.name}", "--no-wait")
        finally:
            os.unlink(file.name)

        path = (f"/subscriptions/{self.subscription_id}/resourceGroups/{group}"
                f"/providers/Microsoft.Resources/deployments/{name}")
        while True:
            deployment = self.arm("GET", path, api_version=RESOURCES_API)
            state = deployment["properties"]["provisioningState"] if deployment else "Accepted"
            elapsed = int(time.time() - start)
            if state == "Succeeded":
                break
            if state in ("Failed", "Canceled"):
                raise RuntimeError(f"Deployment {name} {state.lower()}:\n" + "\n".join(self._failures(path)))
            if elapsed > timeout_minutes * 60:
                raise TimeoutError(f"Deployment {name} is still {state} after {timeout_minutes} minutes.")
            pending = [op for op in self._operations(path) if op[2] != "Succeeded"]
            waiting = ", ".join(f"{kind} {resource}" for kind, resource, _ in pending[:3]) or state
            print(f"⏳ {elapsed:>4} s  {waiting}")
            time.sleep(15)

        print(f"✅ Deployed {template_path.name} in {elapsed} s")
        return {key: value["value"] for key, value in (deployment["properties"].get("outputs") or {}).items()}

    def _operations(self, deployment_path: str):
        """Return (type, name, state) for each resource in a deployment."""
        found = self.arm("GET", f"{deployment_path}/operations", api_version=RESOURCES_API) or {"value": []}
        operations = []
        for operation in found["value"]:
            target = operation["properties"].get("targetResource") or {}
            if target.get("resourceType"):
                kind = target["resourceType"].split("/")[-1]
                operations.append((kind, target.get("resourceName", "").split("/")[-1],
                                   operation["properties"]["provisioningState"]))
        return operations

    def _failures(self, deployment_path: str):
        """Return readable error messages for the failed operations of a deployment."""
        def messages(error):
            details = error.get("details") or []
            if not details:
                yield f"{error.get('code')}: {error.get('message')}"
            for detail in details:
                yield from messages(detail)

        found = self.arm("GET", f"{deployment_path}/operations", api_version=RESOURCES_API) or {"value": []}
        lines = []
        for operation in found["value"]:
            props = operation["properties"]
            if props["provisioningState"] == "Failed":
                target = (props.get("targetResource") or {}).get("resourceName", "deployment")
                error = (props.get("statusMessage") or {}).get("error") or props.get("statusMessage") or {}
                lines += [f"❌ {target}: {message}" for message in messages(error)]
        return lines or ["❌ See the deployment in the Azure portal for details."]

    # Gateway helpers ---------------------------------------------------------------------------------------------

    def api_key(self, name: str):
        """Return (value, created) for a runtime API key, creating the key if it's missing."""
        key_id = f"{self.gateway_id}/apiKeys/{name}"
        created = self.arm("GET", key_id) is None
        if created:
            self.arm("PUT", key_id, {"properties": {}})
        return self.arm("POST", f"{key_id}/listSecrets")["primaryKey"], created

    def signed_in_identity(self):
        """Return the object ID, principal type, and display name of the identity behind az login."""
        me = claims(self.token())
        principal_type = "ServicePrincipal" if me.get("idtyp") == "app" else "User"
        return me["oid"], principal_type, me.get("upn") or me.get("unique_name") or me.get("appid")

    def role_assignments(self, principal_id: str):
        """List the AI Gateway data-plane roles that the principal holds on the gateway, including inherited ones."""
        found = self.arm("GET", f"{self.gateway_id}/providers/Microsoft.Authorization/roleAssignments",
                         api_version=ROLES_API, params={"$filter": f"principalId eq '{principal_id}'"})["value"]
        return [{"id": a["id"], "role": ROLES[a["properties"]["roleDefinitionId"].split("/")[-1]],
                 "scope": a["properties"]["scope"]}
                for a in found if a["properties"]["roleDefinitionId"].split("/")[-1] in ROLES]


# Calls that wait for new configuration to apply ---------------------------------------------------------------------

def retry(call, statuses=(401, 403, 404, 429), minutes: int = 10, wait: int = 30):
    """Run an OpenAI SDK call until it stops failing with one of the statuses or a 5xx, then return its result.

    New keys, models, policies, and role assignments take from seconds to a few minutes to apply.
    """
    from openai import APIStatusError

    deadline = time.time() + minutes * 60
    while True:
        try:
            return call()
        except APIStatusError as error:
            if not (error.status_code in statuses or error.status_code >= 500) or time.time() > deadline:
                raise
            print(f"⏳ HTTP {error.status_code}, waiting for the configuration to apply...")
            time.sleep(wait)


def wait_for_status(check, expected: int, minutes: int = 10, wait: int = 30) -> int:
    """Call check(), which returns an HTTP status, until it returns the expected one or time runs out."""
    deadline = time.time() + minutes * 60
    while True:
        status = check()
        if status == expected or time.time() > deadline:
            return status
        print(f"⏳ HTTP {status}, waiting for {expected}...")
        time.sleep(wait)


def wait_for_endpoint(url: str, attempts: int = 20, wait: int = 15) -> requests.Response:
    """GET a URL, retrying while a brand-new host name doesn't resolve yet."""
    for attempt in range(1, attempts + 1):
        try:
            return requests.get(url, timeout=30)
        except requests.ConnectionError:
            print(f"⏳ Waiting for {url.split('/')[2]} to resolve ({attempt}/{attempts})")
            time.sleep(wait)
    raise TimeoutError(f"{url} didn't answer. Check the gateway in the portal.")


def claims(token: str) -> dict:
    """Decode the payload of a JWT access token. Never print the token itself."""
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


# MCP over Streamable HTTP --------------------------------------------------------------------------------------------

def parse_mcp(response: requests.Response) -> dict:
    """Return the JSON-RPC message from a JSON or server-sent events (SSE) response."""
    if "text/event-stream" in response.headers.get("content-type", ""):
        data = [line[5:].strip() for line in response.text.splitlines() if line.startswith("data:")]
        return json.loads(data[-1]) if data else {}
    return response.json() if response.content else {}


def mcp_session(url: str, key: str):
    """Run initialize and notifications/initialized. Return the headers for later requests and the server info."""
    headers = {"api-key": key, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    init = requests.post(url, headers=headers, timeout=60, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                   "clientInfo": {"name": "aigateway-labs", "version": "1.0"}}})
    init.raise_for_status()
    result = parse_mcp(init)["result"]
    headers["MCP-Protocol-Version"] = result["protocolVersion"]
    if init.headers.get("mcp-session-id"):
        headers["Mcp-Session-Id"] = init.headers["mcp-session-id"]
    requests.post(url, headers=headers, timeout=60, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    return headers, result


def mcp_request(url: str, headers: dict, method: str, params: dict | None = None, id: int = 2) -> dict:
    """Send one JSON-RPC request in an MCP session and return the response message."""
    response = requests.post(url, headers=headers, timeout=120,
                             json={"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}})
    response.raise_for_status()
    return parse_mcp(response)
