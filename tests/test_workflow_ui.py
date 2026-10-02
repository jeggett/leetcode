import json
from pathlib import Path

import pytest

from scripts import lc


def problem(root: Path, language: str, number: str) -> Path:
    path = root / "src" / ("typescript" if language == "ts" else "python") / f"p_{number}_example"
    path.mkdir(parents=True)
    return path


def test_remembered_selection_precedes_branch_and_directory_precedes_selection(tmp_path):
    selected = problem(tmp_path, "py", "0035")
    caller = problem(tmp_path, "ts", "0001")
    lc.activate_problem(tmp_path, "py", "35")

    def fail_git(*_):
        pytest.fail("should not need git")

    assert lc.detect_problem_context(tmp_path, tmp_path, git_run=fail_git).directory == selected
    assert lc.detect_problem_context(tmp_path, caller, git_run=fail_git).directory == caller
    assert lc.build_command(["show", "ts", "1"], tmp_path, selected) == (
        "uv",
        "run",
        "python",
        "scripts/submission.py",
        "ts",
        "1",
    )


@pytest.mark.parametrize("command", ["test", "t", "live", "watch", "w"])
def test_focused_runner_arguments_survive_separator(tmp_path, command):
    directory = problem(tmp_path, "ts", "0035")
    result = lc.build_command([command, "--", "--help", "--", "boundary"], tmp_path, directory)
    assert result[-4:] == ("--", "--help", "--", "boundary")
    assert result[:5] == ("pnpm", "run", "test:one", "ts", "0035")


def test_focused_python_runner_arguments(tmp_path):
    directory = problem(tmp_path, "py", "0035")
    assert lc.build_command(["test", "--", "-k", "boundary"], tmp_path, directory)[-3:] == (
        "--",
        "-k",
        "boundary",
    )


def test_noninteractive_new_never_prompts(monkeypatch, capsys):
    monkeypatch.setattr(lc.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("must not prompt"))
    assert lc.main(["new"]) == 2
    assert "lc new URL" in capsys.readouterr().err


def test_no_argument_noninteractive_prints_active_and_help(tmp_path, monkeypatch, capsys):
    problem(tmp_path, "py", "0035")
    lc.activate_problem(tmp_path, "py", "35")
    monkeypatch.setattr(lc, "__file__", str(tmp_path / "scripts/lc.py"))
    monkeypatch.setenv("LC_CALLER_CWD", str(tmp_path))
    monkeypatch.setattr(lc.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("must not prompt"))
    assert lc.main([]) == 0
    output = capsys.readouterr().out
    assert "Active problem: 0035 (py)" in output
    assert "lc help" in output


def test_menu_enter_is_never_submission_and_named_actions_work(tmp_path, monkeypatch):
    problem(tmp_path, "ts", "0035")
    lc.activate_problem(tmp_path, "ts", "35")
    answers = iter(["", "test", "5", "0"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    calls = []
    monkeypatch.setattr(lc, "dispatch", lambda args, *_: calls.append(args) or 0)
    assert lc.menu(tmp_path, tmp_path) == 0
    assert calls == [["test"], ["done"]]


def test_menu_selection_overrides_original_caller_directory(tmp_path, monkeypatch, capsys):
    caller = problem(tmp_path, "ts", "0001")
    problem(tmp_path, "py", "0035")
    answers = iter(["select", "2", "0"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    assert lc.menu(tmp_path, caller) == 0
    selected = json.loads((tmp_path / ".lc/active.json").read_text())
    assert selected == {"language": "py", "problem_id": "0035"}
    assert "0035 example (py)" in capsys.readouterr().out


def test_new_prompts_for_language_and_url(monkeypatch):
    answers = iter(["https://leetcode.com/problems/two-sum/", "py"])
    monkeypatch.setattr(lc.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    assert lc.prompt_new() == ["py", "https://leetcode.com/problems/two-sum/"]


@pytest.mark.parametrize(
    "command", ["test", "live", "watch", "done", "finish", "show", "submit", "copy"]
)
def test_command_help_does_not_dispatch(command, monkeypatch, capsys):
    monkeypatch.setattr(lc, "dispatch", lambda *_: pytest.fail("help must not dispatch"))
    assert lc.main([command, "--help"]) == 0
    output = capsys.readouterr().out
    assert "lc " in output
    assert "guided menu" not in output


def test_help_after_runner_separator_is_forwarded(tmp_path, monkeypatch):
    directory = problem(tmp_path, "ts", "0035")
    monkeypatch.setattr(lc, "__file__", str(tmp_path / "scripts/lc.py"))
    monkeypatch.setenv("LC_CALLER_CWD", str(directory))
    calls = []
    monkeypatch.setattr(lc, "run_interactive_command", lambda args, *_: calls.append(args) or 0)
    assert lc.main(["test", "--", "--help"]) == 0
    assert calls[0][-2:] == ("--", "--help")


def test_typo_suggestion(tmp_path):
    with pytest.raises(lc.LcUsageError, match="lc done"):
        lc.build_command(["dnoe"], tmp_path, tmp_path)


def test_finish_alias_dispatches_done(tmp_path, monkeypatch):
    from scripts import done

    calls = []
    monkeypatch.setattr(done, "done_command", lambda args, *_: calls.append(args) or 0)
    assert lc.dispatch(["finish", "py", "35"], tmp_path, tmp_path) == 0
    assert calls == [["py", "35"]]


def test_manual_reopen_activates_without_overwriting(tmp_path, monkeypatch):
    directory = problem(tmp_path, "py", "0035")
    source = directory / f"{directory.name}.py"
    test = directory / f"test_{directory.name}.py"
    source.write_text("my solution")
    test.write_text("my tests")
    monkeypatch.setattr(lc, "preflight_git", lambda *_: "main")
    monkeypatch.setattr(lc, "run_interactive_command", lambda *_: pytest.fail("must not scaffold"))
    assert lc.dispatch(["new", "py", "35", "Example"], tmp_path, tmp_path) == 0
    assert source.read_text() == "my solution" and test.read_text() == "my tests"
    assert lc.detect_problem_context(tmp_path, tmp_path).directory == directory


@pytest.mark.parametrize("command", ["login", "logout"])
def test_session_commands_dispatch_arguments(tmp_path, monkeypatch, command):
    from scripts import leetcode_session

    calls = []
    monkeypatch.setattr(
        leetcode_session, f"{command}_command", lambda args, root: calls.append((args, root)) or 0
    )
    arguments = ["--check"] if command == "login" else []
    assert lc.dispatch([command, *arguments], tmp_path, tmp_path) == 0
    assert calls == [(arguments, tmp_path)]


@pytest.mark.parametrize("command", ["login", "logout"])
def test_session_help_never_dispatches(command, monkeypatch, capsys):
    monkeypatch.setattr(lc, "dispatch", lambda *_: pytest.fail("help must not dispatch"))
    assert lc.main([command, "--help"]) == 0
    assert f"lc {command}" in capsys.readouterr().out


def test_session_menu_actions_keep_existing_numbers(tmp_path, monkeypatch):
    answers = iter(["9", "logout", "5", "0"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    calls = []
    monkeypatch.setattr(lc, "dispatch", lambda args, *_: calls.append(args) or 0)
    assert lc.menu(tmp_path, tmp_path) == 0
    assert calls == [["login"], ["logout"], ["done"]]


@pytest.mark.parametrize("arguments", [[], ["--browser"]])
def test_done_backend_selection(tmp_path, monkeypatch, arguments):
    from scripts import done

    calls = []
    monkeypatch.setattr(done, "finish_problem", lambda *args, **kwargs: calls.append(kwargs) or 0)
    assert done.done_command(["py", "35", *arguments], tmp_path, tmp_path) == 0
    expected = {"resume": None, "retry_uncertain": False}
    if arguments:
        expected["browser_factory"] = done.LeetCodeBrowser
    assert calls == [expected]


def test_done_defaults_to_saved_session():
    from scripts import done

    assert done.finish_problem.__kwdefaults__["browser_factory"] is done.LeetCodeSession


def test_done_rejects_duplicate_browser_option(tmp_path):
    from scripts import done

    with pytest.raises(done.DoneError, match="--browser"):
        done.done_command(["py", "35", "--browser", "--browser"], tmp_path, tmp_path)


def test_noninteractive_session_check_does_not_prompt(tmp_path, monkeypatch):
    from scripts import leetcode_session

    monkeypatch.setattr(lc, "__file__", str(tmp_path / "scripts/lc.py"))
    monkeypatch.setenv("LC_CALLER_CWD", str(tmp_path))
    monkeypatch.setattr(lc.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("must not prompt"))
    calls = []
    monkeypatch.setattr(
        leetcode_session, "login_command", lambda args, root: calls.append((args, root)) or 0
    )
    assert lc.main(["login", "--check"]) == 0
    assert calls == [(["--check"], tmp_path)]


@pytest.mark.parametrize("command", ["list", "next"])
def test_practice_help_does_not_dispatch(command, monkeypatch, capsys):
    monkeypatch.setattr(lc, "dispatch", lambda *_: pytest.fail("help must not dispatch"))
    assert lc.main([command, "--help"]) == 0
    assert f"lc {command}" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["list", "next"])
def test_missing_practice_list_noninteractive_never_prompts(tmp_path, monkeypatch, command):
    monkeypatch.setattr(lc.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("must not prompt"))
    with pytest.raises(lc.LcUsageError, match="lc list URL"):
        lc.dispatch([command], tmp_path, tmp_path)


def test_menu_list_import_with_saved_snapshot_and_next(tmp_path, monkeypatch):
    from scripts import practice

    monkeypatch.setattr(practice, "load_list", lambda _: {"version": 1})
    answers = iter(["11", "1", "https://leetcode.com/problem-list/new/", "py", "12", "5", "0"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    calls = []
    monkeypatch.setattr(lc, "dispatch", lambda args, *_: calls.append(args) or 0)
    assert lc.menu(tmp_path, tmp_path) == 0
    assert calls == [
        ["list"],
        ["list", "py", "https://leetcode.com/problem-list/new/"],
        ["next"],
        ["done"],
    ]


def test_list_menu_can_replace_damaged_snapshot(tmp_path, monkeypatch, capsys):
    (tmp_path / ".lc").mkdir()
    (tmp_path / ".lc/practice.json").write_text("invalid JSON")
    answers = iter(["1", "https://leetcode.com/problem-list/new/", ""])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    calls = []
    monkeypatch.setattr(lc, "dispatch", lambda args, *_: calls.append(args) or 0)
    lc.list_menu(tmp_path)
    assert calls == [["list", "ts", "https://leetcode.com/problem-list/new/"]]
    assert "invalid local state" in capsys.readouterr().err
