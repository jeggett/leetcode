import os
import subprocess
from pathlib import Path

import pytest


def test_doctor_bootstrap_disables_mise_auto_install() -> None:
    script = (Path(__file__).resolve().parents[1] / "bin/lc").read_text(encoding="utf-8")
    doctor_branch = script.split("doctor|d)", 1)[1].split("esac", 1)[0]

    assert "exec_direct_python -m scripts.doctor" in doctor_branch
    assert "command -v mise" in doctor_branch
    assert "MISE_AUTO_INSTALL=0 mise -C" in doctor_branch
    assert "env MISE_AUTO_INSTALL=0 mise -C" in doctor_branch


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [(["--help"], "the local LeetCode workflow"), (["test", "--help"], "usage: lc test")],
)
def test_help_bypasses_broken_version_manager_python_shims(
    tmp_path: Path, arguments: list[str], expected: str
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    fake_bin = tmp_path / "bin"
    shim_log = tmp_path / "shim.log"
    fake_bin.mkdir()
    for name in ("python", "python3"):
        shim = fake_bin / name
        shim.write_text(
            '#!/usr/bin/env sh\nprintf "%s\\n" "${MISE_AUTO_INSTALL-unset}" >> "$LC_TEST_SHIM_LOG"\nexit 127\n',
            encoding="utf-8",
        )
        shim.chmod(0o755)

    result = subprocess.run(
        [repository_root / "bin/lc", *arguments],
        cwd=repository_root,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "MISE_AUTO_INSTALL": "1",
            "LC_TEST_SHIM_LOG": str(shim_log),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert expected in result.stdout
    probes = shim_log.read_text(encoding="utf-8").splitlines()
    assert len(probes) >= 2
    assert set(probes) == {"0"}
