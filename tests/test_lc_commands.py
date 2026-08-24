from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts import lc


PROBLEM_URL = "https://leetcode.com/problems/search-insert-position/"


def make_problem(root: Path, language: str, problem_id: str = "0035") -> Path:
    """Create a complete conventional problem directory."""
    slug = "search_insert_position"
    directory = root / "src" / ("python" if language == "py" else "typescript")
    directory /= f"p_{problem_id}_{slug}"
    directory.mkdir(parents=True)
    extension = "py" if language == "py" else "ts"
    source = directory / f"{directory.name}.{extension}"
    test = (
        directory / f"test_{directory.name}.py"
        if language == "py"
        else directory / f"{directory.name}.test.ts"
    )
    source.write_text("# solution\n" if language == "py" else "export {};\n", encoding="utf-8")
    test.write_text(
        "def test_placeholder(): pass\n" if language == "py" else "export {};\n", encoding="utf-8"
    )
    return directory


def initialize_git_repository(root: Path) -> None:
    """Create the clean main-branch baseline needed by real lifecycle tests."""
    subprocess.run(("git", "init", "-b", "main"), cwd=root, check=True, capture_output=True)
    marker = root / ".gitignore"
    marker.write_text(".lc/\n", encoding="utf-8")
    subprocess.run(("git", "add", "."), cwd=root, check=True)
    subprocess.run(
        (
            "git",
            "-c",
            "user.name=Leet Test",
            "-c",
            "user.email=lc@example.invalid",
            "commit",
            "-m",
            "initialize",
        ),
        cwd=root,
        check=True,
        capture_output=True,
    )


def branch_runner(branch: str) -> lc.CommandResult:
    """Return a Git runner that only permits the branch lookup used for context."""

    def run(command: Sequence[str], _cwd: Path) -> lc.CommandResult:
        assert tuple(command) == ("git", "branch", "--show-current")
        return lc.CommandResult(0, f"{branch}\n")

    return run


class LifecycleGit:
    """Small stateful Git double for start/resume branch assertions."""

    def __init__(
        self,
        root: Path,
        branch: str = "feat/p-0099-existing",
        *,
        dirty: bool = False,
    ) -> None:
        self.root = root
        self.branch = branch
        self.dirty = dirty
        self.branches = {"main", branch}
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, command: Sequence[str], cwd: Path) -> lc.CommandResult:
        assert cwd == self.root
        call = tuple(command)
        self.calls.append(call)
        if call == ("git", "rev-parse", "--show-toplevel"):
            return lc.CommandResult(0, f"{self.root}\n")
        if call == ("git", "status", "--porcelain"):
            return lc.CommandResult(0, "?? src/new-solution.ts\n" if self.dirty else "")
        if call == ("git", "branch", "--show-current"):
            return lc.CommandResult(0, f"{self.branch}\n")
        if call[:4] == ("git", "show-ref", "--verify", "--quiet"):
            return lc.CommandResult(
                0 if call[-1].removeprefix("refs/heads/") in self.branches else 1
            )
        if call == ("git", "for-each-ref", "--format=%(refname)", "refs/remotes"):
            return lc.CommandResult(0)
        if call == ("git", "for-each-ref", "--format=%(refname:short)", "refs/heads"):
            return lc.CommandResult(0, "\n".join(sorted(self.branches)))
        if call[:3] == ("git", "switch", "-c"):
            self.branch = call[3]
            self.branches.add(self.branch)
            return lc.CommandResult(0)
        if call[:2] == ("git", "switch"):
            self.branch = call[2]
            return lc.CommandResult(0)
        if call[:3] == ("git", "branch", "-D"):
            self.branches.discard(call[3])
            return lc.CommandResult(0)
        raise AssertionError(f"unexpected Git command: {call}")


def test_detects_a_problem_from_caller_directory_before_git(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "ts")

    context = lc.detect_problem_context(
        tmp_path,
        directory / "nested" / "editor",
        git_run=branch_runner("not-a-problem-branch"),
    )

    assert context is not None
    assert context.language == "ts"
    assert context.problem_id == "0035"
    assert context.directory == directory


def test_detects_only_strict_feature_problem_branches(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "py")
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    context = lc.detect_problem_context(
        tmp_path,
        outside,
        git_run=branch_runner("feat/p-0035-search-insert-position"),
    )
    assert context is not None
    assert context.language == "py"
    assert context.problem_id == "0035"
    assert context.directory == directory

    assert (
        lc.detect_problem_context(
            tmp_path,
            outside,
            git_run=branch_runner("feature/p-0035-search-insert-position"),
        )
        is None
    )
    assert (
        lc.detect_problem_context(
            tmp_path,
            outside,
            git_run=branch_runner("feat/p-35-search-insert-position"),
        )
        is None
    )


def test_start_uses_main_and_repeats_idempotently(tmp_path: Path) -> None:
    git = LifecycleGit(tmp_path)
    metadata = lc.ProblemMetadata(
        "0035",
        "Search Insert Position",
        "search-insert-position",
        PROBLEM_URL,
        "searchInsert(nums: number[], target: number): number",
    )

    def creator(
        root: Path,
        language: str,
        problem_id: str,
        title: Sequence[str],
        url: str,
        signature: str | None,
        *,
        details: object,
    ) -> tuple[Path, Path, str]:
        assert (language, problem_id, url, signature) == (
            "ts",
            "0035",
            PROBLEM_URL,
            metadata.signature,
        )
        assert details == lc.ProblemDetails()
        directory = root / "src/typescript/p_0035_search_insert_position"
        directory.mkdir(parents=True)
        source = directory / "p_0035_search_insert_position.ts"
        test = directory / "p_0035_search_insert_position.test.ts"
        source.write_text("", encoding="utf-8")
        test.write_text("", encoding="utf-8")
        return source, test, "feat/p-0035-search-insert-position"

    result = lc.start_problem(
        tmp_path,
        "ts",
        PROBLEM_URL,
        fetch=lambda _language, _url: metadata,
        run=git,
        creator=creator,
    )
    git.dirty = True
    repeated = lc.start_problem(
        tmp_path,
        "ts",
        PROBLEM_URL,
        fetch=lambda _language, _url: metadata,
        run=git,
        creator=creator,
    )

    assert result.created
    assert not repeated.created
    assert result.branch == repeated.branch == "feat/p-0035-search-insert-position"
    assert ("git", "switch", "main") in git.calls
    assert ("git", "switch", "-c", "feat/p-0035-search-insert-position") in git.calls


def test_start_restores_original_branch_when_base_validation_fails(tmp_path: Path) -> None:
    original_branch = "feature/current-work"
    target_branch = "feat/p-0035-search-insert-position"
    git = LifecycleGit(tmp_path, branch=original_branch)
    problem = lc.ProblemMetadata(
        "0035",
        "Search Insert Position",
        "search-insert-position",
        PROBLEM_URL,
        "searchInsert(nums: number[], target: number): number",
    )

    def remote_collision(command: Sequence[str], cwd: Path) -> lc.CommandResult:
        if tuple(command) == ("git", "for-each-ref", "--format=%(refname)", "refs/remotes"):
            return lc.CommandResult(0, f"refs/remotes/origin/{target_branch}\n")
        return git(command, cwd)

    with pytest.raises(lc.LeetError, match="branch already exists on a remote"):
        lc.start_problem(
            tmp_path,
            "ts",
            PROBLEM_URL,
            fetch=lambda _language, _url: problem,
            run=remote_collision,
        )

    assert git.branch == original_branch
    assert ("git", "switch", "main") in git.calls
    assert ("git", "switch", original_branch) in git.calls


def test_start_restores_original_branch_when_existing_target_is_incomplete(
    tmp_path: Path,
) -> None:
    original_branch = "feature/current-work"
    target_branch = "feat/p-0035-search-insert-position"
    git = LifecycleGit(tmp_path, branch=original_branch)
    git.branches.add(target_branch)

    with pytest.raises(lc.LeetError, match="has no local problem directory"):
        lc.start_problem(tmp_path, None, "35", run=git)

    assert git.branch == original_branch
    assert ("git", "switch", target_branch) in git.calls
    assert ("git", "switch", original_branch) in git.calls


def test_start_restores_original_branch_when_existing_target_has_partial_scaffold(
    tmp_path: Path,
) -> None:
    original_branch = "feature/current-work"
    target_branch = "feat/p-0035-search-insert-position"
    directory = make_problem(tmp_path, "ts")
    (directory / f"{directory.name}.test.ts").unlink()
    git = LifecycleGit(tmp_path, branch=original_branch)
    git.branches.add(target_branch)

    with pytest.raises(lc.LeetError, match="incomplete local problem scaffold"):
        lc.start_problem(tmp_path, None, "35", run=git)

    assert git.branch == original_branch
    assert ("git", "switch", target_branch) in git.calls
    assert ("git", "switch", original_branch) in git.calls


def test_start_is_repeatable_with_real_untracked_scaffold_files(tmp_path: Path) -> None:
    initialize_git_repository(tmp_path)
    problem = lc.ProblemMetadata(
        "0035",
        "Search Insert Position",
        "search-insert-position",
        PROBLEM_URL,
        "searchInsert(nums: number[], target: number): number",
    )

    created = lc.start_problem(
        tmp_path,
        "ts",
        PROBLEM_URL,
        fetch=lambda _language, _url: problem,
    )
    status = subprocess.run(
        ("git", "status", "--porcelain"),
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout.strip()

    def unexpected_fetch(_language: str, _url: str) -> lc.ProblemMetadata:
        raise AssertionError("an idempotent start must not refetch metadata")

    repeated = lc.start_problem(tmp_path, None, PROBLEM_URL, fetch=unexpected_fetch)

    assert created.created is True
    assert repeated.created is False
    assert repeated.language == "ts"
    assert repeated.directory == created.directory


def test_no_branch_start_is_repeatable_with_dirty_scaffold_files(tmp_path: Path) -> None:
    initialize_git_repository(tmp_path)
    problem = lc.ProblemMetadata(
        "0035",
        "Search Insert Position",
        "search-insert-position",
        PROBLEM_URL,
        "searchInsert(nums: number[], target: number): number",
    )

    created = lc.start_problem(
        tmp_path,
        "ts",
        PROBLEM_URL,
        fetch=lambda _language, _url: problem,
        no_branch=True,
    )

    def unexpected_fetch(_language: str, _url: str) -> lc.ProblemMetadata:
        raise AssertionError("an idempotent --no-branch start must not refetch metadata")

    repeated = lc.start_problem(
        tmp_path,
        None,
        PROBLEM_URL,
        fetch=unexpected_fetch,
        no_branch=True,
    )
    branch = subprocess.run(
        ("git", "branch", "--show-current"),
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    assert created.created is True
    assert repeated.created is False
    assert repeated.directory == created.directory
    assert branch.stdout.strip() == "main"


def test_no_branch_id_start_is_repeatable_with_dirty_solution(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "ts")
    source = directory / f"{directory.name}.ts"
    test = directory / f"{directory.name}.test.ts"
    source.write_text("export function solve(): number { return 1; }\n", encoding="utf-8")
    test.write_text('test("example", () => expect(true).toBe(true));\n', encoding="utf-8")
    initialize_git_repository(tmp_path)
    source.write_text("export function solve(): number { return 2; }\n", encoding="utf-8")

    repeated = lc.start_problem(tmp_path, None, "35", no_branch=True)
    branch = subprocess.run(
        ("git", "branch", "--show-current"),
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    assert repeated.created is False
    assert repeated.language == "ts"
    assert repeated.directory == directory
    assert branch.stdout.strip() == "main"


def test_start_without_language_detects_a_python_only_problem(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "py", "1512")
    git = LifecycleGit(tmp_path, branch="main")

    result = lc.start_problem(tmp_path, None, "1512", run=git)

    assert result.language == "py"
    assert result.directory == directory
    assert result.branch == "feat/p-1512-search-insert-position"


def test_active_timer_conflict_stops_before_branch_or_file_mutation(tmp_path: Path) -> None:
    git = LifecycleGit(tmp_path, branch="main")
    active = lc.Session("session-99", "0099", "ts", "new", datetime.now(UTC))
    problem = lc.ProblemMetadata(
        "0035",
        "Search Insert Position",
        "search-insert-position",
        PROBLEM_URL,
        "searchInsert(nums: number[], target: number): number",
    )
    created = False

    def creator(*_arguments: object, **_keywords: object) -> tuple[Path, Path, str]:
        nonlocal created
        created = True
        raise AssertionError("creator must not run while another timer is active")

    with pytest.raises(lc.LeetError, match="0099.*already active"):
        lc.start_problem(
            tmp_path,
            "ts",
            PROBLEM_URL,
            fetch=lambda _language, _url: problem,
            run=git,
            creator=creator,
            active_session=active,
        )

    assert created is False
    assert git.branch == "main"
    assert not any(call[:2] == ("git", "switch") for call in git.calls)


def test_resume_by_id_switches_existing_branch(tmp_path: Path) -> None:
    make_problem(tmp_path, "ts")
    git = LifecycleGit(tmp_path)
    git.branches.add("feat/p-0035-search-insert-position")

    result = lc.resume_problem(tmp_path, "35", run=git)

    assert result.problem_id == "0035"
    assert result.branch == "feat/p-0035-search-insert-position"
    assert git.branch == result.branch


def test_resume_detects_language_after_switching_to_problem_branch(tmp_path: Path) -> None:
    git = LifecycleGit(tmp_path)
    target_branch = "feat/p-0035-search-insert-position"
    git.branches.add(target_branch)

    def switch_with_python_problem(command: Sequence[str], cwd: Path) -> lc.CommandResult:
        result = git(command, cwd)
        if tuple(command) == ("git", "switch", target_branch):
            make_problem(tmp_path, "py")
        return result

    result = lc.resume_problem(tmp_path, "35", run=switch_with_python_problem)

    assert result.language == "py"
    assert result.directory == tmp_path / "src/python/p_0035_search_insert_position"
    assert git.branch == target_branch


def test_resume_rejects_a_different_active_problem_before_switching(tmp_path: Path) -> None:
    make_problem(tmp_path, "ts")
    git = LifecycleGit(tmp_path)
    git.branches.add("feat/p-0035-search-insert-position")
    active = lc.Session("active", "0099", "ts", "new", datetime.now(UTC))

    with pytest.raises(lc.LeetError, match="0099.*already active"):
        lc.resume_problem(tmp_path, "35", run=git, active_session=active)

    assert git.branch == "feat/p-0099-existing"
    assert not any(call[:2] == ("git", "switch") for call in git.calls)


def test_start_timer_is_idempotent_for_the_same_problem(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "ts")
    source = directory / f"{directory.name}.ts"
    test = directory / f"{directory.name}.test.ts"
    source.write_text("export function solve(): void {}\n", encoding="utf-8")
    test.write_text('test("example", () => expect(true).toBe(true));\n', encoding="utf-8")
    result = lc.LifecycleResult(
        language="ts",
        problem_id="0035",
        directory=directory,
        source_path=source,
        test_path=test,
        branch="feat/p-0035-search-insert-position",
    )

    first, first_created = lc._ensure_practice_session(tmp_path, result)
    repeated, repeated_created = lc._ensure_practice_session(tmp_path, result)

    assert first_created is True
    assert repeated_created is False
    assert repeated == first
    assert (tmp_path / ".lc" / "practice-active.json").is_file()


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (("test", "35"), ("pnpm", "run", "test:one", "ts", "35")),
        (("test", "py", "35"), ("pnpm", "run", "test:one", "py", "35")),
        (("test", "ts"), ("pnpm", "run", "test:ts")),
        (
            (
                "test",
                "src/python/p_0035_search_insert_position/test_p_0035_search_insert_position.py",
            ),
            (
                "pnpm",
                "run",
                "test:py",
                "src/python/p_0035_search_insert_position/test_p_0035_search_insert_position.py",
            ),
        ),
        (
            (
                "test",
                "src/typescript/p_0035_search_insert_position/p_0035_search_insert_position.ts",
            ),
            (
                "pnpm",
                "run",
                "test:ts",
                "src/typescript/p_0035_search_insert_position/p_0035_search_insert_position.test.ts",
            ),
        ),
        (("test", "ts", "35", "--watch"), ("pnpm", "run", "test:one", "ts", "35", "--watch")),
        (
            ("submit", "35"),
            ("uv", "run", "python", "scripts/submission.py", "ts", "35"),
        ),
        (
            ("submit", "py", "35", "--copy"),
            ("uv", "run", "python", "scripts/submission.py", "py", "35", "--copy"),
        ),
        (("ready",), ("python", "scripts/ready.py", "changed")),
        (("check",), ("pnpm", "run", "check")),
        (("test-all",), ("pnpm", "run", "test")),
        (("incomplete",), ("pnpm", "run", "incomplete")),
        (("doctor",), ("python", "scripts/doctor.py")),
        (("compat",), ("pnpm", "run", "compat")),
        (("typecheck",), ("pnpm", "run", "typecheck")),
        (("format",), ("pnpm", "run", "format")),
        (("format", "check"), ("pnpm", "run", "format:check")),
        (("format", "py", "--check"), ("pnpm", "run", "format:check:py")),
        (("format-check", "ts"), ("pnpm", "run", "format:check:ts")),
        (("lint",), ("pnpm", "run", "lint")),
        (("lint", "py"), ("pnpm", "run", "lint:py")),
    ],
)
def test_builds_the_documented_dispatcher_commands(
    tmp_path: Path, arguments: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    assert lc.build_command(arguments, tmp_path, tmp_path) == expected


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (("t", "35"), ("pnpm", "run", "test:one", "ts", "35")),
        (("w", "35"), ("pnpm", "run", "test:one", "ts", "35", "--watch")),
        (
            ("s", "35"),
            ("uv", "run", "python", "scripts/submission.py", "ts", "35"),
        ),
        (
            ("copy", "35"),
            ("uv", "run", "python", "scripts/submission.py", "ts", "35", "--copy-only"),
        ),
        (("r",), ("python", "scripts/ready.py", "changed")),
        (("c",), ("pnpm", "run", "check")),
        (("fmt", "ts"), ("pnpm", "run", "format:ts")),
    ],
)
def test_builds_alias_commands(
    tmp_path: Path, arguments: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    assert lc.build_command(arguments, tmp_path, tmp_path) == expected


def test_uses_detected_context_for_test_submit_and_watch(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "ts")

    assert lc.build_command(("test",), tmp_path, directory) == (
        "pnpm",
        "run",
        "test:one",
        "ts",
        "0035",
    )
    assert lc.build_command(("w",), tmp_path, directory) == (
        "pnpm",
        "run",
        "test:one",
        "ts",
        "0035",
        "--watch",
    )
    assert lc.build_command(("submit", "--copy"), tmp_path, directory) == (
        "uv",
        "run",
        "python",
        "scripts/submission.py",
        "ts",
        "0035",
        "--copy",
    )


def test_allows_runner_passthrough_for_focused_id_and_current_tests(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "ts")

    assert lc.build_command(("test", "35", "--", "--run", "search"), tmp_path, tmp_path) == (
        "pnpm",
        "run",
        "test:one",
        "ts",
        "35",
        "--run",
        "search",
    )
    assert lc.build_command(("test", "--", "--reporter", "verbose"), tmp_path, directory) == (
        "pnpm",
        "run",
        "test:one",
        "ts",
        "0035",
        "--reporter",
        "verbose",
    )


def test_supports_python_watch_for_the_current_problem(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "py")

    assert lc.build_command(("test", "--watch"), tmp_path, directory) == (
        "pnpm",
        "run",
        "test:one",
        "py",
        "0035",
        "--watch",
    )


def test_builds_scoped_ready_commands(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "py")
    git_run = branch_runner("feat/p-0035-search-insert-position")

    assert lc.build_command(("ready", "--current"), tmp_path, directory, git_run=git_run) == (
        "python",
        "scripts/ready.py",
        "current",
        "py",
        "0035",
    )
    assert lc.build_command(("ready", "--changed"), tmp_path, tmp_path) == (
        "python",
        "scripts/ready.py",
        "changed",
    )
    assert lc.build_command(("ready", "all"), tmp_path, tmp_path) == (
        "python",
        "scripts/ready.py",
        "all",
    )
    assert lc.build_command(("ready",), tmp_path, directory, git_run=git_run) == (
        "python",
        "scripts/ready.py",
        "current",
        "py",
        "0035",
    )


def test_builds_practice_commands_with_language_shorthand(tmp_path: Path) -> None:
    assert lc.build_command(("today", "py", "--limit", "2"), tmp_path, tmp_path) == (
        "python",
        "scripts/practice.py",
        "today",
        "--language",
        "py",
        "--limit",
        "2",
        "--human",
        "--root",
        str(tmp_path),
    )
    assert lc.build_command(
        ("practice", "start", "ts", "35", "--mode", "mock"), tmp_path, tmp_path
    ) == (
        "python",
        "scripts/practice.py",
        "start",
        "--language",
        "ts",
        "35",
        "--mode",
        "mock",
        "--human",
        "--root",
        str(tmp_path),
    )
    assert lc.build_command(
        ("finish", "--result", "solved", "--confidence", "4"), tmp_path, tmp_path
    ) == (
        "python",
        "scripts/practice.py",
        "finish",
        "--result",
        "solved",
        "--confidence",
        "4",
        "--human",
        "--root",
        str(tmp_path),
    )


def test_submit_exposes_safe_copy_and_preflight_controls(tmp_path: Path) -> None:
    assert lc.build_command(("copy", "35"), tmp_path, tmp_path) == (
        "uv",
        "run",
        "python",
        "scripts/submission.py",
        "ts",
        "35",
        "--copy-only",
    )
    assert lc.build_command(
        ("submit", "py", "35", "--copy-only", "--no-check"), tmp_path, tmp_path
    ) == (
        "uv",
        "run",
        "python",
        "scripts/submission.py",
        "py",
        "35",
        "--copy-only",
        "--no-check",
    )


def test_requires_explicit_all_outside_a_problem_context(tmp_path: Path) -> None:
    git_run = branch_runner("main")

    with pytest.raises(lc.LcUsageError, match="test all"):
        lc.build_command(("test",), tmp_path, tmp_path, git_run=git_run)
    with pytest.raises(lc.LcUsageError, match="watch all"):
        lc.build_command(("watch",), tmp_path, tmp_path, git_run=git_run)
    assert lc.build_command(("test", "all"), tmp_path, tmp_path, git_run=git_run) == (
        "pnpm",
        "run",
        "test",
    )
    assert lc.build_command(("watch", "all"), tmp_path, tmp_path, git_run=git_run) == (
        "pnpm",
        "run",
        "test:ts:watch",
    )


def test_typescript_is_the_default_when_a_branch_has_both_languages(tmp_path: Path) -> None:
    typescript_directory = make_problem(tmp_path, "ts")
    make_problem(tmp_path, "py")

    context = lc.detect_problem_context(
        tmp_path,
        tmp_path,
        git_run=branch_runner("feat/p-0035-search-insert-position"),
    )

    assert context == lc.ProblemContext("ts", "0035", typescript_directory)


def test_resolves_relative_test_paths_from_the_original_caller_directory(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "py")
    test_name = "test_p_0035_search_insert_position.py"

    assert lc.build_command(("test", test_name), tmp_path, directory) == (
        "pnpm",
        "run",
        "test:py",
        f"src/python/p_0035_search_insert_position/{test_name}",
    )


def test_current_reports_problem_branch_and_colocated_paths(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "ts")
    source = directory / f"{directory.name}.ts"
    test = directory / f"{directory.name}.test.ts"
    source.write_text("", encoding="utf-8")
    test.write_text("", encoding="utf-8")

    context, branch, source_path, test_path = lc.current_problem_status(
        tmp_path,
        directory,
        git_run=branch_runner("feat/p-0035-search-insert-position"),
    )

    assert context == lc.ProblemContext("ts", "0035", directory)
    assert branch == "feat/p-0035-search-insert-position"
    assert source_path == source
    assert test_path == test


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("test", "35", "--watch", "--watch"), "only be provided once"),
        (("submit", "35", "--copy", "--copy"), "only be provided once"),
        (("test", "../outside.py"), "inside this repository"),
        (("format", "rust"), "language must"),
        (("unknown",), "unknown command"),
    ],
)
def test_rejects_ambiguous_or_unsafe_invocations(
    tmp_path: Path, arguments: tuple[str, ...], message: str
) -> None:
    with pytest.raises(lc.LcUsageError, match=message):
        lc.build_command(arguments, tmp_path, tmp_path, git_run=branch_runner("main"))


def test_manual_scaffold_preserves_language_and_metadata_arguments(tmp_path: Path) -> None:
    signature = "answer(self, value: int) -> int"

    assert lc.build_command(
        (
            "new",
            "python",
            "42",
            "Answer",
            "Everything",
            "--url",
            PROBLEM_URL,
            "--signature",
            signature,
        ),
        tmp_path,
        tmp_path,
    ) == (
        "pnpm",
        "run",
        "new",
        "py",
        "42",
        "Answer",
        "Everything",
        "--url",
        PROBLEM_URL,
        "--signature",
        signature,
    )


def test_vscode_url_task_uses_the_resumable_start_workflow() -> None:
    tasks_path = Path(__file__).resolve().parents[1] / ".vscode/tasks.json"
    document = json.loads(tasks_path.read_text(encoding="utf-8"))
    task = next(
        item for item in document["tasks"] if item["label"] == "New LeetCode Problem from URL"
    )

    assert task["args"][-3:] == [
        "start",
        "${input:problemLanguage}",
        "${input:problemUrl}",
    ]


def test_main_preserves_url_scaffolding_and_delegates_manual_new(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repository"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    monkeypatch.setattr(lc, "__file__", str(scripts / "lc.py"))

    scaffold_calls: list[tuple[Path, str, str]] = []
    manual_calls: list[tuple[tuple[str, ...], Path]] = []

    def scaffold(root_arg: Path, language: str, url: str) -> lc.ScaffoldResult:
        scaffold_calls.append((root_arg, language, url))
        metadata = lc.ProblemMetadata(
            "0035", "Search Insert Position", "search-insert-position", url, "solve(): number"
        )
        source = (
            root_arg
            / "src/typescript/p_0035_search-insert-position/p_0035_search-insert-position.ts"
        )
        test = (
            root_arg
            / "src/typescript/p_0035_search-insert-position/p_0035_search-insert-position.test.ts"
        )
        return lc.ScaffoldResult(metadata, source, test, "feat/p-0035-search-insert-position")

    def run(command: tuple[str, ...], cwd: Path) -> int:
        manual_calls.append((command, cwd))
        return 0

    monkeypatch.setattr(lc, "scaffold_from_url", scaffold)
    monkeypatch.setattr(lc, "run_interactive_command", run)

    assert lc.main([PROBLEM_URL]) == 0
    assert lc.main(["py", PROBLEM_URL]) == 0
    assert lc.main(["new", PROBLEM_URL]) == 0
    assert lc.main(["new", "python", PROBLEM_URL]) == 0
    assert scaffold_calls == [
        (root, "ts", PROBLEM_URL),
        (root, "py", PROBLEM_URL),
        (root, "ts", PROBLEM_URL),
        (root, "py", PROBLEM_URL),
    ]

    assert lc.main(["new", "1512", "Number", "of", "Good", "Pairs"]) == 0
    assert manual_calls == [
        (("pnpm", "run", "new", "ts", "1512", "Number", "of", "Good", "Pairs"), root)
    ]


def test_main_preserves_implicit_start_language_and_prechecks_timer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repository"
    scripts = root / "scripts"
    directory = root / "src/python/p_1512_number_of_good_pairs"
    scripts.mkdir(parents=True)
    directory.mkdir(parents=True)
    monkeypatch.setattr(lc, "__file__", str(scripts / "lc.py"))
    active = lc.Session("session-1512", "1512", "py", "new", datetime.now(UTC))
    captured: dict[str, object] = {}

    def start(
        root_arg: Path,
        language: str | None,
        value: str,
        **options: object,
    ) -> lc.LifecycleResult:
        captured.update(root=root_arg, language=language, value=value, options=options)
        return lc.LifecycleResult(
            "py",
            "1512",
            directory,
            directory / "p_1512_number_of_good_pairs.py",
            directory / "test_p_1512_number_of_good_pairs.py",
            "feat/p-1512-number-of-good-pairs",
        )

    monkeypatch.setattr(
        lc,
        "_read_active_practice_session",
        lambda _root, **_kwargs: active,
    )
    monkeypatch.setattr(lc, "start_problem", start)

    assert lc.main(["start", "1512"]) == 0
    assert captured["root"] == root
    assert captured["language"] is None
    assert captured["value"] == "1512"
    options = captured["options"]
    assert isinstance(options, dict)
    assert options["active_session"] == active

    assert lc.main(["start", "1512", "--no-timer"]) == 0
    options = captured["options"]
    assert isinstance(options, dict)
    assert options["active_session"] == active


def test_main_holds_session_transaction_across_lifecycle_and_timer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repository"
    scripts = root / "scripts"
    directory = root / "src/typescript/p_0035_search_insert_position"
    scripts.mkdir(parents=True)
    directory.mkdir(parents=True)
    monkeypatch.setattr(lc, "__file__", str(scripts / "lc.py"))
    locked = False

    class Transaction:
        def __enter__(self) -> None:
            nonlocal locked
            locked = True

        def __exit__(self, *_args: object) -> None:
            nonlocal locked
            locked = False

    class Store:
        def session_transaction(self) -> Transaction:
            return Transaction()

        def read_active(self) -> None:
            assert locked
            return None

    store = Store()
    result = lc.LifecycleResult(
        "ts",
        "0035",
        directory,
        directory / f"{directory.name}.ts",
        directory / f"{directory.name}.test.ts",
        "feat/p-0035-search-insert-position",
    )

    def start(*_args: object, **_kwargs: object) -> lc.LifecycleResult:
        assert locked
        return result

    def ensure(*_args: object, **options: object) -> tuple[lc.Session, bool]:
        assert locked
        assert options["store"] is store
        return lc.Session("session", "0035", "ts", "new", datetime.now(UTC)), True

    monkeypatch.setattr(lc, "PracticeStore", lambda _root: store)
    monkeypatch.setattr(lc, "start_problem", start)
    monkeypatch.setattr(lc, "_ensure_practice_session", ensure)

    assert lc.main(["start", "35"]) == 0
    assert locked is False


def test_main_propagates_child_status_and_help_never_runs_a_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repository"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    monkeypatch.setattr(lc, "__file__", str(scripts / "lc.py"))
    monkeypatch.setenv("LC_CALLER_CWD", str(root))
    calls: list[tuple[tuple[str, ...], Path]] = []

    def run(command: tuple[str, ...], cwd: Path) -> int:
        calls.append((command, cwd))
        return 37

    monkeypatch.setattr(lc, "run_interactive_command", run)

    assert lc.main(["ready"]) == 37
    assert calls == [(("python", "scripts/ready.py", "changed"), root)]

    assert lc.main([]) == 0
    assert lc.main(["help"]) == 0
    assert lc.main(["test", "--help"]) == 0
    assert calls == [(("python", "scripts/ready.py", "changed"), root)]


def test_finish_help_documents_elapsed_seconds(capsys: pytest.CaptureFixture[str]) -> None:
    assert lc.main(["finish", "--help"]) == 0

    output = capsys.readouterr().out
    assert "--elapsed SECONDS" in output
    assert "duration in seconds" in output
