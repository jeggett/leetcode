from pathlib import Path

import pytest

from scripts.problem_paths import (
    ProblemPathError,
    normalize_problem_id,
    matching_problem_directories,
    require_source_path,
    require_test_path,
    resolve_problem_paths,
)


def make_problem(root: Path, language: str, problem_id: str, slug: str) -> Path:
    directory = root / "src" / ("python" if language == "py" else "typescript")
    directory /= f"p_{problem_id}_{slug}"
    directory.mkdir(parents=True)
    stem = directory.name
    source = directory / f"{stem}.{'py' if language == 'py' else 'ts'}"
    test = directory / (f"test_{stem}.py" if language == "py" else f"{stem}.test.ts")
    source.write_text("solution", encoding="utf-8")
    test.write_text("test", encoding="utf-8")
    return directory


def test_resolves_one_zero_padded_problem_directory(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "py", "0092", "reverse_linked_list_ii")

    paths = resolve_problem_paths(tmp_path, "py", "92.")

    assert paths.problem_id == "0092"
    assert paths.directory == directory
    assert paths.source_path == directory / "p_0092_reverse_linked_list_ii.py"
    assert paths.test_path == directory / "test_p_0092_reverse_linked_list_ii.py"
    assert require_source_path(paths).is_file()
    assert require_test_path(paths).is_file()


@pytest.mark.parametrize("value", ["", "0", "-2", "a", "12.3", "9" * 5000])
def test_normalize_problem_id_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ProblemPathError, match="positive integer"):
        normalize_problem_id(value)


def test_rejects_unknown_language_and_missing_problem(tmp_path: Path) -> None:
    with pytest.raises(ProblemPathError, match="language"):
        resolve_problem_paths(tmp_path, "go", "1")
    with pytest.raises(ProblemPathError, match="no ts problem directory found for ID 0001"):
        resolve_problem_paths(tmp_path, "ts", "1")


def test_rejects_ambiguous_problem_directories(tmp_path: Path) -> None:
    make_problem(tmp_path, "ts", "0001", "two_sum")
    make_problem(tmp_path, "ts", "0001", "another_two_sum")

    with pytest.raises(ProblemPathError, match="multiple ts problem directories"):
        resolve_problem_paths(tmp_path, "ts", "1")


def test_requires_the_conventional_source_and_test_files(tmp_path: Path) -> None:
    directory = tmp_path / "src/python/p_0001_two_sum"
    directory.mkdir(parents=True)
    paths = resolve_problem_paths(tmp_path, "py", "1")

    with pytest.raises(ProblemPathError, match="solution source is missing"):
        require_source_path(paths)
    with pytest.raises(ProblemPathError, match="solution test is missing"):
        require_test_path(paths)


@pytest.mark.parametrize("language", ["py", "ts"])
def test_scaffolding_and_lookup_share_the_canonical_layout(tmp_path: Path, language: str) -> None:
    from scripts.new_problem import create_problem

    source, test, _ = create_problem(tmp_path, language, "00001", ["Two Sum"])
    paths = resolve_problem_paths(tmp_path, language, "1")
    assert paths.problem_id == "0001"
    assert require_source_path(paths) == source
    assert require_test_path(paths) == test
    assert matching_problem_directories(paths.directory.parent, "0001") == [paths.directory]
