import sys
from pathlib import Path

from scripts import doctor


def test_reports_setup_prerequisites_and_missing_dependencies(tmp_path: Path) -> None:
    checks = doctor.collect_checks(tmp_path, find_command=lambda _: "/usr/bin/tool")
    assert all(available for name, available, _ in checks if name in doctor.COMMANDS)
    missing = {name: remedy for name, available, remedy in checks if not available}
    assert missing["@babel/parser"] == "run pnpm install --frozen-lockfile"
    assert missing[".venv/pytest"] == "run uv sync --frozen"


def test_reports_installed_files_without_a_version_or_platform_audit(tmp_path: Path) -> None:
    for package in doctor.NODE_PACKAGES:
        path = tmp_path / "node_modules" / package / "package.json"
        path.parent.mkdir(parents=True)
        path.write_text("{}")
    scripts = tmp_path / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
    scripts.mkdir(parents=True)
    suffix = ".exe" if sys.platform == "win32" else ""
    for name in ("python", "pytest", "ruff"):
        (scripts / f"{name}{suffix}").touch()
    checks = doctor.collect_checks(tmp_path, find_command=lambda _: "/usr/bin/tool")
    assert all(available for _, available, _ in checks)
    assert not (tmp_path / ".git").exists()


def test_main_reports_failure_and_next_steps(tmp_path: Path, capsys) -> None:
    assert doctor.main([str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "FAIL @babel/parser" in output
    assert "run pnpm install --frozen-lockfile" in output
    assert doctor.main(["--help"]) == 0
    assert doctor.main(["too", "many"]) == 2
