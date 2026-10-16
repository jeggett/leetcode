"""Check setup prerequisites without installing tools or duplicating lockfiles."""

import shutil
import sys
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


def collect_checks(
    root: Path, *, find_command: Callable[[str], str | None] = shutil.which
) -> list[tuple[str, bool, str]]:
    """Report available commands and local dependencies; lc ready validates them."""
    checks = [
        (
            command,
            bool(find_command(command)),
            f"install {command}" if command in {"mise", "git"} else "run mise install",
        )
        for command in COMMANDS
    ]
    checks.extend(
        (
            package,
            (root / "node_modules" / package / "package.json").is_file(),
            "run pnpm install --frozen-lockfile",
        )
        for package in NODE_PACKAGES
    )
    scripts = root / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
    suffix = ".exe" if sys.platform == "win32" else ""
    checks.extend(
        (f".venv/{tool}", (scripts / f"{tool}{suffix}").is_file(), "run uv sync --frozen")
        for tool in ("python", "pytest", "ruff")
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
        print(f"{'PASS' if available else 'FAIL'} {name}: {'found' if available else detail}")
    if all(available for _, available, _ in checks):
        print("Setup files found. Run lc ready to validate the workspace.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
