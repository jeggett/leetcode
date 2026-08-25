#!/usr/bin/env python3
"""Run a fast problem-scoped quality gate or the complete repository gate."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import tomllib
from contextlib import contextmanager
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from os import environ
from pathlib import Path
from typing import Iterator

try:
    from scripts.check_incomplete import scaffold_markers
    from scripts.practice import PracticeError, load_problem_metadata, load_track_manifest
    from scripts.problem_paths import (
        ProblemPathError,
        ProblemPaths,
        normalize_problem_id,
        require_source_path,
        require_test_path,
        resolve_problem_paths,
    )
except ModuleNotFoundError:
    from check_incomplete import scaffold_markers
    from practice import PracticeError, load_problem_metadata, load_track_manifest
    from problem_paths import (
        ProblemPathError,
        ProblemPaths,
        normalize_problem_id,
        require_source_path,
        require_test_path,
        resolve_problem_paths,
    )


class ReadyError(ValueError):
    """Raised when a scoped quality gate cannot be selected or completed."""


VALID_METADATA_KINDS = frozenset({"function", "class", "design"})
LANGUAGE_ALIASES = {
    "py": "py",
    "python": "py",
    "ts": "ts",
    "typescript": "ts",
}


@dataclass(frozen=True)
class CommandResult:
    """Command result shape used by changed-path discovery tests."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[..., subprocess.CompletedProcess[str]]
GitRunner = Callable[[Sequence[str], Path], CommandResult]

# Staged snapshots reuse the already-installed environments read-only.  These files determine
# which packages those environments should contain; an unstaged edit would make the snapshot's
# source tree and the live dependency directories describe different projects.
DEPENDENCY_MANIFESTS = frozenset(
    {
        ".node-version",
        ".python-version",
        "mise.toml",
        "package.json",
        "pnpm-lock.yaml",
        "pyproject.toml",
        "uv.lock",
    }
)


def run_git(command: Sequence[str], cwd: Path) -> CommandResult:
    """Run one read-only Git query."""
    result = subprocess.run(command, cwd=cwd, capture_output=True, check=False, text=True)
    return CommandResult(result.returncode, result.stdout, result.stderr)


def incomplete_problem(paths: ProblemPaths) -> list[str]:
    """Return generated markers from one solution and its test."""
    findings: list[str] = []
    for path in (require_source_path(paths), require_test_path(paths)):
        for marker in scaffold_markers(path, path.read_text(encoding="utf-8")):
            findings.append(f"{path}: {marker}")
    return findings


def validate_problem_metadata(paths: ProblemPaths) -> None:
    """Validate identity fields in an optional tracked ``problem.toml``.

    Existing legacy problem directories may not have metadata, so absence is allowed.  Once a
    metadata file exists, its problem ID, language, and kind must be explicit and consistent with
    the directory being gated.  ``new_problem.py`` writes these fields at the repository root of
    each problem directory.
    """

    metadata_path = paths.directory / "problem.toml"
    if not metadata_path.is_file():
        return
    try:
        load_problem_metadata(metadata_path)
    except PracticeError as error:
        raise ReadyError(str(error)) from error
    try:
        document = tomllib.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ReadyError(f"invalid metadata {metadata_path}: {error}") from error
    if not isinstance(document, dict):  # pragma: no cover - tomllib currently returns a dict.
        raise ReadyError(f"invalid metadata {metadata_path}: top-level TOML value must be a table")

    problems: list[str] = []
    values = document
    for table_name in ("problem", "metadata"):
        table = document.get(table_name)
        if isinstance(table, dict):
            values = {**document, **table}
            break

    raw_id = values.get("id")
    try:
        metadata_id = normalize_problem_id(str(raw_id))
    except ProblemPathError as error:
        problems.append(f"id must be a positive integer matching {paths.problem_id}: {error}")
    else:
        if metadata_id != paths.problem_id:
            problems.append(f"id {metadata_id} does not match problem {paths.problem_id}")

    raw_language = values.get("language")
    if not isinstance(raw_language, str):
        problems.append(f"language must be 'py' or 'ts' matching {paths.language}")
    else:
        metadata_language = LANGUAGE_ALIASES.get(raw_language.strip().lower())
        if metadata_language is None:
            problems.append(f"language {raw_language!r} is not 'py' or 'ts'")
        elif metadata_language != paths.language:
            problems.append(
                f"language {metadata_language} does not match problem language {paths.language}"
            )

    raw_kind = values.get("kind")
    if not isinstance(raw_kind, str) or raw_kind not in VALID_METADATA_KINDS:
        allowed = ", ".join(sorted(VALID_METADATA_KINDS))
        problems.append(f"kind must be one of {allowed}")

    if problems:
        raise ReadyError(f"invalid metadata {metadata_path}:\n" + "\n".join(problems))


def validate_all_problem_metadata(root: Path) -> None:
    """Validate metadata for every conventional problem in the repository."""

    directory_pattern = re.compile(r"^p_(?P<problem_id>[0-9]+)_[a-z0-9][a-z0-9_]*$")
    for language, directory_name in (("py", "python"), ("ts", "typescript")):
        language_root = root / "src" / directory_name
        if not language_root.is_dir():
            continue
        seen_problem_ids: dict[str, Path] = {}
        for directory in sorted(language_root.iterdir()):
            match = directory_pattern.fullmatch(directory.name)
            if not directory.is_dir():
                continue
            if match is None:
                if directory.name.startswith("p_"):
                    raise ReadyError(f"invalid problem directory name: {directory}")
                continue
            try:
                problem_id = normalize_problem_id(match["problem_id"])
            except ProblemPathError as error:
                raise ReadyError(f"invalid problem directory {directory}: {error}") from error
            previous = seen_problem_ids.get(problem_id)
            if previous is not None:
                raise ReadyError(
                    f"duplicate normalized problem ID {problem_id} for {previous} and {directory}"
                )
            seen_problem_ids[problem_id] = directory
            paths = ProblemPaths(language, problem_id, directory)
            try:
                require_source_path(paths)
                require_test_path(paths)
            except ProblemPathError as error:
                raise ReadyError(f"incomplete problem {directory}: {error}") from error
            validate_problem_metadata(paths)


def validate_track_metadata(root: Path) -> None:
    """Validate the repository's configured practice-track manifest."""

    track_path = root / "tracks" / "interview-core.toml"
    try:
        load_track_manifest(track_path)
    except PracticeError as error:
        raise ReadyError(str(error)) from error


def _git_error(result: CommandResult, fallback: str) -> ReadyError:
    return ReadyError((result.stderr or result.stdout).strip() or fallback)


def problem_commands(root: Path, paths: ProblemPaths, *, no_sync: bool = False) -> list[list[str]]:
    """Build the shortest reliable quality sequence for one problem."""
    source = str(require_source_path(paths).relative_to(root))
    test = str(require_test_path(paths).relative_to(root))
    if paths.language == "ts":
        return [
            ["pnpm", "exec", "biome", "format", source, test],
            ["pnpm", "exec", "biome", "lint", source, test],
            ["pnpm", "exec", "tsc", "--noEmit"],
            ["pnpm", "exec", "vitest", "run", test],
        ]
    uv_run = ["uv", "run"]
    if no_sync:
        uv_run.append("--no-sync")
    return [
        [*uv_run, "ruff", "format", "--check", source, test],
        [*uv_run, "ruff", "check", source, test],
        [*uv_run, "pytest", test],
    ]


def run_problem_gate(
    root: Path,
    paths: ProblemPaths,
    *,
    run: Runner = subprocess.run,
    no_sync: bool = False,
) -> None:
    """Require completion, formatting, linting, types, and focused tests."""
    findings = incomplete_problem(paths)
    if findings:
        raise ReadyError("incomplete scaffold:\n" + "\n".join(findings))
    validate_problem_metadata(paths)
    print(f"Ready scope: {paths.language} {paths.problem_id}")
    for command in problem_commands(root, paths, no_sync=no_sync):
        result = run(command, cwd=root, check=False)
        if result.returncode != 0:
            raise ReadyError(
                f"command failed with exit status {result.returncode}: {' '.join(command)}"
            )


def changed_paths(root: Path, *, git_run: GitRunner = run_git) -> list[str]:
    """Return branch, worktree, and untracked paths changed from the default branch."""
    tracked = git_run(("git", "diff", "--name-only", "--diff-filter=ACMRD", "HEAD"), root)
    if tracked.returncode != 0:
        tracked = git_run(("git", "diff", "--name-only", "--diff-filter=ACMRD"), root)
        if tracked.returncode != 0:
            raise _git_error(tracked, "could not inspect Git diff")
    branch_paths: set[str] = set()
    default_branch = git_run(
        ("git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"), root
    )
    if default_branch.returncode == 0 and default_branch.stdout.strip():
        base = default_branch.stdout.strip()
        merge_base = git_run(("git", "merge-base", "HEAD", base), root)
        if merge_base.returncode == 0 and merge_base.stdout.strip():
            committed = git_run(
                (
                    "git",
                    "diff",
                    "--name-only",
                    "--diff-filter=ACMRD",
                    f"{merge_base.stdout.strip()}..HEAD",
                ),
                root,
            )
            if committed.returncode != 0:
                raise _git_error(committed, "could not inspect committed branch diff")
            branch_paths.update(committed.stdout.splitlines())
    untracked = git_run(("git", "ls-files", "--others", "--exclude-standard"), root)
    if untracked.returncode != 0:
        raise ReadyError(
            (untracked.stderr or untracked.stdout).strip() or "could not inspect files"
        )
    return sorted(
        branch_paths | set(tracked.stdout.splitlines()) | set(untracked.stdout.splitlines())
    )


def staged_paths(root: Path, *, git_run: GitRunner = run_git) -> list[str]:
    """Return only paths represented by the index relative to ``HEAD``.

    Unlike :func:`changed_paths`, this deliberately excludes unstaged edits and untracked files.
    The deletion filter is important: a staged removal of a required source or test must select
    that problem so the snapshot gate can reject it safely.
    """

    result = git_run(
        ("git", "diff", "--cached", "--name-only", "--diff-filter=ACMRD", "HEAD"),
        root,
    )
    if result.returncode != 0:
        result = git_run(
            ("git", "diff", "--cached", "--name-only", "--diff-filter=ACMRD"),
            root,
        )
        if result.returncode != 0:
            raise _git_error(result, "could not inspect staged Git diff")
    return sorted(set(result.stdout.splitlines()))


def staged_dependency_divergences(
    root: Path,
    paths: Sequence[str],
    *,
    git_run: GitRunner = run_git,
) -> tuple[str, ...]:
    """Return unstaged manifest edits that make the staged dependency view ambiguous."""
    if not paths:
        return ()
    dependency_manifests = sorted(DEPENDENCY_MANIFESTS)
    result = git_run(("git", "diff", "--name-only", "--", *dependency_manifests), root)
    if result.returncode != 0:
        raise _git_error(result, "could not compare staged dependency manifests")
    return tuple(sorted(set(result.stdout.splitlines()).intersection(dependency_manifests)))


@contextmanager
def staged_snapshot(root: Path, *, git_run: GitRunner = run_git) -> Iterator[Path]:
    """Materialize the index in a temporary directory and yield its root.

    ``git checkout-index`` reads blobs from the index directly.  Consequently a staged quality
    gate cannot accidentally read a later unstaged edit or an untracked file from the caller's
    working tree.  Dependency directories are linked when available so real format/test commands
    remain usable without copying generated environments into the snapshot.
    """

    with tempfile.TemporaryDirectory(prefix="ready-staged-") as temporary:
        snapshot = Path(temporary)
        prefix = f"{snapshot}{'' if str(snapshot).endswith('/') else '/'}"
        result = git_run(("git", "checkout-index", "--all", f"--prefix={prefix}"), root)
        if result.returncode != 0:
            raise _git_error(result, "could not materialize staged Git snapshot")
        for dependency in ("node_modules", ".venv"):
            source = root / dependency
            target = snapshot / dependency
            if source.exists() and not target.exists():
                try:
                    target.symlink_to(source, target_is_directory=True)
                except OSError as error:
                    raise ReadyError(
                        f"could not link {dependency} into staged snapshot: {error}"
                    ) from error
        yield snapshot


def changed_problem_keys(paths: Sequence[str]) -> tuple[list[tuple[str, str]], bool]:
    """Return changed problem IDs and whether repository tooling also changed."""
    keys: set[tuple[str, str]] = set()
    requires_full = False
    code_prefixes = ("bin/", "scripts/", "tests/", ".github/", ".husky/", ".vscode/")
    code_files = {
        "package.json",
        "pnpm-lock.yaml",
        "pyproject.toml",
        "uv.lock",
        "lc.toml",
        ".node-version",
        ".python-version",
        "tsconfig.json",
        "vitest.config.ts",
        "vitest.retry.config.ts",
        "biome.json",
        "mise.toml",
    }
    for value in paths:
        parts = Path(value).parts
        if parts and parts[0] == "src":
            if len(parts) >= 3 and parts[1] in {"python", "typescript"}:
                directory = parts[2]
                if directory.startswith("p_"):
                    raw_problem_id, separator, slug = directory[2:].partition("_")
                    if not separator or not slug:
                        requires_full = True
                        continue
                    try:
                        problem_id = normalize_problem_id(raw_problem_id)
                    except ProblemPathError:
                        requires_full = True
                    else:
                        keys.add(("py" if parts[1] == "python" else "ts", problem_id))
                    continue
            # Shared data structures, new source roots, malformed problem directories, and any
            # other source change cannot be safely mapped to one focused problem gate.
            requires_full = True
            continue
        if parts and parts[0] == "tracks":
            requires_full = True
            continue
        if value.startswith(code_prefixes) or value in code_files:
            requires_full = True
    return sorted(keys), requires_full


def run_changed_gate(
    root: Path,
    *,
    run: Runner = subprocess.run,
    git_run: GitRunner = run_git,
) -> None:
    """Check changed problems, falling back to the full gate for tooling changes."""
    paths = changed_paths(root, git_run=git_run)
    if not paths:
        # A clean feature branch may contain only committed changes relative to
        # its base.  Without a reliable merge-base in every local checkout,
        # the safe fallback is the complete gate rather than a false no-op.
        run_full_gate(root, run=run)
        return
    keys, requires_full = changed_problem_keys(paths)
    if requires_full:
        run_full_gate(root, run=run)
        return
    if not keys:
        run_full_gate(root, run=run)
        return
    for language, problem_id in keys:
        try:
            paths = resolve_problem_paths(root, language, problem_id)
        except ProblemPathError as error:
            raise ReadyError(
                f"changed problem {language} {problem_id} is incomplete: {error}"
            ) from error
        try:
            run_problem_gate(root, paths, run=run)
        except ProblemPathError as error:
            raise ReadyError(
                f"changed problem {language} {problem_id} is incomplete: {error}"
            ) from error


def run_staged_gate(
    root: Path,
    *,
    run: Runner = subprocess.run,
    git_run: GitRunner = run_git,
) -> None:
    """Run a quality gate against only the staged index snapshot.

    Tooling changes trigger the complete gate in the snapshot.  Problem changes run the focused
    gate against snapshot paths.  A missing source, test, or problem directory is reported as a
    readiness error before any formatter or test process can operate on a partial problem.
    """

    paths = staged_paths(root, git_run=git_run)
    keys, requires_full = changed_problem_keys(paths)
    if not paths:
        print("Ready scope: no staged changes")
        return
    divergences = staged_dependency_divergences(root, paths, git_run=git_run)
    if divergences:
        names = ", ".join(divergences)
        raise ReadyError(
            "unstaged dependency manifest edits make the staged dependency view unsafe: "
            f"{names}; stage or discard them before running the staged gate"
        )
    with staged_snapshot(root, git_run=git_run) as snapshot:
        if requires_full:
            run_full_gate(snapshot, run=run, no_sync=True)
            return
        if not keys:
            print("Ready scope: no staged solution code")
            return
        for language, problem_id in keys:
            try:
                problem = resolve_problem_paths(snapshot, language, problem_id)
            except ProblemPathError as error:
                raise ReadyError(
                    f"staged problem {language} {problem_id} is incomplete: {error}"
                ) from error
            try:
                run_problem_gate(snapshot, problem, run=run, no_sync=True)
            except ProblemPathError as error:
                raise ReadyError(
                    f"staged problem {language} {problem_id} is incomplete: {error}"
                ) from error


def run_full_gate(root: Path, *, run: Runner = subprocess.run, no_sync: bool = False) -> None:
    """Delegate to the complete, non-recursive package quality gate."""
    print("Ready scope: all")
    kwargs: dict[str, object] = {"cwd": root, "check": False}
    if no_sync:
        environment = dict(environ)
        environment["UV_NO_SYNC"] = "1"
        kwargs["env"] = environment
    result = run(["pnpm", "run", "ready:all"], **kwargs)
    if result.returncode != 0:
        raise ReadyError(f"full quality gate failed with exit status {result.returncode}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``current``, ``changed``, ``staged``, or ``all`` readiness."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parents[1]
    try:
        if arguments == ["changed"]:
            run_changed_gate(root)
        elif arguments == ["staged"]:
            run_staged_gate(root)
        elif arguments == ["all"]:
            run_full_gate(root)
        elif arguments == ["metadata"]:
            validate_all_problem_metadata(root)
            validate_track_metadata(root)
        elif len(arguments) == 3 and arguments[0] == "current":
            run_problem_gate(root, resolve_problem_paths(root, arguments[1], arguments[2]))
        else:
            raise ReadyError(
                "usage: ready.py current <py|ts> <ID> | changed | staged | metadata | all"
            )
    except (OSError, ProblemPathError, ReadyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2 if str(error).startswith("usage:") else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
