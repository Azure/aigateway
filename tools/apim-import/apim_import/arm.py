"""Minimal Azure Resource Manager client.

Credentials come from the Azure CLI (``az account get-access-token``) so the tool
inherits the operator's login, tenant, and cloud without any extra dependency.
HTTP goes through ``urllib`` rather than ``az rest`` so that status codes, paging
headers, and error bodies stay intact.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterable

DEFAULT_ENDPOINT = "https://management.azure.com"
RETRY_STATUSES = {408, 429, 500, 502, 503, 504}


class ArmError(RuntimeError):
    """A request failed in a way the caller cannot recover from."""

    def __init__(self, message: str, *, status: int | None = None, url: str = "", body: Any = None):
        super().__init__(message)
        self.status = status
        self.url = url
        self.body = body


@dataclass
class ArmResponse:
    status: int
    body: Any
    text: str
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class ArmClient:
    """Reads ARM. Never writes, and never calls a ``list*`` secret action."""

    def __init__(
        self,
        *,
        subscription: str | None = None,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: int = 90,
        max_retries: int = 4,
        user_agent: str = "apim-import/0.1",
    ) -> None:
        self.subscription = subscription
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = user_agent
        self._token: str | None = None
        self._token_expiry: float = 0.0
        self.call_count = 0

    # ---------------------------------------------------------------- auth

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 120:
            return self._token
        cmd = [
            "az", "account", "get-access-token",
            "--resource", self.endpoint,
            "--output", "json",
            "--only-show-errors",
        ]
        if self.subscription:
            cmd += ["--subscription", self.subscription]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except FileNotFoundError as exc:  # pragma: no cover - environment dependent
            raise ArmError("The Azure CLI ('az') is not on PATH. Install it and run 'az login'.") from exc
        if proc.returncode != 0:
            raise ArmError(
                "Could not acquire an ARM token from the Azure CLI. Run 'az login' "
                f"(and 'az account set -s <subscription>') first.\n{proc.stderr.strip()}"
            )
        payload = json.loads(proc.stdout)
        self._token = payload["accessToken"]
        expires_on = payload.get("expires_on") or payload.get("expiresOn")
        try:
            self._token_expiry = float(expires_on)
        except (TypeError, ValueError):
            self._token_expiry = time.time() + 1800
        return self._token

    # ------------------------------------------------------------ requests

    def request(
        self,
        method: str,
        url: str,
        *,
        api_version: str | None = None,
        params: dict[str, str] | None = None,
        accept: str = "application/json",
    ) -> ArmResponse:
        full = self._build_url(url, api_version, params)
        attempt = 0
        while True:
            attempt += 1
            req = urllib.request.Request(full, method=method.upper())
            req.add_header("Authorization", f"Bearer {self._access_token()}")
            req.add_header("Accept", accept)
            req.add_header("User-Agent", self.user_agent)
            try:
                self.call_count += 1
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    return ArmResponse(resp.status, _maybe_json(raw), raw, dict(resp.headers))
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                response = ArmResponse(exc.code, _maybe_json(raw), raw, dict(exc.headers or {}))
                if exc.code in RETRY_STATUSES and attempt <= self.max_retries:
                    time.sleep(_retry_delay(response, attempt))
                    continue
                return response
            except urllib.error.URLError as exc:
                if attempt <= self.max_retries:
                    time.sleep(min(2 ** attempt, 20))
                    continue
                raise ArmError(f"Network error calling {full}: {exc.reason}", url=full) from exc

    def _build_url(self, url: str, api_version: str | None, params: dict[str, str] | None) -> str:
        if not url.startswith("http"):
            url = f"{self.endpoint}/{url.lstrip('/')}"
        query = dict(params or {})
        if api_version:
            query.setdefault("api-version", api_version)
        if not query:
            return url
        split = urllib.parse.urlsplit(url)
        existing = dict(urllib.parse.parse_qsl(split.query))
        existing.update(query)
        return urllib.parse.urlunsplit(
            (split.scheme, split.netloc, split.path, urllib.parse.urlencode(existing), split.fragment)
        )

    # ------------------------------------------------------------- helpers

    def get(self, url: str, api_version: str, **params: str) -> ArmResponse:
        return self.request("GET", url, api_version=api_version, params=params or None)

    def get_json(self, url: str, api_version: str, **params: str) -> dict | None:
        """Return the resource body, or ``None`` when ARM reports 404."""
        resp = self.get(url, api_version, **params)
        if resp.status == 404:
            return None
        if not resp.ok:
            raise ArmError(_error_message(resp), status=resp.status, url=url, body=resp.body)
        return resp.body if isinstance(resp.body, dict) else None

    def list(self, url: str, api_version: str, **params: str) -> list[dict]:
        """Follow ``nextLink`` to the end of a collection."""
        items: list[dict] = []
        resp = self.get(url, api_version, **params)
        while True:
            if resp.status == 404:
                return items
            if not resp.ok:
                raise ArmError(_error_message(resp), status=resp.status, url=url, body=resp.body)
            body = resp.body if isinstance(resp.body, dict) else {}
            items.extend(body.get("value") or [])
            next_link = body.get("nextLink")
            if not next_link:
                return items
            resp = self.request("GET", next_link)

    def get_policy(self, scope_url: str, api_version: str, policy_name: str = "policy") -> dict | None:
        """Return ``{"format": ..., "value": <xml>}`` or ``None`` when unset.

        ``format=rawxml`` keeps policy expressions exactly as authored; the JSON
        ``Accept`` header keeps the envelope instead of a bare XML document.
        """
        url = f"{scope_url.rstrip('/')}/policies/{policy_name}"
        resp = self.request(
            "GET", url, api_version=api_version, params={"format": "rawxml"}, accept="application/json"
        )
        if resp.status == 404:
            return None
        if not resp.ok:
            raise ArmError(_error_message(resp), status=resp.status, url=url, body=resp.body)
        if isinstance(resp.body, dict):
            return resp.body.get("properties") or None
        return {"format": "rawxml", "value": resp.text}


def _maybe_json(raw: str) -> Any:
    raw = raw.lstrip("﻿").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _retry_delay(resp: ArmResponse, attempt: int) -> float:
    retry_after = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
    if retry_after:
        try:
            return min(float(retry_after), 60.0)
        except ValueError:
            pass
    return min(2 ** attempt, 20)


def _error_message(resp: ArmResponse) -> str:
    if isinstance(resp.body, dict):
        error = resp.body.get("error") or {}
        code = error.get("code") or "Unknown"
        message = error.get("message") or resp.text[:400]
        return f"{resp.status} {code}: {message}"
    return f"{resp.status}: {resp.text[:400]}"


def newest_api_version(
    namespace: str, resource_type: str, *, prefer_stable: bool = True, timeout: int = 30
) -> str | None:
    """Ask the Azure CLI which API versions a resource type exposes.

    Returns ``None`` rather than blocking when the CLI is slow or absent, so a
    caller always has a documented default to fall back to.
    """
    cmd = [
        "az", "provider", "show", "--namespace", namespace,
        "--query", f"resourceTypes[?resourceType=='{resource_type}'].apiVersions | [0]",
        "--output", "json", "--only-show-errors",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired):  # pragma: no cover
        return None
    if proc.returncode != 0:
        return None
    try:
        versions: Iterable[str] = json.loads(proc.stdout) or []
    except json.JSONDecodeError:
        return None
    versions = list(versions)
    if prefer_stable:
        stable = [v for v in versions if "preview" not in v]
        if stable:
            return sorted(stable)[-1]
    return versions[0] if versions else None
