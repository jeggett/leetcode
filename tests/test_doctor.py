from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts import doctor
from scripts.doctor import CommandResult, collect_checks, format_report, main, parse_version


def write_metadata(root: Path, *, package_manager: str = "pnpm@11.20.0") -> None:
    (root / ".node-version").write_text("26.7.0\n", encoding="utf-8")
    (root / "mise.toml").write_text(
        '[tools]\npython = "3.14.7"\nuv = "0.12.2"\n',
        encoding="utf-8",
    )
    (root / "package.json").write_text(
        json.dumps(
            {
                "packageManager": package_manager,
                "engines": {"node": ">=22.13.0"},
                "devDependencies": {"vitest": "4.1.10"},
            }
        ),
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[dependency-groups]\ndev = ["pytest==9.1.1"]\n',
        encoding="utf-8",
    )


def write_dependencies(
    root: Path, *, node_version: str = "4.1.10", python_version: str = "9.1.1"
) -> None:
    node_dependency = root / "node_modules" / "vitest"
    node_dependency.mkdir(parents=True)
    (node_dependency / "package.json").write_text(
        json.dumps({"name": "vitest", "version": node_version}),
        encoding="utf-8",
    )

    site_packages = root / ".venv" / "lib" / "python3.14" / "site-packages"
    pytest_package = site_packages / "pytest"
    pytest_package.mkdir(parents=True)
    (pytest_package / "__init__.py").write_text("", encoding="utf-8")
    metadata_directory = site_packages / f"pytest-{python_version}.dist-info"
    metadata_directory.mkdir()
    (metadata_directory / "METADATA").write_text(
        f"Metadata-Version: 2.4\nName: pytest\nVersion: {python_version}\n",
        encoding="utf-8",
    )


def write_husky_installation(root: Path) -> None:
    source_hook = root / ".husky" / "pre-commit"
    source_hook.parent.mkdir(parents=True)
    source_hook.write_text("mise exec -- pnpm ready\n", encoding="utf-8")

    husky_directory = root / ".husky" / "_"
    husky_directory.mkdir(parents=True)
    generated_hook = husky_directory / "pre-commit"
    generated_hook.write_text(
        '#!/usr/bin/env sh\n. "$(dirname "$0")/h"\n',
        encoding="utf-8",
    )
    launcher = husky_directory / "h"
    launcher.write_text(
        "#!/usr/bin/env sh\n"
        'n=$(basename "$0")\n'
        's=$(dirname "$(dirname "$0")")/$n\n'
        'sh -e "$s" "$@"\n',
        encoding="utf-8",
    )
    if os.name == "posix":
        generated_hook.chmod(0o755)
        launcher.chmod(0o755)


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
    write_dependencies(tmp_path)
    write_husky_installation(tmp_path)

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
    assert not results["pnpm version"].passed
    assert "expected 10.0.0, found 11.20.0" in results["pnpm version"].detail
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
    assert "expected pnpm@<version>" in results["packageManager"].detail
    assert not results["pnpm version"].passed
    assert "not pinned in package.json packageManager" in results["pnpm version"].detail


def test_collect_checks_rejects_a_pnpm_pin_in_mise(tmp_path: Path) -> None:
    write_metadata(tmp_path)
    (tmp_path / "mise.toml").write_text(
        '[tools]\npnpm = "11.20.0"\npython = "3.14.7"\nuv = "0.12.2"\n',
        encoding="utf-8",
    )

    checks = collect_checks(
        tmp_path,
        find_command=lambda _: "/usr/bin/tool",
        run=command_runner,
    )
    metadata = next(check for check in checks if check.name == "metadata")

    assert not metadata.passed
    assert "must not pin pnpm" in metadata.detail


def test_collect_checks_requires_the_husky_hook_path(tmp_path: Path) -> None:
    write_metadata(tmp_path)
    write_dependencies(tmp_path)
    write_husky_installation(tmp_path)

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


def test_collect_checks_rejects_empty_dependency_directories(tmp_path: Path) -> None:
    write_metadata(tmp_path)
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".venv").mkdir()
    write_husky_installation(tmp_path)

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
    write_husky_installation(tmp_path)

    checks = collect_checks(
        tmp_path,
        find_command=lambda _: "/usr/bin/tool",
        run=command_runner,
    )
    results = {check.name: check for check in checks}

    assert results["node_modules (vitest)"].detail.startswith("expected 4.1.10, found 4.0.0")
    assert results[".venv (pytest)"].detail.startswith("expected 9.1.1, found 9.0.0")


@pytest.mark.parametrize(
    ("missing_path", "check_name", "remedy"),
    [
        (
            Path(".husky/pre-commit"),
            "Husky source pre-commit hook",
            "restore .husky/pre-commit",
        ),
        (Path(".husky/_/pre-commit"), "Husky generated pre-commit hook", "pnpm prepare"),
        (Path(".husky/_/h"), "Husky launcher", "pnpm prepare"),
    ],
)
def test_collect_checks_requires_husky_hook_files(
    tmp_path: Path, missing_path: Path, check_name: str, remedy: str
) -> None:
    write_metadata(tmp_path)
    write_dependencies(tmp_path)
    write_husky_installation(tmp_path)
    (tmp_path / missing_path).unlink()

    checks = collect_checks(
        tmp_path,
        find_command=lambda _: "/usr/bin/tool",
        run=command_runner,
    )
    result = next(check for check in checks if check.name == check_name)

    assert not result.passed
    assert remedy in result.detail


@pytest.mark.parametrize(
    ("path", "contents", "check_name"),
    [
        (
            Path(".husky/_/pre-commit"),
            "#!/usr/bin/env sh\nexit 0\n",
            "Husky generated pre-commit hook",
        ),
        (Path(".husky/_/h"), "#!/usr/bin/env sh\nexit 0\n", "Husky launcher"),
    ],
)
def test_collect_checks_rejects_inert_husky_generated_files(
    tmp_path: Path, path: Path, contents: str, check_name: str
) -> None:
    write_metadata(tmp_path)
    write_dependencies(tmp_path)
    write_husky_installation(tmp_path)
    target = tmp_path / path
    target.write_text(contents, encoding="utf-8")
    if os.name == "posix":
        target.chmod(0o755)

    checks = collect_checks(
        tmp_path,
        find_command=lambda _: "/usr/bin/tool",
        run=command_runner,
    )
    result = next(check for check in checks if check.name == check_name)

    assert not result.passed
    assert "pnpm prepare" in result.detail


@pytest.mark.parametrize(
    "contents",
    [
        "exit 0\n",
        "exit 0\nmise exec -- pnpm ready\n",
    ],
)
def test_collect_checks_rejects_inert_husky_source_hook(tmp_path: Path, contents: str) -> None:
    write_metadata(tmp_path)
    write_dependencies(tmp_path)
    write_husky_installation(tmp_path)
    (tmp_path / ".husky" / "pre-commit").write_text(contents, encoding="utf-8")

    checks = collect_checks(
        tmp_path,
        find_command=lambda _: "/usr/bin/tool",
        run=command_runner,
    )
    result = next(check for check in checks if check.name == "Husky source pre-commit hook")

    assert not result.passed
    assert "mise exec -- pnpm ready" in result.detail


@pytest.mark.skipif(os.name != "posix", reason="POSIX executable bits are unavailable")
@pytest.mark.parametrize(
    ("path", "check_name"),
    [
        (Path(".husky/_/pre-commit"), "Husky generated pre-commit hook"),
        (Path(".husky/_/h"), "Husky launcher"),
    ],
)
def test_collect_checks_requires_executable_generated_husky_files(
    tmp_path: Path,
    path: Path,
    check_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_metadata(tmp_path)
    write_dependencies(tmp_path)
    write_husky_installation(tmp_path)
    target = tmp_path / path
    monkeypatch.setattr(
        doctor.os,
        "access",
        lambda candidate, mode: Path(candidate) != target or mode != os.X_OK,
    )

    checks = collect_checks(
        tmp_path,
        find_command=lambda _: "/usr/bin/tool",
        run=command_runner,
    )
    result = next(check for check in checks if check.name == check_name)

    assert not result.passed
    assert "not executable" in result.detail


def test_main_returns_nonzero_when_setup_is_incomplete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(tmp_path)]) == 1
    assert "FAIL metadata:" in capsys.readouterr().out
