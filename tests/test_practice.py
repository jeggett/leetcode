"""Ordered list import, offline progress, and Next selection."""

import pytest

from scripts import lc, practice
from scripts.lc_state import StateError, write_state

URL = "https://leetcode.com/problem-list/example/"


def question(number, status=None):
    return {
        "questionFrontendId": str(number),
        "titleSlug": f"problem-{number}",
        "title": f"Problem {number}",
        "difficulty": "EASY",
        "paidOnly": False,
        "status": status,
    }


class Session:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.offsets = []
        self.logged_in = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def require_login(self):
        self.logged_in = True

    def graphql(self, query, variables):
        assert self.logged_in
        assert "CUSTOM" in query
        self.offsets.append(variables["skip"])
        return {"favoriteQuestionList": next(self.pages)}


def page(items, total=None, more=False):
    return {
        "questions": items,
        "totalLength": len(items) if total is None else total,
        "hasMore": more,
    }


def imported(root, questions):
    session = Session([page(questions)])
    return practice.import_list(root, URL, "py", session_factory=lambda _: session)


def test_paginated_order_dedup_and_whitelist(tmp_path):
    first = [{**question(3), "unwanted": "private"}, question(1)]
    session = Session([page(first, 4, True), page([question(1), question(2)], 4)])
    state = practice.import_list(
        tmp_path, URL + "?order=custom#top", session_factory=lambda _: session
    )
    assert session.offsets == [0, 2]
    assert [q["questionFrontendId"] for q in state["questions"]] == ["0003", "0001", "0002"]
    assert "unwanted" not in state["questions"][0]
    assert state["url"] == URL


@pytest.mark.parametrize(
    "pages",
    [
        [page([question(1)], 2)],
        [page([], 2, True)],
        [page([question(1)], 2, True), page([question(2)], 3)],
        [page([question(1)], 2, True), page([question(1)], 2, True)],
        [page([{**question(1), "status": "UNKNOWN"}])],
        [page([{**question(1), "questionFrontendId": "0"}])],
    ],
)
def test_invalid_import_preserves_saved_snapshot(tmp_path, pages):
    imported(tmp_path, [question(9)])
    before = (tmp_path / ".lc/practice.json").read_bytes()
    with pytest.raises(practice.PracticeError):
        practice.import_list(tmp_path, URL, session_factory=lambda _: Session(pages))
    assert (tmp_path / ".lc/practice.json").read_bytes() == before


@pytest.mark.parametrize(
    "url",
    [
        "http://leetcode.com/problem-list/a/",
        "https://evil.com/problem-list/a/",
        "https://user@leetcode.com/problem-list/a/",
        "https://leetcode.com:443/problem-list/a/",
        "https://leetcode.com/studyplan/a/",
        "https://leetcode.com/problems/two-sum/",
    ],
)
def test_invalid_urls(url):
    with pytest.raises(practice.PracticeError):
        practice.canonicalize_list_url(url)


def attempt(status):
    return {
        "status": status,
        "source_hash": "abc",
        "submission_hash": "def",
        "files": {},
        "submission_id": "123",
    }


def test_accepted_in_either_language_and_history_only_advances(tmp_path):
    state = imported(tmp_path, [question(3, "AC"), question(1), question(2)])
    write_state(
        tmp_path / ".lc/submissions/ts-0001.json",
        {"version": 1, "attempts": [attempt("accepted"), attempt("rejected")]},
    )
    write_state(
        tmp_path / ".lc/submissions/py-0002.json", {"version": 1, "attempts": [attempt("pending")]}
    )
    assert practice.next_question(tmp_path, state)["questionFrontendId"] == "0002"
    write_state(
        tmp_path / ".lc/submissions/py-0002.json", {"version": 1, "attempts": [attempt("accepted")]}
    )
    assert practice.next_question(tmp_path, state) is None


def test_bad_journal_cannot_mark_solved(tmp_path):
    state = imported(tmp_path, [question(1)])
    write_state(
        tmp_path / ".lc/submissions/ts-0001.json",
        {"version": 1, "attempts": [{"status": "accepted"}]},
    )
    with pytest.raises(StateError, match="journal"):
        practice.next_question(tmp_path, state)


def test_next_repeats_until_accepted_and_complete_does_not_scaffold(tmp_path, monkeypatch):
    imported(tmp_path, [question(1), question(2, "AC")])
    calls = []
    monkeypatch.setattr(lc, "scaffold_from_url", lambda *args: calls.append(args))
    monkeypatch.setattr(lc, "_print_scaffold_result", lambda *_: None)
    for _ in range(2):
        assert lc.dispatch(["next"], tmp_path, tmp_path) == 0
    assert calls == [(tmp_path, "py", "https://leetcode.com/problems/problem-1/")] * 2
    write_state(
        tmp_path / ".lc/submissions/ts-0001.json", {"version": 1, "attempts": [attempt("accepted")]}
    )
    assert lc.dispatch(["next"], tmp_path, tmp_path) == 0
    assert len(calls) == 2


def test_refresh_preserves_language_and_show_is_offline(tmp_path, monkeypatch):
    imported(tmp_path, [question(1)])
    calls = []
    monkeypatch.setattr(
        practice, "import_list", lambda *args: calls.append(args) or practice.load_list(tmp_path)
    )
    assert lc.dispatch(["list"], tmp_path, tmp_path) == 0
    assert calls == []
    assert lc.dispatch(["list", "--refresh"], tmp_path, tmp_path) == 0
    assert calls == [(tmp_path, URL, "py")]


@pytest.mark.parametrize("field", ["status", "difficulty"])
def test_nested_invalid_remote_fields_are_clean_errors(tmp_path, field):
    session = Session([page([{**question(1), field: {"bad": "data"}}])])
    with pytest.raises(practice.PracticeError):
        practice.import_list(tmp_path, URL, session_factory=lambda _: session)
    assert not (tmp_path / ".lc/practice.json").exists()


def test_next_reopens_existing_files_unchanged_and_activates(tmp_path, monkeypatch):
    imported(tmp_path, [question(1)])
    directory = tmp_path / "src/python/p_0001_example"
    directory.mkdir(parents=True)
    source = directory / "p_0001_example.py"
    tests = directory / "test_p_0001_example.py"
    source.write_text("# Problem URL: https://leetcode.com/problems/problem-1/\nmy solution\n")
    tests.write_text("my tests\n")
    original = (source.read_bytes(), tests.read_bytes())
    monkeypatch.setattr(lc, "preflight_git", lambda *_: "main")
    for _ in range(2):
        assert lc.dispatch(["next"], tmp_path, tmp_path) == 0
    assert (source.read_bytes(), tests.read_bytes()) == original
    assert lc.detect_problem_context(tmp_path, tmp_path).problem_id == "0001"


def test_import_and_show_do_not_change_active_problem(tmp_path):
    active = tmp_path / ".lc/active.json"
    write_state(active, {"language": "ts", "problem_id": "0099"})
    before = active.read_bytes()
    state = imported(tmp_path, [question(1)])
    practice.show_list(tmp_path, state)
    assert active.read_bytes() == before


def test_empty_or_unavailable_import_preserves_saved_snapshot(tmp_path):
    imported(tmp_path, [question(1)])
    before = (tmp_path / ".lc/practice.json").read_bytes()
    with pytest.raises(practice.PracticeError, match="empty or unavailable"):
        practice.import_list(tmp_path, URL, session_factory=lambda _: Session([page([])]))
    assert (tmp_path / ".lc/practice.json").read_bytes() == before


def test_live_status_values_normalize_and_select_first_unsolved(tmp_path):
    state = imported(
        tmp_path, [question(217, "SOLVED"), question(334, "TO_DO"), question(1, "ATTEMPTED")]
    )
    assert [item["status"] for item in state["questions"]] == ["AC", "NOT_STARTED", "TRIED"]
    assert practice.next_question(tmp_path, state)["questionFrontendId"] == "0334"
    assert practice.load_list(tmp_path) == state
