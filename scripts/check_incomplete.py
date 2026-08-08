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
PYTHON_SKIP_MARKER = "@pytest.mark.skip("
TYPESCRIPT_SKIP_MARKER = "test.skip("

SCAFFOLD_MARKERS = (IMPLEMENTATION_MARKER, TEST_MARKER)
SOURCE_DIRECTORIES = ("src/python", "src/typescript")

PYTHON_SKIP_PATTERN = re.compile(r"^[ \t]*@pytest\.mark\.skip\s*\(", re.MULTILINE)
TYPESCRIPT_SKIP_PATTERN = re.compile(r"^[ \t]*test\.skip\s*\(", re.MULTILINE)
COMPLEXITY_PATTERN = re.compile(r"\btime:\s*TODO\s*,\s*space:\s*TODO\b")


def is_scaffold_test(path: Path) -> bool:
    """Return whether a path has one of the generated test-file names."""
    return (path.name.startswith("test_") and path.suffix == ".py") or path.name.endswith(
        ".test.ts"
    )


def scaffold_markers(path: Path, content: str) -> list[str]:
    """Return incomplete scaffold markers found in one source or test file."""
    markers = [marker for marker in SCAFFOLD_MARKERS if marker in content]
    if (
        path.suffix == ".ts"
        and IMPLEMENTATION_MARKER not in content
        and COMPLEXITY_PATTERN.search(content)
    ):
        markers.append(COMPLEXITY_MARKER)
    if is_scaffold_test(path) and TEST_MARKER not in content:
        skip_pattern, skip_marker = (
            (PYTHON_SKIP_PATTERN, PYTHON_SKIP_MARKER)
            if path.suffix == ".py"
            else (TYPESCRIPT_SKIP_PATTERN, TYPESCRIPT_SKIP_MARKER)
        )
        if skip_pattern.search(content):
            markers.append(skip_marker)
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
