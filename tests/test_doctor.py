import json
import subprocess
import sys
from pathlib import Path

from scripts import doctor


def setup_project(root: Path) -> dict[str, str]:
    """Create a small, internally consistent set of project declarations."""
    node_packages = {
        "@babel/parser": "1.2.3",
        "@biomejs/biome": "2.3.4",
        "typescript": "3.4.5",
        "typescript-judge": "npm:typescript@4.5.6",
        "vitest": "5.6.7",
        "lefthook": "6.7.8",
    }
    (root / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@11.12.13",
                "engines": {"pnpm": "11.12.13"},
                "devDependencies": node_packages,
            }
        )
    )
    (root / "mise.toml").write_text(
        '[tools]\npnpm = "11.12.13"\npython = "3.15.2"\nuv = "0.13.6"\n'
    )
    (root / "pyproject.toml").write_text(
        '[dependency-groups]\ndev = ["pytest==9.2.0", "ruff==0.17.3"]\n'
    )
    (root / ".node-version").write_text("26.13.0\n")
    (root / ".python-version").write_text("3.15.2\n")
    (root / ".judge-node-version").write_text("22.14.0\n")

    for name, spec in node_packages.items():
        package_name, version = (
            spec.removeprefix("npm:").rsplit("@", 1) if spec.startswith("npm:") else (name, spec)
        )
        manifest = root / "node_modules" / name / "package.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"name": package_name, "version": version}))

    scripts = root / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
    scripts.mkdir(parents=True)
    suffix = ".exe" if sys.platform == "win32" else ""
    python_tools = {"python": "3.15.2", "pytest": "9.2.0", "ruff": "0.17.3"}
    for name in python_tools:
        (scripts / f"{name}{suffix}").touch()
    return {
        **{str(scripts / f"{name}{suffix}"): version for name, version in python_tools.items()},
        "/available/node": "26.13.0",
        "/available/pnpm": "11.12.13",
        "/available/python": "3.15.2",
        "/available/uv": "0.13.6",
        str(Path("/judge") / "bin" / f"node{suffix}"): "22.14.0",
    }


def available(command: str) -> str:
    return f"/available/{command}"


def fake_runner(versions: dict[str, str]):
    def run(command, **kwargs):
        assert kwargs["env"]["MISE_AUTO_INSTALL"] == "0"
        assert kwargs["timeout"] == 5
        if command[0] == "/available/mise":
            assert command[1:] == ["where", "node@22.14.0"]
            return subprocess.CompletedProcess(command, 0, stdout="/judge\n", stderr="")
        return subprocess.CompletedProcess(
            command, 0, stdout=versions.get(command[0], "") + "\n", stderr=""
        )

    return run


def test_reports_matching_declared_versions(tmp_path: Path) -> None:
    versions = setup_project(tmp_path)
    checks = doctor.collect_checks(tmp_path, find_command=available, run=fake_runner(versions))

    assert all(passed for _, passed, _ in checks)
    details = {name: detail for name, _, detail in checks}
    assert details["node"] == "found 26.13.0"
    assert details["typescript-judge"] == "found 4.5.6"
    assert details[".venv/python"] == "found 3.15.2"
    assert details["judge node"] == "found 22.14.0"


def test_reports_version_drift_and_repairs(tmp_path: Path) -> None:
    versions = setup_project(tmp_path)
    versions["/available/pnpm"] = "10.0.0"
    versions[str(next((tmp_path / ".venv").rglob("pytest*")))] = "8.0.0"
    (tmp_path / "node_modules" / "@babel/parser" / "package.json").unlink()
    suffix = ".exe" if sys.platform == "win32" else ""
    versions[str(Path("/judge") / "bin" / f"node{suffix}")] = "20.0.0"

    checks = doctor.collect_checks(tmp_path, find_command=available, run=fake_runner(versions))
    failures = {name: detail for name, passed, detail in checks if not passed}
    assert failures["pnpm"] == "expected 11.12.13, found 10.0.0; run mise install"
    assert failures["@babel/parser"] == (
        "expected 1.2.3, found unavailable; run pnpm install --frozen-lockfile"
    )
    assert failures[".venv/pytest"] == "expected 9.2.0, found 8.0.0; run uv sync --frozen"
    assert failures["judge node"] == (
        "expected 22.14.0, found 20.0.0; run mise install node@22.14.0"
    )


def test_handles_unavailable_or_timed_out_commands(tmp_path: Path) -> None:
    versions = setup_project(tmp_path)
    run_normal = fake_runner(versions)

    def run(command, **kwargs):
        if command[0] == "/available/uv":
            raise subprocess.TimeoutExpired(command, 5)
        return run_normal(command, **kwargs)

    checks = doctor.collect_checks(
        tmp_path,
        find_command=lambda name: None if name == "mise" else available(name),
        run=run,
    )
    failures = {name: detail for name, passed, detail in checks if not passed}
    assert failures["mise"] == "install mise"
    assert failures["uv"] == "expected 0.13.6, found unavailable; run mise install"
    assert failures["judge node"] == (
        "expected 22.14.0, found unavailable; run mise install node@22.14.0"
    )


def test_main_help_and_usage() -> None:
    assert doctor.main(["--help"]) == 0
    assert doctor.main(["too", "many"]) == 2
