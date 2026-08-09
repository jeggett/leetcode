from pathlib import Path

from pytest import CaptureFixture

from scripts.check_incomplete import incomplete_scaffolds, main


IMPLEMENTATION_MARKER = "TODO: implement the solution"
TEST_MARKER = "TODO: add examples and edge cases"
COMPLEXITY_MARKER = "time: TODO, space: TODO"
GENERATED_TEST_SENTINEL = "GENERATED_SCAFFOLD_TEST"


def write_source(root: Path, relative_path: str, content: str) -> None:
    """Create a source file beneath a temporary repository root."""
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_returns_no_matches_for_completed_sources_and_unrelated_todos(tmp_path: Path) -> None:
    write_source(tmp_path, "src/python/p_0001.py", "# TODO: explain this later\n")
    write_source(tmp_path, "src/typescript/p_0002.ts", "// TODO: optimize\n")

    assert incomplete_scaffolds(tmp_path) == []


def test_reports_each_matching_source_file_and_marker(tmp_path: Path) -> None:
    write_source(tmp_path, "src/python/p_0001.py", f'"""{IMPLEMENTATION_MARKER}."""\n')
    write_source(tmp_path, "src/typescript/p_0002.test.ts", f"// {TEST_MARKER}\n")

    assert incomplete_scaffolds(tmp_path) == [
        (Path("src/python/p_0001.py"), IMPLEMENTATION_MARKER),
        (Path("src/typescript/p_0002.test.ts"), TEST_MARKER),
    ]


def test_reports_multiple_markers_in_one_file(tmp_path: Path) -> None:
    write_source(
        tmp_path,
        "src/python/p_0001.py",
        f"# {TEST_MARKER}\n# {IMPLEMENTATION_MARKER}\n",
    )

    assert incomplete_scaffolds(tmp_path) == [
        (Path("src/python/p_0001.py"), IMPLEMENTATION_MARKER),
        (Path("src/python/p_0001.py"), TEST_MARKER),
    ]


def test_reports_typescript_complexity_placeholder(tmp_path: Path) -> None:
    write_source(
        tmp_path,
        "src/typescript/p_0001/p_0001.ts",
        "/* time:TODO , space:  TODO */\nexport function p0001(): void {}\n",
    )

    assert incomplete_scaffolds(tmp_path) == [
        (Path("src/typescript/p_0001/p_0001.ts"), COMPLEXITY_MARKER),
    ]


def test_reports_generated_scaffold_sentinel_with_changed_reason(tmp_path: Path) -> None:
    write_source(
        tmp_path,
        "src/python/p_0001/test_p_0001.py",
        f'# {GENERATED_TEST_SENTINEL}\n@pytest.mark.skip(reason="renamed")\ndef test_p_0001() -> None:\n    pass\n',
    )
    write_source(
        tmp_path,
        "src/typescript/p_0002/p_0002.test.ts",
        f'// {GENERATED_TEST_SENTINEL}\ntest.skip("renamed", () => {{}});\n',
    )

    assert incomplete_scaffolds(tmp_path) == [
        (Path("src/python/p_0001/test_p_0001.py"), GENERATED_TEST_SENTINEL),
        (Path("src/typescript/p_0002/p_0002.test.ts"), GENERATED_TEST_SENTINEL),
    ]


def test_detects_only_anchored_sentinels_in_conventional_test_files(tmp_path: Path) -> None:
    write_source(
        tmp_path,
        "src/python/p_0001/p_0001.py",
        f"# {GENERATED_TEST_SENTINEL}\n",
    )
    write_source(
        tmp_path,
        "src/python/p_0001/test_p_0001.py",
        f'# {GENERATED_TEST_SENTINEL} trailing\nvalue = "{GENERATED_TEST_SENTINEL}"\n',
    )
    write_source(
        tmp_path,
        "src/typescript/p_0002/p_0002.test.ts",
        f"// {GENERATED_TEST_SENTINEL}\n",
    )

    assert incomplete_scaffolds(tmp_path) == [
        (Path("src/typescript/p_0002/p_0002.test.ts"), GENERATED_TEST_SENTINEL),
    ]


def test_exact_test_marker_takes_priority_over_generated_sentinel(tmp_path: Path) -> None:
    write_source(
        tmp_path,
        "src/python/p_0001/test_p_0001.py",
        f"# {GENERATED_TEST_SENTINEL}\n# {TEST_MARKER}\n",
    )

    assert incomplete_scaffolds(tmp_path) == [
        (Path("src/python/p_0001/test_p_0001.py"), TEST_MARKER),
    ]


def test_does_not_treat_non_generated_skips_as_scaffolds(tmp_path: Path) -> None:
    write_source(
        tmp_path,
        "src/python/p_0001/test_p_0001.py",
        '@pytest.mark.skip(reason="platform")\ndef test_p_0001() -> None:\n    pass\n',
    )
    write_source(
        tmp_path,
        "src/typescript/p_0002/p_0002.test.ts",
        'test.skip("platform", () => {});\n',
    )

    assert incomplete_scaffolds(tmp_path) == []


def test_reports_python_complexity_placeholder(tmp_path: Path) -> None:
    write_source(
        tmp_path,
        "src/python/p_0001/p_0001.py",
        f"# {COMPLEXITY_MARKER}\nclass Solution:\n    pass\n",
    )

    assert incomplete_scaffolds(tmp_path) == [
        (Path("src/python/p_0001/p_0001.py"), COMPLEXITY_MARKER),
    ]


def test_missing_source_directories_are_clean(tmp_path: Path) -> None:
    assert incomplete_scaffolds(tmp_path) == []


def test_main_returns_status_and_prints_matches(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    write_source(tmp_path, "src/python/p_0001.py", f"# {IMPLEMENTATION_MARKER}\n")

    assert main([str(tmp_path)]) == 1
    assert capsys.readouterr().out == f"src/python/p_0001.py: {IMPLEMENTATION_MARKER}\n"
    assert main([str(tmp_path / "missing")]) == 0
