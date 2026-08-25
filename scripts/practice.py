#!/usr/bin/env python3
"""Interview practice scheduling for the local LeetCode workspace.

The module intentionally has no third-party dependencies.  Problems are discovered from the
repository's conventional ``src/{typescript,python}/p_####_*`` directories.  Optional metadata can
be placed in a problem directory as ``problem.toml``::

    title = "Two Sum"
    pattern = "hash-map"
    difficulty = "easy"
    target_minutes = 20
    signature = "twoSum(nums: number[], target: number): number[]"

Metadata may also be nested under a ``[problem]`` table.  The optional
``tracks/interview-core.toml`` file uses the same fields in ``[[problems]]`` entries and fills in
missing per-problem metadata.  A problem-local file always wins over the track manifest.

Practice state is deliberately separate from solutions. Finishing a session appends one JSON
object to ``.lc/practice-history.jsonl`` and removes ``.lc/practice-active.json``.

The review schedule is intentionally simple and documented here.  The interval is measured from
the finish time:

* ``solved``: confidence 1/2/3/4 -> 0/1/3/7 days; repeated confidence-4 solves expand
  through 14, 30, and 60 days;
* ``hinted``: confidence 1/2/3/4 -> 0/1/2/3 days;
* ``failed``: confidence 1/2/3/4 -> 0/0/0/1 days.

``today`` selects due problems first and then unseen problems.  Selection is deterministic (due
time, target time, and problem ID), which makes it suitable for both the ``lc`` dispatcher and
tests.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import re
import statistics
import sys
import tomllib
import uuid
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from scripts.config import ConfigError, load_config
except ModuleNotFoundError:
    from config import ConfigError, load_config


STATE_DIRECTORY_NAME = ".lc"
HISTORY_FILE_NAME = "practice-history.jsonl"
ACTIVE_FILE_NAME = "practice-active.json"
SESSION_LOCK_FILE_NAME = "practice-session.lock"
TRACK_FILE_NAME = "interview-core.toml"

LANGUAGE_DIRECTORIES = {"ts": "typescript", "py": "python"}
LANGUAGE_ALIASES = {
    "ts": "ts",
    "typescript": "ts",
    "py": "py",
    "python": "py",
}
VALID_MODES = frozenset({"new", "review", "mock"})
VALID_RESULTS = frozenset({"solved", "hinted", "failed"})
VALID_FILTERS = frozenset({"all", "due", "unseen", "scheduled"})
VALID_METADATA_KINDS = frozenset({"class", "design", "function", "language-drill"})

# Index confidence - 1 is the first item.  Kept public so callers can explain a due date.
SCHEDULE_DAYS: dict[str, tuple[int, int, int, int]] = {
    "solved": (0, 1, 3, 7),
    "hinted": (0, 1, 2, 3),
    "failed": (0, 0, 0, 1),
}
CLEAN_SOLVE_INTERVALS = (7, 14, 30, 60)

PROBLEM_DIRECTORY_PATTERN = re.compile(r"^p_(?P<number>[0-9]+)_(?P<slug>[a-z0-9][a-z0-9_]*)$")
TS_FUNCTION_START_PATTERN = re.compile(
    r"(?m)^[ \t]*(?P<prefix>(?:export\s+default\s+|export\s+)?(?:async\s+)?"
    r"function\s+\*?\s*(?P<name>[A-Za-z_$][A-Za-z0-9_$]*))"
)
TS_CLASS_PATTERN = re.compile(
    r"(?m)^[ \t]*(?P<header>(?:(?:export|default|abstract|declare)\s+)*class\s+"
    r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)(?:[^\n{]*)?)\s*\{"
)
TS_CLASS_MEMBER_PATTERN = re.compile(
    r"^(?:(?:(?:public|private|protected|static|readonly|abstract|override|async|get|set)\s+)*"
    r")(?:constructor|\*?\s*#?[A-Za-z_$][A-Za-z0-9_$]*)"
    r"(?:\s*<.*?>)?\s*"
    r"\((?:[^(){}]|\{[^{}]*\}|\([^()]*\))*\)\s*(?::\s*.+)?$",
    re.DOTALL,
)
TS_CLASS_FIELD_PATTERN = re.compile(
    r"^(?P<modifiers>(?:(?:public|private|protected|static|readonly|declare|abstract|override)\s+)*)"
    r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)(?P<marker>[!?]?)\s*:\s*(?P<tail>.+)$",
    re.DOTALL,
)
TS_EXPORT_DECLARATION_PATTERN = re.compile(
    r"(?m)^[ \t]*export\s+(?:default\s+)?"
    r"(?P<kind>const|let|var|type|interface|enum|namespace)\s+"
    r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)"
)
TS_TYPE_DECLARATION_START_PATTERN = re.compile(
    r"(?m)^[ \t]*(?P<header>(?:export\s+)?(?P<kind>type|interface|enum)\s+"
    r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]*))"
)
PY_METHOD_PATTERN = re.compile(r"(?m)^(?P<indent>[ \t]+)def\s+(?P<header>[^\n]+):[ \t]*$")


class PracticeError(ValueError):
    """Base class for expected practice configuration and workflow errors."""


class ProblemDiscoveryError(PracticeError):
    """Raised when a problem cannot be discovered unambiguously."""


class ProblemNotFoundError(ProblemDiscoveryError):
    """Raised when a requested problem ID does not exist for a language."""


class MetadataError(PracticeError):
    """Raised when a TOML metadata file has an invalid value."""


class PracticeStateError(PracticeError):
    """Raised when mutable practice state is missing or malformed."""


def normalize_language(value: str | None = "ts") -> str:
    """Return the canonical two-letter language name.

    TypeScript is the default.  ``typescript``/``ts`` and ``python``/``py`` are accepted for
    parity with the rest of the repository.
    """

    if value is None:
        return "ts"
    try:
        return LANGUAGE_ALIASES[value.strip().lower()]
    except (AttributeError, KeyError) as error:
        raise PracticeError("language must be 'ts'/'typescript' or 'py'/'python'") from error


def normalize_problem_id(value: str | int) -> str:
    """Return a positive problem ID padded to four digits."""

    text = str(value).strip().removesuffix(".")
    if not text.isdecimal():
        raise PracticeError("problem ID must be a positive integer")
    try:
        number = int(text)
    except ValueError as error:
        raise PracticeError("problem ID must be a positive integer") from error
    if number <= 0:
        raise PracticeError("problem ID must be a positive integer")
    return f"{number:04d}"


def _utc(value: datetime | date | None = None) -> datetime:
    """Normalize a datetime-like value to an aware UTC datetime."""

    if value is None:
        return datetime.now(UTC)
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    return value.isoformat()


def _parse_datetime(value: Any, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PracticeStateError(f"{field_name} must be an ISO datetime")
    try:
        return _utc(datetime.fromisoformat(value))
    except ValueError as error:
        raise PracticeStateError(f"{field_name} must be an ISO datetime") from error


def _positive_int(value: Any, field_name: str, *, allow_none: bool = True) -> int | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MetadataError(f"{field_name} must be a positive integer")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise MetadataError(f"{field_name} must be a non-empty string")
    return value.strip()


def _metadata_table(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the most specific metadata table from a TOML document."""

    for key in ("problem", "metadata"):
        section = payload.get(key)
        if isinstance(section, Mapping):
            merged = dict(payload)
            merged.update(section)
            return merged
    return payload


@dataclass(frozen=True)
class ProblemMetadata:
    """Optional metadata attached to a problem or track entry."""

    title: str | None = None
    title_slug: str | None = None
    pattern: str | None = None
    difficulty: str | None = None
    target_minutes: int | None = None
    signature: str | None = None
    tags: tuple[str, ...] = ()
    notes: str | None = None
    kind: str | None = None
    problem_id: str | None = None
    source_path: Path | None = field(default=None, repr=False, compare=False)

    def __getitem__(self, key: str) -> Any:
        """Allow lightweight mapping-style access for integrations."""

        if key == "tags":
            return self.tags
        try:
            return getattr(self, key)
        except AttributeError as error:
            raise KeyError(key) from error

    def get(self, key: str, default: Any = None) -> Any:
        """Return a metadata field using dictionary-like semantics."""

        try:
            return self[key]
        except KeyError:
            return default

    def to_dict(self) -> dict[str, Any]:
        """Return JSON/TOML-friendly metadata without the local source path."""

        result: dict[str, Any] = {}
        for key in (
            "title",
            "title_slug",
            "pattern",
            "difficulty",
            "target_minutes",
            "signature",
            "notes",
            "kind",
            "problem_id",
        ):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        if self.tags:
            result["tags"] = list(self.tags)
        return result


def _parse_metadata(payload: Mapping[str, Any], source_path: Path | None = None) -> ProblemMetadata:
    values = _metadata_table(payload)
    problem_id_value = values.get("id", values.get("problem_id"))
    problem_id = normalize_problem_id(problem_id_value) if problem_id_value is not None else None
    title = _optional_text(values.get("title"), "title")
    title_slug = _optional_text(values.get("title_slug", values.get("slug")), "title_slug")
    pattern = _optional_text(values.get("pattern"), "pattern")
    difficulty = _optional_text(values.get("difficulty"), "difficulty")
    if difficulty is not None:
        difficulty = difficulty.lower()
        if difficulty not in {"easy", "medium", "hard"}:
            raise MetadataError("difficulty must be easy, medium, or hard")
    target_minutes = _positive_int(values.get("target_minutes"), "target_minutes")
    signature = _optional_text(values.get("signature"), "signature")
    notes = _optional_text(values.get("notes"), "notes")
    kind = _optional_text(values.get("kind"), "kind")
    if kind is not None and kind not in VALID_METADATA_KINDS:
        raise MetadataError("kind must be class, design, function, or language-drill")
    raw_tags = values.get("tags", values.get("topics", ()))
    if isinstance(raw_tags, str):
        raw_tags = (raw_tags,)
    if not isinstance(raw_tags, (list, tuple)) or any(
        not isinstance(tag, str) or not tag.strip() for tag in raw_tags
    ):
        raise MetadataError("tags must be a list of non-empty strings")
    tags = tuple(dict.fromkeys(tag.strip() for tag in raw_tags))
    return ProblemMetadata(
        title=title,
        title_slug=title_slug,
        pattern=pattern,
        difficulty=difficulty,
        target_minutes=target_minutes,
        signature=signature,
        tags=tags,
        notes=notes,
        kind=kind,
        problem_id=problem_id,
        source_path=source_path,
    )


def load_problem_metadata(path: Path | str) -> ProblemMetadata | None:
    """Read an optional ``problem.toml`` file from a directory or direct file path.

    ``None`` is returned when the file does not exist.  Invalid TOML and invalid field values are
    reported as :class:`MetadataError` with the file path included.
    """

    path = Path(path)
    candidate = path / "problem.toml" if path.is_dir() else path
    if not candidate.is_file():
        return None
    try:
        with candidate.open("rb") as stream:
            payload = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise MetadataError(f"could not read metadata {candidate}: {error}") from error
    try:
        return _parse_metadata(payload, candidate)
    except PracticeError as error:
        raise MetadataError(f"invalid metadata {candidate}: {error}") from error


@dataclass(frozen=True)
class TrackEntry:
    """A metadata entry from a track manifest, including IDs not scaffolded yet."""

    problem_id: str
    metadata: ProblemMetadata

    @property
    def id(self) -> str:
        return self.problem_id

    @property
    def pattern(self) -> str | None:
        return self.metadata.pattern

    @property
    def difficulty(self) -> str | None:
        return self.metadata.difficulty

    @property
    def target_minutes(self) -> int | None:
        return self.metadata.target_minutes

    def __getitem__(self, key: str) -> Any:
        if key == "problem_id" or key == "id":
            return self.problem_id
        return self.metadata[key]

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def to_dict(self) -> dict[str, Any]:
        result = {"problem_id": self.problem_id}
        result.update(self.metadata.to_dict())
        return result


def _track_entries(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    entries = payload.get("problems")
    if isinstance(entries, list):
        for index, entry in enumerate(entries, 1):
            if not isinstance(entry, Mapping):
                raise MetadataError(f"track problems entry {index} must be a table")
        return entries
    if isinstance(entries, Mapping):
        mapped: list[Mapping[str, Any]] = []
        for problem_id, entry in entries.items():
            if not isinstance(entry, Mapping):
                raise MetadataError(f"track problem {problem_id} must be a table")
            values = dict(entry)
            values.setdefault("id", problem_id)
            mapped.append(values)
        return mapped
    if entries is not None:
        raise MetadataError("track problems must be a list or table")

    singular_entries = payload.get("problem")
    if isinstance(singular_entries, Mapping):
        mapped = []
        for problem_id, entry in singular_entries.items():
            if not isinstance(entry, Mapping):
                raise MetadataError(f"track problem {problem_id} must be a table")
            values = dict(entry)
            values.setdefault("id", problem_id)
            mapped.append(values)
        return mapped
    if singular_entries is not None:
        raise MetadataError("track problem must be a table")

    # Also accept [p_0001] and [problem.0001] style tables for easy hand editing.
    mapped = []
    for key, entry in payload.items():
        if str(key).isdecimal() or str(key).startswith("p_"):
            if not isinstance(entry, Mapping):
                raise MetadataError(f"track problem {key} must be a table")
            values = dict(entry)
            values.setdefault("id", str(key).removeprefix("p_"))
            mapped.append(values)
    return mapped


def load_track_manifest(path: Path | str) -> dict[str, TrackEntry]:
    """Load a track TOML file keyed by normalized problem ID.

    The supported primary shape is ``[[problems]]`` with an ``id`` field.  A mapping under
    ``[problems.<id>]`` is accepted as a convenience.  Duplicate IDs are rejected so selection
    cannot silently use the wrong pattern or target time.
    """

    path = Path(path)
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as stream:
            payload = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise MetadataError(f"could not read track manifest {path}: {error}") from error
    entries: dict[str, TrackEntry] = {}
    for raw_entry in _track_entries(payload):
        try:
            metadata = _parse_metadata(raw_entry, path)
            if metadata.problem_id is None:
                raise MetadataError("track entry requires id")
        except PracticeError as error:
            raise MetadataError(f"invalid track entry in {path}: {error}") from error
        if metadata.problem_id in entries:
            raise MetadataError(f"duplicate problem ID {metadata.problem_id} in {path}")
        entries[metadata.problem_id] = TrackEntry(metadata.problem_id, metadata)
    return dict(sorted(entries.items(), key=lambda item: int(item[0])))


def _merge_metadata(
    primary: ProblemMetadata | None, fallback: ProblemMetadata | None
) -> ProblemMetadata:
    """Merge track defaults with problem-local values, preferring local values."""

    primary = primary or ProblemMetadata()
    fallback = fallback or ProblemMetadata()
    tags = tuple(dict.fromkeys((*fallback.tags, *primary.tags)))
    return ProblemMetadata(
        title=primary.title or fallback.title,
        title_slug=primary.title_slug or fallback.title_slug,
        pattern=primary.pattern or fallback.pattern,
        difficulty=primary.difficulty or fallback.difficulty,
        target_minutes=primary.target_minutes or fallback.target_minutes,
        signature=primary.signature or fallback.signature,
        tags=tags,
        notes=primary.notes or fallback.notes,
        kind=(
            fallback.kind if fallback.kind == "language-drill" else primary.kind or fallback.kind
        ),
        problem_id=primary.problem_id or fallback.problem_id,
        source_path=primary.source_path or fallback.source_path,
    )


@dataclass(frozen=True)
class Problem:
    """One discovered solution directory and its merged metadata."""

    problem_id: str
    language: str
    directory: Path
    slug: str
    metadata: ProblemMetadata

    @property
    def id(self) -> str:
        return self.problem_id

    @property
    def title(self) -> str:
        return self.metadata.title or self.slug.replace("_", " ").title()

    @property
    def source_path(self) -> Path:
        extension = "ts" if self.language == "ts" else "py"
        return self.directory / f"{self.directory.name}.{extension}"

    @property
    def test_path(self) -> Path:
        prefix = "" if self.language == "ts" else "test_"
        suffix = ".test.ts" if self.language == "ts" else ".py"
        return self.directory / f"{prefix}{self.directory.name}{suffix}"

    @property
    def target_minutes(self) -> int | None:
        return self.metadata.target_minutes

    @property
    def pattern(self) -> str | None:
        return self.metadata.pattern

    @property
    def difficulty(self) -> str | None:
        return self.metadata.difficulty

    @property
    def signature(self) -> str | None:
        return self.metadata.signature

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem_id": self.problem_id,
            "id": self.problem_id,
            "language": self.language,
            "slug": self.slug,
            "title": self.title,
            "directory": str(self.directory),
            "source_path": str(self.source_path),
            "pattern": self.metadata.pattern,
            "difficulty": self.metadata.difficulty,
            "target_minutes": self.metadata.target_minutes,
            "kind": self.metadata.kind,
            "metadata": self.metadata.to_dict(),
        }


def _default_track_path(root: Path) -> Path:
    return root / "tracks" / TRACK_FILE_NAME


def discover_problems(
    root: Path | str = ".",
    language: str | None = "ts",
    *,
    track_path: Path | str | None = None,
) -> list[Problem]:
    """Discover conventional problem directories for one language.

    ``language='all'`` is accepted for reporting and statistics; the default remains TypeScript.
    Duplicate normalized IDs in one language raise :class:`ProblemDiscoveryError`.
    """

    repository_root = Path(root)
    try:
        configured_target_minutes = load_config(repository_root).default_minutes
    except ConfigError as error:
        raise MetadataError(str(error)) from error
    if language is not None and language.strip().lower() == "all":
        languages = ("ts", "py")
    else:
        languages = (normalize_language(language),)
    if track_path is None:
        manifest_path = _default_track_path(repository_root)
    else:
        manifest_path = Path(track_path)
        if not manifest_path.is_absolute():
            manifest_path = repository_root / manifest_path
    manifest = load_track_manifest(manifest_path)
    discovered: list[Problem] = []
    for canonical_language in languages:
        solutions = repository_root / "src" / LANGUAGE_DIRECTORIES[canonical_language]
        if not solutions.is_dir():
            continue
        by_id: dict[str, Path] = {}
        for directory in sorted(path for path in solutions.iterdir() if path.is_dir()):
            match = PROBLEM_DIRECTORY_PATTERN.fullmatch(directory.name)
            if match is None:
                continue
            problem_id = normalize_problem_id(match["number"])
            if problem_id in by_id:
                names = f"{by_id[problem_id].name}, {directory.name}"
                raise ProblemDiscoveryError(
                    f"multiple {canonical_language} problem directories for ID {problem_id}: {names}"
                )
            by_id[problem_id] = directory
        for problem_id, directory in by_id.items():
            local_metadata = load_problem_metadata(directory)
            track_metadata = manifest.get(problem_id)
            merged = _merge_metadata(
                local_metadata,
                track_metadata.metadata if track_metadata is not None else None,
            )
            merged = _merge_metadata(
                merged,
                ProblemMetadata(title_slug=match_slug(directory.name)),
            )
            if merged.target_minutes is None:
                merged = replace(merged, target_minutes=configured_target_minutes)
            merged = replace(merged, problem_id=problem_id)
            discovered.append(
                Problem(
                    problem_id=problem_id,
                    language=canonical_language,
                    directory=directory,
                    slug=match_slug(directory.name),
                    metadata=merged,
                )
            )
    return sorted(discovered, key=lambda problem: (problem.language, int(problem.problem_id)))


def match_slug(directory_name: str) -> str:
    """Return the slug portion of a conventional problem directory name."""

    match = PROBLEM_DIRECTORY_PATTERN.fullmatch(directory_name)
    if match is None:
        raise ProblemDiscoveryError(f"not a conventional problem directory: {directory_name}")
    return match["slug"]


def _find_problem(
    root: Path | str,
    problem_id: str | int,
    language: str | None = "ts",
    *,
    track_path: Path | str | None = None,
) -> Problem:
    normalized = normalize_problem_id(problem_id)
    matches = [
        problem
        for problem in discover_problems(root, language, track_path=track_path)
        if problem.problem_id == normalized
    ]
    if not matches:
        raise ProblemNotFoundError(
            f"no {normalize_language(language)} problem directory found for ID {normalized}"
        )
    return matches[0]


def schedule_due_at(
    finished_at: datetime | date,
    result: str,
    confidence: int,
) -> datetime:
    """Return the next due datetime using :data:`SCHEDULE_DAYS`."""

    result = _validate_result(result)
    confidence = _validate_confidence(confidence)
    return _utc(finished_at) + timedelta(days=SCHEDULE_DAYS[result][confidence - 1])


def due_date(finished_at: datetime | date, result: str, confidence: int) -> date:
    """Return only the calendar date of :func:`schedule_due_at`."""

    return schedule_due_at(finished_at, result, confidence).date()


def progressive_due_at(
    finished_at: datetime | date,
    result: str,
    confidence: int,
    previous: Sequence[PracticeRecord],
) -> datetime:
    """Expand repeated clean solves through 7/14/30/60-day retrieval intervals."""
    validated_result = _validate_result(result)
    validated_confidence = _validate_confidence(confidence)
    if validated_result != "solved" or validated_confidence != 4:
        return schedule_due_at(finished_at, validated_result, validated_confidence)
    clean_streak = 0
    for record in reversed(sorted(previous, key=lambda item: item.finished_at)):
        if record.result != "solved" or record.confidence != 4:
            break
        clean_streak += 1
    interval = CLEAN_SOLVE_INTERVALS[min(clean_streak, len(CLEAN_SOLVE_INTERVALS) - 1)]
    return _utc(finished_at) + timedelta(days=interval)


def _validate_result(value: str) -> str:
    if isinstance(value, str):
        value = value.strip().lower()
    if not isinstance(value, str) or value not in VALID_RESULTS:
        raise PracticeError("result must be solved, hinted, or failed")
    return value


def _validate_confidence(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in (1, 2, 3, 4):
        raise PracticeError("confidence must be an integer from 1 to 4")
    return value


def _validate_mode(value: str | None, *, default: str = "new") -> str:
    mode = default if value is None else value
    if isinstance(mode, str):
        mode = mode.strip().lower()
    if not isinstance(mode, str) or mode not in VALID_MODES:
        raise PracticeError("mode must be new, review, or mock")
    return mode


@dataclass(frozen=True)
class Session:
    """An active or completed practice session."""

    session_id: str
    problem_id: str
    language: str
    mode: str
    started_at: datetime
    problem_title: str | None = None

    @property
    def id(self) -> str:
        return self.session_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "id": self.session_id,
            "problem_id": self.problem_id,
            "language": self.language,
            "mode": self.mode,
            "started_at": _iso(self.started_at),
            "title": self.problem_title,
        }


@dataclass(frozen=True)
class PracticeRecord:
    """One immutable result appended to practice history."""

    record_id: str
    session_id: str
    problem_id: str
    language: str
    mode: str
    result: str
    confidence: int
    elapsed_seconds: float
    started_at: datetime
    finished_at: datetime
    due_at: datetime
    notes: str | None = None

    @property
    def id(self) -> str:
        return self.record_id

    @property
    def due_date(self) -> date:
        return self.due_at.date()

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": "finish",
            "record_id": self.record_id,
            "session_id": self.session_id,
            "problem_id": self.problem_id,
            "language": self.language,
            "mode": self.mode,
            "result": self.result,
            "confidence": self.confidence,
            "elapsed_seconds": self.elapsed_seconds,
            "elapsed": self.elapsed_seconds,
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            # timestamp is retained as a convenient JSONL event time for simple consumers.
            "timestamp": _iso(self.finished_at),
            "due_at": _iso(self.due_at),
            "due": _iso(self.due_at),
            "due_date": self.due_date.isoformat(),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ProblemStatus:
    """A discovered problem annotated with its latest practice state."""

    problem: Problem
    state: str
    last_record: PracticeRecord | None
    attempts: int

    @property
    def problem_id(self) -> str:
        return self.problem.problem_id

    @property
    def id(self) -> str:
        return self.problem.problem_id

    @property
    def language(self) -> str:
        return self.problem.language

    @property
    def title(self) -> str:
        return self.problem.title

    @property
    def due_at(self) -> datetime | None:
        return self.last_record.due_at if self.last_record else None

    @property
    def last(self) -> PracticeRecord | None:
        return self.last_record

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem_id": self.problem.problem_id,
            "id": self.problem.problem_id,
            "language": self.problem.language,
            "title": self.problem.title,
            "slug": self.problem.slug,
            "state": self.state,
            "attempts": self.attempts,
            "due_at": _iso(self.due_at),
            "due_date": self.due_at.date().isoformat() if self.due_at else None,
            "last_result": self.last_record.result if self.last_record else None,
            "confidence": self.last_record.confidence if self.last_record else None,
            "last_finished_at": _iso(self.last_record.finished_at) if self.last_record else None,
            "pattern": self.problem.metadata.pattern,
            "difficulty": self.problem.metadata.difficulty,
            "target_minutes": self.problem.metadata.target_minutes,
            "kind": self.problem.metadata.kind,
        }


def _record_from_dict(payload: Mapping[str, Any], source: Path) -> PracticeRecord:
    try:
        record_id = str(payload["record_id"])
        session_id = str(payload["session_id"])
        problem_id = normalize_problem_id(payload["problem_id"])
        language = normalize_language(str(payload["language"]))
        mode = _validate_mode(str(payload["mode"]))
        result = _validate_result(str(payload["result"]))
        raw_confidence = payload["confidence"]
        if isinstance(raw_confidence, bool) or not isinstance(raw_confidence, int):
            raise ValueError("confidence must be an integer")
        confidence = _validate_confidence(raw_confidence)
        raw_elapsed = payload["elapsed_seconds"]
        if isinstance(raw_elapsed, bool) or not isinstance(raw_elapsed, (int, float)):
            raise ValueError("elapsed_seconds must be a number")
        elapsed = float(raw_elapsed)
        if elapsed < 0 or not math.isfinite(elapsed):
            raise ValueError("elapsed_seconds cannot be negative")
        started_at = _parse_datetime(payload["started_at"], "started_at")
        finished_at = _parse_datetime(payload["finished_at"], "finished_at")
        due_at = _parse_datetime(payload["due_at"], "due_at")
        if started_at is None or finished_at is None or due_at is None:
            raise ValueError("timestamps cannot be null")
        notes = payload.get("notes")
        if notes is not None and not isinstance(notes, str):
            raise ValueError("notes must be a string")
    except (KeyError, TypeError, ValueError, PracticeError) as error:
        raise PracticeStateError(f"invalid history record in {source}: {error}") from error
    return PracticeRecord(
        record_id=record_id,
        session_id=session_id,
        problem_id=problem_id,
        language=language,
        mode=mode,
        result=result,
        confidence=confidence,
        elapsed_seconds=elapsed,
        started_at=started_at,
        finished_at=finished_at,
        due_at=due_at,
        notes=notes,
    )


class PracticeStore:
    """Filesystem adapter for the ignored ``.lc`` practice state."""

    def __init__(self, root: Path | str = ".") -> None:
        self.root = Path(root)
        try:
            state_directory = load_config(self.root).history_directory
        except ConfigError as error:
            raise PracticeStateError(str(error)) from error
        self.state_dir = self.root / state_directory
        self.history_path = self.state_dir / HISTORY_FILE_NAME
        self.active_path = self.state_dir / ACTIVE_FILE_NAME
        self.session_lock_path = self.state_dir / SESSION_LOCK_FILE_NAME
        self.history_file = self.history_path
        self.active_file = self.active_path

    def _ensure_state_dir(self) -> None:
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise PracticeStateError(
                f"could not create practice state directory: {error}"
            ) from error

    def read_history(self) -> list[PracticeRecord]:
        """Read all completed sessions in append order."""

        if not self.history_path.exists():
            return []
        try:
            lines = self.history_path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise PracticeStateError(f"could not read practice history: {error}") from error
        records: list[PracticeRecord] = []
        for line_number, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as error:
                raise PracticeStateError(
                    f"invalid JSON in practice history line {line_number}: {error}"
                ) from error
            if not isinstance(payload, Mapping):
                raise PracticeStateError(f"practice history line {line_number} is not an object")
            records.append(_record_from_dict(payload, self.history_path))
        return records

    # Short aliases keep the store pleasant for integrations that do not need to know the file
    # format names.  The explicit read_* methods remain the canonical API.
    history = read_history

    def append_record(self, record: PracticeRecord) -> None:
        """Append one result atomically at the line level and create ``.lc`` if necessary."""

        self._ensure_state_dir()
        try:
            with self.history_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        except OSError as error:
            raise PracticeStateError(f"could not append practice history: {error}") from error

    @contextmanager
    def session_transaction(self) -> Iterator[None]:
        """Serialize active-session creation, completion, and history updates."""

        self._ensure_state_dir()
        try:
            stream = self.session_lock_path.open("a+", encoding="utf-8")
        except OSError as error:
            raise PracticeStateError(f"could not open practice session lock: {error}") from error
        with stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX)
            except OSError as error:
                raise PracticeStateError(f"could not lock practice session: {error}") from error
            try:
                yield
            finally:
                try:
                    fcntl.flock(stream, fcntl.LOCK_UN)
                except OSError:
                    pass

    def read_active(self) -> Session | None:
        """Return the active session, or ``None`` when no session is active."""

        if not self.active_path.exists():
            return None
        try:
            payload = json.loads(self.active_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PracticeStateError(f"could not read active practice session: {error}") from error
        if not isinstance(payload, Mapping):
            raise PracticeStateError("active practice session must be a JSON object")
        try:
            session_id = str(payload["session_id"])
            problem_id = normalize_problem_id(payload["problem_id"])
            language = normalize_language(str(payload["language"]))
            mode = _validate_mode(str(payload["mode"]))
            started_at = _parse_datetime(payload["started_at"], "started_at")
            if started_at is None:
                raise ValueError("started_at cannot be null")
            title = payload.get("title")
            if title is not None and not isinstance(title, str):
                raise ValueError("title must be a string")
        except (KeyError, TypeError, ValueError, PracticeError) as error:
            raise PracticeStateError(f"invalid active practice session: {error}") from error
        return Session(session_id, problem_id, language, mode, started_at, title)

    active_session = read_active

    def write_active(self, session: Session) -> None:
        """Persist an active session using a replace, so readers never see partial JSON."""

        self._ensure_state_dir()
        temporary = self.active_path.with_name(f".{self.active_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(session.to_dict(), sort_keys=True) + "\n", encoding="utf-8"
            )
            os.replace(temporary, self.active_path)
        except OSError as error:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise PracticeStateError(f"could not write active practice session: {error}") from error

    def clear_active(self) -> None:
        try:
            self.active_path.unlink(missing_ok=True)
        except OSError as error:
            raise PracticeStateError(f"could not clear active practice session: {error}") from error


def _latest_records(records: Iterable[PracticeRecord]) -> dict[tuple[str, str], PracticeRecord]:
    latest: dict[tuple[str, str], PracticeRecord] = {}
    for record in records:
        key = (record.language, record.problem_id)
        previous = latest.get(key)
        if previous is None or (record.finished_at, record.record_id) >= (
            previous.finished_at,
            previous.record_id,
        ):
            latest[key] = record
    return latest


def _problem_status(
    problem: Problem,
    records: Sequence[PracticeRecord],
    now: datetime,
) -> ProblemStatus:
    matching = [
        record
        for record in records
        if record.language == problem.language and record.problem_id == problem.problem_id
    ]
    latest = _latest_records(matching).get((problem.language, problem.problem_id))
    if latest is None:
        state = "unseen"
    elif latest.due_at <= now:
        state = "due"
    else:
        state = "scheduled"
    return ProblemStatus(problem, state, latest, len(matching))


def _record_filter_language(language: str | None) -> str | None:
    return _language_scope(language)


def _language_scope(language: str | None) -> str | None:
    """Return a language or ``None`` for the explicit all-language reporting scope."""

    if language is not None and language.strip().lower() == "all":
        return None
    return normalize_language(language)


def _filtered_records(store: PracticeStore, language: str | None) -> list[PracticeRecord]:
    records = store.read_history()
    canonical = _record_filter_language(language)
    return [record for record in records if canonical is None or record.language == canonical]


def select_today(
    root: Path | str = ".",
    language: str | None = "ts",
    *,
    limit: int = 1,
    now: datetime | date | None = None,
    track_path: Path | str | None = None,
) -> list[Problem]:
    """Select due problems first, then unseen problems, up to ``limit`` items."""

    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise PracticeError("limit must be a positive integer")
    repository_root = Path(root)
    canonical_language = _language_scope(language)
    discovery_language = canonical_language or "all"
    current = _utc(now)
    store = PracticeStore(repository_root)
    records = _filtered_records(store, language)
    statuses = [
        _problem_status(problem, records, current)
        for problem in discover_problems(repository_root, discovery_language, track_path=track_path)
    ]
    due = sorted(
        (status for status in statuses if status.state == "due"),
        key=lambda status: (
            status.due_at or datetime.min.replace(tzinfo=UTC),
            status.problem.target_minutes or 10**9,
            int(status.problem.problem_id),
        ),
    )
    unseen = sorted(
        (status for status in statuses if status.state == "unseen"),
        key=lambda status: (
            status.problem.target_minutes or 10**9,
            int(status.problem.problem_id),
        ),
    )
    return [status.problem for status in [*due, *unseen][:limit]]


def today(
    root: Path | str = ".",
    language: str | None = "ts",
    *,
    limit: int = 1,
    now: datetime | date | None = None,
) -> list[Problem]:
    """Stable API alias for :func:`select_today`."""

    return select_today(root, language, limit=limit, now=now)


def review_queue(
    root: Path | str = ".",
    language: str | None = "ts",
    *,
    limit: int | None = None,
    now: datetime | date | None = None,
) -> list[Problem]:
    """Return all currently due problems, ordered by due time.

    ``limit=None`` returns the complete queue.  A positive limit is useful for a compact CLI
    dashboard.
    """

    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0):
        raise PracticeError("limit must be a positive integer")
    repository_root = Path(root)
    canonical_language = _language_scope(language)
    discovery_language = canonical_language or "all"
    current = _utc(now)
    records = _filtered_records(PracticeStore(repository_root), language)
    statuses = [
        _problem_status(problem, records, current)
        for problem in discover_problems(repository_root, discovery_language)
    ]
    due = sorted(
        (status for status in statuses if status.state == "due"),
        key=lambda status: (
            status.due_at or datetime.min.replace(tzinfo=UTC),
            int(status.problem.problem_id),
        ),
    )
    problems = [status.problem for status in due]
    return problems if limit is None else problems[:limit]


def start_in_transaction(
    store: PracticeStore,
    problem_id: str | int | None,
    language: str | None,
    mode: str | None,
    now: datetime | date | None,
    *,
    track_path: Path | str | None = None,
) -> Session:
    """Create a session while the caller holds ``store.session_transaction()``."""

    repository_root = store.root
    canonical_language = normalize_language(language)
    current = _utc(now)
    if problem_id is None:
        candidates = select_today(
            repository_root,
            canonical_language,
            limit=1,
            now=current,
            track_path=track_path,
        )
        if not candidates:
            raise PracticeError("no due or unseen problems are available")
        problem = candidates[0]
    else:
        problem = _find_problem(
            repository_root,
            problem_id,
            canonical_language,
            track_path=track_path,
        )
    if store.read_active() is not None:
        raise PracticeStateError("a practice session is already active; finish it first")
    records = _filtered_records(store, canonical_language)
    latest = _latest_records(records).get((canonical_language, problem.problem_id))
    selected_mode = mode
    if selected_mode is None:
        selected_mode = "review" if latest is not None and latest.due_at <= current else "new"
    selected_mode = _validate_mode(selected_mode)
    session = Session(
        session_id=uuid.uuid4().hex,
        problem_id=problem.problem_id,
        language=canonical_language,
        mode=selected_mode,
        started_at=current,
        problem_title=problem.title,
    )
    store.write_active(session)
    return session


def _new_session(
    root: Path | str,
    problem_id: str | int | None,
    language: str | None,
    mode: str | None,
    now: datetime | date | None,
    *,
    track_path: Path | str | None = None,
) -> Session:
    store = PracticeStore(root)
    with store.session_transaction():
        return start_in_transaction(
            store,
            problem_id,
            language,
            mode,
            now,
            track_path=track_path,
        )


def start(
    root: Path | str = ".",
    problem_id: str | int | None = None,
    language: str | None = "ts",
    *,
    mode: str | None = None,
    now: datetime | date | None = None,
    track_path: Path | str | None = None,
) -> Session:
    """Start a new, review, or mock session and persist it as the active session."""

    return _new_session(root, problem_id, language, mode, now, track_path=track_path)


def finish(
    root: Path | str = ".",
    result: str = "failed",
    confidence: int = 1,
    *,
    elapsed_seconds: float | int | None = None,
    elapsed: float | int | None = None,
    now: datetime | date | None = None,
    session_id: str | None = None,
    notes: str | None = None,
) -> PracticeRecord:
    """Finish the active session, append its result, and schedule its next due date."""

    if elapsed_seconds is not None and elapsed is not None:
        raise PracticeError("provide only one of elapsed_seconds or elapsed")
    provided_elapsed = elapsed_seconds if elapsed_seconds is not None else elapsed
    if provided_elapsed is not None:
        if isinstance(provided_elapsed, bool):
            raise PracticeError("elapsed seconds must be non-negative")
        try:
            provided_elapsed = float(provided_elapsed)
        except (TypeError, ValueError) as error:
            raise PracticeError("elapsed seconds must be non-negative") from error
        if not math.isfinite(provided_elapsed) or provided_elapsed < 0:
            raise PracticeError("elapsed seconds must be non-negative")
    validated_result = _validate_result(result)
    validated_confidence = _validate_confidence(confidence)
    store = PracticeStore(root)
    with store.session_transaction():
        history = store.read_history()
        session = store.read_active()
        if session is None:
            existing = next((record for record in history if record.session_id == session_id), None)
            if existing is not None:
                return existing
            raise PracticeStateError("no active practice session")
        if session_id is not None and session.session_id != session_id:
            raise PracticeStateError("session ID does not match the active session")
        existing = next(
            (record for record in history if record.session_id == session.session_id), None
        )
        if existing is not None:
            store.clear_active()
            return existing
        finished_at = _utc(now)
        computed_elapsed = (finished_at - session.started_at).total_seconds()
        elapsed_value = computed_elapsed if provided_elapsed is None else provided_elapsed
        if not math.isfinite(elapsed_value) or elapsed_value < 0:
            raise PracticeError("finish time cannot precede session start")
        if notes is not None and not isinstance(notes, str):
            raise PracticeError("notes must be a string")
        previous_records = [
            record
            for record in history
            if record.language == session.language and record.problem_id == session.problem_id
        ]
        record = PracticeRecord(
            record_id=uuid.uuid4().hex,
            session_id=session.session_id,
            problem_id=session.problem_id,
            language=session.language,
            mode=session.mode,
            result=validated_result,
            confidence=validated_confidence,
            elapsed_seconds=elapsed_value,
            started_at=session.started_at,
            finished_at=finished_at,
            due_at=progressive_due_at(
                finished_at,
                validated_result,
                validated_confidence,
                previous_records,
            ),
            notes=notes,
        )
        store.append_record(record)
        store.clear_active()
        return record


def review(
    root: Path | str = ".",
    problem_id: str | int | None = None,
    language: str | None = "ts",
    *,
    limit: int | None = None,
    now: datetime | date | None = None,
) -> list[Problem] | Session:
    """Show the due queue, or start an explicitly requested problem in review mode."""

    if problem_id is None:
        return review_queue(root, language, limit=limit, now=now)
    return start(root, problem_id, language, mode="review", now=now)


def list_problems(
    root: Path | str = ".",
    language: str | None = "ts",
    *,
    filter: str = "all",
    now: datetime | date | None = None,
    track_path: Path | str | None = None,
) -> list[ProblemStatus]:
    """List discovered problems annotated with ``unseen``, ``due``, or ``scheduled`` state."""

    if filter not in VALID_FILTERS:
        raise PracticeError("filter must be all, due, unseen, or scheduled")
    repository_root = Path(root)
    current = _utc(now)
    canonical_language = _language_scope(language)
    discovery_language = canonical_language or "all"
    store = PracticeStore(repository_root)
    records = _filtered_records(store, language)
    statuses = [
        _problem_status(problem, records, current)
        for problem in discover_problems(
            repository_root,
            discovery_language,
            track_path=track_path,
        )
    ]
    if filter != "all":
        statuses = [status for status in statuses if status.state == filter]
    return statuses


def list_items(
    root: Path | str = ".",
    language: str | None = "ts",
    *,
    filter: str = "all",
    now: datetime | date | None = None,
) -> list[ProblemStatus]:
    """Readable alias for :func:`list_problems` (avoids shadowing ``list``)."""

    return list_problems(root, language, filter=filter, now=now)


def collect_stats(
    root: Path | str = ".",
    language: str | None = "ts",
    *,
    now: datetime | date | None = None,
) -> dict[str, Any]:
    """Return aggregate attempts, latest states, timing, and due/unseen counts."""

    repository_root = Path(root)
    canonical_language = _language_scope(language)
    current = _utc(now)
    statuses = list_problems(repository_root, language, now=current)
    records = _filtered_records(PracticeStore(repository_root), language)
    attempts_by_result = Counter(record.result for record in records)
    latest_by_result = Counter(
        status.last_record.result for status in statuses if status.last_record is not None
    )
    by_mode = Counter(record.mode for record in records)
    elapsed_values = [record.elapsed_seconds for record in records]
    confidence_values = [record.confidence for record in records]
    due_values = [status.due_at for status in statuses if status.state == "scheduled"]
    due_values.extend(status.due_at for status in statuses if status.state == "due")
    due_values = [value for value in due_values if value is not None]
    attempted = len(statuses) - sum(status.state == "unseen" for status in statuses)
    average_elapsed = sum(elapsed_values) / len(elapsed_values) if elapsed_values else 0.0
    median_elapsed = statistics.median(elapsed_values) if elapsed_values else 0.0
    average_confidence = (
        sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    )
    problems_by_key = {
        (status.problem.language, status.problem.problem_id): status.problem for status in statuses
    }
    pattern_timings: dict[str, list[float]] = {}
    difficulty_timings: dict[str, list[float]] = {}
    for record in records:
        problem = problems_by_key.get((record.language, record.problem_id))
        if problem is None:
            continue
        if problem.pattern:
            pattern_timings.setdefault(problem.pattern, []).append(record.elapsed_seconds)
        if problem.difficulty:
            difficulty_timings.setdefault(problem.difficulty, []).append(record.elapsed_seconds)

    def solve_rate(values: Sequence[PracticeRecord]) -> float:
        return sum(record.result == "solved" for record in values) / len(values) if values else 0.0

    review_records = [record for record in records if record.mode in {"review", "mock"}]
    reviews_7d = [
        record for record in review_records if record.finished_at >= current - timedelta(days=7)
    ]
    reviews_30d = [
        record for record in review_records if record.finished_at >= current - timedelta(days=30)
    ]
    pattern_matrix: dict[str, dict[str, int]] = {}
    for status in statuses:
        pattern = status.problem.pattern or "unclassified"
        summary = pattern_matrix.setdefault(
            pattern, {"total": 0, "attempted": 0, "due": 0, "solved": 0}
        )
        summary["total"] += 1
        summary["attempted"] += int(status.attempts > 0)
        summary["due"] += int(status.state == "due")
        summary["solved"] += int(
            status.last_record is not None and status.last_record.result == "solved"
        )
    weak_patterns = []
    for pattern, summary in pattern_matrix.items():
        attempted_count = summary["attempted"]
        pattern_solve_rate = summary["solved"] / attempted_count if attempted_count else 0.0
        if attempted_count > 0 and (summary["due"] > 0 or pattern_solve_rate < 1.0):
            weak_patterns.append(
                {
                    "pattern": pattern,
                    "attempted": attempted_count,
                    "total": summary["total"],
                    "due": summary["due"],
                    "solved": summary["solved"],
                    "solve_rate": pattern_solve_rate,
                }
            )
    weak_patterns.sort(key=lambda item: (-item["due"], item["solve_rate"], item["pattern"]))
    return {
        "language": canonical_language or "all",
        "total": len(statuses),
        "total_problems": len(statuses),
        "attempted": attempted,
        "unseen": sum(status.state == "unseen" for status in statuses),
        "due": sum(status.state == "due" for status in statuses),
        "scheduled": sum(status.state == "scheduled" for status in statuses),
        "attempts": len(records),
        "solved": attempts_by_result["solved"],
        "hinted": attempts_by_result["hinted"],
        "failed": attempts_by_result["failed"],
        "by_result": dict(attempts_by_result),
        "results": dict(attempts_by_result),
        "latest_by_result": dict(latest_by_result),
        "by_mode": dict(by_mode),
        "modes": dict(by_mode),
        "average_elapsed_seconds": average_elapsed,
        "average_elapsed": average_elapsed,
        "median_elapsed_seconds": median_elapsed,
        "median_elapsed": median_elapsed,
        "average_confidence": average_confidence,
        "completion_rate": (attempts_by_result["solved"] / len(records) if records else 0.0),
        "hint_free_rate": solve_rate(records),
        "independent_resolve_rate_7d": solve_rate(reviews_7d),
        "independent_resolve_rate_30d": solve_rate(reviews_30d),
        "median_elapsed_by_pattern": {
            key: statistics.median(values) for key, values in sorted(pattern_timings.items())
        },
        "median_elapsed_by_difficulty": {
            key: statistics.median(values) for key, values in sorted(difficulty_timings.items())
        },
        "pattern_matrix": dict(sorted(pattern_matrix.items())),
        "weak_patterns": weak_patterns,
        "interview_dsa_total": sum(
            status.problem.metadata.kind != "language-drill" for status in statuses
        ),
        "next_due_at": _iso(min(due_values)) if due_values else None,
    }


def stats(
    root: Path | str = ".",
    language: str | None = "ts",
    *,
    now: datetime | date | None = None,
) -> dict[str, Any]:
    """Stable API alias for :func:`collect_stats`."""

    return collect_stats(root, language, now=now)


class Practice:
    """Convenience object for callers dispatching several practice commands."""

    def __init__(self, root: Path | str = ".", language: str | None = "ts") -> None:
        self.root = Path(root)
        self.language = normalize_language(language)

    def today(self, *, limit: int = 1, now: datetime | date | None = None) -> list[Problem]:
        return today(self.root, self.language, limit=limit, now=now)

    def start(
        self,
        problem_id: str | int | None = None,
        *,
        mode: str | None = None,
        now: datetime | date | None = None,
    ) -> Session:
        return start(self.root, problem_id, self.language, mode=mode, now=now)

    def finish(
        self,
        result: str = "failed",
        confidence: int = 1,
        *,
        elapsed_seconds: float | int | None = None,
        elapsed: float | int | None = None,
        now: datetime | date | None = None,
        notes: str | None = None,
    ) -> PracticeRecord:
        return finish(
            self.root,
            result,
            confidence,
            elapsed_seconds=elapsed_seconds,
            elapsed=elapsed,
            now=now,
            notes=notes,
        )

    def review(
        self,
        problem_id: str | int | None = None,
        *,
        limit: int | None = None,
        now: datetime | date | None = None,
    ) -> list[Problem] | Session:
        return review(self.root, problem_id, self.language, limit=limit, now=now)

    def list(
        self, *, filter: str = "all", now: datetime | date | None = None
    ) -> list[ProblemStatus]:
        return list_problems(self.root, self.language, filter=filter, now=now)

    def stats(self, *, now: datetime | date | None = None) -> dict[str, Any]:
        return stats(self.root, self.language, now=now)


# Explicit names for dispatchers that prefer verb-noun functions over the short CLI verbs.
start_session = start
finish_session = finish
select_due = review_queue
practice_stats = stats
find_problems = discover_problems
list_command = list_problems


def _json_default(value: Any) -> str:
    if isinstance(value, (Path, datetime, date)):
        return value.isoformat()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _common_options(parser: argparse.ArgumentParser, *, allow_all: bool = False) -> None:
    parser.add_argument("--root", type=Path, default=argparse.SUPPRESS, help="repository root")
    parser.add_argument(
        "--language",
        "-l",
        default=argparse.SUPPRESS,
        choices=("ts", "typescript", "py", "python", *(("all",) if allow_all else ())),
        help="problem language (default: ts)",
    )
    parser.add_argument(
        "--human",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print concise terminal output instead of JSON",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser used by :func:`main`."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument(
        "--language",
        "-l",
        default=None,
        choices=("ts", "typescript", "py", "python", "all"),
        help="problem language (default: lc.toml primary_language)",
    )
    parser.add_argument(
        "--human", action="store_true", help="print concise terminal output instead of JSON"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    command = subparsers.add_parser("today", help="select due then unseen problems")
    _common_options(command, allow_all=True)
    command.add_argument("--limit", type=int, default=1)

    command = subparsers.add_parser("start", help="start a practice session")
    _common_options(command)
    command.add_argument("problem_id", nargs="?")
    command.add_argument("--problem-id", "--id", dest="explicit_problem_id", default=None)
    command.add_argument("--mode", choices=sorted(VALID_MODES), default=None)

    command = subparsers.add_parser("finish", help="finish the active practice session")
    _common_options(command)
    command.add_argument("--result", choices=sorted(VALID_RESULTS), required=True)
    command.add_argument("--confidence", type=int, default=1)
    command.add_argument(
        "--elapsed",
        type=float,
        default=None,
        dest="elapsed_seconds",
        metavar="SECONDS",
        help="elapsed session duration in seconds",
    )
    command.add_argument("--notes", default=None)
    command.add_argument("--session-id", default=None)

    command = subparsers.add_parser("review", help="show due problems or start one in review mode")
    _common_options(command, allow_all=True)
    command.add_argument("problem_id", nargs="?")
    command.add_argument("--problem-id", "--id", dest="explicit_problem_id", default=None)
    command.add_argument("--limit", type=int, default=None)

    command = subparsers.add_parser("list", help="list practice status for discovered problems")
    _common_options(command, allow_all=True)
    filters = command.add_mutually_exclusive_group()
    filters.add_argument("--filter", choices=sorted(VALID_FILTERS), default="all")
    filters.add_argument("--due", action="store_const", const="due", dest="filter")
    filters.add_argument("--unseen", action="store_const", const="unseen", dest="filter")

    command = subparsers.add_parser("stats", help="show aggregate practice statistics")
    _common_options(command, allow_all=True)
    return parser


def _print_json(value: Any) -> None:
    print(json.dumps(value, default=_json_default, indent=2, sort_keys=True))


def _problem_summary(problem: Problem) -> str:
    difficulty = problem.difficulty or "-"
    pattern = problem.pattern or "unclassified"
    target = f"{problem.target_minutes}m" if problem.target_minutes else "-"
    return (
        f"{problem.problem_id}  {problem.language:<2}  {difficulty:<6}  "
        f"{pattern:<24} {target:>4}  {problem.title}"
    )


def _print_human(value: Any) -> None:
    """Print practice results for a person at a terminal; JSON remains the script default."""
    if isinstance(value, list):
        if not value:
            print("No matching problems.")
            return
        for item in value:
            if isinstance(item, ProblemStatus):
                due = f", due {item.due_at.date().isoformat()}" if item.due_at else ""
                print(
                    f"{_problem_summary(item.problem)}  "
                    f"[{item.state}, {item.attempts} attempt(s){due}]"
                )
            elif isinstance(item, Problem):
                print(_problem_summary(item))
            else:  # pragma: no cover - CLI dispatch only emits the types above.
                print(item)
        return
    if isinstance(value, Session):
        title = f" — {value.problem_title}" if value.problem_title else ""
        print(f"Started {value.mode}: {value.problem_id} ({value.language}){title}")
        print(f"Timer: {value.started_at.isoformat()}")
        print("Finish: lc finish --result solved|hinted|failed --confidence 1-4")
        return
    if isinstance(value, PracticeRecord):
        minutes = value.elapsed_seconds / 60
        print(
            f"Finished {value.problem_id} ({value.language}): {value.result}, "
            f"{minutes:.1f}m, confidence {value.confidence}"
        )
        print(f"Next review: {value.due_at.date().isoformat()}")
        return

    if isinstance(value, dict):
        print(
            f"Practice ({value['language']}): {value['attempted']}/{value['total']} attempted, "
            f"{value['due']} due, {value['unseen']} unseen"
        )
        print(
            f"Attempts: {value['attempts']} — solved {value['solved']}, "
            f"hinted {value['hinted']}, failed {value['failed']}"
        )
        print(
            f"Timing: average {value['average_elapsed_seconds'] / 60:.1f}m, "
            f"median {value['median_elapsed_seconds'] / 60:.1f}m"
        )
        print(
            f"Hint-free: {value['hint_free_rate']:.0%}; independent re-solves: "
            f"7d {value['independent_resolve_rate_7d']:.0%}, "
            f"30d {value['independent_resolve_rate_30d']:.0%}"
        )
        due_patterns = sorted(
            (
                (pattern, summary)
                for pattern, summary in value["pattern_matrix"].items()
                if summary["due"]
            ),
            key=lambda item: (-item[1]["due"], item[0]),
        )
        weak_patterns = value.get("weak_patterns", [])
        if weak_patterns:
            print(
                "Weak patterns: "
                + ", ".join(
                    f"{item['pattern']} ({item['solve_rate']:.0%} solved, {item['due']} due)"
                    for item in weak_patterns[:5]
                )
            )
        elif due_patterns:
            print(
                "Due patterns: "
                + ", ".join(
                    f"{pattern} ({summary['due']})" for pattern, summary in due_patterns[:5]
                )
            )
        return
    print(value)  # pragma: no cover - defensive fallback for future command types.


def _print_result(value: Any, *, human: bool) -> None:
    if human:
        _print_human(value)
    else:
        if isinstance(value, list):
            _print_json([item.to_dict() for item in value])
        elif hasattr(value, "to_dict"):
            _print_json(value.to_dict())
        else:
            _print_json(value)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the practice CLI and return a process-style status code."""

    parser = build_parser()
    arguments = parser.parse_args(argv)
    root = Path(getattr(arguments, "root", Path.cwd()))
    try:
        configured_language = load_config(root).primary_language
        language = getattr(arguments, "language", None) or configured_language
        human = getattr(arguments, "human", False)
        problem_id = getattr(arguments, "explicit_problem_id", None) or getattr(
            arguments, "problem_id", None
        )
        all_languages_allowed = arguments.command in {"today", "list", "stats"} or (
            arguments.command == "review" and problem_id is None
        )
        if language == "all" and not all_languages_allowed:
            raise PracticeError(
                "--language all is only supported by today, list, stats, and review without an ID"
            )
        if arguments.command == "today":
            _print_result(today(root, language, limit=arguments.limit), human=human)
        elif arguments.command == "start":
            _print_result(start(root, problem_id, language, mode=arguments.mode), human=human)
        elif arguments.command == "finish":
            _print_result(
                finish(
                    root,
                    arguments.result,
                    arguments.confidence,
                    elapsed_seconds=arguments.elapsed_seconds,
                    notes=arguments.notes,
                    session_id=arguments.session_id,
                ),
                human=human,
            )
        elif arguments.command == "review":
            reviewed = review(
                root,
                problem_id,
                language,
                limit=arguments.limit,
            )
            _print_result(reviewed, human=human)

        elif arguments.command == "list":
            _print_result(list_problems(root, language, filter=arguments.filter), human=human)
        elif arguments.command == "stats":
            _print_result(stats(root, language), human=human)
        else:  # pragma: no cover - argparse enforces the command choices.
            parser.error(f"unknown command: {arguments.command}")
    except (ConfigError, OSError, PracticeError) as error:
        print(f"practice: {error}", file=sys.stderr)
        return 2
    return 0


run = main


if __name__ == "__main__":
    raise SystemExit(main())
