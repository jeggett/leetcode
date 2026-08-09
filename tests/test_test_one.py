import subprocess
from pathlib import Path

import pytest

from scripts import test_one
from scripts.test_one import TestOneError, focused_command, parse_arguments, run_focused_test


def make_test(root: Path, language: str) -> Path:
    stem = "p_0092_reverse_linked_list_ii"
    directory = root / "src" / ("python" if language == "py" else "typescript") / stem
    directory.mkdir(parents=True)
    name = f"test_{stem}.py" if language == "py" else f"{stem}.test.ts"
    path = directory / name
    path.write_text("test", encoding="utf-8")
    return path


def test_parses_test_one_arguments_and_rejects_python_watch() -> None:
    assert parse_arguments(["ts", "92", "--watch"]) == ("ts", "92", True)
    assert parse_arguments(["py", "92"]) == ("py", "92", False)
    with pytest.raises(TestOneError, match="only supported for TypeScript"):
        parse_arguments(["py", "92", "--watch"])


@pytest.mark.parametrize(
    "arguments, message",
    [
        ([], "usage:"),
        (["go", "1"], "language"),
        (["ts", "1", "--other"], "unknown option"),
        (["ts", "1", "--watch", "--watch"], "only be provided once"),
    ],
)
def test_rejects_invalid_test_one_arguments(arguments: list[str], message: str) -> None:
    with pytest.raises(TestOneError, match=message):
        parse_arguments(arguments)


def test_builds_existing_focused_runner_commands(tmp_path: Path) -> None:
    typescript_test = make_test(tmp_path, "ts")
    python_test = make_test(tmp_path, "py")

    assert focused_command(tmp_path, "ts", "92") == [
        "pnpm",
        "test:ts",
        str(typescript_test.relative_to(tmp_path)),
    ]
    assert focused_command(tmp_path, "ts", "92", watch=True) == [
        "pnpm",
        "test:ts:watch",
        str(typescript_test.relative_to(tmp_path)),
    ]
    assert focused_command(tmp_path, "py", "92") == [
        "pnpm",
        "test:py",
        str(python_test.relative_to(tmp_path)),
    ]


def test_builds_a_focused_command_for_a_legacy_python_test_name(tmp_path: Path) -> None:
    stem = "p_1512_number_of_good_pairs"
    directory = tmp_path / "src/python" / stem
    directory.mkdir(parents=True)
    legacy_test = directory / "test_1512_number_of_good_pairs.py"
    legacy_test.write_text("test", encoding="utf-8")

    assert focused_command(tmp_path, "py", "1512") == [
        "pnpm",
        "test:py",
        str(legacy_test.relative_to(tmp_path)),
    ]


def test_builds_a_focused_command_for_an_unpadded_legacy_typescript_directory(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "src/typescript/p_457_circular_array_loop"
    directory.mkdir(parents=True)
    test_path = directory / "p_457_circular_array_loop.test.ts"
    test_path.write_text("test", encoding="utf-8")

    assert focused_command(tmp_path, "ts", "457") == [
        "pnpm",
        "test:ts",
        str(test_path.relative_to(tmp_path)),
    ]


def test_run_focused_test_uses_root_as_working_directory(tmp_path: Path) -> None:
    make_test(tmp_path, "ts")
    calls: list[tuple[object, object]] = []

    def fake_run(command: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 7, "", "")

    assert run_focused_test(tmp_path, "ts", "92", run=fake_run) == 7
    assert calls == [
        (
            [
                "pnpm",
                "test:ts",
                "src/typescript/p_0092_reverse_linked_list_ii/p_0092_reverse_linked_list_ii.test.ts",
            ],
            {"cwd": tmp_path, "check": False},
        )
    ]


def test_main_returns_runner_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_test(tmp_path, "py")
    monkeypatch.setattr(test_one, "__file__", str(tmp_path / "scripts" / "test_one.py"))
    monkeypatch.setattr(test_one, "run_focused_test", lambda *_arguments: 3)

    assert test_one.main(["py", "92"]) == 3
