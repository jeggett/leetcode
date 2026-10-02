"""Import an ordered practice snapshot and track account-wide Accepted results."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

try:
    from scripts.lc_state import StateError, read_state, write_state
    from scripts.leetcode_session import LeetCodeSession
except ModuleNotFoundError:
    from lc_state import StateError, read_state, write_state
    from leetcode_session import LeetCodeSession

LIST_PATH = re.compile(r"^/problem-list/([a-zA-Z0-9_-]+)/?$")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
QUERY = """query($slug:String!,$skip:Int!,$limit:Int!){
  favoriteQuestionList(favoriteSlug:$slug,skip:$skip,limit:$limit,version:"v2",
    sortBy:{sortField:CUSTOM,sortOrder:ASCENDING}){
    questions{questionFrontendId title titleSlug difficulty paidOnly status}
    totalLength hasMore
  }
}"""
PAGE_SIZE = 100
MAX_QUESTIONS = 10000
ACCEPTED = {"accepted", "committing", "committed", "pushed"}
STATUSES = ACCEPTED | {"submitting", "pending", "rejected", "abandoned"}
REMOTE_STATUSES = {
    "SOLVED": "AC",
    "TO_DO": "NOT_STARTED",
    "ATTEMPTED": "TRIED",
    "AC": "AC",
    "TRIED": "TRIED",
    "NOT_STARTED": "NOT_STARTED",
    None: None,
}


class PracticeError(ValueError):
    """A list or its saved progress could not be verified."""


def canonicalize_list_url(value: str) -> tuple[str, str]:
    try:
        parsed = urlsplit(value.strip())
        valid = (
            parsed.scheme == "https"
            and parsed.hostname == "leetcode.com"
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        valid = False
    if not valid:
        raise PracticeError("use https://leetcode.com/problem-list/<slug>/")
    match = LIST_PATH.fullmatch(parsed.path)
    if not match:
        raise PracticeError(
            "use a LeetCode problem-list URL; for a study plan, open its problem list first"
        )
    return f"https://leetcode.com/problem-list/{match[1]}/", match[1]


def _question(value: object) -> dict:
    if not isinstance(value, dict):
        raise PracticeError("LeetCode returned an invalid list question")
    number = value.get("questionFrontendId")
    slug = value.get("titleSlug")
    title = value.get("title")
    if (
        not isinstance(number, str)
        or not re.fullmatch(r"[0-9]+", number)
        or int(number) <= 0
        or not isinstance(slug, str)
        or not SLUG.fullmatch(slug)
        or not isinstance(title, str)
        or not title.strip()
        or not isinstance(value.get("difficulty"), str)
        or value.get("difficulty") not in {"EASY", "MEDIUM", "HARD", "Easy", "Medium", "Hard"}
        or type(value.get("paidOnly")) is not bool
        or (value.get("status") is not None and not isinstance(value.get("status"), str))
        or value.get("status") not in REMOTE_STATUSES
        or "status" not in value
    ):
        raise PracticeError("LeetCode returned incomplete or invalid list metadata")
    return {
        "questionFrontendId": str(int(number)).zfill(4),
        "titleSlug": slug,
        "title": title.strip(),
        "difficulty": value["difficulty"],
        "paidOnly": value["paidOnly"],
        "status": REMOTE_STATUSES[value["status"]],
    }


def load_list(root: Path) -> dict:
    state = read_state(root / ".lc/practice.json")
    if not state:
        return {}
    if (
        type(state.get("version")) is not int
        or state.get("version") != 1
        or not isinstance(state.get("language"), str)
        or state.get("language") not in {"ts", "py"}
        or not isinstance(state.get("url"), str)
        or not isinstance(state.get("imported_at"), str)
        or not isinstance(state.get("questions"), list)
    ):
        raise PracticeError("invalid saved practice list; import it again with lc list URL")
    canonicalize_list_url(state["url"])
    questions = [_question(item) for item in state["questions"]]
    if len({item["questionFrontendId"] for item in questions}) != len(questions):
        raise PracticeError("duplicate IDs in saved practice list; import it again")
    return {**state, "questions": questions}


def import_list(root: Path, url: str, language: str = "ts", *, session_factory=None) -> dict:
    canonical, slug = canonicalize_list_url(url)
    if language not in {"ts", "py"}:
        raise PracticeError("language must be ts or py")
    questions = []
    seen = set()
    expected_total = None
    offset = 0
    with (session_factory or LeetCodeSession)(root) as session:
        session.require_login()
        for _ in range(MAX_QUESTIONS // PAGE_SIZE + 1):
            data = session.graphql(QUERY, {"slug": slug, "skip": offset, "limit": PAGE_SIZE})
            page = data.get("favoriteQuestionList") if isinstance(data, dict) else None
            if not isinstance(page, dict):
                raise PracticeError("LeetCode list was not found or is unavailable")
            total, more, items = page.get("totalLength"), page.get("hasMore"), page.get("questions")
            if (
                type(total) is not int
                or not 0 <= total <= MAX_QUESTIONS
                or type(more) is not bool
                or not isinstance(items, list)
                or len(items) > PAGE_SIZE
                or (expected_total is not None and total != expected_total)
            ):
                raise PracticeError("LeetCode returned inconsistent list pagination; retry import")
            expected_total = total
            added = 0
            for raw in items:
                item = _question(raw)
                if item["questionFrontendId"] not in seen:
                    seen.add(item["questionFrontendId"])
                    questions.append(item)
                    added += 1
            offset += len(items)
            if offset > total or (more and (not added or offset >= total)):
                raise PracticeError("LeetCode list pagination stalled or changed; retry import")
            if not more:
                if offset != total:
                    raise PracticeError("LeetCode returned only part of the list; retry import")
                break
        else:
            raise PracticeError("LeetCode list exceeded the pagination limit")
    if not questions:
        raise PracticeError(
            "list is empty or unavailable; check its URL and access, then lc list URL"
        )
    state = {
        "version": 1,
        "language": language,
        "url": canonical,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "questions": questions,
    }
    write_state(root / ".lc/practice.json", state)
    return state


def solved_ids(root: Path, state: dict) -> set[str]:
    solved = {item["questionFrontendId"] for item in state["questions"] if item["status"] == "AC"}
    for path in sorted((root / ".lc/submissions").glob("*.json")):
        match = re.fullmatch(r"(?:ts|py)-([0-9]+)\.json", path.name)
        if not match:
            continue
        journal = read_state(path)
        attempts = journal.get("attempts")
        if (
            int(match[1]) <= 0
            or type(journal.get("version")) is not int
            or journal.get("version") != 1
            or not isinstance(attempts, list)
        ):
            raise StateError(f"invalid submission journal: {path}")
        for attempt in attempts:
            if (
                not isinstance(attempt, dict)
                or not isinstance(attempt.get("status"), str)
                or attempt.get("status") not in STATUSES
                or not isinstance(attempt.get("source_hash"), str)
                or not isinstance(attempt.get("submission_hash"), str)
                or not isinstance(attempt.get("files"), dict)
                or (
                    attempt.get("status") not in {"submitting", "abandoned"}
                    and (
                        not re.fullmatch(r"[0-9]+", str(attempt.get("submission_id", "")))
                        or int(attempt["submission_id"]) <= 0
                    )
                )
                or (
                    attempt.get("status") in {"committed", "pushed", "committing"}
                    and not re.fullmatch(
                        r"[0-9a-f]{40,64}",
                        str(
                            attempt.get(
                                "head_before_commit"
                                if attempt["status"] == "committing"
                                else "commit",
                                "",
                            )
                        ),
                    )
                )
            ):
                raise StateError(f"invalid submission journal: {path}")
            if attempt["status"] in ACCEPTED:
                solved.add(str(int(match[1])).zfill(4))
    return solved


def next_question(root: Path, state: dict) -> dict | None:
    solved = solved_ids(root, state)
    return next(
        (item for item in state["questions"] if item["questionFrontendId"] not in solved), None
    )


def show_list(root: Path, state: dict) -> None:
    solved = solved_ids(root, state)
    count = sum(item["questionFrontendId"] in solved for item in state["questions"])
    print(f"Practice list: {state['url']} ({state['language']})")
    print(f"Progress: {count}/{len(state['questions'])} Accepted")
    for item in state["questions"]:
        status = "Accepted" if item["questionFrontendId"] in solved else "Unsolved"
        premium = " · Premium" if item["paidOnly"] else ""
        print(
            f"{item['questionFrontendId']} {item['title']} · {item['difficulty']}{premium} · {status}"
        )
    print("Next: lc next" if count < len(state["questions"]) else "Practice list complete.")
