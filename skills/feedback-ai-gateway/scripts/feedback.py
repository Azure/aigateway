"""Create a local feedback archive from explicitly selected UTF-8 session exports."""

import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import zipfile


MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024


class Anonymizer:
    """Best-effort scrubbing; semantic review is still required before sharing."""

    def __init__(self, sensitive_values=()):
        self.tokens = {}
        self.sensitive_values = sorted(set(sensitive_values), key=len, reverse=True)

    def token(self, value, kind):
        key = (kind, value)
        if key not in self.tokens:
            self.tokens[key] = f"[{kind}_{len(self.tokens) + 1}]"
        return self.tokens[key]

    def scrub(self, text):
        for value in self.sensitive_values:
            text = text.replace(value, self.token(value, "PRIVATE"))
        text = re.sub(
            r"-----BEGIN [^\r\n]*PRIVATE KEY-----.*?-----END [^\r\n]*PRIVATE KEY-----",
            lambda match: self.token(match[0], "SECRET"),
            text,
            flags=re.DOTALL,
        )
        text = re.sub(
            r"""(?ix)(["']?(?:authorization|proxy-authorization|api[-_]?key|"""
            r"""x-api-key|ocp-apim-subscription-key|password|passwd|secret|"""
            r"""client[-_]?secret|access[-_]?token|refresh[-_]?token|"""
            r"""accountkey|sharedaccesssignature|sig)["']?\s*[:=]\s*)"""
            r"""(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;}\r\n]+(?:[ \t]+[^\s,;}\r\n]+)?)""",
            lambda match: match[1] + self.token(match[0][len(match[1]):], "SECRET"),
            text,
        )
        patterns = (
            ("SECRET", r"(?i)\bBearer\s+[A-Za-z0-9._~+/\-=]+"),
            ("SECRET", r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
            ("SECRET", r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]+)\b"),
            ("RESOURCE", r"(?i)/subscriptions/[^\s\"'<>]+"),
            ("URL", r"(?i)\b(?:https?|wss?)://[^\s\"'<>]+"),
            ("EMAIL", r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
            ("ID", r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
            ("PATH", r"""(?i)(?:[A-Z]:[\\/]|/(?:home|Users|root|tmp|var|mnt|workspace|workspaces)/)[^\s"'<>]+"""),
        )
        for kind, pattern in patterns:
            text = re.sub(pattern, lambda match: self.token(match[0], kind), text)
        text = re.sub(
            r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])",
            self.scrub_ip,
            text,
        )
        text = re.sub(
            r"(?<![\w:])(?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F:.]*(?![\w:])",
            self.scrub_ip,
            text,
        )
        return text

    def scrub_ip(self, match):
        try:
            ipaddress.ip_address(match[0])
        except ValueError:
            return match[0]
        return self.token(match[0], "IP")


def read_text(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Inputs must be regular files, not directories or symlinks.")
    with path.open("rb") as stream:
        content = stream.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("An input exceeds the 20 MiB per-file limit.")
    text = content.decode("utf-8")
    if "\x00" in text:
        raise ValueError("Binary input is not supported; provide a UTF-8 session export.")
    return text, len(content)


def create_bundle(*, session_files, context_files, output, agent, sharing,
                  anonymize=False, sensitive_values=()):
    if sharing == "issue" and not anonymize:
        raise ValueError("Issue bundles require --anonymize and subsequent human review.")
    scrubber = Anonymizer(sensitive_values)
    entries = {}
    total = 0
    for kind, paths in (("session", session_files), ("context", context_files)):
        for index, path in enumerate(paths, 1):
            text, size = read_text(Path(path))
            total += size
            if total > MAX_TOTAL_BYTES:
                raise ValueError("Selected inputs exceed the 50 MiB total limit.")
            if anonymize:
                text = scrubber.scrub(text)
            entries[f"{kind}-{index:03d}.txt"] = text.encode("utf-8")
    if not session_files:
        raise ValueError("Select at least one session export.")
    manifest = {
        "schemaVersion": 1,
        "agent": agent,
        "createdUtc": datetime.now(timezone.utc).isoformat(),
        "sharing": sharing,
        "anonymization": "automated-scrub-review-required" if anonymize else "none",
        "reviewRequired": True,
        "files": [
            {"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in entries.items()
        ],
    }
    entries["manifest.json"] = json.dumps(manifest, indent=2).encode("utf-8")
    entries["REVIEW.txt"] = (
        "This archive was created locally. Nothing has been uploaded.\n"
        "Inspect every file before sharing. Automated scrubbing is not proof of anonymity.\n"
        "Free-text identities, source code, customer data, and unusual secrets may remain.\n"
        "For GitHub issues, semantically anonymize the session and review the final ZIP,\n"
        "issue title, body, and attachments. Never attach an original/private bundle.\n"
    ).encode("utf-8")
    output = Path(output)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in entries.items():
                    info = zipfile.ZipInfo(name)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 3
                    info.external_attr = 0o100600 << 16
                    archive.writestr(info, data)
    except BaseException:
        output.unlink()
        raise
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-file", type=Path, action="append", required=True)
    parser.add_argument("--context-file", type=Path, action="append", default=[])
    parser.add_argument("--agent", choices=("copilot", "claude", "gemini", "cursor", "other"), required=True)
    parser.add_argument("--sharing", choices=("private", "issue"), default="private")
    parser.add_argument("--anonymize", action="store_true")
    parser.add_argument(
        "--sensitive-values-file", type=Path,
        help="Local UTF-8 JSON array of additional literal strings to replace; never bundled.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        values = []
        if args.sensitive_values_file:
            if not args.anonymize:
                raise ValueError("--sensitive-values-file requires --anonymize.")
            values = json.loads(read_text(args.sensitive_values_file)[0])
            if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
                raise ValueError("Sensitive values must be a JSON array of nonempty strings.")
        output = create_bundle(
            session_files=args.session_file, context_files=args.context_file,
            output=args.output, agent=args.agent, sharing=args.sharing,
            anonymize=args.anonymize, sensitive_values=values,
        )
    except (OSError, ValueError, UnicodeError) as error:
        print(f"Feedback bundle failed: {error}", file=sys.stderr)
        return 1
    print(f"Local feedback ZIP: {output.resolve()}")
    print("Nothing uploaded. Review the archive before sharing; automated scrubbing is not a guarantee.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
