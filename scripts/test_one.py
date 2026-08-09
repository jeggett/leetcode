#!/usr/bin/env python3
"""Run the colocated test file for exactly one LeetCode solution."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

try:
    from scripts.problem_paths import ProblemPathError, require_test_path, resolve_problem_paths
except ModuleNotFoundError:
    from problem_paths import ProblemPathError, require_test_path, resolve_problem_paths


class TestOneError(ValueError):
    """Raised when a focused test invocation is invalid."""

    __test__ = False


def parse_arguments(arguments: Sequence[str]) -> tuple[str, str, bool]:
    """Parse ``test_one <py|ts> <id> [--watch]``."""
    if len(arguments) < 2:
        raise TestOneError("usage: test_one <py|ts> <id> [--watch]")
    language, problem_id, *options = arguments
    if language not in {"py", "ts"}:
        raise TestOneError("language must be 'py' or 'ts'")
    if any(option != "--watch" for option in options):
        unknown = next(option for option in options if option != "--watch")
        raise TestOneError(f"unknown option: {unknown}")
    if options.count("--watch") > 1:
        raise TestOneError("--watch may only be provided once")
    watch = "--watch" in options
    if language == "py" and watch:
        raise TestOneError("--watch is only supported for TypeScript tests")
    return language, problem_id, watch


def focused_command(root: Path, language: str, problem_id: str, watch: bool = False) -> list[str]:
    """Return the existing package runner command for one colocated test file."""
    paths = resolve_problem_paths(root, language, problem_id)
    test_path = require_test_path(paths)
    script = "test:ts:watch" if language == "ts" and watch else f"test:{language}"
    return ["pnpm", script, str(test_path.relative_to(root))]


def run_focused_test(
    root: Path,
    language: str,
    problem_id: str,
    watch: bool = False,
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    """Run one test file and return the runner's exit status."""
    result = run(focused_command(root, language, problem_id, watch), cwd=root, check=False)
    return result.returncode


def main(argv: Sequence[str] | None = None) -> int:
    """Run the focused test command-line interface."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        language, problem_id, watch = parse_arguments(arguments)
        return run_focused_test(Path(__file__).resolve().parents[1], language, problem_id, watch)
    except (ProblemPathError, TestOneError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2 if str(error).startswith("usage:") else 1


if __name__ == "__main__":
    raise SystemExit(main())
