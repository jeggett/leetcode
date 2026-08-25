#!/usr/bin/env python3
"""Report whether a checkout is ready to run the repository quality gate.

The command is deliberately read-only. It inspects configuration, installed
dependency metadata, and a few platform integrations without trying to repair
anything. All command and executable lookups are injectable so the checks
remain useful in tests and when the normal project toolchain is unavailable.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable, Mapping, Sequence
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
PACKAGE_MANAGER_PATTERN = re.compile(r"pnpm@v?(\d+(?:\.\d+){0,2})")

NODE_DEPENDENCIES = ("@biomejs/biome", "typescript", "vitest", "lefthook")
PYTHON_DEPENDENCIES = ("pytest", "pytest-timeout", "pytest-watcher", "ruff")
# Compatibility names retained for callers that used the original
# representative-dependency checks.
NODE_DEPENDENCY = "vitest"
PYTHON_DEPENDENCY = "pytest"

LEFTHOOK_CONFIG = Path("lefthook.yml")
LEFTHOOK_GENERATED_HOOK = Path(".git/hooks/pre-commit")
LEFTHOOK_COMMAND = "mise exec -- uv run python scripts/ready.py staged"
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
WSL_MOUNT_PATTERN = re.compile(r"^/mnt/[a-z](?:/|$)", re.IGNORECASE)


@dataclass(frozen=True)
class Check:
    """One readiness check and its human-readable result."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class CommandResult:
    """The limited command result needed by this module."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


CommandRunner = Callable[[Sequence[str], Path], CommandResult]
CommandFinder = Callable[[str], str | None]


def run_command(command: Sequence[str], cwd: Path) -> CommandResult:
    """Run a read-only command and return only the fields used by this module."""
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as error:
        return CommandResult(1, stderr=str(error))
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _run(run: CommandRunner, command: Sequence[str], cwd: Path) -> CommandResult:
    """Call an injected runner while keeping diagnostics alive on stub failures."""
    try:
        return run(command, cwd)
    except (KeyError, OSError, TypeError, ValueError) as error:
        return CommandResult(1, stderr=str(error))


def parse_version(output: str) -> str | None:
    """Extract the first ordinary dotted version from a version command's output."""
    match = VERSION_PATTERN.search(output)
    return match.group(1) if match else None


def read_metadata(root: Path) -> tuple[dict[str, str], dict[str, object], dict[str, object]]:
    """Read the pinned tool and dependency metadata required for setup checks."""
    node_version_file = (root / ".node-version").read_text(encoding="utf-8").strip()
    node_file_match = VERSION_PATTERN.fullmatch(node_version_file)
    if node_file_match is None:
        raise ValueError(".node-version must contain one dotted Node version")

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

    if "pnpm" not in tools and "npm:pnpm" in tools:
        tools["pnpm"] = tools["npm:pnpm"]
    missing_tools = [name for name in ("node", "pnpm", "python", "uv") if name not in tools]
    if missing_tools:
        raise ValueError("mise.toml must pin project tools: " + ", ".join(missing_tools))
    if node_file_match.group(1) != tools["node"]:
        raise ValueError(
            f".node-version ({node_file_match.group(1)}) does not match mise.toml node ({tools['node']})"
        )
    for name in ("node", "pnpm", "python", "uv"):
        if VERSION_PATTERN.fullmatch(tools[name]) is None:
            raise ValueError(f"mise.toml {name} pin must contain one dotted version")

    if not isinstance(package_data, dict):
        raise ValueError("package.json must contain an object")
    if not isinstance(project_data, dict):
        raise ValueError("pyproject.toml must contain an object")
    return dict(tools), package_data, project_data


def expected_package_manager_version(package: dict[str, object]) -> str | None:
    """Return the exact pnpm version declared by package.json's packageManager field."""
    package_manager = package.get("packageManager")
    match = (
        PACKAGE_MANAGER_PATTERN.fullmatch(package_manager)
        if isinstance(package_manager, str)
        else None
    )
    return match.group(1) if match else None


def metadata_checks(tools: dict[str, str], package: dict[str, object]) -> list[Check]:
    """Check package metadata is consistent with the project-local tool pins."""
    checks: list[Check] = []

    package_manager = package.get("packageManager")
    expected_pnpm = tools.get("pnpm")
    package_pnpm = expected_package_manager_version(package)
    package_manager_ok = package_pnpm is not None and package_pnpm == expected_pnpm
    checks.append(
        Check(
            "packageManager",
            package_manager_ok,
            f"{package_manager}"
            if package_manager_ok
            else f"{package_manager!s}; expected pnpm@{expected_pnpm}",
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

    pnpm_requirement = engines.get("pnpm") if isinstance(engines, dict) else None
    if pnpm_requirement is not None:
        expected_engine = str(expected_pnpm) if expected_pnpm is not None else ""
        engine_version = str(pnpm_requirement).removeprefix("pnpm@")
        checks.append(
            Check(
                "pnpm engine",
                engine_version == expected_engine,
                str(pnpm_requirement)
                if engine_version == expected_engine
                else f"expected {expected_engine}",
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
    package: dict[str, object],
    available: set[str],
    run: CommandRunner,
) -> list[Check]:
    """Compare installed runtime versions with the repository's metadata pins."""
    checks: list[Check] = []
    for command, invocation in VERSION_COMMANDS.items():
        expected = tools.get(command)
        if expected is None and command == "pnpm":
            expected = expected_package_manager_version(package)
        if expected is None:
            checks.append(Check(f"{command} version", False, "not pinned in mise.toml"))
            continue
        if command not in available:
            checks.append(Check(f"{command} version", False, "command is unavailable"))
            continue

        result = _run(run, invocation, root)
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
    normalized_dependency = re.sub(r"[-_.]+", "-", dependency).lower()
    for site_packages in python_site_packages(root):
        for metadata_path in sorted(site_packages.glob("*.dist-info/METADATA")):
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
    """Verify the local quality tools instead of merely checking directory existence."""
    checks: list[Check] = []
    for dependency in NODE_DEPENDENCIES:
        checks.append(
            dependency_check(
                f"node_modules ({dependency})",
                dependency,
                package_dependency_version(package, dependency),
                installed_node_dependency_version(root, dependency),
                "run pnpm install --frozen-lockfile",
            )
        )
    for dependency in PYTHON_DEPENDENCIES:
        checks.append(
            dependency_check(
                f".venv ({dependency})",
                dependency,
                project_dependency_version(project, dependency),
                installed_python_dependency_version(root, dependency),
                "run uv sync --frozen",
            )
        )
    return checks


def read_text_file(path: Path) -> str | None:
    """Read a UTF-8 text file without executing or changing it."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return None


def is_executable(path: Path) -> bool:
    """Require executable generated hooks on POSIX while staying portable elsewhere."""
    return os.name != "posix" or os.access(path, os.X_OK)


def mise_trust_check(root: Path, available: set[str], run: CommandRunner) -> Check:
    """Verify the project config is trusted without trusting it as a side effect."""
    if "mise" not in available:
        return Check("mise trust", False, "mise command is unavailable")
    result = _run(run, ("mise", "trust", "--show"), root)
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if result.returncode != 0:
        return Check("mise trust", False, "could not inspect trust; run mise trust")
    if re.search(r"\buntrusted\b", output, re.IGNORECASE):
        return Check("mise trust", False, "mise.toml is untrusted; run mise trust")
    if re.search(r"\btrusted\b", output, re.IGNORECASE):
        return Check("mise trust", True, "mise.toml is trusted")
    return Check("mise trust", False, "could not find mise.toml trust status; run mise trust")


def lefthook_config_check(root: Path) -> Check:
    """Verify the tracked Lefthook pre-commit command."""
    contents = read_text_file(root / LEFTHOOK_CONFIG)
    if contents is None:
        return Check("Lefthook pre-commit config", False, "missing; restore lefthook.yml")
    if "pre-commit:" not in contents or LEFTHOOK_COMMAND not in contents:
        return Check("Lefthook pre-commit config", False, f"must run {LEFTHOOK_COMMAND}")
    return Check("Lefthook pre-commit config", True, f"runs {LEFTHOOK_COMMAND}")


def lefthook_generated_hook_check(root: Path) -> Check:
    """Verify Lefthook installed an executable Git pre-commit hook."""
    hook_path = root / LEFTHOOK_GENERATED_HOOK
    contents = read_text_file(hook_path)
    if contents is None:
        return Check("Lefthook generated pre-commit hook", False, "missing; run pnpm prepare")
    if "lefthook" not in contents.lower():
        return Check("Lefthook generated pre-commit hook", False, "not generated by Lefthook")
    if not is_executable(hook_path):
        return Check(
            "Lefthook generated pre-commit hook", False, "not executable; run pnpm prepare"
        )
    return Check("Lefthook generated pre-commit hook", True, "dispatches Lefthook")


def lefthook_checks(root: Path, available: set[str], run: CommandRunner) -> list[Check]:
    """Verify tracked and installed Lefthook configuration."""
    return [lefthook_config_check(root), lefthook_generated_hook_check(root)]


def clipboard_check(
    find_command: CommandFinder = shutil.which,
    *,
    platform: str | None = None,
) -> Check:
    """Check that a supported native or WSL clipboard command is available."""
    effective_platform = sys.platform if platform is None else platform
    if effective_platform.startswith("win"):
        candidates = ("clip",)
    elif effective_platform == "darwin":
        candidates = ("pbcopy",)
    else:
        candidates = ("wl-copy", "xclip", "xsel", "clip.exe")

    available = next((candidate for candidate in candidates if find_command(candidate)), None)
    if available is None:
        listed = ", ".join(candidates)
        return Check(
            "clipboard",
            False,
            f"no supported clipboard command found; install one of {listed}",
        )
    return Check("clipboard", True, available)


def _is_wsl(
    *,
    platform: str,
    environ: Mapping[str, str],
    proc_version: str | None,
) -> bool:
    if platform.startswith("win") or platform == "darwin":
        return False
    if environ.get("WSL_INTEROP") or environ.get("WSL_DISTRO_NAME"):
        return True
    return bool(proc_version and re.search(r"microsoft|wsl", proc_version, re.IGNORECASE))


def wsl_repository_path_check(
    root: Path,
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    proc_version: str | None = None,
) -> Check:
    """Warn when a WSL checkout lives on the mounted Windows filesystem."""
    effective_platform = sys.platform if platform is None else platform
    effective_environment = os.environ if environ is None else environ
    if proc_version is None and effective_platform.startswith("linux"):
        proc_version = read_text_file(Path("/proc/version"))
    if not _is_wsl(
        platform=effective_platform,
        environ=effective_environment,
        proc_version=proc_version,
    ):
        return Check("WSL repository path", True, "not running under WSL")

    normalized_root = root.resolve().as_posix()
    if WSL_MOUNT_PATTERN.match(normalized_root):
        return Check(
            "WSL repository path",
            False,
            f"{normalized_root} is on a Windows mount; move the checkout into the WSL filesystem",
        )
    return Check("WSL repository path", True, f"{normalized_root} is on the WSL filesystem")


def collect_checks(
    root: Path,
    *,
    find_command: CommandFinder = shutil.which,
    run: CommandRunner = run_command,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    proc_version: str | None = None,
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
    checks.append(mise_trust_check(root, available, run))
    checks.append(
        wsl_repository_path_check(
            root,
            platform=platform,
            environ=environ,
            proc_version=proc_version,
        )
    )
    checks.append(clipboard_check(find_command, platform=platform))

    try:
        tools, package, project = read_metadata(root)
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        checks.append(Check("metadata", False, str(error)))
        return checks

    checks.extend(metadata_checks(tools, package))
    checks.extend(version_checks(root, tools, package, available, run))
    checks.extend(dependency_checks(root, package, project))
    checks.extend(lefthook_checks(root, available, run))
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
    if arguments in (["-h"], ["--help"]):
        print("usage: doctor.py [root]")
        return 0
    if len(arguments) > 1:
        print("usage: doctor.py [root]", file=sys.stderr)
        return 2

    root = Path(arguments[0]).resolve() if arguments else Path.cwd()
    checks = collect_checks(root)
    print(format_report(checks))
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
