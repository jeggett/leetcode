import os
import subprocess
from pathlib import Path


def test_doctor_bootstrap_disables_mise_auto_install() -> None:
    script = (Path(__file__).resolve().parents[1] / "bin/lc").read_text(encoding="utf-8")
    doctor_branch = script.split("doctor|d)", 1)[1].split("esac", 1)[0]

    assert 'exec_direct_python "$REPOSITORY_ROOT/scripts/doctor.py"' in doctor_branch
    assert "command -v mise" in doctor_branch
    assert "MISE_AUTO_INSTALL=0 mise -C" in doctor_branch
    assert "env MISE_AUTO_INSTALL=0 mise -C" in doctor_branch


def test_help_bypasses_broken_version_manager_python_shims(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("python", "python3"):
        shim = fake_bin / name
        shim.write_text("#!/usr/bin/env sh\nexit 127\n", encoding="utf-8")
        shim.chmod(0o755)

    result = subprocess.run(
        [repository_root / "bin/lc", "--help"],
        cwd=repository_root,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "the local LeetCode workflow" in result.stdout
