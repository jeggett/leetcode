"""Small, private, atomic files for local workflow state."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class StateError(ValueError):
    """Local state needs attention before the workflow can continue."""


def read_state(path: Path) -> dict:
    """Read a state object, distinguishing missing files from damaged state."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (ValueError, UnicodeError) as error:
        raise StateError(f"invalid local state: {path}; restore it from a backup") from error
    if not isinstance(value, dict):
        raise StateError(f"invalid local state: {path}; expected an object")
    return value


def write_state(path: Path, value: dict) -> None:
    """Replace one JSON file atomically; interrupted writes keep the previous file."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".state-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
