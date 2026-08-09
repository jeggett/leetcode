from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.doctor import CommandResult, collect_checks, format_report, main, parse_version


def write_metadata(root: Path, *, package_manager: str = "pnpm@11.20.0") -> None:
    (root / "mise.toml").write_text(
        '[tools]\nnode = "26.7.0"\npnpm = "11.20.0"\npython = "3.14.7"\nuv = "0.12.2"\n',
        encoding="utf-8",
    )
    (root / "package.json").write_text(
        json.dumps(
            {
                "packageManager": package_manager,
                "engines": {"node": ">=22.13.0"},
            }
        ),
        encoding="utf-8",
    )


def command_runner(command: tuple[str, ...] | list[str], _: Path) -> CommandResult:
    outputs = {
        ("node", "--version"): "v26.7.0\n",
        ("pnpm", "--version"): "11.20.0\n",
        ("python", "--version"): "Python 3.14.7\n",
        ("uv", "--version"): "uv 0.12.2\n",
        ("git", "config", "--get", "core.hooksPath"): ".husky/_\n",
    }
    return CommandResult(0, outputs[tuple(command)])


def test_parse_version_accepts_common_version_command_output() -> None:
    assert parse_version("v26.7.0\n") == "26.7.0"
    assert parse_version("Python 3.14.7") == "3.14.7"
    assert parse_version("unversioned") is None


def test_collect_checks_reports_a_ready_checkout(tmp_path: Path) -> None:
    write_metadata(tmp_path)
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".venv").mkdir()

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
    assert "expected pnpm@11.20.0" in results["packageManager"].detail
    assert "pnpm install --frozen-lockfile" in results["node_modules"].detail
    assert "uv sync --frozen" in results[".venv"].detail


def test_collect_checks_requires_the_husky_hook_path(tmp_path: Path) -> None:
    write_metadata(tmp_path)
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".venv").mkdir()

    def wrong_hook_runner(command: tuple[str, ...] | list[str], cwd: Path) -> CommandResult:
        if tuple(command) == ("git", "config", "--get", "core.hooksPath"):
            return CommandResult(0, ".husky\n")
        return command_runner(command, cwd)

    checks = collect_checks(
        tmp_path,
        find_command=lambda _: "/usr/bin/tool",
        run=wrong_hook_runner,
    )
    hook = next(check for check in checks if check.name == "git core.hooksPath")

    assert not hook.passed
    assert "pnpm prepare" in hook.detail


def test_main_returns_nonzero_when_setup_is_incomplete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(tmp_path)]) == 1
    assert "FAIL metadata:" in capsys.readouterr().out
