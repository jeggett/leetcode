"""Check pinned tools and local dependencies without installing anything."""

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable, Sequence
from pathlib import Path

COMMANDS = ("mise", "node", "pnpm", "python", "uv", "git")
NODE_PACKAGES = (
    "@babel/parser",
    "@biomejs/biome",
    "typescript",
    "typescript-judge",
    "vitest",
    "lefthook",
)
VERSION = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]+)?")
Runner = Callable[..., subprocess.CompletedProcess[str]]


def run_version_command(
    root: Path, command: list[str], run: Runner
) -> subprocess.CompletedProcess[str] | None:
    """Read command output without allowing mise to install missing tools."""
    try:
        return run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            env={**os.environ, "MISE_AUTO_INSTALL": "0"},
        )
    except OSError, subprocess.TimeoutExpired, UnicodeError:
        return None


def command_version(root: Path, command: list[str], run: Runner) -> str | None:
    result = run_version_command(root, command, run)
    if result is None or result.returncode:
        return None
    match = VERSION.search((result.stdout or "") + " " + (result.stderr or ""))
    return match.group() if match else None


def version_check(
    name: str, expected: str, found: str | None, remedy: str
) -> tuple[str, bool, str]:
    if expected == found:
        return name, True, f"found {found}"
    return name, False, f"expected {expected}, found {found or 'unavailable'}; {remedy}"


def collect_checks(
    root: Path,
    *,
    find_command: Callable[[str], str | None] = shutil.which,
    run: Runner = subprocess.run,
) -> list[tuple[str, bool, str]]:
    """Compare installed tools and dependencies with their declared versions."""
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    mise = tomllib.loads((root / "mise.toml").read_text(encoding="utf-8"))
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    tools = {
        "node": (root / ".node-version").read_text(encoding="utf-8").strip(),
        "pnpm": mise["tools"]["pnpm"],
        "python": (root / ".python-version").read_text(encoding="utf-8").strip(),
        "uv": mise["tools"]["uv"],
    }
    python_packages = dict(
        spec.split("==", 1)
        for spec in project["dependency-groups"]["dev"]
        if spec.split("==", 1)[0] in {"pytest", "ruff"}
    )
    judge = (root / ".judge-node-version").read_text(encoding="utf-8").strip()

    commands = {name: find_command(name) for name in COMMANDS}
    checks = [
        (name, bool(commands[name]), "found" if commands[name] else f"install {name}")
        for name in ("mise", "git")
    ]
    for name, expected in tools.items():
        path = commands[name]
        found = command_version(root, [path, "--version"], run) if path else None
        checks.append(version_check(name, expected, found, "run mise install"))

    for name in NODE_PACKAGES:
        # The judge compiler uses an npm alias; its version follows the last @.
        expected = package["devDependencies"][name].rsplit("@", 1)[-1]
        path = root / "node_modules" / name / "package.json"
        try:
            found = json.loads(path.read_text(encoding="utf-8"))["version"]
        except OSError, ValueError, KeyError:
            found = None
        checks.append(version_check(name, expected, found, "run pnpm install --frozen-lockfile"))

    scripts = root / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
    suffix = ".exe" if sys.platform == "win32" else ""
    for name, expected in {"python": tools["python"], **python_packages}.items():
        path = scripts / f"{name}{suffix}"
        found = command_version(root, [str(path), "--version"], run) if path.is_file() else None
        checks.append(version_check(f".venv/{name}", expected, found, "run uv sync --frozen"))

    judge_version = None
    if commands["mise"]:
        located = run_version_command(root, [commands["mise"], "where", f"node@{judge}"], run)
        if located is not None and not located.returncode and located.stdout.strip():
            node = Path(located.stdout.strip()) / "bin" / f"node{suffix}"
            judge_version = command_version(root, [str(node), "--version"], run)
    checks.append(
        version_check("judge node", judge, judge_version, f"run mise install node@{judge}")
    )
    return checks


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) > 1 or arguments in (["-h"], ["--help"]):
        print("usage: doctor [root]")
        return 2 if len(arguments) > 1 else 0
    root = Path(arguments[0]).resolve() if arguments else Path.cwd()
    checks = collect_checks(root)
    for name, available, detail in checks:
        print(f"{'PASS' if available else 'FAIL'} {name}: {detail}")
    if all(available for _, available, _ in checks):
        print("Pinned tools and dependencies found. Run lc ready to validate the workspace.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
