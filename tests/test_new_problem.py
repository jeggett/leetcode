import subprocess
import sys
from pathlib import Path

import pytest

from scripts import new_problem
from scripts.check_incomplete import (
    GENERATED_TEST_SENTINEL,
    IMPLEMENTATION_MARKER,
    TEST_MARKER,
    incomplete_scaffolds,
)
from scripts.new_problem import (
    ScaffoldError,
    create_problem,
    normalize_problem_id,
    parse_arguments,
    slugify,
    suggested_branch,
    validate_signature,
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


def test_python_problem_title_is_comment_only_and_handles_triple_quotes(tmp_path: Path) -> None:
    title = 'Bob\'s """quoted""" \\ challenge'
    source, _, _ = create_problem(tmp_path, "py", "42", [title])

    contents = source.read_text(encoding="utf-8")
    assert "PROBLEM_TITLE" not in contents
    assert f"# Problem: {title}" in contents
    compile(contents, str(source), "exec")

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


def test_creates_signature_aware_typescript_scaffold(tmp_path: Path) -> None:
    source, test, _ = create_problem(
        tmp_path,
        "ts",
        "1512",
        ["Number of Good Pairs"],
        signature="numIdenticalPairs(nums: number[]): number",
    )

    assert "export function numIdenticalPairs(nums: number[]): number {" in source.read_text(
        encoding="utf-8"
    )
    test_contents = test.read_text(encoding="utf-8")
    assert "test.skip.each(cases)" in test_contents
    assert 'name: "TODO: add examples and edge cases"' in test_contents
    assert "numIdenticalPairs(...args)" in test_contents


def test_generated_generic_typescript_signature_typechecks(tmp_path: Path) -> None:
    source, test, _ = create_problem(
        tmp_path,
        "ts",
        "1",
        ["Identity"],
        signature="identity<T>(value: T): T",
    )

    result = subprocess.run(
        [
            "pnpm",
            "exec",
            "tsc",
            "--ignoreConfig",
            "--noEmit",
            "--strict",
            "--target",
            "es2024",
            "--module",
            "esnext",
            "--moduleResolution",
            "bundler",
            "--types",
            "vitest/globals",
            str(source),
            str(test),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_creates_signature_aware_python_scaffold(tmp_path: Path) -> None:
    source, test, _ = create_problem(
        tmp_path,
        "py",
        "1512",
        ["Number of Good Pairs"],
        signature="numIdenticalPairs(self, nums: list[int]) -> int",
    )

    contents = source.read_text(encoding="utf-8")
    assert "def numIdenticalPairs(self, nums: list[int]) -> int:" in contents
    assert "raise NotImplementedError" in contents
    assert "@pytest.mark.parametrize" in test.read_text(encoding="utf-8")
    compile(contents, str(source), "exec")


def test_generated_scaffolds_are_detected_as_incomplete(tmp_path: Path) -> None:
    python_source, python_test, _ = create_problem(
        tmp_path,
        "py",
        "1",
        ["Two Sum"],
        signature="twoSum(self, nums: list[int], target: int) -> list[int]",
    )
    typescript_source, typescript_test, _ = create_problem(
        tmp_path,
        "ts",
        "1",
        ["Two Sum"],
        signature="twoSum(nums: number[], target: number): number[]",
    )

    assert incomplete_scaffolds(tmp_path) == [
        (python_source.relative_to(tmp_path), IMPLEMENTATION_MARKER),
        (python_test.relative_to(tmp_path), TEST_MARKER),
        (typescript_test.relative_to(tmp_path), TEST_MARKER),
        (typescript_source.relative_to(tmp_path), IMPLEMENTATION_MARKER),
    ]
    assert GENERATED_TEST_SENTINEL in python_test.read_text(encoding="utf-8")
    assert GENERATED_TEST_SENTINEL in typescript_test.read_text(encoding="utf-8")


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
        None,
    )


def test_parses_signature_after_title() -> None:
    assert parse_arguments(
        [
            "ts",
            "1512",
            "Number of Good Pairs",
            "--signature",
            "numIdenticalPairs(nums: number[]): number",
        ]
    ) == (
        "ts",
        "1512",
        ["Number of Good Pairs"],
        None,
        "numIdenticalPairs(nums: number[]): number",
    )


@pytest.mark.parametrize(
    ("language", "signature", "name"),
    [
        ("ts", "numIdenticalPairs(nums: number[]): number", "numIdenticalPairs"),
        ("ts", "identity<T>(value: T): T", "identity"),
        ("py", "numIdenticalPairs(self, nums: list[int]) -> int", "numIdenticalPairs"),
    ],
)
def test_extracts_signature_callable_name(language: str, signature: str, name: str) -> None:
    assert validate_signature(language, signature) == (signature, name)


@pytest.mark.parametrize(
    ("language", "signature"),
    [
        ("ts", "123invalid(): void"),
        ("ts", "method(args)"),
        ("ts", "method(): void\nother(): void"),
        ("ts", "method(): void\u2028other(): void"),
        ("ts", "class(): void"),
        ("ts", "method<T(value: T): T"),
        ("ts", "method(): void {"),
        ("ts", "method(): void; process.exit()"),
        ("ts", "method(): void // comment"),
        ("ts", "method(): void => value"),
        ("ts", "method(): :"),
        ("ts", "method(): void)"),
        ("py", "class(self) -> int"),
        ("py", "method(value: int) -> int"),
        ("py", "method(self)"),
        ("py", "method(self) -> int\npass"),
        ("py", "method(self) -> int\u2028pass"),
        ("py", "method(self) -> int:"),
        ("py", "method(self) -> int # comment"),
        ("py", "method(self) -> int; pass"),
        ("py", "method(self) -> int)"),
    ],
)
def test_rejects_malformed_signatures(language: str, signature: str) -> None:
    with pytest.raises(ScaffoldError, match="signature"):
        validate_signature(language, signature)


def test_main_prints_short_focused_test_and_ready_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(new_problem, "__file__", str(tmp_path / "scripts" / "new_problem.py"))

    assert new_problem.main(["py", "8", "String to Integer (atoi)"]) == 0

    output = capsys.readouterr().out
    assert "pnpm test:one py 0008" in output
    assert "pnpm ready" in output


def test_main_prints_typescript_watch_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(new_problem, "__file__", str(tmp_path / "scripts" / "new_problem.py"))

    assert new_problem.main(["ts", "8", "String to Integer (atoi)"]) == 0

    output = capsys.readouterr().out
    assert "pnpm test:one ts 0008" in output
    assert "pnpm test:one ts 0008 --watch" in output


def test_usage_mentions_signature_option() -> None:
    with pytest.raises(ScaffoldError, match=r"--signature SIGNATURE"):
        parse_arguments([])


def test_rejects_collisions_without_overwriting(tmp_path: Path) -> None:
    source, _, _ = create_problem(tmp_path, "py", "1", ["Two", "Sum"])

    with pytest.raises(ScaffoldError, match="problem ID already exists"):
        create_problem(tmp_path, "py", "1", ["Two", "Sum"])
    assert "class Solution:" in source.read_text(encoding="utf-8")


def test_rejects_duplicate_problem_ids_with_a_different_slug(tmp_path: Path) -> None:
    create_problem(tmp_path, "py", "1", ["Two", "Sum"])

    with pytest.raises(ScaffoldError, match="problem ID already exists"):
        create_problem(tmp_path, "py", "1", ["A", "Different", "Title"])


def test_rejects_legacy_unpadded_problem_id_directory(tmp_path: Path) -> None:
    legacy_directory = tmp_path / "src/typescript/p_457_circular_array_loop"
    legacy_directory.mkdir(parents=True)

    with pytest.raises(ScaffoldError, match="problem ID already exists"):
        create_problem(tmp_path, "ts", "457", ["Circular Array Loop"])
