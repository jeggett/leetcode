from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.doctor import CommandResult, collect_checks, format_report, main, parse_version


def write_metadata(root: Path, *, package_manager: str = "pnpm@11.20.0") -> None:
    (root / ".node-version").write_text("22.14.0\n", encoding="utf-8")
    (root / "mise.toml").write_text(
        '[tools]\nnode = "22.14.0"\n"npm:pnpm" = "11.20.0"\npython = "3.14.7"\nuv = "0.12.2"\n',
        encoding="utf-8",
    )
    (root / "package.json").write_text(
        json.dumps(
            {
                "packageManager": package_manager,
                "engines": {"node": ">=22.13.0", "pnpm": "11.20.0"},
                "devDependencies": {
                    "@biomejs/biome": "2.5.7",
                    "lefthook": "2.1.10",
                    "typescript": "5.7.3",
                    "vitest": "4.1.10",
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[dependency-groups]\n"
        'dev = ["pytest==9.1.1", "pytest-timeout==2.4.0", '
        '"pytest-watcher==0.6.3", "ruff==0.16.2"]\n',
        encoding="utf-8",
    )


def write_dependencies(
    root: Path,
    *,
    node_version: str = "4.1.10",
    python_version: str = "9.1.1",
) -> None:
    node_versions = {
        "@biomejs/biome": "2.5.7",
        "lefthook": "2.1.10",
        "typescript": "5.7.3",
        "vitest": node_version,
    }
    for dependency, version in node_versions.items():
        node_dependency = root / "node_modules" / dependency
        node_dependency.mkdir(parents=True)
        (node_dependency / "package.json").write_text(
            json.dumps({"name": dependency, "version": version}),
            encoding="utf-8",
        )

    site_packages = root / ".venv" / "lib" / "python3.14" / "site-packages"
    python_versions = {
        "pytest": python_version,
        "pytest-timeout": "2.4.0",
        "pytest-watcher": "0.6.3",
        "ruff": "0.16.2",
    }
    for dependency, version in python_versions.items():
        metadata_directory = site_packages / f"{dependency}-{version}.dist-info"
        metadata_directory.mkdir(parents=True)
        (metadata_directory / "METADATA").write_text(
            f"Metadata-Version: 2.4\nName: {dependency}\nVersion: {version}\n",
            encoding="utf-8",
        )


def write_lefthook_installation(root: Path) -> None:
    (root / "lefthook.yml").write_text(
        "pre-commit:\n  commands:\n    staged-ready:\n"
        "      run: mise exec -- uv run python scripts/ready.py staged\n",
        encoding="utf-8",
    )
    generated_hook = root / ".git" / "hooks" / "pre-commit"
    generated_hook.parent.mkdir(parents=True)
    generated_hook.write_text('#!/bin/sh\nlefthook run pre-commit -- "$@"\n', encoding="utf-8")
    if os.name == "posix":
        generated_hook.chmod(0o755)


def command_runner(command: tuple[str, ...] | list[str], _: Path) -> CommandResult:
    outputs = {
        ("mise", "trust", "--show"): "/tmp/project: trusted\n",
        ("node", "--version"): "v22.14.0\n",
        ("pnpm", "--version"): "11.20.0\n",
        ("python", "--version"): "Python 3.14.7\n",
        ("uv", "--version"): "uv 0.12.2\n",
        ("git", "config", "--get", "core.hooksPath"): "",
        ("git", "rev-parse", "--path-format=absolute", "--git-path", "hooks/pre-commit"): str(
            _ / ".git/hooks/pre-commit"
        ),
    }
    return CommandResult(0, outputs[tuple(command)])


def test_parse_version_accepts_common_version_command_output() -> None:
    assert parse_version("v22.14.0\n") == "22.14.0"
    assert parse_version("Python 3.14.7") == "3.14.7"
    assert parse_version("unversioned") is None


def test_collect_checks_reports_a_ready_checkout(tmp_path: Path) -> None:
    write_metadata(tmp_path)
    write_dependencies(tmp_path)
    write_lefthook_installation(tmp_path)

    checks = collect_checks(
        tmp_path,
        find_command=lambda _: "/usr/bin/tool",
        run=command_runner,
    )

    assert all(check.passed for check in checks)
    assert format_report(checks).endswith("Doctor: ready")


def test_collect_checks_reports_setup_failures_with_remedies(tmp_path: Path) -> None:
    write_metadata(tmp_path, package_manager="pnpm@10.0.0")

    checks = collect_checks(
        tmp_path,
        find_command=lambda command: "/usr/bin/tool" if command != "uv" else None,
        run=command_runner,
    )
    results = {check.name: check for check in checks}

    assert not results["command: uv"].passed
    assert not results["packageManager"].passed
    assert "expected pnpm@11.20.0" in results["packageManager"].detail
    assert "pnpm install --frozen-lockfile" in results["node_modules (vitest)"].detail
    assert "uv sync --frozen" in results[".venv (pytest)"].detail


def test_collect_checks_rejects_non_pnpm_package_manager(tmp_path: Path) -> None:
    write_metadata(tmp_path, package_manager="npm@11.20.0")

    checks = collect_checks(
        tmp_path,
        find_command=lambda _: "/usr/bin/tool",
        run=command_runner,
    )
    results = {check.name: check for check in checks}

    assert not results["packageManager"].passed
    assert "expected pnpm@11.20.0" in results["packageManager"].detail


def test_collect_checks_requires_project_local_tool_pins(tmp_path: Path) -> None:
    write_metadata(tmp_path)
    (tmp_path / "mise.toml").write_text(
        '[tools]\npython = "3.14.7"\nuv = "0.12.2"\n',
        encoding="utf-8",
    )

    checks = collect_checks(
        tmp_path,
        find_command=lambda _: "/usr/bin/tool",
        run=command_runner,
    )
    metadata = next(check for check in checks if check.name == "metadata")

    assert not metadata.passed
    assert "must pin project tools: node, pnpm" in metadata.detail


def test_collect_checks_rejects_empty_dependency_directories(tmp_path: Path) -> None:
    write_metadata(tmp_path)
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".venv").mkdir()
    write_lefthook_installation(tmp_path)

    checks = collect_checks(
        tmp_path,
        find_command=lambda _: "/usr/bin/tool",
        run=command_runner,
    )
    results = {check.name: check for check in checks}

    assert not results["node_modules (vitest)"].passed
    assert not results[".venv (pytest)"].passed


def test_collect_checks_rejects_stale_dependency_versions(tmp_path: Path) -> None:
    write_metadata(tmp_path)
    write_dependencies(tmp_path, node_version="4.0.0", python_version="9.0.0")
    write_lefthook_installation(tmp_path)

    checks = collect_checks(
        tmp_path,
        find_command=lambda _: "/usr/bin/tool",
        run=command_runner,
    )
    results = {check.name: check for check in checks}

    assert results["node_modules (vitest)"].detail.startswith("expected 4.1.10, found 4.0.0")
    assert results[".venv (pytest)"].detail.startswith("expected 9.1.1, found 9.0.0")


def test_collect_checks_requires_lefthook_config(tmp_path: Path) -> None:
    write_metadata(tmp_path)
    write_dependencies(tmp_path)
    write_lefthook_installation(tmp_path)
    (tmp_path / "lefthook.yml").unlink()
    checks = collect_checks(tmp_path, find_command=lambda _: "/usr/bin/tool", run=command_runner)
    result = next(check for check in checks if check.name == "Lefthook pre-commit config")
    assert not result.passed


def test_collect_checks_rejects_inert_lefthook_config(tmp_path: Path) -> None:
    write_metadata(tmp_path)
    write_dependencies(tmp_path)
    write_lefthook_installation(tmp_path)
    (tmp_path / "lefthook.yml").write_text("pre-commit: {}\n", encoding="utf-8")
    checks = collect_checks(tmp_path, find_command=lambda _: "/usr/bin/tool", run=command_runner)
    result = next(check for check in checks if check.name == "Lefthook pre-commit config")
    assert not result.passed


def test_collect_checks_requires_generated_lefthook_hook(tmp_path: Path) -> None:
    write_metadata(tmp_path)
    write_dependencies(tmp_path)
    write_lefthook_installation(tmp_path)
    (tmp_path / ".git/hooks/pre-commit").unlink()
    checks = collect_checks(tmp_path, find_command=lambda _: "/usr/bin/tool", run=command_runner)
    result = next(check for check in checks if check.name == "Lefthook generated pre-commit hook")
    assert not result.passed
    assert "pnpm prepare" in result.detail


def test_collect_checks_resolves_worktree_hook_through_git(tmp_path: Path) -> None:
    write_metadata(tmp_path)
    write_dependencies(tmp_path)
    write_lefthook_installation(tmp_path)
    shared_hook = tmp_path / "shared-hooks/pre-commit"
    shared_hook.parent.mkdir()
    shared_hook.write_text('#!/bin/sh\nlefthook run pre-commit -- "$@"\n', encoding="utf-8")
    shared_hook.chmod(0o755)

    def worktree_runner(command: tuple[str, ...] | list[str], root: Path) -> CommandResult:
        if tuple(command) == (
            "git",
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            "hooks/pre-commit",
        ):
            return CommandResult(0, f"{shared_hook}\n")
        return command_runner(command, root)

    checks = collect_checks(tmp_path, find_command=lambda _: "/usr/bin/tool", run=worktree_runner)
    result = next(check for check in checks if check.name == "Lefthook generated pre-commit hook")
    assert result.passed


def test_main_returns_nonzero_when_setup_is_incomplete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(tmp_path)]) == 1
    assert "FAIL metadata:" in capsys.readouterr().out
