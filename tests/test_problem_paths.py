from pathlib import Path

import pytest

from scripts.problem_paths import (
    ProblemPathError,
    normalize_problem_id,
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


def test_resolves_an_unpadded_legacy_problem_directory_with_a_normalized_id(tmp_path: Path) -> None:
    directory = make_problem(tmp_path, "ts", "457", "circular_array_loop")

    paths = resolve_problem_paths(tmp_path, "ts", "457")

    assert paths.problem_id == "0457"
    assert paths.directory == directory
    assert require_source_path(paths) == directory / "p_457_circular_array_loop.ts"
    assert require_test_path(paths) == directory / "p_457_circular_array_loop.test.ts"


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


def test_rejects_canonical_and_legacy_problem_directory_ambiguity(tmp_path: Path) -> None:
    make_problem(tmp_path, "ts", "0457", "circular_array_loop")
    make_problem(tmp_path, "ts", "457", "circular_array_loop_legacy")

    with pytest.raises(ProblemPathError, match="multiple ts problem directories"):
        resolve_problem_paths(tmp_path, "ts", "457")


def test_requires_the_conventional_source_and_test_files(tmp_path: Path) -> None:
    directory = tmp_path / "src/python/p_0001_two_sum"
    directory.mkdir(parents=True)
    paths = resolve_problem_paths(tmp_path, "py", "1")

    with pytest.raises(ProblemPathError, match="solution source is missing"):
        require_source_path(paths)
    with pytest.raises(ProblemPathError, match="solution test is missing"):
        require_test_path(paths)


def test_resolves_one_existing_legacy_python_test_name(tmp_path: Path) -> None:
    directory = tmp_path / "src/python/p_1512_number_of_good_pairs"
    directory.mkdir(parents=True)
    (directory / "p_1512_number_of_good_pairs.py").write_text("solution", encoding="utf-8")
    legacy_test = directory / "test_1512_number_of_good_pairs.py"
    legacy_test.write_text("test", encoding="utf-8")

    paths = resolve_problem_paths(tmp_path, "py", "1512")

    assert require_test_path(paths) == legacy_test


def test_rejects_multiple_python_test_naming_conventions(tmp_path: Path) -> None:
    make_problem(tmp_path, "py", "0001", "two_sum")
    directory = tmp_path / "src/python/p_0001_two_sum"
    (directory / "test_0001_two_sum.py").write_text("test", encoding="utf-8")

    with pytest.raises(ProblemPathError, match="multiple solution tests"):
        require_test_path(resolve_problem_paths(tmp_path, "py", "1"))
