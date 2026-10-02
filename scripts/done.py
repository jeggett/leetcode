"""Check, submit, and save one accepted solution, with durable retry progress."""

from __future__ import annotations

import fcntl
import hashlib
import re
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.lc_state import read_state, write_state
    from scripts.leetcode_browser import BrowserError, LeetCodeBrowser
    from scripts.leetcode_session import LeetCodeSession
    from scripts.problem_paths import require_source_path, require_test_path, resolve_problem_paths
    from scripts.submission import SubmissionError, read_submission
    from scripts.submission_result import normalize_result, result_summary
except ModuleNotFoundError:
    from lc_state import read_state, write_state
    from leetcode_browser import BrowserError, LeetCodeBrowser
    from leetcode_session import LeetCodeSession
    from problem_paths import require_source_path, require_test_path, resolve_problem_paths
    from submission import SubmissionError, read_submission
    from submission_result import normalize_result, result_summary


class DoneError(ValueError):
    """A workflow step needs attention before it can continue."""


def source_hash(source: str) -> str:
    return hashlib.sha256(source.encode()).hexdigest()


@contextmanager
def workflow_lock(root: Path):
    """Serialize submissions, profile use, and index changes across lc processes."""
    directory = root / ".lc"
    directory.mkdir(exist_ok=True, mode=0o700)
    with (directory / "done.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise DoneError("another lc done is running; wait for it to finish") from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def finish_problem(
    root: Path,
    language: str,
    problem_id: str,
    *,
    resume: str | None = None,
    retry_uncertain: bool = False,
    run=subprocess.run,
    browser_factory=LeetCodeSession,
) -> int:
    with workflow_lock(root):
        try:
            return _finish_problem(
                root,
                language,
                problem_id,
                resume=resume,
                retry_uncertain=retry_uncertain,
                run=run,
                browser_factory=browser_factory,
            )
        except (BrowserError, SubmissionError) as error:
            raise DoneError(str(error)) from error


def _finish_problem(
    root: Path,
    language: str,
    problem_id: str,
    *,
    resume: str | None,
    retry_uncertain: bool,
    run,
    browser_factory,
) -> int:
    paths = resolve_problem_paths(root, language, problem_id)
    source_path = require_source_path(paths)
    require_test_path(paths)
    directory = paths.directory.relative_to(root).as_posix()
    relative_source = source_path.relative_to(root).as_posix()
    print(
        f"LeetCode {paths.problem_id}: {paths.stem.split('_', 2)[2].replace('_', ' ')} ({language})"
    )

    def command(*arguments: str, capture: bool = True, allow_failure: bool = False):
        result = run(arguments, cwd=root, check=False, text=True, capture_output=capture)
        if result.returncode and not allow_failure:
            detail = ((result.stderr or "") + (result.stdout or "")).strip() if capture else ""
            raise DoneError(
                f"{' '.join(arguments)} failed (exit {result.returncode})"
                f"{': ' + detail if detail else ''}; fix it, then retry lc done"
            )
        return result

    def git(*arguments: str) -> str:
        return command("git", *arguments).stdout

    def guard_index() -> None:
        if git("branch", "--show-current").strip() != "main":
            raise DoneError("lc done requires main; next: git switch main")
        staged = git("diff", "--cached", "--name-only", "--no-renames", "-z").split("\0")
        unrelated = [name for name in staged if name and not name.startswith(directory + "/")]
        if unrelated:
            raise DoneError(
                "unrelated staged changes: "
                + ", ".join(unrelated)
                + "; unstage them before retrying lc done"
            )

    def snapshot() -> dict[str, str]:
        names = git("ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", directory)
        result = {}
        for name in names.split("\0"):
            if not name:
                continue
            path = root / name
            if path.is_symlink() or not path.resolve().is_relative_to(paths.directory.resolve()):
                raise DoneError("problem files must be regular files inside the problem directory")
            if path.exists():
                result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    guard_index()
    state_path = root / ".lc" / "submissions" / f"{language}-{paths.problem_id}.json"
    state = read_state(state_path)
    if not state:
        state = {"version": 1, "attempts": []}
    statuses = {
        "submitting",
        "pending",
        "accepted",
        "rejected",
        "committing",
        "committed",
        "pushed",
        "abandoned",
    }
    if (
        state.get("version") != 1
        or not isinstance(state.get("attempts"), list)
        or any(
            not isinstance(item, dict)
            or item.get("status") not in statuses
            or not isinstance(item.get("source_hash"), str)
            or not isinstance(item.get("submission_hash"), str)
            or not isinstance(item.get("files"), dict)
            or (
                item.get("status") not in {"submitting", "abandoned"}
                and not str(item.get("submission_id", "")).isdecimal()
            )
            or (
                item.get("status") in {"committed", "pushed"}
                and not re.fullmatch(r"[0-9a-f]{40,64}", str(item.get("commit", "")))
            )
            or (
                item.get("status") == "committing"
                and not re.fullmatch(r"[0-9a-f]{40,64}", str(item.get("head_before_commit", "")))
            )
            for item in state["attempts"]
        )
    ):
        raise DoneError(f"invalid submission journal: {state_path}; restore it before retrying")
    attempts = state["attempts"]

    def save() -> None:
        write_state(state_path, state)

    raw_source = source_path.read_text(encoding="utf-8")
    digest = source_hash(raw_source)
    unfinished = next(
        (
            item
            for item in reversed(attempts)
            if item["status"] in {"submitting", "pending", "accepted", "committing", "committed"}
        ),
        None,
    )
    if unfinished and unfinished["source_hash"] != digest:
        raise DoneError(
            "source changed since the pending submission/save; restore the submitted source before retrying lc done"
        )
    attempt = unfinished or next(
        (
            item
            for item in reversed(attempts)
            if item["source_hash"] == digest and item["status"] == "pushed"
        ),
        None,
    )
    if resume and (not resume.isdecimal() or int(resume) <= 0):
        raise DoneError("--resume needs a positive submission ID")
    if resume and retry_uncertain:
        raise DoneError("choose --resume or --retry-uncertain")
    if (resume or retry_uncertain) and (attempt is None or attempt["status"] != "submitting"):
        raise DoneError("recovery options only apply to an uncertain submission")
    if retry_uncertain:
        attempt["status"] = "abandoned"
        save()
        attempt = None
    if attempt and attempt["status"] == "submitting" and not resume:
        raise DoneError(
            "submission outcome is uncertain; check LeetCode submission history, then use "
            "lc done --resume SUBMISSION_ID. If no submission exists, use lc done --retry-uncertain"
        )

    if attempt and attempt["status"] in {"accepted", "committing", "committed", "pushed"}:
        print(result_summary(attempt))

    if attempt and attempt["status"] == "pushed":
        # A test-only edit still deserves a new checked commit, using the accepted source.
        if (
            snapshot() == attempt["files"]
            and not git("diff", "--name-only", attempt["commit"], "HEAD", "--", directory).strip()
        ):
            print(f"Already Accepted and pushed: {attempt['commit']}")
            return 0
        attempt = {**attempt, "status": "accepted", "commit": None}
        attempts.append(attempt)

    if attempt is None or attempt["status"] == "accepted":
        formatter = (
            ("pnpm", "exec", "biome", "format", "--write", directory)
            if language == "ts"
            else ("uv", "run", "ruff", "format", directory)
        )
        command(*formatter, capture=False)
        raw_source = source_path.read_text(encoding="utf-8")
        digest = source_hash(raw_source)
        if attempt and attempt["source_hash"] != digest:
            raise DoneError("formatting changed the accepted source; restore it before retrying")
        checked_files = snapshot()
        command("pnpm", "run", "ready", capture=False)
        if snapshot() != checked_files:
            raise DoneError("problem files changed during checks; retry lc done")
        if attempt:
            attempt["files"] = checked_files
            save()
    else:
        checked_files = attempt["files"]

    payload = read_submission(root, language, paths.problem_id)
    if source_hash(source_path.read_text(encoding="utf-8")) != digest:
        raise DoneError("source changed while rendering; retry lc done")
    if attempt and source_hash(payload) != attempt["submission_hash"]:
        raise DoneError("rendered submission changed; inspect the journal before retrying")
    if attempt is None:
        # Formatting may restore exactly the source of a previously saved acceptance.
        previous = next(
            (
                item
                for item in reversed(attempts)
                if item["status"] == "pushed" and item["submission_hash"] == source_hash(payload)
            ),
            None,
        )
        if previous:
            attempt = {
                **previous,
                "status": "accepted",
                "source_hash": digest,
                "files": checked_files,
                "commit": None,
            }
            attempts.append(attempt)
            save()
            print(result_summary(attempt))
    if attempt is None or attempt["status"] in {"submitting", "pending"}:
        url_match = re.search(
            r"Problem URL: https://leetcode\.com/problems/([a-z0-9]+(?:-[a-z0-9]+)*)/(?:\s|$)",
            raw_source,
        )
        if not url_match:
            metadata = read_state(root / ".lc" / "problems" / f"{language}-{paths.problem_id}.json")
            url_match = re.fullmatch(
                r"https://leetcode\.com/problems/([a-z0-9]+(?:-[a-z0-9]+)*)/",
                str(metadata.get("url", "")),
            )
        if not url_match:
            raise DoneError("problem URL is unknown; next: lc new URL to reopen it, then lc done")
        slug = url_match[1]
        with browser_factory(root) as browser:
            question_id = browser.prepare(slug, paths.problem_id)
            if attempt is None:
                # Journal intent before the POST. A crash after this point must not resend.
                attempt = {
                    "status": "submitting",
                    "source_hash": digest,
                    "submission_hash": source_hash(payload),
                    "files": checked_files,
                    "slug": slug,
                    "language": language,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                attempts.append(attempt)
                save()
                try:
                    submission_id = browser.submit(slug, language, question_id, payload)
                except BrowserError as error:
                    raise DoneError(
                        f"{error}; submission outcome is uncertain. "
                        "Next: check LeetCode history, then lc done --resume SUBMISSION_ID"
                    ) from error
                attempt.update(status="pending", submission_id=submission_id)
                save()
            elif resume:
                browser.verify_submission(resume, slug, language, payload)
                attempt.update(status="pending", submission_id=resume)
                save()
            print(f"Judging submission {attempt['submission_id']}…", flush=True)
            verdict = browser.wait(attempt["submission_id"])
            accepted = verdict["status_code"] == 10
            result = normalize_result(verdict, attempt["submission_id"])
            attempt.update(
                status="accepted" if accepted else "rejected",
                verdict=result.get("verdict", str(verdict["status_code"])),
                result=result,
            )
            save()
            print(result_summary(attempt))
            if not accepted:
                print("Next: edit the solution, then lc test and lc done")
                return 1

    if snapshot() != attempt["files"]:
        raise DoneError(
            "problem files changed while judging; nothing saved. Restore the checked files and retry lc done"
        )
    guard_index()

    def verify_commit(commit: str) -> None:
        committed_source = git("show", f"{commit}:{relative_source}")
        if source_hash(committed_source) != attempt["source_hash"]:
            raise DoneError(
                "saved commit does not match the accepted source; review Git before retrying"
            )

    if attempt["status"] == "committing":
        head = git("rev-parse", "HEAD").strip()
        if head != attempt["head_before_commit"]:
            parent = git("rev-parse", f"{head}^").strip()
            names = git(
                "diff-tree", "--no-commit-id", "--name-only", "--no-renames", "-r", head
            ).splitlines()
            if parent != attempt["head_before_commit"] or any(
                not name.startswith(directory + "/") for name in names
            ):
                raise DoneError("main moved during save; review Git before retrying lc done")
            verify_commit(head)
            attempt.update(status="committed", commit=head)
            save()
        else:
            attempt["status"] = "accepted"

    if attempt["status"] == "accepted":
        git("add", "--", directory)
        guard_index()
        if (
            snapshot() != attempt["files"]
            or source_hash(git("show", f":{relative_source}")) != digest
        ):
            raise DoneError("source changed during staging; review changes before retrying lc done")
        head = git("rev-parse", "HEAD").strip()
        changes = git("diff", "--cached", "--name-only", "--", directory).strip()
        if changes:
            attempt.update(status="committing", head_before_commit=head)
            save()
            title = paths.stem.split("_", 2)[2].replace("_", " ")
            command("git", "commit", "-m", f"feat({paths.problem_id}): {title}", capture=False)
            head = git("rev-parse", "HEAD").strip()
        verify_commit(head)
        attempt.update(status="committed", commit=head)
        save()
    commit = attempt["commit"]
    verify_commit(commit)
    guard_index()
    # Push the saved commit explicitly, so unrelated later commits cannot slip in.
    command("git", "push", "origin", f"{commit}:refs/heads/main", capture=False)
    attempt["status"] = "pushed"
    save()
    print(f"Saved and pushed: {commit}")
    return 0


def done_command(arguments: list[str], root: Path, caller_cwd: Path) -> int:
    try:
        from scripts.lc import _canonical_language, detect_problem_context
    except ModuleNotFoundError:
        from lc import _canonical_language, detect_problem_context
    values = list(arguments)
    resume = None
    retry_uncertain = False
    use_browser = False
    targets = []
    while values:
        value = values.pop(0)
        if value == "--resume" and values and resume is None:
            resume = values.pop(0)
        elif value == "--retry-uncertain" and not retry_uncertain:
            retry_uncertain = True
        elif value == "--browser" and not use_browser:
            use_browser = True
        elif value.startswith("-"):
            raise DoneError(f"unknown or incomplete done option: {value}; next: lc help done")
        else:
            targets.append(value)
    language = _canonical_language(targets[0]) if targets else None
    if language:
        targets.pop(0)
    if len(targets) > 1:
        raise DoneError("usage: lc done [ts|py] [ID]")
    if targets:
        language = language or "ts"
        problem_id = targets[0]
    else:
        context = detect_problem_context(root, caller_cwd)
        if context is None:
            raise DoneError("no active problem; next: lc new URL")
        language = language or context.language
        problem_id = context.problem_id
    backend = {"browser_factory": LeetCodeBrowser} if use_browser else {}
    return finish_problem(
        root, language, problem_id, resume=resume, retry_uncertain=retry_uncertain, **backend
    )
