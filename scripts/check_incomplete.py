#!/usr/bin/env python3
"""Fail when generated solution scaffolds have not been completed."""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from pathlib import Path


IMPLEMENTATION_MARKER = "TODO: implement the solution"
TEST_MARKER = "TODO: add examples and edge cases"
COMPLEXITY_MARKER = "time: TODO, space: TODO"
GENERATED_TEST_SENTINEL = "GENERATED_SCAFFOLD_TEST"

SCAFFOLD_MARKERS = (IMPLEMENTATION_MARKER, TEST_MARKER)
SOURCE_DIRECTORIES = ("src/python", "src/typescript")

COMPLEXITY_PATTERN = re.compile(r"\btime:\s*TODO\s*,\s*space:\s*TODO\b")
PYTHON_TEST_NAME = re.compile(r"^test_.+\.py$")
TYPESCRIPT_TEST_NAME = re.compile(r"^.+\.test\.ts$")
PYTHON_GENERATED_TEST_SENTINEL_PATTERN = re.compile(
    rf"^[ \t]*#[ \t]*{GENERATED_TEST_SENTINEL}[ \t]*$", re.MULTILINE
)
TYPESCRIPT_GENERATED_TEST_SENTINEL_PATTERN = re.compile(
    rf"^[ \t]*//[ \t]*{GENERATED_TEST_SENTINEL}[ \t]*$", re.MULTILINE
)


def is_conventional_test(path: Path) -> bool:
    """Return whether a path uses a conventional generated test-file name."""
    return bool(PYTHON_TEST_NAME.fullmatch(path.name) or TYPESCRIPT_TEST_NAME.fullmatch(path.name))


def has_generated_test_sentinel(path: Path, content: str) -> bool:
    """Return whether a conventional test contains an exact generated sentinel comment."""
    if not is_conventional_test(path):
        return False
    pattern = (
        PYTHON_GENERATED_TEST_SENTINEL_PATTERN
        if path.suffix == ".py"
        else TYPESCRIPT_GENERATED_TEST_SENTINEL_PATTERN
    )
    return pattern.search(content) is not None


def scaffold_markers(path: Path, content: str) -> list[str]:
    """Return incomplete scaffold markers found in one source or test file."""
    markers = [marker for marker in SCAFFOLD_MARKERS if marker in content]
    if (
        path.suffix in {".py", ".ts"}
        and IMPLEMENTATION_MARKER not in content
        and COMPLEXITY_PATTERN.search(content)
    ):
        markers.append(COMPLEXITY_MARKER)
    if has_generated_test_sentinel(path, content) and TEST_MARKER not in content:
        markers.append(GENERATED_TEST_SENTINEL)
    return markers


def incomplete_scaffolds(root: Path) -> list[tuple[Path, str]]:
    """Return relative paths and scaffold markers found below the source directories."""
    matches: list[tuple[Path, str]] = []
    for source_directory in SOURCE_DIRECTORIES:
        directory = root / source_directory
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix not in {".py", ".ts"}:
                continue
            content = path.read_text(encoding="utf-8")
            for marker in scaffold_markers(path, content):
                matches.append((path.relative_to(root), marker))
    return matches


def format_report(matches: Sequence[tuple[Path, str]]) -> str:
    """Format incomplete scaffold matches for command-line output."""
    return "\n".join(f"{path}: {marker}" for path, marker in matches)


def main(argv: Sequence[str] | None = None) -> int:
    """Check a repository root, returning one when incomplete scaffolds are found."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) > 1:
        print("usage: check_incomplete.py [root]", file=sys.stderr)
        return 2

    root = Path(arguments[0]) if arguments else Path.cwd()
    matches = incomplete_scaffolds(root)
    if not matches:
        return 0

    print(format_report(matches))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
