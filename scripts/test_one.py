#!/usr/bin/env python3
"""Run the colocated test file for exactly one LeetCode solution."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts.arguments import UsageError, parse, split_runner_args
from scripts.problem_paths import ProblemPathError, require_test_path, resolve_problem_paths


class TestOneError(ValueError):
    """Raised when a focused test invocation is invalid."""

    __test__ = False


@dataclass(frozen=True)
class TestOneArguments:
    """The parsed focused-test options and arguments for the package runner."""

    __test__ = False

    language: str
    problem_id: str
    watch: bool
    runner_args: tuple[str, ...] = ()


def parse_invocation(arguments: Sequence[str]) -> TestOneArguments:
    """Keep low-level runner options after the ID, with an optional separator."""
    values, runner_args = split_runner_args(arguments)
    # Legacy pnpm test:one forwards everything after the first runner option.
    boundary = next((i for i in range(2, len(values)) if values[i] != "--watch"), len(values))
    runner_args = values[boundary:] + runner_args
    try:
        options = parse("test", values[:boundary])
    except UsageError as error:
        raise TestOneError(str(error)) from error
    return TestOneArguments(
        options.language, options.problem_id, bool(options.watch), tuple(runner_args)
    )


def focused_command(
    root: Path,
    language: str,
    problem_id: str,
    watch: bool = False,
    *,
    runner_args: Sequence[str] = (),
) -> list[str]:
    """Return the existing package runner command for one colocated test file."""
    if watch and language == "py":
        raise TestOneError("watch mode is only supported for TypeScript")
    paths = resolve_problem_paths(root, language, problem_id)
    test_path = require_test_path(paths)
    script = f"test:{language}:watch" if watch else f"test:{language}"
    return ["pnpm", "run", script, str(test_path.relative_to(root)), *runner_args]


def run_focused_test(
    root: Path,
    language: str,
    problem_id: str,
    watch: bool = False,
    *,
    runner_args: Sequence[str] = (),
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    """Run one test file and return the runner's exit status."""
    result = run(
        focused_command(root, language, problem_id, watch, runner_args=runner_args),
        cwd=root,
        check=False,
    )
    return result.returncode


def main(argv: Sequence[str] | None = None) -> int:
    """Run the focused test command-line interface."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        parsed = parse_invocation(arguments)
        return run_focused_test(
            Path(__file__).resolve().parents[1],
            parsed.language,
            parsed.problem_id,
            parsed.watch,
            runner_args=parsed.runner_args,
        )
    except (ProblemPathError, TestOneError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2 if str(error).startswith("usage:") else 1


if __name__ == "__main__":
    raise SystemExit(main())
