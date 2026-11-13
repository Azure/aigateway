"""Where the Azure CLI actually is on this machine.

Every ``az`` subprocess in the tool goes through :func:`az_argv`. On Windows the
CLI is ``az.cmd``, a batch file: ``CreateProcess`` appends only ``.exe`` to a
bare name and never consults ``PATHEXT``, so ``subprocess.run(["az", ...])``
raises ``FileNotFoundError`` there even with the CLI installed and on ``PATH``.
``shutil.which`` does apply ``PATHEXT``, so resolving the name first makes one
argv work on every platform.

Running a batch file means ``cmd.exe`` re-parses the arguments, so nothing with
shell metacharacters should be passed as a scalar flag. The tool already holds
to that: structured payloads and every credential go to ``az`` as ``@file``.
"""

from __future__ import annotations

import shutil

_UNRESOLVED = object()
_cached: object | str | None = _UNRESOLVED


def az_executable(*, refresh: bool = False) -> str | None:
    """The file ``az`` resolves to, or ``None`` when it is not on ``PATH``."""
    global _cached
    if refresh or _cached is _UNRESOLVED:
        _cached = shutil.which("az")
    return _cached  # type: ignore[return-value]


def az_available() -> bool:
    return az_executable() is not None


def az_argv(argv: list[str]) -> list[str]:
    """``argv`` with ``az`` replaced by the file ``PATH`` resolves it to.

    Falls back to the bare name when nothing resolves, so the caller still gets
    the ``FileNotFoundError`` it already handles rather than a different failure.
    """
    if argv and argv[0] == "az":
        return [az_executable() or "az", *argv[1:]]
    return argv


CLI_MISSING = (
    "The Azure CLI ('az') is not on PATH. Install it from "
    "https://aka.ms/azure-cli and run 'az login'."
)
