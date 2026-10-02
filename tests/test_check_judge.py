from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.check_judge import JudgeCheckError, check_judge, judge_node, render_submissions


def fixture_root(root: Path) -> None:
    (root / ".judge-node-version").write_text("22.14.0\n")
    for package, entrypoint in (("typescript-judge", "bin/tsc"), ("vitest", "vitest.mjs")):
        location = root / "node_modules" / package
        (location / entrypoint).parent.mkdir(parents=True, exist_ok=True)
        (location / entrypoint).touch()
        (location / "package.json").write_text(
            json.dumps({"name": "typescript", "version": "5.7.3"})
        )
    types = root / "src/typescript"
    types.mkdir(parents=True)
    (types / "judge-types.d.ts").write_text("declare class ListNode {}\n")
    for number in (1, 2):
        directory = types / f"p_{number:04d}_sample"
        directory.mkdir()
        (directory / f"{directory.name}.ts").write_text(
            "export function solve(): number { return 1; }\n"
        )


def test_render_uses_real_submission_exports_and_legacy_paths(tmp_path: Path) -> None:
    fixture_root(tmp_path)
    directory = tmp_path / "src/typescript/p_0001_sample"
    directory.rename(directory.with_name("p_1_sample"))
    directory = directory.with_name("p_1_sample")
    (directory / "p_0001_sample.ts").rename(directory / "p_1_sample.ts")
    destination = tmp_path / "rendered"
    destination.mkdir()
    files = render_submissions(tmp_path, destination)
    assert len(files) == 2
    assert all("export" not in path.read_text() for path in files)


@pytest.mark.parametrize("compiler_status,runtime_status", [(2, 0), (0, 3), (0, 0)])
def test_check_configuration_and_failure_propagation(
    tmp_path: Path, compiler_status: int, runtime_status: int
) -> None:
    fixture_root(tmp_path)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[:2] == ["mise", "where"]:
            return subprocess.CompletedProcess(command, 0, "/tmp/judge", "")
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "v22.14.0\n", "")
        if "--project" in command:
            config = json.loads(Path(command[-1]).read_text())
            assert config["compilerOptions"] == {
                "alwaysStrict": True,
                "strictBindCallApply": True,
                "strictFunctionTypes": True,
                "target": "ES2024",
                "moduleDetection": "force",
                "types": [],
                "noEmit": True,
            }
            assert len(config["files"]) == 3
            assert all("export" not in Path(file).read_text() for file in config["files"][1:])
            return subprocess.CompletedProcess(command, compiler_status)
        assert command == [
            "/tmp/judge/bin/node",
            str(tmp_path / "node_modules/vitest/vitest.mjs"),
            "run",
        ]
        return subprocess.CompletedProcess(command, runtime_status)

    assert check_judge(tmp_path, run=run) == (compiler_status or runtime_status)
    assert any(command[-1] == "run" for command in calls) == (compiler_status == 0)


@pytest.mark.parametrize("located,version", [(1, "v22.14.0"), (0, "v26.7.0")])
def test_judge_node_requires_installed_exact_runtime(
    tmp_path: Path, located: int, version: str
) -> None:
    (tmp_path / ".judge-node-version").write_text("22.14.0\n")

    def run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            located if command[0] == "mise" else 0,
            "/tmp/node" if command[0] == "mise" else version,
            "",
        )

    with pytest.raises(JudgeCheckError, match="mise install node@22.14.0"):
        judge_node(tmp_path, run=run)


def test_real_compiler_isolates_scopes_and_rejects_test_globals(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    compiler = repository / "node_modules/typescript-judge/bin/tsc"
    if not compiler.is_file():
        pytest.skip("pinned judge compiler is not installed")
    fixture_root(tmp_path)
    destination = tmp_path / "rendered"
    destination.mkdir()
    files = render_submissions(tmp_path, destination)
    config = destination / "tsconfig.json"
    config.write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "types": [],
                    "moduleDetection": "force",
                    "target": "ES2024",
                    "noEmit": True,
                },
                "files": list(map(str, files)),
            }
        )
    )
    command = ["node", str(compiler), "--project", str(config)]
    assert subprocess.run(command, capture_output=True).returncode == 0
    files[0].write_text(files[0].read_text() + "describe('leak', () => {});\n")
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Cannot find name 'describe'" in result.stdout


@pytest.mark.parametrize("manifest", [[], None, {"name": "typescript", "version": "7.0.2"}])
def test_check_rejects_invalid_compiler_metadata(tmp_path: Path, manifest) -> None:
    fixture_root(tmp_path)
    (tmp_path / "node_modules/typescript-judge/package.json").write_text(json.dumps(manifest))

    def run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 0, "/tmp/judge" if command[0] == "mise" else "v22.14.0", ""
        )

    with pytest.raises(JudgeCheckError, match="pnpm install --frozen-lockfile"):
        check_judge(tmp_path, run=run)
