"""Read the small repository-local configuration shared by workflow commands."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Raised when ``lc.toml`` contains unsafe or unsupported values."""


@dataclass(frozen=True)
class LcConfig:
    """Stable user preferences for repository and interview-practice behavior."""

    base_branch: str = "main"
    primary_language: str = "ts"
    default_minutes: int = 35
    history_directory: str = ".lc"


def load_config(root: Path) -> LcConfig:
    """Load ``lc.toml`` or return comfortable defaults when it is absent."""
    path = root / "lc.toml"
    if not path.is_file():
        return LcConfig()
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"could not read {path}: {error}") from error

    repository = document.get("repository", {})
    practice = document.get("practice", {})
    if not isinstance(repository, dict) or not isinstance(practice, dict):
        raise ConfigError("lc.toml repository and practice sections must be tables")
    base_branch = repository.get("base_branch", "main")
    primary_language = practice.get("primary_language", "ts")
    default_minutes = practice.get("default_minutes", 35)
    history_directory = practice.get("history_directory", ".lc")
    if not isinstance(base_branch, str) or not base_branch or base_branch.startswith("-"):
        raise ConfigError("repository.base_branch must be a branch name")
    if primary_language not in {"py", "ts"}:
        raise ConfigError("practice.primary_language must be 'py' or 'ts'")
    if (
        not isinstance(default_minutes, int)
        or isinstance(default_minutes, bool)
        or default_minutes <= 0
    ):
        raise ConfigError("practice.default_minutes must be a positive integer")
    if (
        not isinstance(history_directory, str)
        or not history_directory
        or Path(history_directory).is_absolute()
        or ".." in Path(history_directory).parts
        or not Path(history_directory).parts
        or Path(history_directory).parts[0] != ".lc"
    ):
        raise ConfigError("practice.history_directory must stay under the ignored .lc directory")
    try:
        (root / history_directory).resolve().relative_to(root.resolve())
    except (OSError, ValueError) as error:
        raise ConfigError("practice.history_directory must not escape through a symlink") from error
    return LcConfig(base_branch, primary_language, default_minutes, history_directory)
