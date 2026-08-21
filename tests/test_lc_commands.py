from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts import lc


PROBLEM_URL = "https://leetcode.com/problems/search-insert-position/"


def make_problem(root: Path, language: str, problem_id: str = "0035") -> Path:
    """Create the minimum conventional directory needed for context detection."""
    slug = "search_insert_position"
    directory = root / "src" / ("python" if language == "py" else "typescript")
    directory /= f"p_{problem_id}_{slug}"
    directory.mkdir(parents=True)
    return directory


def branch_runner(branch: str) -> lc.CommandResult:
    """Return a Git runner that only permits the branch lookup used for context."""

    def run(command: Sequence[str], _cwd: Path) -> lc.CommandResult:
        assert tuple(command) == ("git", "branch", "--show-current")
        return lc.CommandResult(0, f"{branch}\n")

    return run


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
        (("test", "ts", "35", "--watch"), ("pnpm", "run", "test:one", "ts", "35", "--watch")),
        (
            ("submit", "35"),
            ("uv", "run", "python", "scripts/submission.py", "ts", "35"),
        ),
        (
            ("submit", "py", "35", "--copy"),
            ("uv", "run", "python", "scripts/submission.py", "py", "35", "--copy"),
        ),
        (("ready",), ("pnpm", "run", "ready")),
        (("check",), ("pnpm", "run", "check")),
        (("test-all",), ("pnpm", "run", "test")),
        (("incomplete",), ("pnpm", "run", "incomplete")),
        (("doctor",), ("pnpm", "run", "doctor")),
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
            ("uv", "run", "python", "scripts/submission.py", "ts", "35", "--copy"),
        ),
        (("r",), ("pnpm", "run", "ready")),
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


def test_rejects_python_watch_without_running_a_child(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "py")

    with pytest.raises(lc.LcUsageError, match="only supported for TypeScript"):
        lc.build_command(("test", "--watch"), tmp_path, directory)


def test_falls_back_to_all_tests_and_all_typescript_watch(tmp_path: Path) -> None:
    git_run = branch_runner("main")

    assert lc.build_command(("test",), tmp_path, tmp_path, git_run=git_run) == (
        "pnpm",
        "run",
        "test",
    )
    assert lc.build_command(("watch",), tmp_path, tmp_path, git_run=git_run) == (
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


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("test", "py", "--watch"), "only supported for TypeScript"),
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
    assert calls == [(("pnpm", "run", "ready"), root)]

    assert lc.main([]) == 0
    assert lc.main(["help"]) == 0
    assert lc.main(["test", "--help"]) == 0
    assert calls == [(("pnpm", "run", "ready"), root)]
