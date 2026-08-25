import re
import subprocess
from pathlib import Path

import pytest

from scripts.ready import (
    CommandResult,
    ReadyError,
    changed_paths,
    changed_problem_keys,
    problem_commands,
    run_changed_gate,
    run_problem_gate,
    run_staged_gate,
    staged_paths,
    validate_all_problem_metadata,
    validate_problem_metadata,
    validate_track_metadata,
)
from scripts.problem_paths import resolve_problem_paths


def make_problem(root: Path, language: str = "ts", metadata: str | None = None) -> None:
    language_dir = "typescript" if language == "ts" else "python"
    stem = "p_0001_two_sum"
    directory = root / "src" / language_dir / stem
    directory.mkdir(parents=True)
    if language == "ts":
        (directory / f"{stem}.ts").write_text(
            "/* time: O(n), space: O(n) */\nexport function twoSum(): number[] { return []; }\n",
            encoding="utf-8",
        )
        (directory / f"{stem}.test.ts").write_text(
            'test("example", () => expect(true).toBe(true));\n', encoding="utf-8"
        )
    else:
        (directory / f"{stem}.py").write_text(
            '"""time: O(n), space: O(n)"""\nclass Solution:\n    pass\n', encoding="utf-8"
        )
        (directory / f"test_{stem}.py").write_text(
            "def test_example():\n    assert True\n", encoding="utf-8"
        )
    if metadata is not None:
        (directory / "problem.toml").write_text(metadata, encoding="utf-8")


def initialize_git(root: Path) -> None:
    """Create a local baseline so staged-index tests do not touch the main repository."""
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "ready@example.test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "Ready Tests"],
        check=True,
    )
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-qm", "baseline"],
        check=True,
    )


def test_problem_commands_are_language_scoped(tmp_path: Path) -> None:
    make_problem(tmp_path, "ts")
    paths = resolve_problem_paths(tmp_path, "ts", "1")

    commands = problem_commands(tmp_path, paths)

    assert commands[-1] == [
        "pnpm",
        "exec",
        "vitest",
        "run",
        "src/typescript/p_0001_two_sum/p_0001_two_sum.test.ts",
    ]
    assert ["pnpm", "exec", "tsc", "--noEmit"] in commands


def test_problem_gate_stops_on_first_failed_command(tmp_path: Path) -> None:
    make_problem(tmp_path, "py")
    paths = resolve_problem_paths(tmp_path, "py", "1")
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 1)

    with pytest.raises(ReadyError, match="command failed"):
        run_problem_gate(tmp_path, paths, run=run)

    assert len(calls) == 1


def test_changed_paths_select_problems_and_escalate_tooling() -> None:
    keys, full = changed_problem_keys(
        [
            "src/python/p_0001_two_sum/p_0001_two_sum.py",
            "src/typescript/p_0206_reverse_linked_list/p_0206_reverse_linked_list.ts",
            "README.md",
        ]
    )
    assert keys == [("py", "0001"), ("ts", "0206")]
    assert full is False

    _, full = changed_problem_keys(["scripts/lc.py"])
    assert full is True


def test_changed_paths_combines_committed_and_worktree_changes(tmp_path: Path) -> None:
    def git_run(command: tuple[str, ...], _cwd: Path) -> CommandResult:
        if command[1:3] == ("symbolic-ref", "--quiet"):
            return CommandResult(0, "origin/main\n")
        if command[1] == "merge-base":
            return CommandResult(0, "abc123\n")
        if command[-1] == "abc123..HEAD":
            return CommandResult(0, "src/python/p_0001_one/p_0001_one.py\n")
        if command[1] == "diff":
            return CommandResult(0, "src/python/p_0002_two/p_0002_two.py\n")
        return CommandResult(0, "")

    assert changed_paths(tmp_path, git_run=git_run) == [
        "src/python/p_0001_one/p_0001_one.py",
        "src/python/p_0002_two/p_0002_two.py",
    ]

    _, full = changed_problem_keys(["bin/lc"])
    assert full is True

    for compatibility_file in ("lc.toml", ".node-version", ".python-version"):
        _, full = changed_problem_keys([compatibility_file])
        assert full is True


def test_changed_paths_route_unknown_source_and_track_changes_to_full_gate() -> None:
    for changed in (
        "src/typescript/data_structures/heap.ts",
        "src/shared/judge_helpers.ts",
        "src/typescript/p_not-a-problem/notes.md",
        "src/typescript/p_0001/no-slug.ts",
        "tracks/interview-core.toml",
    ):
        keys, full = changed_problem_keys([changed])

        assert keys == []
        assert full is True


def test_changed_gate_uses_full_gate_for_tooling_changes(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def git_run(command: tuple[str, ...], _cwd: Path) -> CommandResult:
        if command[1] == "diff":
            return CommandResult(0, "scripts/lc.py\n")
        return CommandResult(0, "")

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    run_changed_gate(tmp_path, run=run, git_run=git_run)

    assert commands == [["pnpm", "run", "ready:all"]]


def test_changed_gate_uses_full_gate_when_clean_branch_has_no_worktree_diff(
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def git_run(_command: tuple[str, ...], _cwd: Path) -> CommandResult:
        return CommandResult(0, "")

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    run_changed_gate(tmp_path, run=run, git_run=git_run)

    assert commands == [["pnpm", "run", "ready:all"]]


def test_problem_gate_rejects_invalid_or_inconsistent_metadata(tmp_path: Path) -> None:
    cases = (
        ('id = ["bad"]\nlanguage = "ts"\nkind = "function"\n', "invalid metadata"),
        ('id = "0002"\nlanguage = "ts"\nkind = "function"\n', "does not match"),
        ('id = "0001"\nlanguage = "py"\nkind = "function"\n', "language py"),
        ('id = "0001"\nlanguage = "ts"\nkind = "unknown"\n', "kind must be"),
    )
    for metadata, message in cases:
        case_root = tmp_path / message.replace(" ", "-")
        make_problem(case_root, metadata=metadata)
        paths = resolve_problem_paths(case_root, "ts", "1")
        with pytest.raises(ReadyError, match=message):
            run_problem_gate(case_root, paths, run=lambda *_args, **_kwargs: None)


def test_problem_gate_accepts_consistent_metadata(tmp_path: Path) -> None:
    make_problem(tmp_path, metadata='id = "0001"\nlanguage = "ts"\nkind = "function"\n')
    paths = resolve_problem_paths(tmp_path, "ts", "1")
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    validate_problem_metadata(paths)
    run_problem_gate(tmp_path, paths, run=run)

    assert len(calls) == 4


@pytest.mark.parametrize("table_name", ["problem", "metadata"])
def test_problem_gate_accepts_identity_fields_in_supported_metadata_tables(
    tmp_path: Path, table_name: str
) -> None:
    make_problem(
        tmp_path,
        metadata=f'[{table_name}]\nid = "0001"\nlanguage = "ts"\nkind = "function"\n',
    )

    validate_problem_metadata(resolve_problem_paths(tmp_path, "ts", "1"))


@pytest.mark.parametrize(
    "invalid_field",
    ['target_minutes = "35"\n', "topics = [1]\n"],
)
def test_problem_metadata_validation_checks_all_supported_fields(
    tmp_path: Path, invalid_field: str
) -> None:
    make_problem(
        tmp_path,
        metadata=('id = "0001"\nlanguage = "ts"\nkind = "function"\n' + invalid_field),
    )

    with pytest.raises(ReadyError, match="target_minutes|tags"):
        validate_problem_metadata(resolve_problem_paths(tmp_path, "ts", "1"))


def test_full_metadata_validation_checks_every_problem(tmp_path: Path) -> None:
    make_problem(
        tmp_path,
        "ts",
        metadata='id = "0002"\nlanguage = "ts"\nkind = "function"\n',
    )

    with pytest.raises(ReadyError, match="does not match problem 0001"):
        validate_all_problem_metadata(tmp_path)


def test_full_metadata_validation_requires_every_problem_test(tmp_path: Path) -> None:
    make_problem(tmp_path, "ts")
    test_path = tmp_path / "src/typescript/p_0001_two_sum/p_0001_two_sum.test.ts"
    test_path.unlink()

    with pytest.raises(ReadyError, match="solution test is missing"):
        validate_all_problem_metadata(tmp_path)


def test_full_metadata_validation_rejects_duplicate_normalized_ids(tmp_path: Path) -> None:
    make_problem(tmp_path, "ts")
    duplicate = tmp_path / "src/typescript/p_1_duplicate"
    duplicate.mkdir(parents=True)
    (duplicate / "p_1_duplicate.ts").write_text("export function duplicate(): void {}\n")
    (duplicate / "p_1_duplicate.test.ts").write_text("test.todo('duplicate');\n")

    with pytest.raises(ReadyError, match="duplicate normalized problem ID 0001"):
        validate_all_problem_metadata(tmp_path)


def test_full_metadata_validation_rejects_malformed_problem_directories(tmp_path: Path) -> None:
    malformed = tmp_path / "src/typescript/p_0001_two-sum"
    malformed.mkdir(parents=True)

    with pytest.raises(ReadyError, match="invalid problem directory name"):
        validate_all_problem_metadata(tmp_path)


def test_track_metadata_validation_rejects_invalid_repository_manifest(tmp_path: Path) -> None:
    track = tmp_path / "tracks/interview-core.toml"
    track.parent.mkdir(parents=True)
    track.write_text('[[problems]]\nid = "not-a-number"\n', encoding="utf-8")

    with pytest.raises(ReadyError, match="invalid track entry"):
        validate_track_metadata(tmp_path)


def test_staged_paths_include_deletions_but_not_unstaged_or_untracked(tmp_path: Path) -> None:
    make_problem(tmp_path)
    initialize_git(tmp_path)
    source = tmp_path / "src/typescript/p_0001_two_sum/p_0001_two_sum.ts"
    source.unlink()
    subprocess.run(["git", "-C", str(tmp_path), "add", "-u"], check=True)
    (tmp_path / "untracked.txt").write_text("not staged", encoding="utf-8")
    staged = staged_paths(tmp_path)

    assert staged == ["src/typescript/p_0001_two_sum/p_0001_two_sum.ts"]


def test_staged_gate_reads_index_snapshot_not_unstaged_source(tmp_path: Path) -> None:
    make_problem(tmp_path)
    initialize_git(tmp_path)
    source = tmp_path / "src/typescript/p_0001_two_sum/p_0001_two_sum.ts"
    staged_source = "export function twoSum(): number[] { return [1]; }\n"
    source.write_text(staged_source, encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", str(source)], check=True)
    source.write_text("export function twoSum(): number[] { return [2]; }\n", encoding="utf-8")

    seen: list[Path] = []

    def run(
        command: list[str], *, cwd: Path, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        seen.append(cwd)
        assert (cwd / "src/typescript/p_0001_two_sum/p_0001_two_sum.ts").read_text(
            encoding="utf-8"
        ) == staged_source
        return subprocess.CompletedProcess(command, 0)

    run_staged_gate(tmp_path, run=run)

    assert seen
    assert all(path != tmp_path for path in seen)


def test_staged_gate_rejects_staged_dependency_manifest_divergence(tmp_path: Path) -> None:
    make_problem(tmp_path)
    package = tmp_path / "package.json"
    package.write_text('{"name": "staged"}\n', encoding="utf-8")
    initialize_git(tmp_path)

    package.write_text('{"name": "first"}\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", str(package)], check=True)
    package.write_text('{"name": "second"}\n', encoding="utf-8")

    with pytest.raises(ReadyError, match="unstaged dependency manifest edits"):
        run_staged_gate(tmp_path, run=lambda *_args, **_kwargs: None)


def test_staged_gate_rejects_unstaged_only_dependency_manifest_edits(tmp_path: Path) -> None:
    make_problem(tmp_path)
    package = tmp_path / "package.json"
    package.write_text('{"name": "baseline"}\n', encoding="utf-8")
    initialize_git(tmp_path)
    source = tmp_path / "src/typescript/p_0001_two_sum/p_0001_two_sum.ts"
    source.write_text("export function twoSum(): number[] { return [1]; }\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", str(source)], check=True)
    package.write_text('{"name": "unstaged"}\n', encoding="utf-8")

    with pytest.raises(ReadyError, match=r"unsafe: package\.json"):
        run_staged_gate(tmp_path, run=lambda *_args, **_kwargs: None)


@pytest.mark.parametrize("pin_file", ["mise.toml", ".node-version", ".python-version"])
def test_staged_gate_rejects_unstaged_toolchain_pin_edits(tmp_path: Path, pin_file: str) -> None:
    make_problem(tmp_path)
    pin = tmp_path / pin_file
    pin.write_text("baseline\n", encoding="utf-8")
    initialize_git(tmp_path)
    source = tmp_path / "src/typescript/p_0001_two_sum/p_0001_two_sum.ts"
    source.write_text("export function twoSum(): number[] { return [1]; }\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", str(source)], check=True)
    pin.write_text("unstaged\n", encoding="utf-8")

    with pytest.raises(ReadyError, match=rf"unsafe: .*{re.escape(pin_file)}"):
        run_staged_gate(tmp_path, run=lambda *_args, **_kwargs: None)


def test_staged_python_gate_disables_uv_environment_sync(tmp_path: Path) -> None:
    make_problem(tmp_path, "py")
    initialize_git(tmp_path)
    source = tmp_path / "src/python/p_0001_two_sum/p_0001_two_sum.py"
    source.write_text(
        '"""time: O(n), space: O(1)"""\nclass Solution:\n    pass\n', encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(tmp_path), "add", str(source)], check=True)
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    run_staged_gate(tmp_path, run=run)

    assert commands
    assert all(command[:3] == ["uv", "run", "--no-sync"] for command in commands)


def test_staged_full_gate_disables_uv_environment_sync(tmp_path: Path) -> None:
    make_problem(tmp_path)
    track = tmp_path / "tracks/interview-core.toml"
    track.parent.mkdir()
    track.write_text("name = 'core'\n", encoding="utf-8")
    initialize_git(tmp_path)
    track.write_text("name = 'updated'\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", str(track)], check=True)
    environments: list[dict[str, str] | None] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        environment = kwargs.get("env")
        environments.append(environment if isinstance(environment, dict) else None)
        return subprocess.CompletedProcess(command, 0)

    run_staged_gate(tmp_path, run=run)

    assert environments and environments[0] is not None
    assert environments[0]["UV_NO_SYNC"] == "1"


def test_staged_gate_validates_index_metadata_not_unstaged_metadata(tmp_path: Path) -> None:
    make_problem(tmp_path)
    initialize_git(tmp_path)
    metadata = tmp_path / "src/typescript/p_0001_two_sum/problem.toml"
    metadata.write_text('id = "0002"\nlanguage = "ts"\nkind = "function"\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", str(metadata)], check=True)
    metadata.write_text('id = "0001"\nlanguage = "ts"\nkind = "function"\n', encoding="utf-8")

    with pytest.raises(ReadyError, match="does not match"):
        run_staged_gate(tmp_path, run=lambda *_args, **_kwargs: None)


def test_staged_gate_rejects_deleted_required_source(tmp_path: Path) -> None:
    make_problem(tmp_path)
    initialize_git(tmp_path)
    source = tmp_path / "src/typescript/p_0001_two_sum/p_0001_two_sum.ts"
    source.unlink()
    subprocess.run(["git", "-C", str(tmp_path), "add", "-u"], check=True)

    with pytest.raises(ReadyError, match="staged problem ts 0001 is incomplete"):
        run_staged_gate(tmp_path, run=lambda *_args, **_kwargs: None)


def test_lefthook_pre_commit_uses_staged_mode() -> None:
    hook = Path(__file__).resolve().parents[1] / "lefthook.yml"

    contents = hook.read_text(encoding="utf-8")
    assert "pre-commit:" in contents
    assert "scripts/ready.py staged" in contents
