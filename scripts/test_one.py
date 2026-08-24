#!/usr/bin/env python3
"""Run the colocated test file for exactly one LeetCode solution."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

try:
    from scripts.problem_paths import ProblemPathError, require_test_path, resolve_problem_paths
except ModuleNotFoundError:
    from problem_paths import ProblemPathError, require_test_path, resolve_problem_paths


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


def parse_arguments(arguments: Sequence[str]) -> tuple[str, str, bool]:
    """Parse ``test_one <py|ts> <id> [--watch]``."""
    parsed = parse_invocation(arguments)
    if parsed.runner_args:
        raise TestOneError(f"unknown option: {parsed.runner_args[0]}")
    return parsed.language, parsed.problem_id, parsed.watch


def parse_invocation(arguments: Sequence[str]) -> TestOneArguments:
    """Parse focused-test options while preserving arguments for the test runner.

    ``--watch`` is this wrapper's only option.  Everything after an explicit ``--``
    (or the first non-wrapper option) is passed to Vitest or pytest unchanged.  The
    explicit separator is optional because ``lc`` removes it while dispatching the
    package script.
    """
    if len(arguments) < 2:
        raise TestOneError("usage: test_one <py|ts> <id> [--watch] [-- RUNNER_ARGS...]")
    language, problem_id, *options = arguments
    if language not in {"py", "ts"}:
        raise TestOneError("language must be 'py' or 'ts'")

    watch = False
    runner_args: list[str] = []
    forwarding = False
    for index, option in enumerate(options):
        if not forwarding and option == "--":
            runner_args.extend(options[index + 1 :])
            break
        if not forwarding and option == "--watch":
            if watch:
                raise TestOneError("--watch may only be provided once")
            watch = True
            continue
        forwarding = True
        runner_args.append(option)
    return TestOneArguments(language, problem_id, watch, tuple(runner_args))


def focused_command(
    root: Path,
    language: str,
    problem_id: str,
    watch: bool = False,
    *,
    runner_args: Sequence[str] = (),
) -> list[str]:
    """Return the existing package runner command for one colocated test file."""
    paths = resolve_problem_paths(root, language, problem_id)
    test_path = require_test_path(paths)
    script = f"test:{language}:watch" if watch else f"test:{language}"
    return ["pnpm", script, str(test_path.relative_to(root)), *runner_args]


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
