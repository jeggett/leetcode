from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request

import pytest

from scripts import lc
from scripts.lc import (
    LeetError,
    ProblemMetadata,
    ScaffoldResult,
    canonicalize_problem_url,
    extract_python_signature,
    extract_typescript_signature,
    fetch_problem_metadata,
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
            "class Solution:\n    def reverseList(self, head: Optional[ListNode]) -> Optional[ListNode]:\n        pass\n",
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

    assert result == metadata(expected)
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


@pytest.mark.parametrize("language, signature", [("ts", TS_SIGNATURE), ("py", PY_SIGNATURE)])
def test_url_scaffold_works_without_a_git_repository(
    tmp_path: Path, language: str, signature: str
) -> None:
    result = scaffold_from_url(
        tmp_path, language, PROBLEM_URL, fetch=lambda *_: metadata(signature)
    )
    assert result.source_path.is_file()
    assert result.test_path.is_file()
    assert signature in result.source_path.read_text()
    assert not (tmp_path / ".git").exists()
    with pytest.raises(LeetError, match="problem ID already exists"):
        scaffold_from_url(tmp_path, language, PROBLEM_URL, fetch=lambda *_: metadata(signature))


def test_url_scaffold_preserves_the_branch_and_uncommitted_files(tmp_path: Path) -> None:
    subprocess.run(
        ["git", "init", "--initial-branch=practice", str(tmp_path)], check=True, capture_output=True
    )
    note = tmp_path / "notes.txt"
    note.write_text("work in progress")
    scaffold_from_url(tmp_path, "ts", PROBLEM_URL, fetch=lambda *_: metadata())
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert branch.stdout.strip() == "practice"
    assert note.read_text() == "work in progress"


def test_parses_concise_command_and_prints_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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
    assert "Suggested branch: feat/p-0035-search-insert-position" in output
    assert "lc test" in output
    assert "lc watch" in output
    assert "lc ready" in output


def test_help_prints_usage_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    assert lc.main(["--help"]) == 0
    output = capsys.readouterr().out
    assert output.startswith("lc — the local LeetCode workflow\n")
    assert "lc URL" in output
    assert "lc test" in output
    assert "lc ready" in output


@pytest.mark.parametrize(
    "signature",
    [
        "solve(value: { n: number }, fn: (n: number) => number): { n: number }",
        'solve(value: "a  b"): "a  b"',
    ],
)
def test_extracts_typescript_headers_without_confusing_type_braces(signature: str) -> None:
    assert extract_typescript_signature(f"function {signature} {{}}") == signature
