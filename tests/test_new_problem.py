import subprocess
import sys
from pathlib import Path

import pytest

from scripts import new_problem
from scripts.new_problem import (
    ScaffoldError,
    create_problem,
    normalize_problem_id,
    parse_arguments,
    slugify,
    suggested_branch,
    validate_problem_url,
)


def test_normalization_helpers() -> None:
    assert normalize_problem_id("1512.") == "1512"
    assert normalize_problem_id("8") == "0008"
    assert slugify("Caf\u00e9 & Cr\u00e8me++") == "cafe_creme"
    assert suggested_branch("1512", "number_of_good_pairs") == "feat/p-1512-number-of-good-pairs"


@pytest.mark.parametrize("value", ["", "0", "-1", "12.3", "one", "9" * 5000])
def test_rejects_invalid_problem_numbers(value: str) -> None:
    with pytest.raises(ScaffoldError, match="positive integer"):
        normalize_problem_id(value)


def test_creates_python_layout_and_skipped_test(tmp_path: Path) -> None:
    source, test, branch = create_problem(
        tmp_path, "py", "1512.", ["Number", "of", "Good", "Pairs"]
    )

    assert (
        source == tmp_path / "src/python/p_1512_number_of_good_pairs/p_1512_number_of_good_pairs.py"
    )
    assert test == source.with_name("test_p_1512_number_of_good_pairs.py")
    assert "class Solution:" in source.read_text(encoding="utf-8")
    assert "# Problem: Number of Good Pairs" in source.read_text(encoding="utf-8")
    assert "# TODO: add problem URL" in source.read_text(encoding="utf-8")
    assert "@pytest.mark.skip" in test.read_text(encoding="utf-8")
    compile(source.read_text(encoding="utf-8"), str(source), "exec")
    compile(test.read_text(encoding="utf-8"), str(test), "exec")
    assert branch == "feat/p-1512-number-of-good-pairs"


def test_python_problem_title_uses_a_ruff_compatible_string_literal(tmp_path: Path) -> None:
    title = 'Bob\'s "quoted" \\ challenge'
    source, _, _ = create_problem(tmp_path, "py", "42", [title])

    contents = source.read_text(encoding="utf-8")
    assert 'PROBLEM_TITLE = """' in contents
    namespace: dict[str, object] = {}
    exec(contents, namespace)
    assert namespace["PROBLEM_TITLE"] == title

    executable = "ruff.exe" if sys.platform == "win32" else "ruff"
    ruff = Path(sys.executable).with_name(executable)
    result = subprocess.run(
        [str(ruff), "format", "--no-cache", "--check", str(source)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_creates_typescript_layout(tmp_path: Path) -> None:
    source, test, _ = create_problem(tmp_path, "ts", "92", ["Reverse", "Linked", "List", "II"])

    assert source.name == "p_0092_reverse_linked_list_ii.ts"
    assert test.name == "p_0092_reverse_linked_list_ii.test.ts"
    assert 'from "./p_0092_reverse_linked_list_ii.js"' in test.read_text(encoding="utf-8")
    assert "test.skip" in test.read_text(encoding="utf-8")


def test_preserves_display_title_and_url_metadata(tmp_path: Path) -> None:
    source, _, _ = create_problem(
        tmp_path,
        "ts",
        "1",
        ["Two   Sum:", "A / B */\nChallenge!"],
        "https://leetcode.com/problems/two-sum/",
    )

    contents = source.read_text(encoding="utf-8")
    assert "// LeetCode 0001: Two Sum: A / B */ Challenge!." in contents
    assert "// Problem URL: https://leetcode.com/problems/two-sum/" in contents
    assert source.parent.name == "p_0001_two_sum_a_b_challenge"


@pytest.mark.parametrize(
    "url",
    [
        "http://leetcode.com/problems/two-sum/",
        "https://www.leetcode.com/problems/two-sum/",
        "https://leetcode.com/problems/two-sum",
        "https://leetcode.com/problems/two-sum/?foo=bar",
        "https://leetcode.com/problemset/all/",
    ],
)
def test_rejects_noncanonical_problem_urls(url: str) -> None:
    with pytest.raises(ScaffoldError, match="canonical"):
        validate_problem_url(url)


def test_parses_url_after_title() -> None:
    assert parse_arguments(
        [
            "py",
            "1512",
            "Number of Good Pairs",
            "--url",
            "https://leetcode.com/problems/number-of-good-pairs/",
        ]
    ) == (
        "py",
        "1512",
        ["Number of Good Pairs"],
        "https://leetcode.com/problems/number-of-good-pairs/",
    )


def test_main_prints_focused_test_and_ready_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(new_problem, "__file__", str(tmp_path / "scripts" / "new_problem.py"))

    assert new_problem.main(["py", "8", "String to Integer (atoi)"]) == 0

    output = capsys.readouterr().out
    assert (
        "pnpm test:py src/python/p_0008_string_to_integer_atoi/test_p_0008_string_to_integer_atoi.py"
        in output
    )
    assert "pnpm ready" in output


def test_rejects_collisions_without_overwriting(tmp_path: Path) -> None:
    source, _, _ = create_problem(tmp_path, "py", "1", ["Two", "Sum"])

    with pytest.raises(ScaffoldError, match="target already exists"):
        create_problem(tmp_path, "py", "1", ["Two", "Sum"])
    assert "class Solution:" in source.read_text(encoding="utf-8")
