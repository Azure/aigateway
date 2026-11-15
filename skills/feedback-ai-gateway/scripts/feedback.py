"""Anonymize session transcript summaries for product feedback."""

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import sys


MAX_FILE_BYTES = 20 * 1024 * 1024


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
        raise ValueError("Input must be a regular file, not a directory or symlink.")
    with path.open("rb") as stream:
        content = stream.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("Input exceeds the 20 MiB per-file limit.")
    text = content.decode("utf-8")
    if "\x00" in text:
        raise ValueError("Binary input is not supported; provide a UTF-8 summary export.")
    return text, len(content)


def anonymize_summary(*, summary_file, output, sensitive_values=()):
    """Anonymize a session summary and write it to output."""
    scrubber = Anonymizer(sensitive_values)
    text, _ = read_text(Path(summary_file))
    text = scrubber.scrub(text)

    output = Path(output)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(text.encode("utf-8"))
    except BaseException:
        output.unlink()
        raise
    return output, len(scrubber.tokens)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-file", type=Path, required=True,
                        help="Session summary file (friction, tasks, outcomes)")
    parser.add_argument("--output", type=Path, required=True,
                        help="Anonymized output file path")
    parser.add_argument(
        "--sensitive-values-file", type=Path,
        help="Local UTF-8 JSON array of additional literal strings to replace; never included in output.",
    )
    args = parser.parse_args()
    try:
        values = []
        if args.sensitive_values_file:
            values = json.loads(read_text(args.sensitive_values_file)[0])
            if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
                raise ValueError("Sensitive values must be a JSON array of nonempty strings.")
        output, replacements = anonymize_summary(
            summary_file=args.summary_file, output=args.output,
            sensitive_values=values,
        )
    except (OSError, ValueError, UnicodeError) as error:
        print(f"Anonymization failed: {error}", file=sys.stderr)
        return 1
    print(f"Anonymized summary: {output.resolve()}")
    print(f"Sensitive values masked: {replacements}")
    print("Nothing uploaded. Review before sharing; automated scrubbing is not a guarantee.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
