from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.practice import (
    MetadataError,
    PracticeError,
    PracticeStateError,
    PracticeStore,
    ProblemDiscoveryError,
    build_parser,
    due_date,
    discover_problems,
    finish,
    list_problems,
    load_problem_metadata,
    load_track_manifest,
    main,
    progressive_due_at,
    retry,
    review_queue,
    schedule_due_at,
    start,
    stats,
    today,
)


BASE_TIME = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)


def make_problem(
    root: Path,
    language: str,
    problem_id: str,
    slug: str,
    *,
    source: str | None = None,
    metadata: str | None = None,
) -> Path:
    directory = root / "src" / ("typescript" if language == "ts" else "python")
    directory /= f"p_{problem_id}_{slug}"
    directory.mkdir(parents=True)
    stem = directory.name
    source_path = directory / f"{stem}.{'ts' if language == 'ts' else 'py'}"
    if source is None:
        source = (
            "export function solve(value: number): number { return value; }\n"
            if language == "ts"
            else "class Solution:\n    def solve(self, value: int) -> int:\n        return value\n"
        )
    source_path.write_text(source, encoding="utf-8")
    if metadata is not None:
        (directory / "problem.toml").write_text(metadata, encoding="utf-8")
    return directory


def make_track(root: Path, body: str) -> Path:
    tracks = root / "tracks"
    tracks.mkdir()
    path = tracks / "interview-core.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_discover_problems_reads_local_metadata_and_track_defaults(tmp_path: Path) -> None:
    make_problem(
        tmp_path,
        "ts",
        "0002",
        "two_sum",
        metadata='title = "Local Two Sum"\ndifficulty = "easy"\n',
    )
    make_track(
        tmp_path,
        '[track]\nname = "core"\n\n[[problems]]\nid = "2"\npattern = "hash-map"\ntarget_minutes = 20\n',
    )

    problems = discover_problems(tmp_path, "typescript")

    assert len(problems) == 1
    problem = problems[0]
    assert problem.problem_id == "0002"
    assert problem.title == "Local Two Sum"
    assert problem.metadata.pattern == "hash-map"
    assert problem.metadata.target_minutes == 20
    assert problem.metadata.difficulty == "easy"
    assert problem.source_path.is_file()


def test_discover_problems_detects_duplicate_normalized_ids(tmp_path: Path) -> None:
    make_problem(tmp_path, "ts", "1", "one")
    make_problem(tmp_path, "ts", "0001", "another_one")

    with pytest.raises(ProblemDiscoveryError, match="multiple ts problem directories"):
        discover_problems(tmp_path, "ts")


def test_metadata_and_track_validation_errors_include_context(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "ts", "1", "one")
    metadata_path = directory / "problem.toml"
    metadata_path.write_text("target_minutes = 0\n", encoding="utf-8")
    with pytest.raises(MetadataError, match="target_minutes"):
        load_problem_metadata(directory)

    track = make_track(tmp_path, '[[problems]]\nid = "1"\n\n[[problems]]\nid = "0001"\n')
    with pytest.raises(MetadataError, match="duplicate problem ID 0001"):
        load_track_manifest(track)


@pytest.mark.parametrize(
    "body",
    [
        "problems = [1]\n",
        "[problems]\n0001 = 1\n",
        "[problem]\n0001 = 1\n",
        "p_0001 = 1\n",
    ],
)
def test_track_manifest_rejects_non_table_problem_entries(tmp_path: Path, body: str) -> None:
    track = make_track(tmp_path, body)

    with pytest.raises(MetadataError, match="must be a table|must be a list or table"):
        load_track_manifest(track)


def test_track_manifest_accepts_singular_problem_tables(tmp_path: Path) -> None:
    track = make_track(tmp_path, '[problem.0001]\npattern = "array"\n')

    manifest = load_track_manifest(track)

    assert manifest["0001"].pattern == "array"


def test_schedule_is_deterministic_and_validates_inputs() -> None:
    assert schedule_due_at(BASE_TIME, "solved", 4) == BASE_TIME + timedelta(days=7)
    assert due_date(BASE_TIME, "hinted", 3) == (BASE_TIME + timedelta(days=2)).date()
    with pytest.raises(PracticeError, match="confidence"):
        schedule_due_at(BASE_TIME, "solved", 5)
    with pytest.raises(PracticeError, match="result"):
        schedule_due_at(BASE_TIME, "unknown", 1)


def test_repeated_clean_solves_expand_to_longer_review_intervals(tmp_path: Path) -> None:
    make_problem(tmp_path, "ts", "0001", "one")
    start(tmp_path, "0001", now=BASE_TIME)
    first = finish(tmp_path, "solved", 4, now=BASE_TIME)
    start(tmp_path, "0001", now=BASE_TIME + timedelta(days=7))
    second = finish(tmp_path, "solved", 4, now=BASE_TIME + timedelta(days=7))

    assert first.due_at == BASE_TIME + timedelta(days=7)
    assert second.due_at == BASE_TIME + timedelta(days=21)
    assert progressive_due_at(BASE_TIME, "solved", 4, [first, second]) == BASE_TIME + timedelta(
        days=30
    )


def test_today_prefers_due_then_unseen_and_start_infers_mode(tmp_path: Path) -> None:
    make_problem(tmp_path, "ts", "0001", "first", metadata="target_minutes = 40\n")
    make_problem(tmp_path, "ts", "0002", "second", metadata="target_minutes = 10\n")
    make_problem(tmp_path, "ts", "0003", "third", metadata="target_minutes = 20\n")

    first = start(tmp_path, now=BASE_TIME)
    assert first.problem_id == "0002"
    assert first.mode == "new"
    finish(tmp_path, "failed", 1, elapsed_seconds=12, now=BASE_TIME + timedelta(minutes=20))
    due = today(tmp_path, limit=2, now=BASE_TIME + timedelta(minutes=20))
    assert [problem.problem_id for problem in due] == ["0002", "0003"]

    reviewed = start(tmp_path, "0002", now=BASE_TIME + timedelta(minutes=21))
    assert reviewed.mode == "review"
    with pytest.raises(PracticeStateError, match="already active"):
        start(tmp_path, "0003", now=BASE_TIME + timedelta(minutes=22))


def test_start_automatic_selection_uses_custom_track(tmp_path: Path) -> None:
    make_problem(tmp_path, "ts", "0001", "first")
    make_problem(tmp_path, "ts", "0002", "second")
    track = tmp_path / "custom-track.toml"
    track.write_text(
        '[[problems]]\nid = "0001"\ntarget_minutes = 30\n'
        '[[problems]]\nid = "0002"\ntarget_minutes = 5\n',
        encoding="utf-8",
    )

    session = start(tmp_path, track_path=track, now=BASE_TIME)

    assert session.problem_id == "0002"


def test_finish_persists_history_clears_active_and_computes_elapsed(tmp_path: Path) -> None:
    session = (
        start(tmp_path, "0001", now=BASE_TIME)
        if make_problem(tmp_path, "ts", "0001", "one")
        else None
    )
    assert session is not None
    record = finish(tmp_path, "solved", 4, now=BASE_TIME + timedelta(seconds=95))

    store = PracticeStore(tmp_path)
    assert store.read_active() is None
    assert len(store.read_history()) == 1
    assert record.elapsed_seconds == 95
    assert record.due_at == BASE_TIME + timedelta(seconds=95, days=7)
    line = (tmp_path / ".lc/practice-history.jsonl").read_text(encoding="utf-8").strip()
    assert json.loads(line)["result"] == "solved"


def test_finish_retry_does_not_append_a_session_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_problem(tmp_path, "ts", "0001", "one")
    session = start(tmp_path, "0001", now=BASE_TIME)
    original_clear_active = PracticeStore.clear_active
    clear_attempts = 0

    def fail_first_clear(store: PracticeStore) -> None:
        nonlocal clear_attempts
        clear_attempts += 1
        if clear_attempts == 1:
            raise PracticeStateError("simulated cleanup failure")
        original_clear_active(store)

    monkeypatch.setattr(PracticeStore, "clear_active", fail_first_clear)

    with pytest.raises(PracticeStateError, match="simulated cleanup failure"):
        finish(tmp_path, "solved", 4, now=BASE_TIME, session_id=session.session_id)
    retried = finish(tmp_path, "solved", 4, now=BASE_TIME, session_id=session.session_id)

    store = PracticeStore(tmp_path)
    assert store.read_active() is None
    assert store.read_history() == [retried]


def test_finish_with_session_id_is_idempotent_after_success(tmp_path: Path) -> None:
    make_problem(tmp_path, "ts", "0001", "one")
    session = start(tmp_path, "0001", now=BASE_TIME)

    first = finish(tmp_path, "solved", 4, now=BASE_TIME, session_id=session.session_id)
    second = finish(tmp_path, "solved", 4, now=BASE_TIME, session_id=session.session_id)

    assert second == first
    assert PracticeStore(tmp_path).read_history() == [first]


def test_start_serializes_active_session_check_and_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_problem(tmp_path, "ts", "0001", "one")
    first_read = threading.Event()
    second_read = threading.Event()
    release_write = threading.Event()
    read_lock = threading.Lock()
    read_count = 0
    original_read_active = PracticeStore.read_active
    original_write_active = PracticeStore.write_active

    def track_read(store: PracticeStore):
        nonlocal read_count
        with read_lock:
            read_count += 1
            (first_read if read_count == 1 else second_read).set()
        return original_read_active(store)

    def block_first_write(store: PracticeStore, session) -> None:
        assert release_write.wait(timeout=2)
        original_write_active(store, session)

    monkeypatch.setattr(PracticeStore, "read_active", track_read)
    monkeypatch.setattr(PracticeStore, "write_active", block_first_write)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(start, tmp_path, "0001", now=BASE_TIME)
        assert first_read.wait(timeout=2)
        second = executor.submit(start, tmp_path, "0001", now=BASE_TIME)
        assert not second_read.wait(timeout=0.1)
        release_write.set()
        session = first.result(timeout=2)
        with pytest.raises(PracticeStateError, match="already active"):
            second.result(timeout=2)

    assert second_read.is_set()
    assert PracticeStore(tmp_path).read_active() == session


def test_finish_rejects_invalid_confidence_and_missing_session(tmp_path: Path) -> None:
    with pytest.raises(PracticeStateError, match="no active"):
        finish(tmp_path, "failed", 1)
    make_problem(tmp_path, "ts", "0001", "one")
    start(tmp_path, "0001", now=BASE_TIME)
    with pytest.raises(PracticeError, match="confidence"):
        finish(tmp_path, "solved", 0)
    assert PracticeStore(tmp_path).read_active() is not None


def test_review_queue_and_status_filters(tmp_path: Path) -> None:
    make_problem(tmp_path, "ts", "0001", "one")
    make_problem(tmp_path, "ts", "0002", "two")
    start(tmp_path, "0001", now=BASE_TIME)
    finish(tmp_path, "solved", 4, now=BASE_TIME)
    assert review_queue(tmp_path, now=BASE_TIME + timedelta(days=6)) == []
    assert [
        problem.problem_id for problem in review_queue(tmp_path, now=BASE_TIME + timedelta(days=7))
    ] == ["0001"]
    assert [
        status.problem_id for status in list_problems(tmp_path, filter="unseen", now=BASE_TIME)
    ] == ["0002"]
    assert [
        status.problem_id for status in list_problems(tmp_path, filter="scheduled", now=BASE_TIME)
    ] == ["0001"]


def test_stats_contains_attempt_and_latest_state_aggregates(tmp_path: Path) -> None:
    make_problem(tmp_path, "ts", "0001", "one")
    start(tmp_path, "0001", now=BASE_TIME)
    finish(tmp_path, "hinted", 2, elapsed_seconds=30, now=BASE_TIME)
    start(tmp_path, "0001", now=BASE_TIME + timedelta(days=1))
    finish(tmp_path, "solved", 3, elapsed_seconds=60, now=BASE_TIME + timedelta(days=1))

    result = stats(tmp_path, now=BASE_TIME + timedelta(days=2))

    assert result["attempts"] == 2
    assert result["attempted"] == 1
    assert result["unseen"] == 0
    assert result["by_result"] == {"hinted": 1, "solved": 1}
    assert result["latest_by_result"] == {"solved": 1}
    assert result["average_elapsed_seconds"] == 45
    assert result["median_elapsed_seconds"] == 45
    assert result["by_mode"] == {"new": 1, "review": 1}
    assert result["hint_free_rate"] == 0.5
    assert result["independent_resolve_rate_30d"] == 1.0
    assert "unclassified" in result["pattern_matrix"]


def test_human_stats_surfaces_timing_and_weak_patterns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_problem(
        tmp_path,
        "ts",
        "0001",
        "one",
        metadata='pattern = "two-pointers"\n',
    )
    start(tmp_path, "0001", now=BASE_TIME)
    finish(tmp_path, "failed", 1, elapsed_seconds=90, now=BASE_TIME)

    assert main(["stats", "--root", str(tmp_path), "--human"]) == 0
    output = capsys.readouterr().out

    assert "Timing: average 1.5m, median 1.5m" in output
    assert "Weak patterns: two-pointers" in output


def test_stats_does_not_label_unseen_patterns_as_weaknesses(tmp_path: Path) -> None:
    make_problem(
        tmp_path,
        "ts",
        "0001",
        "one",
        metadata='pattern = "two-pointers"\n',
    )

    assert stats(tmp_path, now=BASE_TIME)["weak_patterns"] == []


def test_finish_help_describes_elapsed_seconds(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["finish", "--help"])
    output = capsys.readouterr().out
    assert "--elapsed SECONDS" in output
    assert "seconds" in output


def test_scaffold_topics_are_accepted_as_practice_tags(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0001",
        "one",
        metadata='title = "One"\ntopics = ["Array", "Hash Table"]\nkind = "function"\n',
    )

    metadata = load_problem_metadata(directory)

    assert metadata is not None
    assert metadata.tags == ("Array", "Hash Table")
    assert metadata.kind == "function"


def test_retry_creates_blank_ts_and_python_artifacts_without_copying_solution(
    tmp_path: Path,
) -> None:
    ts_source = "export function secret(value: number): number { return value + 99; }\n"
    py_source = "from typing import List\n\nclass Solution:\n    def secret(self, values: List[int]) -> int:\n        return 99\n"
    ts_dir = make_problem(tmp_path, "ts", "0001", "one", source=ts_source)
    make_problem(tmp_path, "py", "0002", "two", source=py_source)

    ts_attempt = retry(tmp_path, "0001")
    py_attempt = retry(tmp_path, "0002", "py")

    assert ts_attempt.path.parent.parent.parent == tmp_path / ".lc"
    assert ts_attempt.path != ts_dir / ts_dir.name / "ts"
    assert "value + 99" not in ts_attempt.path.read_text(encoding="utf-8")
    assert "function secret(value: number): number" in ts_attempt.path.read_text(encoding="utf-8")
    assert "return 99" not in py_attempt.path.read_text(encoding="utf-8")
    assert "def secret" in py_attempt.path.read_text(encoding="utf-8")


def test_retry_replaces_unresolved_python_method_defaults(tmp_path: Path) -> None:
    make_problem(
        tmp_path,
        "py",
        "0003",
        "defaults",
        source=(
            'SEP = ":"\n\n'
            "class Formatter:\n"
            "    def __init__(self, separator: str = SEP):\n"
            "        self.separator = separator\n"
        ),
    )

    source = retry(tmp_path, "0003", "py").path.read_text(encoding="utf-8")

    assert "separator: str=..." in source
    namespace: dict[str, object] = {}
    exec(source, namespace)
    namespace["Formatter"]()


def test_retry_preserves_keyword_and_positional_only_constructor_assignments(
    tmp_path: Path,
) -> None:
    make_problem(
        tmp_path,
        "py",
        "0005",
        "constructor_parameters",
        source=(
            "class Node:\n"
            "    def __init__(self, value: int, /, *, label: str):\n"
            "        self.value = value\n"
            "        self.label = label\n"
        ),
    )

    source = retry(tmp_path, "0005", "py").path.read_text(encoding="utf-8")

    assert "self.value = value" in source
    assert "self.label = label" in source


def test_all_language_is_restricted_to_reporting_commands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["retry", "0001", "--language", "all"])

    assert main(["--root", str(tmp_path), "--language", "all", "retry", "0001"]) == 2
    assert "only supported" in capsys.readouterr().err

    assert build_parser().parse_args(["stats", "--language", "all"]).language == "all"


def test_retry_preserves_class_interfaces_without_copying_design_bodies(tmp_path: Path) -> None:
    ts_source = """class Node {
    constructor(value: number) {
        this.value = value;
    }
    value: number;
}

export class LRUCache {
    private secret = 99;

    constructor(capacity: number) {
        this.secret = capacity;
    }

    get(key: number): number {
        return this.secret + key;
    }

    put(key: number, value: number): void {
        this.secret = value + key;
    }

    private helper(): number {
        return this.secret;
    }
}
"""
    py_source = """class Node:
    def __init__(self, value: int) -> None:
        self.value = value


class MinStack:
    def __init__(self) -> None:
        self.values = []

    def push(self, value: int) -> None:
        self.values.append(value)

    def top(self) -> int:
        return self.values[-1]

    def _secret(self) -> int:
        return 99
"""
    ts_directory = make_problem(
        tmp_path,
        "ts",
        "0003",
        "lru_cache",
        source=ts_source,
        metadata='kind = "design"\n',
    )
    py_directory = make_problem(
        tmp_path,
        "py",
        "0004",
        "min_stack",
        source=py_source,
        metadata='kind = "design"\n',
    )
    (ts_directory / "p_0003_lru_cache.test.ts").write_text(
        'import { LRUCache } from "./p_0003_lru_cache.js";\n', encoding="utf-8"
    )
    (py_directory / "test_p_0004_min_stack.py").write_text(
        "from p_0004_min_stack import MinStack\n", encoding="utf-8"
    )

    ts_attempt = retry(tmp_path, "0003")
    py_attempt = retry(tmp_path, "0004", "py")
    ts_retry = ts_attempt.path.read_text(encoding="utf-8")
    py_retry = py_attempt.path.read_text(encoding="utf-8")

    assert "class Node" not in ts_retry
    assert "export class LRUCache" in ts_retry
    assert "constructor(capacity: number)" in ts_retry
    assert "get(key: number): number" in ts_retry
    assert "put(key: number, value: number): void" in ts_retry
    assert "private helper" not in ts_retry
    assert "this.secret" not in ts_retry
    assert "return this.secret" not in ts_retry

    assert "class Node:" not in py_retry
    assert "class MinStack:" in py_retry
    assert "def __init__(self) -> None:" in py_retry
    assert "def push(self, value: int) -> None:" in py_retry
    assert "def top(self) -> int:" in py_retry
    assert "def _secret" not in py_retry
    assert "return 99" not in py_retry
    assert "LRUCache" in ts_attempt.test_path.read_text(encoding="utf-8")
    assert "MinStack" in py_attempt.test_path.read_text(encoding="utf-8")


def test_retry_advances_past_private_typescript_methods(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0009",
        "private_first",
        source=(
            "export class Runner {\n"
            "    private helper(): number { return 1; }\n"
            "    #secret(): number { return 2; }\n"
            "    run(value: number): number { return value; }\n"
            "}\n"
        ),
        metadata='kind = "design"\n',
    )
    (directory / "p_0009_private_first.test.ts").write_text(
        'import { Runner } from "./p_0009_private_first.js";\n', encoding="utf-8"
    )

    source = retry(tmp_path, "0009").path.read_text(encoding="utf-8")

    assert "helper" not in source
    assert "secret" not in source
    assert "run(value: number): number" in source


def test_retry_preserves_typescript_generator_methods(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0010",
        "generator_method",
        source=(
            "export class Values {\n"
            "    *values(): Generator<number> { yield 1; }\n"
            "    size(): number { return 1; }\n"
            "}\n"
        ),
        metadata='kind = "design"\n',
    )
    (directory / "p_0010_generator_method.test.ts").write_text(
        'import { Values } from "./p_0010_generator_method.js";\n', encoding="utf-8"
    )

    source = retry(tmp_path, "0010").path.read_text(encoding="utf-8")

    assert "*values(): Generator<number>" in source
    assert "size(): number" in source


def test_retry_recreates_every_python_class_imported_by_the_test(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "py",
        "0297",
        "codec",
        source=(
            "class TreeNode:\n"
            "    def __init__(self, value: int) -> None:\n"
            "        self.value = value\n\n\n"
            "class Codec:\n"
            "    def serialize(self, root: TreeNode) -> str:\n"
            "        return str(root.value)\n"
        ),
        metadata='kind = "design"\n',
    )
    (directory / "test_p_0297_codec.py").write_text(
        "from p_0297_codec import Codec, TreeNode\n",
        encoding="utf-8",
    )

    attempt = retry(tmp_path, "0297", "py")
    source = attempt.path.read_text(encoding="utf-8")

    assert "class Codec:" in source
    assert "class TreeNode:" in source
    assert source.count("from __future__ import annotations") == 1
    assert "return str(root.value)" not in source


def test_retry_recreates_classes_used_through_python_module_import(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "py",
        "0296",
        "module_codec",
        source=(
            "class TreeNode:\n"
            "    def __init__(self, value: int) -> None:\n"
            "        self.value = value\n\n"
            "class Codec:\n"
            "    def serialize(self, root: TreeNode) -> str:\n"
            "        return str(root.value)\n"
        ),
        metadata='kind = "design"\n',
    )
    (directory / "test_p_0296_module_codec.py").write_text(
        "import p_0296_module_codec as solution\n"
        "node = solution.TreeNode(1)\n"
        "codec = solution.Codec()\n",
        encoding="utf-8",
    )

    source = retry(tmp_path, "0296", "py").path.read_text(encoding="utf-8")

    assert "class TreeNode:" in source
    assert "class Codec:" in source


def test_retry_initializes_safe_python_helper_attributes(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "py",
        "0295",
        "tree_helper",
        source=(
            "class TreeNode:\n    def __init__(self, val: int) -> None:\n        self.val = val\n"
        ),
        metadata='kind = "design"\n',
    )
    (directory / "test_p_0295_tree_helper.py").write_text(
        "from p_0295_tree_helper import TreeNode\n", encoding="utf-8"
    )

    source = retry(tmp_path, "0295", "py").path.read_text(encoding="utf-8")
    namespace: dict[str, object] = {}
    exec(source, namespace)
    node = namespace["TreeNode"](1)

    assert node.val == 1


def test_retry_rejects_unsupported_python_solution_imports_before_writing(
    tmp_path: Path,
) -> None:
    directory = make_problem(
        tmp_path,
        "py",
        "0299",
        "mixed_exports",
        source=(
            "class Solution:\n"
            "    def solve(self) -> int:\n"
            "        return 1\n\n\n"
            "def make_tree():\n"
            "    return object()\n"
        ),
    )
    (directory / "test_p_0299_mixed_exports.py").write_text(
        "from p_0299_mixed_exports import Solution, make_tree\n",
        encoding="utf-8",
    )

    with pytest.raises(PracticeError, match="imported Python export.*make_tree"):
        retry(tmp_path, "0299", "py")

    assert not (tmp_path / ".lc/practice-attempts").exists()


def test_retry_rejects_colocated_python_test_dependencies_before_writing(
    tmp_path: Path,
) -> None:
    directory = make_problem(tmp_path, "py", "0298", "local_helper")
    (directory / "helper.py").write_text("def make_value(): return 1\n", encoding="utf-8")
    (directory / "test_p_0298_local_helper.py").write_text(
        "from helper import make_value\nfrom p_0298_local_helper import Solution\n",
        encoding="utf-8",
    )

    with pytest.raises(PracticeError, match="colocated Python import.*helper.py"):
        retry(tmp_path, "0298", "py")

    assert not (tmp_path / ".lc/practice-attempts").exists()


def test_retry_preserves_python_dataclass_constructor_fields(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "py",
        "0301",
        "tree_node",
        source=(
            "from __future__ import annotations\n"
            "from dataclasses import dataclass\n\n"
            "@dataclass\n"
            "class TreeNode:\n"
            "    val: int\n"
            "    left: TreeNode | None = None\n"
        ),
    )
    (directory / "test_p_0301_tree_node.py").write_text(
        "from p_0301_tree_node import TreeNode\n",
        encoding="utf-8",
    )

    source = retry(tmp_path, "0301", "py").path.read_text(encoding="utf-8")
    namespace: dict[str, object] = {}
    exec(source, namespace)
    tree_node_class = namespace["TreeNode"]
    assert isinstance(tree_node_class, type)
    node = tree_node_class(1)

    assert "@dataclass" in source
    assert "val: int" in source
    assert node.val == 1
    assert node.left is None


def test_retry_replaces_unresolved_python_dataclass_defaults(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "py",
        "0302",
        "dataclass_default",
        source=(
            "from dataclasses import dataclass\n\n"
            "DEFAULT = 7\n\n"
            "@dataclass\n"
            "class Item:\n"
            "    value: int = DEFAULT\n"
        ),
    )
    (directory / "test_p_0302_dataclass_default.py").write_text(
        "from p_0302_dataclass_default import Item\n", encoding="utf-8"
    )

    source = retry(tmp_path, "0302", "py").path.read_text(encoding="utf-8")
    namespace: dict[str, object] = {}
    exec(source, namespace)

    assert "value: int = ..." in source


def test_retry_preserves_builtin_dataclass_default_factories(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "py",
        "0303",
        "dataclass_factory",
        source=(
            "from dataclasses import dataclass, field\n\n"
            "@dataclass\n"
            "class Node:\n"
            "    children: list[int] = field(default_factory=list)\n"
        ),
    )
    (directory / "test_p_0303_dataclass_factory.py").write_text(
        "from p_0303_dataclass_factory import Node\n", encoding="utf-8"
    )

    source = retry(tmp_path, "0303", "py").path.read_text(encoding="utf-8")
    namespace: dict[str, object] = {}
    exec(source, namespace)
    node = namespace["Node"]()
    node.children.append(1)

    assert "field(default_factory=list)" in source
    assert node.children == [1]


def test_retry_drops_unresolved_dataclass_decorator_options(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "py",
        "0304",
        "dataclass_option",
        source=(
            "from dataclasses import dataclass\n\n"
            "ENABLE_ORDER = True\n\n"
            "@dataclass(order=ENABLE_ORDER)\n"
            "class Item:\n"
            "    value: int\n"
        ),
    )
    (directory / "test_p_0304_dataclass_option.py").write_text(
        "from p_0304_dataclass_option import Item\n", encoding="utf-8"
    )

    source = retry(tmp_path, "0304", "py").path.read_text(encoding="utf-8")
    namespace: dict[str, object] = {}
    exec(source, namespace)

    assert "ENABLE_ORDER" not in source


def test_retry_preserves_python_property_setter_and_deleter(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "py",
        "0302",
        "box",
        source=(
            "class Box:\n"
            "    @property\n"
            "    def value(self) -> int:\n"
            "        return 99\n\n"
            "    @value.setter\n"
            "    def value(self, new_value: int) -> None:\n"
            "        self._value = new_value\n\n"
            "    @value.deleter\n"
            "    def value(self) -> None:\n"
            "        del self._value\n"
        ),
        metadata='kind = "design"\n',
    )
    (directory / "test_p_0302_box.py").write_text(
        "from p_0302_box import Box\n",
        encoding="utf-8",
    )

    source = retry(tmp_path, "0302", "py").path.read_text(encoding="utf-8")
    namespace: dict[str, object] = {}
    exec(source, namespace)
    box_class = namespace["Box"]
    assert isinstance(box_class, type)
    descriptor = vars(box_class)["value"]

    assert isinstance(descriptor, property)
    assert descriptor.fset is not None
    assert descriptor.fdel is not None
    assert "return 99" not in source


def test_retry_copies_tests_and_reports_an_isolated_test_command(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "ts", "0001", "one")
    test_path = directory / "p_0001_one.test.ts"
    test_path.write_text(
        'import { solve } from "./p_0001_one.js";\n'
        'test("example", () => expect(solve(1)).toBe(1));\n',
        encoding="utf-8",
    )

    attempt = retry(tmp_path, "0001")

    assert attempt.test_path is not None
    assert attempt.test_path.read_text(encoding="utf-8") == test_path.read_text(encoding="utf-8")
    assert attempt.test_command[:6] == (
        "pnpm",
        "exec",
        "vitest",
        "run",
        "--config",
        "vitest.retry.config.ts",
    )


@pytest.mark.parametrize(
    ("problem_id", "slug", "function_name"),
    [
        ("0092", "reverse_linked_list_ii", "reverseBetween"),
        ("0206", "reverse_linked_list", "reverseList"),
    ],
)
def test_retry_rewrites_shared_typescript_imports_for_isolated_tests(
    tmp_path: Path, problem_id: str, slug: str, function_name: str
) -> None:
    shared = tmp_path / "src/typescript/data_structures/linked_list.ts"
    shared.parent.mkdir(parents=True)
    shared.write_text("export class LinkedList {}\n", encoding="utf-8")
    directory = make_problem(
        tmp_path,
        "ts",
        problem_id,
        slug,
        source=f"export function {function_name}(value: number): number {{ return value + 99; }}\n",
    )
    test_path = directory / f"p_{problem_id}_{slug}.test.ts"
    test_path.write_text(
        f'import {{ LinkedList }} from "../data_structures/linked_list.js";\n'
        f'import {{ {function_name} }} from "./p_{problem_id}_{slug}.js";\n'
        'test("collects retry interfaces", () => {\n'
        "    expect(LinkedList).toBeDefined();\n"
        f'    expect({function_name}).toBeTypeOf("function");\n'
        "});\n",
        encoding="utf-8",
    )

    attempt = retry(tmp_path, problem_id)
    copied_test = attempt.test_path.read_text(encoding="utf-8")

    assert "../../../src/typescript/data_structures/linked_list.js" in copied_test
    assert f'import {{ {function_name} }} from "./p_{problem_id}_{slug}.js"' in copied_test
    assert "return value + 99" not in attempt.path.read_text(encoding="utf-8")


def test_retry_rewrites_dynamic_typescript_test_helpers(tmp_path: Path) -> None:
    helper = tmp_path / "src/typescript/helpers/value.ts"
    helper.parent.mkdir(parents=True)
    helper.write_text("export const value = 1;\n", encoding="utf-8")
    directory = make_problem(tmp_path, "ts", "0011", "dynamic_import")
    (directory / "p_0011_dynamic_import.test.ts").write_text(
        'import { solve } from "./p_0011_dynamic_import.js";\n'
        'test("dynamic", async () => {\n'
        '    const helper = await import("../helpers/value.js");\n'
        "    expect(solve(helper.value)).toBe(1);\n"
        "});\n",
        encoding="utf-8",
    )

    copied_test = retry(tmp_path, "0011").test_path.read_text(encoding="utf-8")

    assert "../../../src/typescript/helpers/value.js" in copied_test


def test_retry_skips_regex_literals_while_balancing_class_methods(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0012",
        "regex_class",
        source=(
            "export class Cleaner {\n"
            '    clean(value: string): string { return value.replace(/}/g, ""); }\n'
            "    size(value: string): number { return value.length; }\n"
            "}\n"
        ),
        metadata='kind = "design"\n',
    )
    (directory / "p_0012_regex_class.test.ts").write_text(
        'import { Cleaner } from "./p_0012_regex_class.js";\n', encoding="utf-8"
    )

    source = retry(tmp_path, "0012").path.read_text(encoding="utf-8")

    assert "clean(value: string): string" in source
    assert "size(value: string): number" in source


def test_retry_preserves_every_imported_typescript_solution_export(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0268",
        "missing_number",
        source=(
            "export function missingNumberHashMap(nums: number[]): number { return 99; }\n"
            "export function missingNumber(nums: number[]): number { return 98; }\n"
        ),
    )
    test_path = directory / "p_0268_missing_number.test.ts"
    test_path.write_text(
        'import { missingNumber, missingNumberHashMap } from "./p_0268_missing_number.js";\n'
        'test("collects both exports", () => {\n'
        '    expect(missingNumber).toBeTypeOf("function");\n'
        '    expect(missingNumberHashMap).toBeTypeOf("function");\n'
        "});\n",
        encoding="utf-8",
    )

    attempt = retry(tmp_path, "0268")
    source = attempt.path.read_text(encoding="utf-8")

    assert "export function missingNumberHashMap(nums: number[]): number" in source
    assert "export function missingNumber(nums: number[]): number" in source
    assert "return 99" not in source
    assert "return 98" not in source


def test_retry_preserves_combined_default_and_named_typescript_imports(
    tmp_path: Path,
) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0269",
        "combined_imports",
        source=(
            "export default function solve(value: number): number { return value + 99; }\n"
            "export function helper(value: number): number { return value + 98; }\n"
        ),
    )
    (directory / "p_0269_combined_imports.test.ts").write_text(
        'import solve, { helper } from "./p_0269_combined_imports.js";\n'
        'test("combined", () => expect(helper(solve(1))).toBe(2));\n',
        encoding="utf-8",
    )

    attempt = retry(tmp_path, "0269")
    source = attempt.path.read_text(encoding="utf-8")

    assert "export default function solve(value: number): number" in source
    assert "export function helper(value: number): number" in source
    assert "return value + 99" not in source
    assert "return value + 98" not in source


def test_retry_preserves_declaration_level_typescript_type_imports(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0270",
        "typed_case",
        source=(
            "export interface Case { value: number }\n"
            "export function solve(item: number): number { return item + 99; }\n"
        ),
    )
    (directory / "p_0270_typed_case.test.ts").write_text(
        'import type { Case } from "./p_0270_typed_case.js";\n'
        'import { solve } from "./p_0270_typed_case.js";\n'
        "const item: Case = { value: 1 };\n"
        'test("typed", () => expect(solve(item.value)).toBe(1));\n',
        encoding="utf-8",
    )

    source = retry(tmp_path, "0270").path.read_text(encoding="utf-8")

    assert source.count("export interface Case") == 1
    assert "export function solve(item: number): number" in source


def test_retry_preserves_type_declarations_referenced_by_function_signatures(
    tmp_path: Path,
) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0005",
        "pair_sum",
        source=(
            "type Coordinate = number;\n"
            "type Pair = [Coordinate, Coordinate];\n\n"
            "export function pairSum(pair: Pair): Pair { return [pair[0], pair[1]]; }\n"
        ),
    )
    (directory / "p_0005_pair_sum.test.ts").write_text(
        'import { pairSum } from "./p_0005_pair_sum.js";\n'
        'test("pair", () => expect(pairSum([1, 2])).toEqual([1, 2]));\n',
        encoding="utf-8",
    )

    attempt = retry(tmp_path, "0005")
    source = attempt.path.read_text(encoding="utf-8")

    assert "type Coordinate = number;" in source
    assert "type Pair = [Coordinate, Coordinate];" in source
    assert "export function pairSum(pair: Pair): Pair" in source
    assert "return [pair[0], pair[1]]" not in source


def test_retry_balances_inline_object_types_before_function_bodies(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0006",
        "inline_object",
        source=(
            "export function summarize(value: { key: string }): { count: number } {\n"
            "    return { count: value.key.length };\n"
            "}\n"
        ),
    )
    (directory / "p_0006_inline_object.test.ts").write_text(
        'import { summarize } from "./p_0006_inline_object.js";\n'
        'test("summary", () => expect(summarize({ key: "x" })).toEqual({ count: 1 }));\n',
        encoding="utf-8",
    )

    attempt = retry(tmp_path, "0006")
    source = attempt.path.read_text(encoding="utf-8")

    assert "function summarize(value: { key: string }): { count: number }" in source
    assert 'throw new Error("TODO: implement retry")' in source
    assert "value.key.length" not in source


def test_retry_balances_inline_object_types_in_class_methods(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0007",
        "inline_method",
        source=(
            "export class Runner {\n"
            "    run(value: { key: string }): { count: number } {\n"
            "        return { count: value.key.length };\n"
            "    }\n"
            "}\n"
        ),
        metadata='kind = "design"\n',
    )
    (directory / "p_0007_inline_method.test.ts").write_text(
        'import { Runner } from "./p_0007_inline_method.js";\n'
        'test("run", () => expect(new Runner().run({ key: "x" })).toEqual({ count: 1 }));\n',
        encoding="utf-8",
    )

    attempt = retry(tmp_path, "0007")
    source = attempt.path.read_text(encoding="utf-8")

    assert "run(value: { key: string }): { count: number }" in source
    assert "value.key.length" not in source


def test_retry_preserves_object_constrained_class_method_generics(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0008",
        "generic_method",
        source=(
            "export class Runner {\n"
            "    run<T extends { value: number }>(item: T): T { return item; }\n"
            "}\n"
        ),
        metadata='kind = "design"\n',
    )
    (directory / "p_0008_generic_method.test.ts").write_text(
        'import { Runner } from "./p_0008_generic_method.js";\n', encoding="utf-8"
    )

    source = retry(tmp_path, "0008").path.read_text(encoding="utf-8")

    assert "run<T extends { value: number }>(item: T): T" in source
    assert "return item" not in source


def test_retry_preserves_public_typescript_class_fields(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0008",
        "tree_node",
        source=(
            "export class TreeNode {\n"
            "    val: number\n"
            "    public left: TreeNode | null = null\n"
            "    private secret: number = 99;\n"
            "    constructor(val: number) { this.val = val; this.left = null; }\n"
            "}\n"
        ),
        metadata='kind = "design"\n',
    )
    (directory / "p_0008_tree_node.test.ts").write_text(
        'import { TreeNode } from "./p_0008_tree_node.js";\n'
        'test("node", () => expect(new TreeNode(1).val).toBe(1));\n',
        encoding="utf-8",
    )

    source = retry(tmp_path, "0008").path.read_text(encoding="utf-8")

    assert "val!: number;" in source
    assert "public left!: TreeNode | null;" in source
    assert "secret" not in source
    assert "this.val = val" not in source


def test_retry_rejects_imported_dataclass_post_init_state(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "py",
        "0006",
        "post_init",
        source=(
            "from dataclasses import dataclass\n\n"
            "@dataclass\n"
            "class Node:\n"
            "    value: int\n"
            "    def __post_init__(self):\n"
            "        self.doubled = self.value * 2\n"
        ),
    )
    (directory / "test_p_0006_post_init.py").write_text(
        "from p_0006_post_init import Node\n", encoding="utf-8"
    )

    with pytest.raises(PracticeError, match="post-init state"):
        retry(tmp_path, "0006", "py")


def test_retry_rejects_initialized_typescript_helper_fields(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0009",
        "helper_state",
        source=(
            "export class Node { val: number = 1; }\n"
            "export function solve(node: Node): number { return node.val; }\n"
        ),
    )
    (directory / "p_0009_helper_state.test.ts").write_text(
        'import { Node, solve } from "./p_0009_helper_state.js";\n', encoding="utf-8"
    )

    with pytest.raises(PracticeError, match="constructor state"):
        retry(tmp_path, "0009")


def test_retry_balances_composite_typescript_defaults(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0010",
        "composite_default",
        source=(
            "const SEP = ':';\n"
            "export function solve(options = { separator: SEP, limit: 1 }): number "
            "{ return options.limit; }\n"
        ),
    )
    (directory / "p_0010_composite_default.test.ts").write_text(
        'import { solve } from "./p_0010_composite_default.js";\n', encoding="utf-8"
    )

    source = retry(tmp_path, "0010").path.read_text(encoding="utf-8")

    assert "solve(options = undefined): number" in source
    assert "limit: 1 }" not in source


def test_retry_carries_referenced_typescript_helper_classes(tmp_path: Path) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0297",
        "codec",
        source=(
            "class TreeNode {\n"
            "    val: number;\n"
            "    constructor(val: number) { this.val = val; }\n"
            "}\n\n"
            "export class Codec {\n"
            "    serialize(root: TreeNode | null): string { return String(root?.val); }\n"
            "    deserialize(data: string): TreeNode | null { return new TreeNode(+data); }\n"
            "}\n"
        ),
        metadata='kind = "design"\n',
    )
    (directory / "p_0297_codec.test.ts").write_text(
        'import { Codec } from "./p_0297_codec.js";\n'
        'test("codec", () => expect(new Codec()).toBeDefined());\n',
        encoding="utf-8",
    )

    source = retry(tmp_path, "0297").path.read_text(encoding="utf-8")

    assert "class TreeNode" in source
    assert "val!: number;" in source
    assert "export class Codec" in source
    assert "return String" not in source
    assert "new TreeNode(+data)" not in source


def test_retry_refuses_unsupported_imported_typescript_shapes_before_writing(
    tmp_path: Path,
) -> None:
    directory = make_problem(
        tmp_path,
        "ts",
        "0300",
        "unsupported_export",
        source="export const answer = 42;\n",
    )
    (directory / "p_0300_unsupported_export.test.ts").write_text(
        'import { answer } from "./p_0300_unsupported_export.js";\n', encoding="utf-8"
    )

    with pytest.raises(PracticeError, match="cannot safely recreate"):
        retry(tmp_path, "0300")
    assert not (tmp_path / ".lc/practice-attempts").exists()


def test_cli_supports_root_and_language_before_or_after_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_problem(tmp_path, "ts", "0001", "one")
    assert main(["--root", str(tmp_path), "today"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output[0]["problem_id"] == "0001"
    assert main(["stats", "--root", str(tmp_path), "--language", "typescript"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["total"] == 1


def test_cli_human_mode_is_concise_and_hides_internal_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_problem(
        tmp_path,
        "ts",
        "0001",
        "two_sum",
        metadata='title = "Two Sum"\ndifficulty = "easy"\ntarget_minutes = 20\n',
    )

    assert main(["today", "--root", str(tmp_path), "--human"]) == 0

    output = capsys.readouterr().out
    assert "0001  ts  easy" in output
    assert "20m  Two Sum" in output
    assert str(tmp_path) not in output


def test_cli_reports_expected_errors_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--root", str(tmp_path), "finish", "--result", "solved"]) == 2
    error = capsys.readouterr().err
    assert "no active" in error
    assert "Traceback" not in error
