#!/usr/bin/env python3
"""Report whether a checkout is ready to run the repository quality gate.

The command is deliberately read-only: it only inspects configuration and runs
version/configuration queries.  Keeping the checks injectable also makes its
diagnostics straightforward to test without depending on a developer machine.
"""

from __future__ import annotations

import json
import os
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
NODE_DEPENDENCY = "vitest"
PYTHON_DEPENDENCY = "pytest"
HUSKY_GENERATED_HOOK = Path(".husky/_/pre-commit")
HUSKY_LAUNCHER = Path(".husky/_/h")
HUSKY_SOURCE_HOOK = Path(".husky/pre-commit")
HUSKY_SOURCE_COMMAND = "mise exec -- pnpm ready"
HUSKY_HOOK_LAUNCHER_PATTERN = re.compile(
    r"""(?mx)
    ^\s*(?:\.|source)\s+
    ["']?\$\(\s*dirname\b[^)\n]*\$0[^)\n]*\)/h["']?\s*$
    """
)
HUSKY_LAUNCHER_NAME_PATTERN = re.compile(r"(?m)^\s*n\s*=[^\n]*\$0")
HUSKY_LAUNCHER_PATH_PATTERN = re.compile(r"(?m)^\s*s\s*=[^\n]*\$n\b")
HUSKY_LAUNCHER_COMMAND_PATTERN = re.compile(
    r"""(?m)^\s*sh\s+-e\s+["']?\$s["']?\s+["']?\$@["']?\s*$"""
)


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


def read_metadata(root: Path) -> tuple[dict[str, str], dict[str, object], dict[str, object]]:
    """Read the tool and dependency metadata required for setup checks."""
    with (root / "mise.toml").open("rb") as mise_file:
        mise_data = tomllib.load(mise_file)
    with (root / "package.json").open(encoding="utf-8") as package_file:
        package_data = json.load(package_file)
    with (root / "pyproject.toml").open("rb") as pyproject_file:
        project_data = tomllib.load(pyproject_file)

    tools = mise_data.get("tools")
    if not isinstance(tools, dict) or not all(
        isinstance(name, str) and isinstance(version, str) for name, version in tools.items()
    ):
        raise ValueError("mise.toml has no valid [tools] table")
    if not isinstance(package_data, dict):
        raise ValueError("package.json must contain an object")
    if not isinstance(project_data, dict):
        raise ValueError("pyproject.toml must contain an object")
    return tools, package_data, project_data


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


def package_dependency_version(package: dict[str, object], dependency: str) -> str | None:
    """Return an exact Node development-dependency version when one is pinned."""
    dev_dependencies = package.get("devDependencies")
    version = dev_dependencies.get(dependency) if isinstance(dev_dependencies, dict) else None
    match = VERSION_PATTERN.fullmatch(version) if isinstance(version, str) else None
    return match.group(1) if match else None


def project_dependency_version(project: dict[str, object], dependency: str) -> str | None:
    """Return an exact Python development-dependency version when one is pinned."""
    dependency_groups = project.get("dependency-groups")
    dev_dependencies = dependency_groups.get("dev") if isinstance(dependency_groups, dict) else None
    if not isinstance(dev_dependencies, list):
        return None

    requirement = re.compile(
        rf"{re.escape(dependency)}\s*==\s*(v?\d+(?:\.\d+){{0,2}})",
        re.IGNORECASE,
    )
    for candidate in dev_dependencies:
        match = requirement.fullmatch(candidate) if isinstance(candidate, str) else None
        if match:
            return match.group(1).removeprefix("v")
    return None


def installed_node_dependency_version(root: Path, dependency: str) -> str | None:
    """Read a local Node dependency's version without executing package-manager code."""
    manifest_path = root / "node_modules" / dependency / "package.json"
    try:
        with manifest_path.open(encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        return None

    if not isinstance(manifest, dict) or manifest.get("name") != dependency:
        return None
    version = manifest.get("version")
    return version if isinstance(version, str) else None


def python_site_packages(root: Path) -> list[Path]:
    """Find conventional virtual-environment site-packages directories."""
    venv = root / ".venv"
    candidates = [venv / "Lib" / "site-packages", *venv.glob("lib/python*/site-packages")]
    return [candidate for candidate in candidates if candidate.is_dir()]


def distribution_metadata(path: Path) -> dict[str, str]:
    """Read the simple fields needed from a Python distribution METADATA file."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError, UnicodeDecodeError:
        return {}

    fields: dict[str, str] = {}
    for line in lines:
        if not line:
            break
        key, separator, value = line.partition(":")
        if separator and key in {"Name", "Version"}:
            fields[key] = value.strip()
    return fields


def installed_python_dependency_version(root: Path, dependency: str) -> str | None:
    """Read a local Python dependency's version without importing it."""
    package_directory = dependency.replace("-", "_")
    normalized_dependency = re.sub(r"[-_.]+", "-", dependency).lower()
    for site_packages in python_site_packages(root):
        if not (site_packages / package_directory / "__init__.py").is_file():
            continue
        for metadata_path in sorted(
            site_packages.glob(f"{package_directory}-*.dist-info/METADATA")
        ):
            metadata = distribution_metadata(metadata_path)
            installed_name = metadata.get("Name", "")
            normalized_name = re.sub(r"[-_.]+", "-", installed_name).lower()
            if normalized_name == normalized_dependency and metadata.get("Version"):
                return metadata["Version"]
    return None


def dependency_check(
    name: str,
    dependency: str,
    expected: str | None,
    installed: str | None,
    remedy: str,
) -> Check:
    """Format an installed dependency check with an actionable repair command."""
    if expected is None:
        return Check(name, False, f"cannot determine pinned {dependency} version")
    if installed is None:
        return Check(name, False, f"missing {dependency} {expected}; {remedy}")
    if installed != expected:
        return Check(name, False, f"expected {expected}, found {installed}; {remedy}")
    return Check(name, True, f"{dependency} {installed}")


def dependency_checks(
    root: Path, package: dict[str, object], project: dict[str, object]
) -> list[Check]:
    """Verify representative locked dependencies instead of empty install directories."""
    return [
        dependency_check(
            "node_modules (vitest)",
            NODE_DEPENDENCY,
            package_dependency_version(package, NODE_DEPENDENCY),
            installed_node_dependency_version(root, NODE_DEPENDENCY),
            "run pnpm install --frozen-lockfile",
        ),
        dependency_check(
            ".venv (pytest)",
            PYTHON_DEPENDENCY,
            project_dependency_version(project, PYTHON_DEPENDENCY),
            installed_python_dependency_version(root, PYTHON_DEPENDENCY),
            "run uv sync --frozen",
        ),
    ]


def read_text_file(path: Path) -> str | None:
    """Read a UTF-8 text file without executing or changing it."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return None


def is_executable(path: Path) -> bool:
    """Require executable generated hooks on POSIX while staying portable elsewhere."""
    return os.name != "posix" or os.access(path, os.X_OK)


def husky_source_hook_check(root: Path) -> Check:
    """Verify Husky has the tracked hook that its generated launcher invokes."""
    contents = read_text_file(root / HUSKY_SOURCE_HOOK)
    if contents is None:
        return Check("Husky source pre-commit hook", False, "missing; restore .husky/pre-commit")
    commands = [
        line.strip()
        for line in contents.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if commands != [HUSKY_SOURCE_COMMAND]:
        return Check(
            "Husky source pre-commit hook",
            False,
            f"must run only {HUSKY_SOURCE_COMMAND}; restore .husky/pre-commit",
        )
    return Check("Husky source pre-commit hook", True, f"runs {HUSKY_SOURCE_COMMAND}")


def husky_generated_hook_check(root: Path) -> Check:
    """Verify the generated Git hook sources Husky's launcher rather than doing nothing."""
    hook_path = root / HUSKY_GENERATED_HOOK
    contents = read_text_file(hook_path)
    if contents is None:
        return Check("Husky generated pre-commit hook", False, "missing; run pnpm prepare")
    if not HUSKY_HOOK_LAUNCHER_PATTERN.search(contents):
        return Check(
            "Husky generated pre-commit hook",
            False,
            "does not source .husky/_/h; run pnpm prepare",
        )
    if not is_executable(hook_path):
        return Check("Husky generated pre-commit hook", False, "not executable; run pnpm prepare")
    return Check("Husky generated pre-commit hook", True, "sources Husky launcher")


def husky_launcher_check(root: Path) -> Check:
    """Verify the generated launcher has the basic Husky hook-dispatch contract."""
    launcher_path = root / HUSKY_LAUNCHER
    contents = read_text_file(launcher_path)
    if contents is None:
        return Check("Husky launcher", False, "missing; run pnpm prepare")

    first_line = contents.splitlines()[0] if contents else ""
    valid_launcher = (
        first_line.startswith("#!")
        and HUSKY_LAUNCHER_NAME_PATTERN.search(contents) is not None
        and HUSKY_LAUNCHER_PATH_PATTERN.search(contents) is not None
        and HUSKY_LAUNCHER_COMMAND_PATTERN.search(contents) is not None
    )
    if not valid_launcher:
        return Check(
            "Husky launcher", False, "does not look like a Husky launcher; run pnpm prepare"
        )
    if not is_executable(launcher_path):
        return Check("Husky launcher", False, "not executable; run pnpm prepare")
    return Check("Husky launcher", True, "dispatches the tracked hook")


def husky_checks(root: Path, available: set[str], run: CommandRunner) -> list[Check]:
    """Verify Git's Husky configuration and a functional generated hook chain."""
    checks: list[Check] = []
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

    checks.extend(
        (
            husky_source_hook_check(root),
            husky_generated_hook_check(root),
            husky_launcher_check(root),
        )
    )
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
        tools, package, project = read_metadata(root)
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        checks.append(Check("metadata", False, str(error)))
        return checks

    checks.extend(metadata_checks(tools, package))
    checks.extend(version_checks(root, tools, available, run))
    checks.extend(dependency_checks(root, package, project))
    checks.extend(husky_checks(root, available, run))
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
