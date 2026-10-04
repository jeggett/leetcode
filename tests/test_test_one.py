import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts import test_one
from scripts.test_one import (
    TestOneArguments,
    TestOneError,
    focused_command,
    parse_invocation,
    run_focused_test,
)


def make_test(root: Path, language: str) -> Path:
    stem = "p_0092_reverse_linked_list_ii"
    directory = root / "src" / ("python" if language == "py" else "typescript") / stem
    directory.mkdir(parents=True)
    name = f"test_{stem}.py" if language == "py" else f"{stem}.test.ts"
    path = directory / name
    path.write_text("test", encoding="utf-8")
    return path


def test_parses_test_one_arguments() -> None:
    assert parse_invocation(["ts", "92", "--watch"]) == TestOneArguments("ts", "92", True)
    assert parse_invocation(["py", "92"]) == TestOneArguments("py", "92", False)


def test_parse_invocation_preserves_runner_arguments() -> None:
    assert parse_invocation(["ts", "92", "--watch", "--", "--run", "search"]) == (
        TestOneArguments("ts", "92", True, ("--run", "search"))
    )
    assert parse_invocation(["py", "92", "--maxfail=1", "-q"]) == TestOneArguments(
        "py", "92", False, ("--maxfail=1", "-q")
    )


@pytest.mark.parametrize(
    "arguments, message",
    [
        ([], "usage:"),
        (["go", "1"], "language"),
        (["ts", "1", "--watch", "--watch"], "only be provided once"),
    ],
)
def test_rejects_invalid_test_one_arguments(arguments: list[str], message: str) -> None:
    with pytest.raises(TestOneError, match=message):
        parse_invocation(arguments)


def test_builds_existing_focused_runner_commands(tmp_path: Path) -> None:
    typescript_test = make_test(tmp_path, "ts")
    python_test = make_test(tmp_path, "py")

    assert focused_command(tmp_path, "ts", "92") == [
        "pnpm",
        "run",
        "test:ts",
        str(typescript_test.relative_to(tmp_path)),
    ]
    assert focused_command(tmp_path, "ts", "92", watch=True) == [
        "pnpm",
        "run",
        "test:ts:watch",
        str(typescript_test.relative_to(tmp_path)),
    ]
    assert focused_command(tmp_path, "py", "92") == [
        "pnpm",
        "run",
        "test:py",
        str(python_test.relative_to(tmp_path)),
    ]
    with pytest.raises(TestOneError, match="only supported for TypeScript"):
        focused_command(tmp_path, "py", "92", watch=True)
    assert focused_command(
        tmp_path,
        "ts",
        "92",
        runner_args=("--run", "search"),
    ) == [
        "pnpm",
        "run",
        "test:ts",
        str(typescript_test.relative_to(tmp_path)),
        "--run",
        "search",
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
                "run",
                "test:ts",
                "src/typescript/p_0092_reverse_linked_list_ii/p_0092_reverse_linked_list_ii.test.ts",
            ],
            {"cwd": tmp_path, "check": False},
        )
    ]


def test_run_focused_test_forwards_args_to_an_executed_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_path = make_test(tmp_path, "py")
    executable_dir = tmp_path / "bin"
    executable_dir.mkdir()
    capture_path = tmp_path / "runner-args.json"
    fake_pnpm = executable_dir / "pnpm"
    fake_pnpm.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

Path(os.environ["LC_TEST_ONE_CAPTURE"]).write_text(
    json.dumps(sys.argv[1:]), encoding="utf-8"
)
raise SystemExit(13)
""",
        encoding="utf-8",
    )
    fake_pnpm.chmod(0o755)
    monkeypatch.setenv("LC_TEST_ONE_CAPTURE", str(capture_path))
    monkeypatch.setenv("PATH", f"{executable_dir}{os.pathsep}{os.environ['PATH']}")

    assert (
        run_focused_test(
            tmp_path,
            "py",
            "92",
            runner_args=("--maxfail=1", "-q"),
        )
        == 13
    )
    assert json.loads(capture_path.read_text(encoding="utf-8")) == [
        "run",
        "test:py",
        str(test_path.relative_to(tmp_path)),
        "--maxfail=1",
        "-q",
    ]


def test_main_returns_runner_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_test(tmp_path, "py")
    monkeypatch.setattr(test_one, "__file__", str(tmp_path / "scripts" / "test_one.py"))
    monkeypatch.setattr(test_one, "run_focused_test", lambda *_arguments, **_kwargs: 3)

    assert test_one.main(["py", "92"]) == 3


def test_main_forwards_watch_and_runner_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_test(tmp_path, "ts")
    monkeypatch.setattr(test_one, "__file__", str(tmp_path / "scripts" / "test_one.py"))
    calls: list[tuple[object, ...]] = []

    def fake_run(*arguments: object, **kwargs: object) -> int:
        calls.append((*arguments, kwargs))
        return 0

    monkeypatch.setattr(test_one, "run_focused_test", fake_run)

    assert test_one.main(["ts", "92", "--watch", "--", "--run", "search"]) == 0
    assert calls == [
        (
            tmp_path,
            "ts",
            "92",
            True,
            {"runner_args": ("--run", "search")},
        )
    ]
