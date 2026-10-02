"""Exercise real local Git history and a controllable judge without remote side effects."""

import json
import subprocess

import pytest

from scripts.done import DoneError, finish_problem, workflow_lock
from scripts.leetcode_browser import BrowserError


class Judge:
    def __init__(self):
        self.submits = 0
        self.waits = []
        self.verifies = []
        self.verdict = {"state": "SUCCESS", "status_code": 10, "status_msg": "Accepted"}
        self.on_wait = None
        self.submit_error = False

    def __call__(self, _root):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def prepare(self, slug, problem_id):
        assert slug == "search-insert-position" and problem_id == "0035"
        return "35"

    def submit(self, slug, language, question_id, source):
        self.submits += 1
        assert "export function" not in source
        if self.submit_error:
            raise BrowserError("connection lost")
        return "123"

    def verify_submission(self, *args):
        self.verifies.append(args)

    def wait(self, submission_id):
        self.waits.append(submission_id)
        if self.on_wait:
            self.on_wait()
        return self.verdict


class Workspace:
    def __init__(self, root, language):
        self.root = root
        self.language = language
        self.calls = []
        self.failure = None
        self.after_commit = None
        self.judge = Judge()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Workflow test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "core.hooksPath", "/dev/null")
        (root / ".gitignore").write_text(".lc/\n__pycache__/\n")
        self.git("add", ".gitignore")
        self.git("commit", "-m", "chore: initialize")
        self.base = self.git("rev-parse", "HEAD").strip()
        remote = root / ".lc" / "remote.git"
        subprocess.run(("git", "init", "--bare", str(remote)), check=True, capture_output=True)
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "origin", "main")
        stem = "p_0035_search_insert_position"
        self.directory = root / "src" / ("typescript" if language == "ts" else "python") / stem
        self.directory.mkdir(parents=True)
        self.source = self.directory / f"{stem}.{language}"
        if language == "ts":
            self.source.write_text(
                "// Problem URL: https://leetcode.com/problems/search-insert-position/\nexport function searchInsert(): number { return 0; }\n"
            )
            self.test = self.directory / f"{stem}.test.ts"
        else:
            self.source.write_text(
                "# Problem URL: https://leetcode.com/problems/search-insert-position/\nclass Solution:\n    def searchInsert(self) -> int:\n        return 0\n"
            )
            self.test = self.directory / f"test_{stem}.py"
        self.test.write_text("# test\n" if language == "py" else "// test\n")
        self.state_path = root / ".lc/submissions" / f"{language}-0035.json"

    def git(self, *args):
        return subprocess.run(
            ("git", *args), cwd=self.root, check=True, text=True, capture_output=True
        ).stdout

    def run(self, args, **kwargs):
        args = tuple(args)
        self.calls.append(args)
        if self.failure and args[: len(self.failure)] == self.failure:
            return subprocess.CompletedProcess(args, 1, "", "intentional failure")
        if args[0] != "git":
            return subprocess.CompletedProcess(args, 0, "", "")
        kwargs["capture_output"] = True
        result = subprocess.run(args, **kwargs)
        if args[:2] == ("git", "commit") and self.after_commit:
            self.after_commit()
        return result

    def done(self, **kwargs):
        return finish_problem(
            self.root, self.language, "35", run=self.run, browser_factory=self.judge, **kwargs
        )

    def state(self):
        return json.loads(self.state_path.read_text())["attempts"][-1]


@pytest.fixture(params=["ts", "py"])
def workspace(tmp_path, request):
    return Workspace(tmp_path, request.param)


def test_accepted_commits_only_problem_and_pushes(workspace):
    unrelated = workspace.root / "notes.txt"
    unrelated.write_text("preserve")
    assert workspace.done() == 0
    assert workspace.state()["status"] == "pushed"
    assert workspace.judge.submits == 1
    assert workspace.git("log", "-1", "--format=%s").strip() == "feat(0035): search insert position"
    changed = workspace.git("diff", "--name-only", workspace.base).splitlines()
    assert len(changed) == 2 and all("p_0035_" in path for path in changed)
    assert workspace.git("rev-parse", "HEAD") == workspace.git("rev-parse", "origin/main")
    assert unrelated.read_text() == "preserve"
    assert workspace.done() == 0
    assert workspace.judge.submits == 1


@pytest.mark.parametrize(
    "failure", [("pnpm", "run", "ready"), ("pnpm", "exec"), ("uv", "run", "ruff")]
)
def test_local_failure_never_submits(tmp_path, failure):
    language = "py" if failure[0] == "uv" else "ts"
    workspace = Workspace(tmp_path, language)
    workspace.failure = failure
    with pytest.raises(DoneError, match="failed"):
        workspace.done()
    assert workspace.judge.submits == 0
    assert not workspace.state_path.exists()


def test_unrelated_staged_changes_stop_before_checks(workspace):
    (workspace.root / "notes.txt").write_text("staged")
    workspace.git("add", "notes.txt")
    with pytest.raises(DoneError, match="unrelated staged"):
        workspace.done()
    assert workspace.judge.submits == 0
    assert not any(call[0] in {"pnpm", "uv"} for call in workspace.calls)
    assert workspace.git("diff", "--cached", "--name-only").strip() == "notes.txt"


def test_requires_main(workspace):
    workspace.git("switch", "-c", "feature/example")
    with pytest.raises(DoneError, match="requires main"):
        workspace.done()
    assert workspace.judge.submits == 0


def test_rejected_leaves_work_uncommitted_and_allows_retry(workspace):
    workspace.judge.verdict = {"status_code": 11, "status_msg": "Wrong Answer"}
    assert workspace.done() == 1
    assert workspace.state()["status"] == "rejected"
    assert workspace.git("rev-parse", "HEAD").strip() == workspace.base
    assert workspace.git("diff", "--cached", "--name-only") == ""
    workspace.judge.verdict = {"status_code": 10, "status_msg": "Accepted"}
    assert workspace.done() == 0
    assert workspace.judge.submits == 2


def test_timeout_resumes_same_submission(workspace):
    def timeout():
        raise BrowserError("judging timed out")

    workspace.judge.on_wait = timeout
    with pytest.raises(DoneError, match="timed out"):
        workspace.done()
    assert workspace.state()["status"] == "pending"
    workspace.judge.on_wait = None
    assert workspace.done() == 0
    assert workspace.judge.submits == 1
    assert workspace.judge.waits == ["123", "123"]


def test_source_change_during_judging_prevents_saving(workspace):
    original = workspace.source.read_text()
    workspace.judge.on_wait = lambda: workspace.source.write_text(original + "\n")
    with pytest.raises(DoneError, match="changed while judging"):
        workspace.done()
    assert workspace.state()["status"] == "accepted"
    assert workspace.git("rev-parse", "HEAD").strip() == workspace.base
    with pytest.raises(DoneError, match="source changed"):
        workspace.done()
    workspace.source.write_text(original)
    workspace.judge.on_wait = None
    assert workspace.done() == 0
    assert workspace.judge.submits == 1


@pytest.mark.parametrize("failure", [("git", "commit"), ("git", "push")])
def test_save_failure_retry_does_not_resubmit(workspace, failure):
    workspace.failure = failure
    with pytest.raises(DoneError, match="failed"):
        workspace.done()
    assert workspace.state()["status"] == ("committing" if failure[-1] == "commit" else "committed")
    workspace.failure = None
    assert workspace.done() == 0
    assert workspace.judge.submits == 1
    assert workspace.git("rev-list", "--count", f"{workspace.base}..HEAD").strip() == "1"


def test_crash_after_git_commit_recovers_without_duplicate_commit(workspace):
    def crash():
        raise KeyboardInterrupt

    workspace.after_commit = crash
    with pytest.raises(KeyboardInterrupt):
        workspace.done()
    assert workspace.state()["status"] == "committing"
    workspace.after_commit = None
    assert workspace.done() == 0
    assert workspace.git("rev-list", "--count", f"{workspace.base}..HEAD").strip() == "1"
    assert workspace.judge.submits == 1


def test_uncertain_post_stops_until_explicit_resolution(workspace):
    workspace.judge.submit_error = True
    with pytest.raises(DoneError, match="uncertain"):
        workspace.done()
    with pytest.raises(DoneError, match="uncertain"):
        workspace.done()
    assert workspace.judge.submits == 1
    workspace.judge.submit_error = False
    assert workspace.done(resume="456") == 0
    assert workspace.judge.submits == 1
    assert workspace.judge.verifies[0][0] == "456"
    assert workspace.judge.waits == ["456"]


def test_explicit_retry_after_verifying_no_submission(workspace):
    workspace.judge.submit_error = True
    with pytest.raises(DoneError):
        workspace.done()
    workspace.judge.submit_error = False
    assert workspace.done(retry_uncertain=True) == 0
    assert workspace.judge.submits == 2


def test_journal_corruption_never_submits(workspace):
    workspace.state_path.parent.mkdir(parents=True)
    workspace.state_path.write_text('{"version": 1, "attempts": [null]}')
    with pytest.raises(DoneError, match="invalid submission journal"):
        workspace.done()
    assert workspace.judge.submits == 0


def test_concurrent_done_stops(workspace):
    with workflow_lock(workspace.root):
        with pytest.raises(DoneError, match="another lc done"):
            workspace.done()
    assert workspace.judge.submits == 0


def test_formatting_back_to_accepted_source_does_not_resubmit(workspace):
    assert workspace.done() == 0
    original = workspace.source.read_text()
    workspace.source.write_text(original + "\n")
    previous_run = workspace.run

    def format_source(args, **kwargs):
        if args[0] != "git" and "format" in args:
            workspace.source.write_text(original)
        return previous_run(args, **kwargs)

    workspace.run = format_source
    assert workspace.done() == 0
    assert workspace.judge.submits == 1


def test_restoring_accepted_work_after_a_revert_saves_without_resubmitting(workspace):
    assert workspace.done() == 0
    source, test = workspace.source.read_text(), workspace.test.read_text()
    workspace.git("revert", "--no-edit", "HEAD")
    workspace.directory.mkdir(parents=True, exist_ok=True)
    workspace.source.write_text(source)
    workspace.test.write_text(test)
    assert workspace.done() == 0
    assert workspace.judge.submits == 1
    assert workspace.git("log", "-1", "--format=%s").strip() == "feat(0035): search insert position"


def test_test_only_change_is_checked_and_saved_without_resubmitting(workspace):
    assert workspace.done() == 0
    workspace.test.write_text(workspace.test.read_text() + "\n")
    assert workspace.done() == 0
    assert workspace.judge.submits == 1
    assert workspace.git("rev-list", "--count", f"{workspace.base}..HEAD").strip() == "2"


def test_deleted_problem_file_does_not_block_failed_push_recovery(workspace):
    obsolete = workspace.directory / "obsolete.txt"
    obsolete.write_text("old notes")
    workspace.git("add", str(obsolete))
    workspace.git("commit", "-m", "chore: add old notes")
    obsolete.unlink()
    workspace.failure = ("git", "push")
    with pytest.raises(DoneError, match="failed"):
        workspace.done()
    workspace.failure = None
    assert workspace.done() == 0
    assert workspace.judge.submits == 1
    assert not obsolete.exists()


def test_reopened_legacy_source_uses_remembered_official_url(workspace):
    from scripts.lc import activate_problem

    workspace.source.write_text(workspace.source.read_text().split("\n", 1)[1])
    activate_problem(
        workspace.root,
        workspace.language,
        "35",
        "https://leetcode.com/problems/search-insert-position/",
    )
    assert workspace.done() == 0
    assert workspace.judge.submits == 1


@pytest.mark.parametrize("code,label", [(10, "Accepted"), (11, "Wrong Answer")])
def test_journal_and_output_include_judge_metrics(workspace, capsys, code, label):
    workspace.judge.verdict = {
        "status_code": code,
        "status_msg": label,
        "status_runtime": "0 ms",
        "status_memory": "12 MB",
        "total_correct": 0,
        "total_testcases": 8,
        "full_runtime_error": "must not persist",
    }
    assert workspace.done() == (0 if code == 10 else 1)
    result = workspace.state()["result"]
    assert result["verdict"] == label and result["status_code"] == code
    assert result["passed"] == 0 and result["total"] == 8
    assert "must not persist" not in workspace.state_path.read_text()
    output = capsys.readouterr().out
    assert "runtime: 0 ms | memory: 12 MB | tests: 0/8" in output
    assert "https://leetcode.com/submissions/detail/123/" in output


def test_failed_push_reuses_saved_metrics(workspace, capsys):
    workspace.judge.verdict.update(status_runtime="2 ms", memory=1048576)
    workspace.failure = ("git", "push")
    with pytest.raises(DoneError, match="failed"):
        workspace.done()
    saved = workspace.state()["result"]
    capsys.readouterr()
    workspace.failure = None
    workspace.judge.verdict = {}
    assert workspace.done() == 0
    assert workspace.state()["result"] == saved
    assert workspace.judge.submits == 1 and workspace.judge.waits == ["123"]
    assert "runtime: 2 ms | memory: 1.00 MiB" in capsys.readouterr().out


def test_old_journal_push_recovery(workspace, capsys):
    workspace.failure = ("git", "push")
    with pytest.raises(DoneError):
        workspace.done()
    state = json.loads(workspace.state_path.read_text())
    state["attempts"][-1].pop("result")
    workspace.state_path.write_text(json.dumps(state))
    capsys.readouterr()
    workspace.failure = None
    assert workspace.done() == 0
    assert "Accepted | https://leetcode.com/submissions/detail/123/" in capsys.readouterr().out
    assert workspace.judge.submits == 1 and workspace.judge.waits == ["123"]
