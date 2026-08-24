#!/usr/bin/env python3
"""Verify the configured workspace runtime and judge-facing language profile."""

from __future__ import annotations

import json
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


class CompatibilityError(ValueError):
    """Raised when compatibility metadata has an invalid container shape."""


@dataclass(frozen=True)
class JudgeProfile:
    """Workspace runtime plus compiler/language settings used for judge-facing code."""

    node: str = "26.7.0"
    typescript: str = "5.7.3"
    python_minor: str = "3.14"
    typescript_target: str = "ES2024"

    @property
    def target(self) -> str:
        """Return the configured TypeScript target using its short profile name."""
        return self.typescript_target


PROFILE = JudgeProfile()
JsonObject = dict[str, object]


def _read_json_object(path: Path, label: str) -> JsonObject:
    """Read a JSON object and reject scalar/array roots before nested access."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CompatibilityError(f"{label} must contain a JSON object")
    return value


def _read_toml_object(path: Path, label: str) -> dict[str, object]:
    """Read a TOML document and make its expected table shape explicit."""
    value = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CompatibilityError(f"{label} must contain a TOML table")
    return value


def _optional_object(container: Mapping[str, object], key: str, label: str) -> JsonObject:
    """Return an optional nested object, rejecting a present non-object value."""
    if key not in container:
        return {}
    value = container[key]
    if not isinstance(value, dict):
        raise CompatibilityError(f"{label} {key} must be an object/table")
    return value


def _required_string(container: Mapping[str, object], key: str, label: str) -> str:
    """Read a required non-empty string from a metadata object."""
    value = container.get(key)
    if not isinstance(value, str) or not value:
        raise CompatibilityError(f"{label} {key} must be a non-empty string")
    return value


def _configured_string(container: Mapping[str, object], key: str, label: str) -> str:
    """Read an optional configured string, treating absence as an unset value."""
    if key not in container:
        return ""
    value = container[key]
    if not isinstance(value, str):
        raise CompatibilityError(f"{label} {key} must be a string")
    return value


def _profile_value(compatibility: Mapping[str, object], primary: str, alias: str) -> str:
    """Read a profile key while accepting the explicit Python-facing alias."""
    if primary in compatibility and alias in compatibility:
        primary_value = compatibility[primary]
        alias_value = compatibility[alias]
        if primary_value != alias_value:
            raise CompatibilityError(f"lc.toml [compatibility] {primary} and {alias} must agree")
    key = primary if primary in compatibility else alias
    return _required_string(compatibility, key, "lc.toml [compatibility]")


def load_profile(root: Path) -> JudgeProfile:
    """Load the compatibility profile from the repository's ``lc.toml`` source of truth."""
    document = _read_toml_object(root / "lc.toml", "lc.toml")
    if "compatibility" not in document:
        raise CompatibilityError("lc.toml must define a [compatibility] table")
    compatibility = document["compatibility"]
    if not isinstance(compatibility, dict):
        raise CompatibilityError("lc.toml [compatibility] must be a table")
    return JudgeProfile(
        node=_required_string(compatibility, "node", "lc.toml [compatibility]"),
        typescript=_required_string(compatibility, "typescript", "lc.toml [compatibility]"),
        python_minor=_profile_value(compatibility, "python", "python_minor"),
        typescript_target=_profile_value(compatibility, "target", "typescript_target"),
    )


def compatibility_issues(root: Path, profile: JudgeProfile | None = None) -> list[str]:
    """Return actionable metadata mismatches without invoking package managers.

    When no profile is supplied, ``lc.toml`` is authoritative.  An explicit
    profile remains injectable for focused tests and callers comparing a
    checkout against a different judge contract.
    """
    try:
        configured_profile = load_profile(root) if profile is None else profile
        package = _read_json_object(root / "package.json", "package.json")
        mise = _read_toml_object(root / "mise.toml", "mise.toml")
        tsconfig = _read_json_object(root / "tsconfig.json", "tsconfig.json")
        tools = _optional_object(mise, "tools", "mise.toml")
        dependencies = _optional_object(package, "devDependencies", "package.json")
        compiler_options = _optional_object(tsconfig, "compilerOptions", "tsconfig.json")
        configured_node = _configured_string(tools, "node", "mise.toml tools")
        typescript = _configured_string(dependencies, "typescript", "package.json devDependencies")
        configured_python = _configured_string(tools, "python", "mise.toml tools")
        target = _configured_string(compiler_options, "target", "tsconfig.json compilerOptions")
        node_version = (root / ".node-version").read_text(encoding="utf-8").strip()
        python_version = (root / ".python-version").read_text(encoding="utf-8").strip()
    except CompatibilityError as error:
        return [str(error)]

    issues: list[str] = []
    if node_version != configured_profile.node:
        issues.append(f"Node must be {configured_profile.node}; found {node_version}")

    if configured_node != configured_profile.node:
        issues.append(
            f"mise Node must be {configured_profile.node}; found {configured_node or 'unset'}"
        )

    if typescript != configured_profile.typescript:
        issues.append(
            f"TypeScript must be {configured_profile.typescript}; found {typescript or 'unset'}"
        )

    for label, version in (("Python", python_version), ("mise Python", configured_python)):
        if not version.startswith(f"{configured_profile.python_minor}."):
            issues.append(
                f"{label} must use {configured_profile.python_minor}.x; found {version or 'unset'}"
            )

    if target.upper() != configured_profile.typescript_target.upper():
        issues.append(
            f"TypeScript target must be {configured_profile.typescript_target}; found {target or 'unset'}"
        )
    return issues


def format_report(issues: Sequence[str], profile: JudgeProfile = PROFILE) -> str:
    """Format a concise compatibility report."""
    if issues:
        return "\n".join([*(f"FAIL {issue}" for issue in issues), "Compatibility: not ready"])
    return (
        f"PASS Node {profile.node}, TypeScript {profile.typescript}, "
        f"Python {profile.python_minor}.x, target {profile.typescript_target}\n"
        "Compatibility: ready"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Check the repository root supplied by the caller, if any."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["-h"], ["--help"]):
        print("usage: compat.py [root]")
        return 0
    if len(arguments) > 1:
        print("usage: compat.py [root]", file=sys.stderr)
        return 2
    root = Path(arguments[0]).resolve() if arguments else Path(__file__).resolve().parents[1]
    try:
        profile = load_profile(root)
        issues = compatibility_issues(root, profile)
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        print(f"error: could not read compatibility metadata: {error}", file=sys.stderr)
        return 1
    print(format_report(issues, profile))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
