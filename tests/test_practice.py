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


def test_all_language_is_restricted_to_reporting_commands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["start", "0001", "--language", "all"])

    assert main(["--root", str(tmp_path), "--language", "all", "start", "0001"]) == 2
    assert "only supported" in capsys.readouterr().err

    assert build_parser().parse_args(["stats", "--language", "all"]).language == "all"


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


def test_metadata_rejects_unknown_difficulty(tmp_path: Path) -> None:
    path = tmp_path / "problem.toml"
    path.write_text('difficulty = "medum"\n', encoding="utf-8")
    with pytest.raises(MetadataError, match="difficulty"):
        load_problem_metadata(path)
