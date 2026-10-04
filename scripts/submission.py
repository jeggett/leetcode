#!/usr/bin/env python3
"""Print a LeetCode-ready solution and optionally copy it to the clipboard."""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

try:
    from scripts.check_incomplete import scaffold_markers
    from scripts.problem_paths import (
        ProblemPathError,
        require_source_path,
        require_test_path,
        resolve_problem_paths,
    )
    from scripts.test_one import focused_command
except ModuleNotFoundError:
    from check_incomplete import scaffold_markers
    from problem_paths import (
        ProblemPathError,
        require_source_path,
        require_test_path,
        resolve_problem_paths,
    )
    from test_one import focused_command


class SubmissionError(ValueError):
    """Raised when a source file cannot safely be prepared for submission."""


@dataclass(frozen=True)
class SubmissionOptions:
    """Validated command options for rendering and copying a submission."""

    language: str
    problem_id: str
    copy: bool = False
    copy_only: bool = False
    check: bool = True


TYPESCRIPT_RENDERER = Path(__file__).with_name("typescript_submission.mjs")


def parse_options(arguments: Sequence[str]) -> SubmissionOptions:
    """Parse submission options, defaulting to a focused safety check."""
    if len(arguments) < 2:
        raise SubmissionError("usage: submission <py|ts> <id> [--copy|--copy-only] [--no-check]")
    language, problem_id, *options = arguments
    if language not in {"py", "ts"}:
        raise SubmissionError("language must be 'py' or 'ts'")
    supported = {"--copy", "--copy-only", "--no-check"}
    if any(option not in supported for option in options):
        unknown = next(option for option in options if option not in supported)
        raise SubmissionError(f"unknown option: {unknown}")
    duplicates = next((option for option in supported if options.count(option) > 1), None)
    if duplicates:
        raise SubmissionError(f"{duplicates} may only be provided once")
    if "--copy" in options and "--copy-only" in options:
        raise SubmissionError("--copy and --copy-only cannot be combined")
    copy_only = "--copy-only" in options
    return SubmissionOptions(
        language=language,
        problem_id=problem_id,
        copy="--copy" in options or copy_only,
        copy_only=copy_only,
        check="--no-check" not in options,
    )


def typescript_submission(source: str) -> str:
    """Prepare TypeScript with the maintained parser used by the Node renderer."""
    result = subprocess.run(
        ["node", str(TYPESCRIPT_RENDERER)],
        input=source,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise SubmissionError(result.stderr.strip() or "could not render TypeScript submission")
    return result.stdout


def read_submission(root: Path, language: str, problem_id: str) -> str:
    """Read the requested solution and transform it only when TypeScript requires it."""
    paths = resolve_problem_paths(root, language, problem_id)
    source = require_source_path(paths).read_text(encoding="utf-8")
    return source if language == "py" else typescript_submission(source)


def preflight_submission(
    root: Path,
    language: str,
    problem_id: str,
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    """Reject incomplete scaffolds and require the focused problem test to pass."""
    paths = resolve_problem_paths(root, language, problem_id)
    source_path = require_source_path(paths)
    test_path = require_test_path(paths)
    incomplete = [
        (path, marker)
        for path in (source_path, test_path)
        for marker in scaffold_markers(path, path.read_text(encoding="utf-8"))
    ]
    if incomplete:
        details = ", ".join(f"{path.name}: {marker}" for path, marker in incomplete)
        raise SubmissionError(f"submission is incomplete: {details}")

    command = focused_command(root, language, problem_id)
    completed = run(command, cwd=root, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        details = ((completed.stdout or "") + (completed.stderr or "")).strip()
        suffix = f": {details}" if details else ""
        raise SubmissionError(
            f"focused test failed with exit status {completed.returncode}{suffix}"
        )


def clipboard_commands(
    platform: str, which: Callable[[str], str | None] = shutil.which
) -> list[list[str]]:
    """Return usable clipboard candidates, ordered by the native preference."""
    if platform.startswith("win"):
        return [["clip"]]
    if platform == "darwin":
        return [["pbcopy"]]
    commands: list[list[str]] = []
    for command in ("wl-copy", "xclip", "xsel", "clip.exe"):
        if which(command):
            if command == "xclip":
                commands.append([command, "-selection", "clipboard"])
            elif command == "xsel":
                commands.append([command, "--clipboard", "--input"])
            else:
                commands.append([command])
    if commands:
        return commands
    raise SubmissionError(
        "no supported clipboard command found (tried wl-copy, xclip, xsel, and clip.exe)"
    )


def copy_to_clipboard(
    content: str,
    *,
    platform: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    """Copy text using the platform's native clipboard tool."""
    effective_platform = sys.platform if platform is None else platform
    errors: list[OSError | subprocess.CalledProcessError] = []
    for command in clipboard_commands(effective_platform, which):
        try:
            run(command, input=content, text=True, check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            errors.append(error)
        else:
            return
    error = errors[-1]
    raise SubmissionError(f"failed to copy submission to clipboard: {error}") from error


def main(argv: Sequence[str] | None = None) -> int:
    """Run the submission command-line interface."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        options = parse_options(arguments)
        root = Path(__file__).resolve().parents[1]
        if options.check:
            preflight_submission(root, options.language, options.problem_id)
        source = read_submission(root, options.language, options.problem_id)
        if options.copy:
            copy_to_clipboard(source)
    except (ProblemPathError, SubmissionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2 if str(error).startswith("usage:") else 1
    if options.copy_only:
        print(f"Copied {options.language} {options.problem_id} submission to the clipboard.")
    else:
        sys.stdout.write(source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
