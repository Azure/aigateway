"""Stable, human-readable identifiers.

Every object in the inventory carries an id derived from its ARM identity, so a
re-collection of an unchanged service produces byte-identical ids and a clean
diff. Agents and the decisions file reference objects by these ids.
"""

from __future__ import annotations

import re

_UNSAFE = re.compile(r"[^A-Za-z0-9._\-/]+")


def _slug(value: str) -> str:
    return _UNSAFE.sub("-", (value or "").strip()).strip("-") or "unnamed"


def scoped(workspace: str | None, name: str) -> str:
    """Prefix a name with its workspace when it is not the implicit default."""
    if workspace and workspace.lower() != "default":
        return f"{_slug(workspace)}/{_slug(name)}"
    return _slug(name)


def api(name: str, workspace: str | None = None) -> str:
    return f"api:{scoped(workspace, name)}"


def backend(name: str, workspace: str | None = None) -> str:
    return f"backend:{scoped(workspace, name)}"


def named_value(name: str, workspace: str | None = None) -> str:
    return f"namedValue:{scoped(workspace, name)}"


def fragment(name: str) -> str:
    return f"policyFragment:{_slug(name)}"


def product(name: str, workspace: str | None = None) -> str:
    return f"product:{scoped(workspace, name)}"


def subscription(name: str, workspace: str | None = None) -> str:
    return f"subscription:{scoped(workspace, name)}"


def certificate(name: str) -> str:
    return f"certificate:{_slug(name)}"


def authorization_server(name: str) -> str:
    return f"authorizationServer:{_slug(name)}"


def openid_provider(name: str) -> str:
    return f"openidProvider:{_slug(name)}"


def credential_provider(name: str) -> str:
    return f"credentialProvider:{_slug(name)}"


def policy(level: str, target: str = "") -> str:
    return f"policy:{_slug(level)}/{_slug(target)}" if target else f"policy:{_slug(level)}"


def asset(kind: str, name: str, workspace: str | None = None) -> str:
    return f"{kind}:{scoped(workspace, name)}"


def secret(kind: str, name: str) -> str:
    return f"secret:{_slug(kind)}/{_slug(name)}"


def expression(digest: str) -> str:
    return f"expr:{digest[:12]}"


def item(subject: str, aspect: str = "") -> str:
    """Stable id for a migration plan item.

    Derived from the asset and the aspect being decided, so an unchanged APIM
    object keeps the same item id across regenerations and a settled decision
    stays attached to it.
    """
    base = _slug(subject.replace(":", "/"))
    return f"item:{base}/{_slug(aspect)}" if aspect else f"item:{base}"


_ARM_URL = re.compile(r"^https?://[^/]+(/subscriptions/.+)$", re.IGNORECASE)


def normalize_arm_id(value: str | None) -> str | None:
    """Reduce a management URL to a bare ARM resource id.

    APIM stores a backend's ``properties.resourceId`` as a *management URI*
    (``https://management.azure.com/subscriptions/...``), while every consumer of
    it -- ARM lookups, and the target's ``deployment.resourceId`` -- wants the
    bare id. Values that are already bare pass through unchanged.
    """
    if not value:
        return value
    match = _ARM_URL.match(value.strip())
    return match.group(1) if match else value


def arm_name(resource_id: str) -> str:
    """Last segment of an ARM resource id."""
    return (resource_id or "").rstrip("/").rsplit("/", 1)[-1]


PORTAL = "https://ai.gateway.azure.com"


def portal_url(resource_id: str | None, page: str = "overview") -> str | None:
    """Deep link to a gateway in the AI Gateway portal.

    An ARM id already starts with a slash, so it is appended to the host as it
    stands -- joining the two with one produces `//subscriptions/...`, which is
    a different path. Returns None for anything that is not an ARM id, so a
    caller never prints a link built from a name or an empty target.
    """
    bare = (normalize_arm_id(resource_id) or "").strip().rstrip("/")
    if not bare.startswith("/subscriptions/"):
        return None
    return f"{PORTAL}{bare}/{page}"


def arm_segment(resource_id: str, segment: str) -> str | None:
    """Value following ``segment`` in an ARM id, case-insensitively."""
    parts = (resource_id or "").strip("/").split("/")
    lowered = [p.lower() for p in parts]
    try:
        index = lowered.index(segment.lower())
    except ValueError:
        return None
    return parts[index + 1] if index + 1 < len(parts) else None
