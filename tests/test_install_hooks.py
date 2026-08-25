from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from scripts.install_hooks import main


def completed(returncode: int, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


def test_skips_installation_outside_git_worktree() -> None:
    with patch("scripts.install_hooks.subprocess.run", return_value=completed(128)) as run:
        assert main() == 0
    assert run.call_count == 1


def test_installs_lefthook_inside_git_worktree() -> None:
    with patch(
        "scripts.install_hooks.subprocess.run",
        side_effect=[completed(0, "true\n"), completed(0)],
    ) as run:
        assert main() == 0
    assert run.call_args_list[1].args[0] == [
        "lefthook",
        "install",
        "--reset-hooks-path",
    ]
    assert run.call_args_list[1].kwargs["cwd"] == Path(__file__).resolve().parent.parent


def test_propagates_lefthook_installation_failure() -> None:
    with patch(
        "scripts.install_hooks.subprocess.run",
        side_effect=[completed(0, "true\n"), completed(1)],
    ):
        assert main() == 1
