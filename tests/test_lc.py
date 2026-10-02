from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request

import pytest

from scripts import lc
from scripts.lc import (
    CommandResult,
    LeetError,
    ProblemMetadata,
    ScaffoldResult,
    canonicalize_problem_url,
    extract_python_signature,
    extract_typescript_signature,
    fetch_problem_metadata,
    parse_arguments,
    scaffold_from_url,
)


PROBLEM_URL = "https://leetcode.com/problems/search-insert-position/"
TS_SIGNATURE = "searchInsert(nums: number[], target: number): number"
PY_SIGNATURE = "searchInsert(self, nums: list[int], target: int) -> int"


def metadata(signature: str = TS_SIGNATURE) -> ProblemMetadata:
    return ProblemMetadata(
        problem_id="0035",
        title="Search Insert Position",
        title_slug="search-insert-position",
        canonical_url=PROBLEM_URL,
        signature=signature,
    )


def graphql_document(*, snippets: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "data": {
            "question": {
                "questionFrontendId": "35",
                "title": "Search Insert Position",
                "titleSlug": "search-insert-position",
                "isPaidOnly": False,
                "codeSnippets": snippets
                if snippets is not None
                else [
                    {
                        "langSlug": "typescript",
                        "code": (
                            "function searchInsert(nums: number[], target: number): number {\n"
                            "    \n};"
                        ),
                    },
                    {
                        "langSlug": "python3",
                        "code": (
                            "class Solution:\n"
                            "    def searchInsert(self, nums: List[int], target: int) -> int:\n"
                            "        "
                        ),
                    },
                ],
            }
        }
    }


class FakeResponse:
    def __init__(self, document: object, *, status: int = 200) -> None:
        self.body = json.dumps(document).encode()
        self.status = status

    def read(self, limit: int = -1) -> bytes:
        return self.body if limit < 0 else self.body[:limit]

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_arguments: object) -> None:
        return None


class FakeGit:
    def __init__(
        self,
        root: Path,
        *,
        dirty: bool = False,
        branch_exists: bool = False,
        remote_branch_exists: bool = False,
    ) -> None:
        self.root = root
        self.dirty = dirty
        self.branch_exists = branch_exists
        self.remote_branch_exists = remote_branch_exists
        self.current_branch = "main"
        self.calls: list[tuple[str, ...]] = []
        self.fail_delete = False

    def __call__(self, command: Sequence[str], cwd: Path) -> CommandResult:
        assert cwd == self.root
        call = tuple(command)
        self.calls.append(call)
        if call == ("git", "rev-parse", "--show-toplevel"):
            return CommandResult(0, f"{self.root}\n")
        if call == ("git", "status", "--porcelain"):
            return CommandResult(0, " M work.py\n" if self.dirty else "")
        if call == ("git", "branch", "--show-current"):
            return CommandResult(0, f"{self.current_branch}\n")
        if call[:4] == ("git", "show-ref", "--verify", "--quiet"):
            return CommandResult(0 if self.branch_exists else 1)
        if call == ("git", "for-each-ref", "--format=%(refname)", "refs/remotes"):
            remote_ref = "refs/remotes/origin/feat/p-0035-search-insert-position\n"
            return CommandResult(0, remote_ref if self.remote_branch_exists else "")
        if call[:3] == ("git", "switch", "-c"):
            self.current_branch = call[3]
            return CommandResult(0)
        if call[:2] == ("git", "switch"):
            self.current_branch = call[2]
            return CommandResult(0)
        if call[:3] == ("git", "branch", "-D"):
            return (
                CommandResult(1, stderr="delete failed") if self.fail_delete else CommandResult(0)
            )
        raise AssertionError(f"unexpected Git command: {call}")


@pytest.mark.parametrize(
    "value",
    [
        PROBLEM_URL,
        PROBLEM_URL.removesuffix("/"),
        f"{PROBLEM_URL}description/",
        f"{PROBLEM_URL}?envType=study-plan",
        f"{PROBLEM_URL}description/?envType=study-plan#code",
    ],
)
def test_canonicalizes_copied_problem_urls(value: str) -> None:
    assert canonicalize_problem_url(value) == (PROBLEM_URL, "search-insert-position")


@pytest.mark.parametrize(
    "value",
    [
        "",
        "http://leetcode.com/problems/search-insert-position/",
        "https://www.leetcode.com/problems/search-insert-position/",
        "https://leetcode.com.evil.test/problems/search-insert-position/",
        "https://leetcode.com:443/problems/search-insert-position/",
        "https://user@leetcode.com/problems/search-insert-position/",
        "https://leetcode.com/problemset/all/",
        "https://leetcode.com/problems/Search-Insert-Position/",
    ],
)
def test_rejects_non_problem_and_untrusted_urls(value: str) -> None:
    with pytest.raises(LeetError, match="URL|url"):
        canonicalize_problem_url(value)


def test_extracts_official_typescript_signature() -> None:
    source = (
        "/** starter */\nfunction searchInsert(nums: number[], target: number): number {\n\n};\n"
    )
    assert extract_typescript_signature(source) == TS_SIGNATURE


def test_extracts_and_modernizes_official_python_signature() -> None:
    source = (
        "class Solution:\n"
        "    def searchInsert(self, nums: List[List[int]], target: Optional[int]) -> int:\n"
        "\n"
    )
    assert (
        extract_python_signature(source)
        == "searchInsert(self, nums: list[list[int]], target: int | None) -> int"
    )


@pytest.mark.parametrize(
    ("extractor", "source", "message"),
    [
        (
            extract_typescript_signature,
            "class LRUCache { constructor(capacity: number) {} }",
            "ordinary function",
        ),
        (
            extract_python_signature,
            "class LRUCache:\n    def __init__(self, capacity: int):\n        pass\n",
            "ordinary Solution method",
        ),
        (
            extract_typescript_signature,
            "type Result = { value: number };\nfunction solve(): Result { return { value: 1 }; }",
            "omitted declaration",
        ),
        (
            extract_python_signature,
            "class Solution:\n    def cloneGraph(self, node: Optional[GraphNode]) -> Optional[GraphNode]:\n        pass\n",
            "unsupported judge type",
        ),
    ],
)
def test_rejects_signatures_that_cannot_be_scaffolded_safely(
    extractor: object, source: str, message: str
) -> None:
    with pytest.raises(LeetError, match=message):
        extractor(source)  # type: ignore[operator]


@pytest.mark.parametrize(
    ("language", "expected"),
    [("ts", TS_SIGNATURE), ("py", PY_SIGNATURE)],
)
def test_fetches_official_metadata_and_selected_language_signature(
    language: str, expected: str
) -> None:
    captured: dict[str, object] = {}

    def open_url(request: Request, *, timeout: int) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(graphql_document())

    result = fetch_problem_metadata(language, PROBLEM_URL, open_url=open_url)

    assert result.signature == expected
    assert result.problem_id == "0035"
    assert result.template_reason == "Official examples or judging metadata are unavailable."
    request = captured["request"]
    assert isinstance(request, Request)
    assert request.full_url == "https://leetcode.com/graphql/"
    assert request.method == "POST"
    assert json.loads(request.data or b"")["variables"] == {"titleSlug": "search-insert-position"}
    assert captured["timeout"] == 20


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"errors": [{"message": "query failed"}]}, "query failed"),
        ({"data": {"question": None}}, "not found"),
        ({"data": {"question": {"questionFrontendId": "LCP 1"}}}, "incomplete"),
        (
            {
                "data": {
                    "question": {
                        **graphql_document()["data"]["question"],  # type: ignore[index]
                        "isPaidOnly": True,
                    }
                }
            },
            "premium",
        ),
        (graphql_document(snippets=[]), "no typescript starter code"),
    ],
)
def test_reports_graphql_and_metadata_failures(document: object, message: str) -> None:
    with pytest.raises(LeetError, match=message):
        fetch_problem_metadata(
            "ts", PROBLEM_URL, open_url=lambda *_args, **_kwargs: FakeResponse(document)
        )


def test_reports_network_and_malformed_response_failures() -> None:
    def offline(*_arguments: object, **_keywords: object) -> object:
        raise URLError("offline")

    with pytest.raises(LeetError, match="offline"):
        fetch_problem_metadata("ts", PROBLEM_URL, open_url=offline)

    class MalformedResponse(FakeResponse):
        def __init__(self) -> None:
            self.body = b"not json"
            self.status = 200

    with pytest.raises(LeetError, match="malformed"):
        fetch_problem_metadata(
            "ts", PROBLEM_URL, open_url=lambda *_args, **_kwargs: MalformedResponse()
        )


def test_scaffolds_on_main(tmp_path: Path) -> None:
    git = FakeGit(tmp_path)

    result = scaffold_from_url(
        tmp_path,
        "ts",
        PROBLEM_URL,
        fetch=lambda _language, _url: metadata(),
        run=git,
    )

    assert result.branch == "main"
    assert git.current_branch == result.branch
    assert result.source_path.read_text(encoding="utf-8").startswith(
        "// LeetCode 0035: Search Insert Position."
    )
    assert f"export function {TS_SIGNATURE}" in result.source_path.read_text(encoding="utf-8")
    assert not any(call[:2] == ("git", "switch") for call in git.calls)
    assert lc.detect_problem_context(tmp_path, tmp_path, git_run=git).problem_id == "0035"


def test_scaffolds_python_with_the_normalized_official_signature(tmp_path: Path) -> None:
    git = FakeGit(tmp_path)

    result = scaffold_from_url(
        tmp_path,
        "py",
        PROBLEM_URL,
        fetch=lambda _language, _url: metadata(PY_SIGNATURE),
        run=git,
    )

    assert result.source_path.name == "p_0035_search_insert_position.py"
    assert f"def {PY_SIGNATURE}:" in result.source_path.read_text(encoding="utf-8")
    assert git.current_branch == "main"


def test_scaffolds_with_real_git_branch_checkout(tmp_path: Path) -> None:
    subprocess.run(
        ("git", "init", "-b", "main"),
        cwd=tmp_path,
        capture_output=True,
        check=True,
        text=True,
    )
    marker = tmp_path / ".gitignore"
    marker.write_text(".venv/\n", encoding="utf-8")
    subprocess.run(("git", "add", ".gitignore"), cwd=tmp_path, check=True)
    subprocess.run(
        (
            "git",
            "-c",
            "user.name=Leet Test",
            "-c",
            "user.email=lc@example.invalid",
            "commit",
            "-m",
            "test: initialize repository",
        ),
        cwd=tmp_path,
        capture_output=True,
        check=True,
        text=True,
    )

    result = scaffold_from_url(
        tmp_path,
        "ts",
        PROBLEM_URL,
        fetch=lambda _language, _url: metadata(),
    )

    current = subprocess.run(
        ("git", "branch", "--show-current"),
        cwd=tmp_path,
        capture_output=True,
        check=True,
        text=True,
    )
    assert current.stdout.strip() == result.branch
    assert result.source_path.is_file()


def test_start_preserves_unrelated_work(tmp_path: Path) -> None:
    git = FakeGit(tmp_path, dirty=True)
    unrelated = tmp_path / "notes.txt"
    unrelated.write_text("keep me")
    result = scaffold_from_url(tmp_path, "ts", PROBLEM_URL, fetch=lambda *_: metadata(), run=git)
    assert result.source_path.is_file()
    assert unrelated.read_text() == "keep me"
    assert git.current_branch == "main"


@pytest.mark.parametrize("branch", ["feature/example", ""])
def test_start_requires_main_before_fetch(tmp_path: Path, branch: str) -> None:
    git = FakeGit(tmp_path)
    git.current_branch = branch
    with pytest.raises(LeetError, match="main"):
        scaffold_from_url(
            tmp_path, "ts", PROBLEM_URL, fetch=lambda *_: pytest.fail("must not fetch"), run=git
        )


def test_branch_is_rechecked_after_fetch(tmp_path: Path) -> None:
    git = FakeGit(tmp_path)

    def fetch(*_):
        git.current_branch = "another"
        return metadata()

    with pytest.raises(LeetError, match="main"):
        scaffold_from_url(tmp_path, "ts", PROBLEM_URL, fetch=fetch, run=git)
    assert not (tmp_path / "src").exists()


def test_reopens_offline_without_overwriting_source_or_tests(tmp_path: Path) -> None:
    git = FakeGit(tmp_path)
    first = scaffold_from_url(tmp_path, "ts", PROBLEM_URL, fetch=lambda *_: metadata(), run=git)
    first.source_path.write_text(first.source_path.read_text() + "// my solution\n")
    first.test_path.write_text("// my tests\n")
    original = first.source_path.read_text()
    reopened = scaffold_from_url(
        tmp_path,
        "ts",
        PROBLEM_URL,
        fetch=lambda *_: pytest.fail("offline reopen should not fetch"),
        run=git,
    )
    assert reopened.reopened
    assert first.source_path.read_text() == original
    assert first.test_path.read_text() == "// my tests\n"


def test_reopens_remembered_legacy_source_without_fetch(tmp_path: Path) -> None:
    git = FakeGit(tmp_path)
    first = scaffold_from_url(tmp_path, "ts", PROBLEM_URL, fetch=lambda *_: metadata(), run=git)
    first.source_path.write_text("// legacy source without a URL\n")
    reopened = scaffold_from_url(tmp_path, "ts", PROBLEM_URL, fetch=lambda *_: metadata(), run=git)
    assert reopened.reopened
    assert first.source_path.read_text() == "// legacy source without a URL\n"


def test_scaffold_failure_leaves_branch_alone(tmp_path: Path) -> None:
    git = FakeGit(tmp_path)

    def fail(*_args, **_kwargs):
        raise OSError("disk full")

    with pytest.raises(LeetError, match="disk full"):
        scaffold_from_url(
            tmp_path, "ts", PROBLEM_URL, fetch=lambda *_: metadata(), run=git, creator=fail
        )
    assert git.current_branch == "main"
    assert not any(call[:2] == ("git", "switch") for call in git.calls)


def test_parses_concise_command_and_prints_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert parse_arguments(["ts", PROBLEM_URL]) == ("ts", PROBLEM_URL)
    assert parse_arguments(["py", PROBLEM_URL]) == ("py", PROBLEM_URL)
    assert parse_arguments([PROBLEM_URL]) == ("ts", PROBLEM_URL)
    with pytest.raises(LeetError, match="language"):
        parse_arguments(["rust", PROBLEM_URL])
    with pytest.raises(LeetError, match="usage"):
        parse_arguments([])
    with pytest.raises(LeetError, match="usage"):
        parse_arguments(["py"])

    source = tmp_path / "src/typescript/p_0035_search_insert_position/x.ts"
    test = source.with_suffix(".test.ts")
    monkeypatch.setattr(lc, "__file__", str(tmp_path / "scripts" / "lc.py"))
    monkeypatch.setattr(
        lc,
        "scaffold_from_url",
        lambda *_arguments: ScaffoldResult(
            metadata(), source, test, "feat/p-0035-search-insert-position"
        ),
    )

    assert lc.main(["ts", PROBLEM_URL]) == 0
    output = capsys.readouterr().out
    assert "Signature: searchInsert" in output
    assert "lc test" in output
    assert "lc live" in output
    assert "lc done" in output


def test_help_prints_usage_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    assert lc.main(["--help"]) == 0
    output = capsys.readouterr().out
    assert output.startswith("lc — the local LeetCode workflow\n")
    assert "lc URL" in output
    assert "lc test" in output
    assert "lc done" in output
