"""Shared contracts and protected local state for the migration adapter."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
import rfc8785


ROOT = Path(__file__).resolve().parents[1]
TOOL_VERSION = "1.0.0"
FILES = (
    "source-inventory.json", "model-catalog.json", "destination-inventory.json", "capability-contract.json",
    "mapping.json", "todos.json", "plan-validation.json", "migration-plan.md",
    "migration-report.md",
)
SECRET = re.compile(
    r"secret|password|credential|connectionstring|authorization|privatekey|primarykey|"
    r"secondarykey|accesskey|apikey|certificatebody|^token$|accesstoken|refreshtoken|"
    r"idtoken|sastoken|signature|pfx|^key$", re.I
)
RID = re.compile(
    r"^/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/"
    r"Microsoft\.ApiManagement/(service|aigateways)/([^/]+)$", re.I
)
GATEWAY_TYPE = "Microsoft.ApiManagement/aigateways"


class MigrationError(Exception):
    """A fail-closed, safe-to-display operational error."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    try:
        content = rfc8785.dumps(value)
    except rfc8785.CanonicalizationError as exc:
        raise MigrationError("JSON is outside the supported canonical numeric/string domain.") from exc
    return "sha256:" + hashlib.sha256(content).hexdigest()


def read_json(path):
    path = Path(path)
    safe_path(path)
    if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
        raise MigrationError("Expected a regular JSON file no larger than 32 MiB.")
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda _: invalid_json(),
                          object_pairs_hook=unique_keys)
    except (ValueError, UnicodeError) as exc:
        raise MigrationError("Malformed JSON input.") from exc


def invalid_json():
    raise MigrationError("Non-finite JSON numbers are not supported.")


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MigrationError("Duplicate JSON object keys are not supported.")
        result[key] = value
    return result


def safe_path(path):
    path = Path(path).absolute()
    if ".." in path.parts:
        raise MigrationError("Parent traversal is not allowed in state or evidence paths.")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise MigrationError("Symlinked state or evidence paths are not allowed.")
        if part.exists() and getattr(part.lstat(), "st_file_attributes", 0) & getattr(
                stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise MigrationError("Reparse-point state or evidence paths are not allowed.")
    return path


def resource_id(value, resource_type="service"):
    match = RID.fullmatch(value)
    if not match or (resource_type and match.group(3).lower() != resource_type) or any(
            c in value for c in ("?", "#", "%", "\\", "..")) or any(
            not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in match.groups()):
        expected = resource_type or "service or aigateways"
        raise MigrationError(f"Expected a complete Microsoft.ApiManagement/{expected} ARM resource ID.")
    return dict(zip(("subscription", "resourceGroup", "gateway"),
                    (match.group(1), match.group(2), match.group(4))))


def child_resource_id(value, parent):
    return (isinstance(value, str) and value.lower().startswith(parent.lower() + "/")
            and not any(part in value for part in ("?", "#", "%", "\\", "..", "//")))


def clean(value, key=""):
    """Redact before persistence, including XML and URLs embedded in errors."""
    if key == "secret" and isinstance(value, bool):
        return value
    if key.replace("_", "").replace("-", "").lower() == "apikey" and isinstance(value, dict):
        header = value.get("headerName")
        if isinstance(header, str) and re.fullmatch(r"[A-Za-z0-9-]+", header):
            return {"headerName": header, "value": {"redacted": True}}
    if key == "credentials" and isinstance(value, dict) and value.get("type") in (
            "none", "header", "managedIdentity", "oauth2"):
        return {"type": value["type"]}
    if SECRET.search(key.replace("-", "").replace("_", "")):
        return {"redacted": True}
    if key.lower() in ("value", "content", "headers", "query", "queryparameters", "data"):
        return {"redacted": True}
    if isinstance(value, dict):
        return {k: clean(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v, key) for v in value]
    if isinstance(value, str):
        if "<" in value or re.search(r"(?i)(bearer\s|[?&](sig|token|key)=|"
                                     r"(api[-_]?key|password|secret|token)\s*[=:])", value):
            return {"redacted": True}
        if value.startswith(("https://", "http://")):
            url = urlsplit(value)
            if url.username or url.password:
                return {"redacted": True}
            return urlunsplit((url.scheme, url.netloc, url.path,
                               urlencode([(k, "[redacted]") for k, _ in
                                          parse_qsl(url.query)]), ""))
    return value


def semantic(value):
    if isinstance(value, dict):
        return {k: semantic(v) for k, v in value.items()
                if k.lower() not in ("etag", "systemdata", "capturedat", "timestamp")}
    if isinstance(value, list):
        return [semantic(v) for v in value]
    return value


def subset(expected, actual):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and subset(v, actual[k]) for k, v in expected.items()
        )
    return expected == actual


def validate_schema(value, name):
    schemas = [read_json(path) for path in (ROOT / "schemas").glob("*.schema.json")]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    schema = read_json(ROOT / "schemas" / f"{name}.schema.json")
    errors = sorted(Draft202012Validator(
        schema, registry=registry, format_checker=FormatChecker()
    ).iter_errors(value), key=lambda error: str(list(error.path)))
    if errors:
        error = errors[0]
        # Schema error messages can include rejected secret input.
        raise MigrationError(f"Invalid {name} document at /{'/'.join(map(str, error.path))}.")


def cli_failure_code(stderr):
    """Recognize only a structured/CLI error code, never a resource-name substring."""
    code = "MethodNotAllowedInPricingTier"
    if re.search(r"\b(Forbidden|Unauthorized|AuthorizationFailed|AuthenticationFailed|InvalidAuthenticationToken|401|403)\b",
                 stderr, re.I):
        return None
    if re.search(r"^ERROR:\s*(?:\([A-Za-z]+\)\s*)?A stale model is still targeted by an alias\.", stderr, re.M):
        return "SyncAliasBoundStale"
    if re.search(r"^ERROR:\s*\(" + code + r"\)", stderr, re.M):
        return code
    start = stderr.find("{")
    if start >= 0:
        try:
            body, _ = json.JSONDecoder(object_pairs_hook=unique_keys).raw_decode(stderr[start:])
            error = body.get("error") if isinstance(body, dict) else None
            if isinstance(error, dict) and error.get("code") == code:
                return code
        except (ValueError, MigrationError):
            pass
    return None


def run_az(args):
    if not args or args[0] != "az":
        raise MigrationError("Only Azure CLI argv templates are executable.")
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=180,
                                check=False)
    except subprocess.TimeoutExpired as exc:
        raise MigrationError("Azure CLI timed out; the outcome may be unknown.") from exc
    except OSError as exc:
        raise MigrationError("Azure CLI could not be started.") from exc
    if result.returncode:
        # Never expose stderr: CLI failures can echo expanded credentials.
        raise MigrationError(f"Azure CLI failed (exit {result.returncode}); "
                             "read/operation is inconclusive. Review securely.", code=cli_failure_code(result.stderr))
    try:
        return json.loads(result.stdout, parse_constant=lambda _: invalid_json(),
                          object_pairs_hook=unique_keys)
    except ValueError as exc:
        raise MigrationError("Azure CLI returned non-JSON output.") from exc


def write_new(path, value):
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    text = value if isinstance(value, str) else json.dumps(value, indent=2) + "\n"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise MigrationError("Output already exists; preserve the baseline and choose a new file.") from exc
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
        output.write(text)
        output.flush()
        os.fsync(output.fileno())


def artifact_digest(name, value):
    if name.endswith(".md"):
        content = value.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        return "sha256:" + hashlib.sha256(content).hexdigest()
    return digest(value)


def sync_directory(path):
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class State:
    """Immutable generations with an atomically replaced regular-file pointer."""

    def __init__(self, path):
        self.path = safe_path(path)

    @contextmanager
    def locked(self, create=False):
        if create:
            self.path.mkdir(parents=True, exist_ok=False, mode=0o700)
            (self.path / "generations").mkdir(mode=0o700)
        if not self.path.is_dir():
            raise MigrationError("Migration workspace does not exist.")
        lock = safe_path(self.path / "LOCK")
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise MigrationError("Workspace is locked; inspect the owning process before recovery.") from exc
        try:
            with os.fdopen(fd, "w") as output:
                output.write(str(os.getpid()))
            yield
        finally:
            lock.unlink()

    def load(self):
        pointer = safe_path(self.path / "CURRENT")
        if not pointer.is_file():
            raise MigrationError("No committed generation; legacy state is read-only.")
        generation = pointer.read_text(encoding="utf-8").strip()
        try:
            if str(uuid.UUID(generation)) != generation:
                raise ValueError
        except ValueError as exc:
            raise MigrationError("Invalid generation pointer.") from exc
        directory = safe_path(self.path / "generations" / generation)
        context = read_json(directory / "context.json")
        if context.get("schemaVersion") != "4.0":
            raise MigrationError("Legacy checkpoint is read-only; initialize a fresh version-4 workspace from current evidence.")
        validate_schema(context, "context")
        bundle = {name: (read_json(directory / name) if name.endswith(".json")
                         else safe_path(directory / name).read_text(encoding="utf-8")) for name in FILES}
        manifest = digest({"generationId": generation, "artifacts": {
            name: artifact_digest(name, value) for name, value in bundle.items()}})
        if context["generationId"] != generation or context["manifestDigest"] != manifest:
            raise MigrationError("Incomplete or modified checkpoint; preserve it for recovery.")
        bundle["context.json"] = context
        for name in ("mapping", "todos", "source-inventory", "model-catalog", "destination-inventory", "capability-contract",
                     "plan-validation"):
            validate_schema(bundle[name + ".json"], name)
        return bundle

    def save(self, bundle):
        generation = str(uuid.uuid4())
        context = bundle["context.json"]
        context["generationId"] = generation
        context["manifestDigest"] = digest({"generationId": generation, "artifacts": {
            name: artifact_digest(name, bundle[name]) for name in FILES}})
        for name in ("context", "mapping", "todos", "source-inventory", "model-catalog", "destination-inventory",
                     "capability-contract", "plan-validation"):
            validate_schema(bundle[f"{name}.json"], name)
        directory = safe_path(self.path / "generations" / generation)
        directory.mkdir(mode=0o700)
        for name in FILES:
            write_new(directory / name, bundle[name])
        write_new(directory / "context.json", context)
        sync_directory(directory)
        sync_directory(self.path / "generations")
        candidate = self.path / f"CURRENT.{generation}"
        write_new(candidate, generation + "\n")
        os.replace(candidate, self.path / "CURRENT")
        sync_directory(self.path)
