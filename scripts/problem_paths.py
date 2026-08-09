"""Resolve a solution's conventional directory and file paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ProblemPathError(ValueError):
    """Raised when a problem cannot be resolved unambiguously."""


@dataclass(frozen=True)
class ProblemPaths:
    """The conventional paths associated with one problem implementation."""

    language: str
    problem_id: str
    directory: Path

    @property
    def stem(self) -> str:
        """Return the shared solution/test filename stem."""
        return self.directory.name

    @property
    def source_path(self) -> Path:
        """Return the implementation source path."""
        extension = "py" if self.language == "py" else "ts"
        return self.directory / f"{self.stem}.{extension}"

    @property
    def test_path(self) -> Path:
        """Return the canonical colocated test path."""
        if self.language == "py":
            return self.directory / f"test_{self.stem}.py"
        return self.directory / f"{self.stem}.test.ts"

    @property
    def test_candidates(self) -> tuple[Path, ...]:
        """Return canonical and, where applicable, legacy test-name candidates."""
        if self.language != "py":
            return (self.test_path,)
        legacy_test = self.directory / f"test_{self.stem.removeprefix('p_')}.py"
        return (self.test_path, legacy_test)


def normalize_problem_id(value: str) -> str:
    """Return a positive numeric problem ID padded to at least four digits."""
    number = value.strip().removesuffix(".")
    if not number.isdecimal():
        raise ProblemPathError("problem ID must be a positive integer")
    try:
        problem_id = int(number)
    except ValueError as error:
        raise ProblemPathError("problem ID must be a positive integer") from error
    if problem_id <= 0:
        raise ProblemPathError("problem ID must be a positive integer")
    return f"{problem_id:04d}"


def language_directory(root: Path, language: str) -> Path:
    """Return the solutions directory for a supported language."""
    directories = {"py": "python", "ts": "typescript"}
    try:
        return root / "src" / directories[language]
    except KeyError as error:
        raise ProblemPathError("language must be 'py' or 'ts'") from error


def resolve_problem_paths(root: Path, language: str, problem_number: str) -> ProblemPaths:
    """Resolve exactly one canonical or legacy problem directory for an ID and language."""
    problem_id = normalize_problem_id(problem_number)
    solutions_directory = language_directory(root, language)
    legacy_problem_id = str(int(problem_id))
    directory_ids = {problem_id, legacy_problem_id}
    matches = sorted(
        path
        for directory_id in directory_ids
        for path in solutions_directory.glob(f"p_{directory_id}_*")
        if path.is_dir()
    )
    if not matches:
        raise ProblemPathError(f"no {language} problem directory found for ID {problem_id}")
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise ProblemPathError(
            f"multiple {language} problem directories found for ID {problem_id}: {names}"
        )
    return ProblemPaths(language=language, problem_id=problem_id, directory=matches[0])


def require_source_path(paths: ProblemPaths) -> Path:
    """Return an existing implementation source path or raise a clear error."""
    if not paths.source_path.is_file():
        raise ProblemPathError(f"solution source is missing: {paths.source_path}")
    return paths.source_path


def require_test_path(paths: ProblemPaths) -> Path:
    """Return one existing colocated test path or raise a clear error."""
    matches = [path for path in paths.test_candidates if path.is_file()]
    if not matches:
        candidates = ", ".join(str(path) for path in paths.test_candidates)
        raise ProblemPathError(f"solution test is missing; expected one of: {candidates}")
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise ProblemPathError(f"multiple solution tests found; choose one convention: {names}")
    return matches[0]
