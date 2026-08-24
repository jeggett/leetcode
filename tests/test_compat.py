import json
from pathlib import Path

import pytest

from scripts.compat import JudgeProfile, compatibility_issues, format_report


def write_profile(
    root: Path,
    *,
    node: str = "26.7.0",
    typescript: str = "5.7.3",
    target: str = "ES2024",
) -> None:
    (root / ".node-version").write_text(f"{node}\n", encoding="utf-8")
    (root / ".python-version").write_text("3.14.7\n", encoding="utf-8")
    (root / "package.json").write_text(
        json.dumps({"devDependencies": {"typescript": typescript}}), encoding="utf-8"
    )
    (root / "mise.toml").write_text(
        f'[tools]\nnode = "{node}"\npython = "3.14.7"\n', encoding="utf-8"
    )
    (root / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"target": target}}), encoding="utf-8"
    )
    (root / "lc.toml").write_text(
        f'[compatibility]\nnode = "{node}"\ntypescript = "{typescript}"\n'
        f'python = "3.14"\ntarget = "{target}"\n',
        encoding="utf-8",
    )


def test_compatibility_profile_accepts_matching_repository(tmp_path: Path) -> None:
    write_profile(tmp_path)

    assert compatibility_issues(tmp_path) == []
    assert "Compatibility: ready" in format_report([])


def test_compatibility_profile_reports_every_actionable_mismatch(tmp_path: Path) -> None:
    write_profile(tmp_path, node="22.14.0", typescript="7.0.2")
    (tmp_path / ".python-version").write_text("3.13.1\n", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"target": "ESNext"}}), encoding="utf-8"
    )

    issues = compatibility_issues(tmp_path, JudgeProfile())

    assert any("Node must be 26.7.0" in issue for issue in issues)
    assert any("TypeScript must be 5.7.3" in issue for issue in issues)
    assert any("Python must use 3.14.x" in issue for issue in issues)
    assert any("target must be ES2024" in issue for issue in issues)


def test_lc_profile_is_the_source_of_truth(tmp_path: Path) -> None:
    write_profile(tmp_path, node="20.11.1", typescript="5.8.2", target="ESNext")

    assert compatibility_issues(tmp_path) == []

    (tmp_path / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"target": "ES2024"}}), encoding="utf-8"
    )
    issues = compatibility_issues(tmp_path)
    assert issues == ["TypeScript target must be ESNext; found ES2024"]


@pytest.mark.parametrize(
    ("path", "contents", "message"),
    [
        (
            "lc.toml",
            '[compatibility]\nnode = []\ntypescript = "5.7.3"\npython = "3.14"\ntarget = "ES2024"\n',
            "lc.toml [compatibility] node must be a non-empty string",
        ),
        ("package.json", "[]\n", "package.json must contain a JSON object"),
        (
            "package.json",
            '{"devDependencies": []}\n',
            "package.json devDependencies must be an object/table",
        ),
        ("mise.toml", "tools = []\n", "mise.toml tools must be an object/table"),
        (
            "tsconfig.json",
            '{"compilerOptions": []}\n',
            "tsconfig.json compilerOptions must be an object/table",
        ),
    ],
)
def test_compatibility_rejects_malformed_container_shapes(
    tmp_path: Path, path: str, contents: str, message: str
) -> None:
    write_profile(tmp_path)
    (tmp_path / path).write_text(contents, encoding="utf-8")

    issues = compatibility_issues(tmp_path)

    assert issues == [message]
