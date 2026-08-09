#!/usr/bin/env python3
"""Report whether a checkout is ready to run the repository quality gate.

The command is deliberately read-only: it only inspects configuration and runs
version/configuration queries.  Keeping the checks injectable also makes its
diagnostics straightforward to test without depending on a developer machine.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


REQUIRED_COMMANDS = ("mise", "node", "pnpm", "python", "uv", "git")
VERSION_COMMANDS = {
    "node": ("node", "--version"),
    "pnpm": ("pnpm", "--version"),
    "python": ("python", "--version"),
    "uv": ("uv", "--version"),
}
VERSION_PATTERN = re.compile(r"v?(\d+(?:\.\d+){0,2})")


@dataclass(frozen=True)
class Check:
    """One readiness check and its human-readable result."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class CommandResult:
    """The limited command result needed by the checker."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


CommandRunner = Callable[[Sequence[str], Path], CommandResult]
CommandFinder = Callable[[str], str | None]


def run_command(command: Sequence[str], cwd: Path) -> CommandResult:
    """Run a read-only command and return only the fields used by this module."""
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def parse_version(output: str) -> str | None:
    """Extract the first ordinary dotted version from a version command's output."""
    match = VERSION_PATTERN.search(output)
    return match.group(1) if match else None


def read_metadata(root: Path) -> tuple[dict[str, str], dict[str, object]]:
    """Read the tool pins and package metadata required for setup checks."""
    with (root / "mise.toml").open("rb") as mise_file:
        mise_data = tomllib.load(mise_file)
    with (root / "package.json").open(encoding="utf-8") as package_file:
        package_data = json.load(package_file)

    tools = mise_data.get("tools")
    if not isinstance(tools, dict) or not all(
        isinstance(name, str) and isinstance(version, str) for name, version in tools.items()
    ):
        raise ValueError("mise.toml has no valid [tools] table")
    if not isinstance(package_data, dict):
        raise ValueError("package.json must contain an object")
    return tools, package_data


def metadata_checks(tools: dict[str, str], package: dict[str, object]) -> list[Check]:
    """Check the package metadata is consistent with the pinned tool versions."""
    checks: list[Check] = []

    package_manager = package.get("packageManager")
    expected_pnpm = f"pnpm@{tools.get('pnpm', '')}"
    checks.append(
        Check(
            "packageManager",
            package_manager == expected_pnpm,
            f"{package_manager!s}"
            if package_manager == expected_pnpm
            else f"expected {expected_pnpm}",
        )
    )

    engines = package.get("engines")
    node_requirement = engines.get("node") if isinstance(engines, dict) else None
    node_version = parse_version(tools.get("node", ""))
    minimum_match = (
        re.fullmatch(r">=\s*(\d+(?:\.\d+){0,2})", node_requirement)
        if isinstance(node_requirement, str)
        else None
    )
    if node_version is None or minimum_match is None:
        checks.append(Check("node engine", False, "cannot compare package metadata"))
    else:
        minimum = minimum_match.group(1)
        compatible = version_tuple(node_version) >= version_tuple(minimum)
        checks.append(
            Check(
                "node engine",
                compatible,
                f"{node_version} satisfies {node_requirement}"
                if compatible
                else f"{node_version} does not satisfy {node_requirement}",
            )
        )
    return checks


def version_tuple(version: str) -> tuple[int, int, int]:
    """Turn a dotted version into a tuple suitable for simple minimum checks."""
    parts = [int(part) for part in version.split(".")]
    return tuple((parts + [0, 0, 0])[:3])  # type: ignore[return-value]


def version_checks(
    root: Path,
    tools: dict[str, str],
    available: set[str],
    run: CommandRunner,
) -> list[Check]:
    """Compare installed runtime versions with the versions pinned by mise."""
    checks: list[Check] = []
    for command, invocation in VERSION_COMMANDS.items():
        expected = tools.get(command)
        if expected is None:
            checks.append(Check(f"{command} version", False, "not pinned in mise.toml"))
            continue
        if command not in available:
            checks.append(Check(f"{command} version", False, "command is unavailable"))
            continue

        result = run(invocation, root)
        found = parse_version(result.stdout or result.stderr)
        passed = result.returncode == 0 and found == expected
        if result.returncode != 0:
            detail = "version command failed"
        elif found is None:
            detail = "could not parse version"
        elif passed:
            detail = found
        else:
            detail = f"expected {expected}, found {found}"
        checks.append(Check(f"{command} version", passed, detail))
    return checks


def collect_checks(
    root: Path,
    *,
    find_command: CommandFinder = shutil.which,
    run: CommandRunner = run_command,
) -> list[Check]:
    """Collect all readiness checks without changing repository state."""
    checks: list[Check] = []
    available = {command for command in REQUIRED_COMMANDS if find_command(command)}
    checks.extend(
        Check(
            f"command: {command}",
            command in available,
            "found" if command in available else "missing",
        )
        for command in REQUIRED_COMMANDS
    )

    try:
        tools, package = read_metadata(root)
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        checks.append(Check("metadata", False, str(error)))
        return checks

    checks.extend(metadata_checks(tools, package))
    checks.extend(version_checks(root, tools, available, run))
    checks.append(
        Check(
            "node_modules",
            (root / "node_modules").is_dir(),
            "present"
            if (root / "node_modules").is_dir()
            else "missing; run pnpm install --frozen-lockfile",
        )
    )
    checks.append(
        Check(
            ".venv",
            (root / ".venv").is_dir(),
            "present" if (root / ".venv").is_dir() else "missing; run uv sync --frozen",
        )
    )

    if "git" not in available:
        checks.append(Check("git core.hooksPath", False, "git command is unavailable"))
    else:
        hooks_path = run(("git", "config", "--get", "core.hooksPath"), root)
        configured_path = hooks_path.stdout.strip() if hooks_path.returncode == 0 else ""
        checks.append(
            Check(
                "git core.hooksPath",
                configured_path == ".husky/_",
                ".husky/_"
                if configured_path == ".husky/_"
                else "expected .husky/_; run pnpm prepare",
            )
        )
    return checks


def format_report(checks: Sequence[Check]) -> str:
    """Format concise per-check results followed by an overall summary."""
    lines = [
        f"{'PASS' if check.passed else 'FAIL'} {check.name}: {check.detail}" for check in checks
    ]
    failures = sum(not check.passed for check in checks)
    lines.append("Doctor: ready" if failures == 0 else f"Doctor: {failures} check(s) failed")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the setup doctor for the optional repository root argument."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) > 1:
        print("usage: doctor.py [root]", file=sys.stderr)
        return 2

    root = Path(arguments[0]).resolve() if arguments else Path.cwd()
    checks = collect_checks(root)
    print(format_report(checks))
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
