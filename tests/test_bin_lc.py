from pathlib import Path


def test_doctor_bootstrap_disables_mise_auto_install() -> None:
    script = (Path(__file__).resolve().parents[1] / "bin/lc").read_text(encoding="utf-8")
    doctor_branch = script.split("doctor|d)", 1)[1].split("esac", 1)[0]

    assert 'exec "$DIRECT_PYTHON" "$REPOSITORY_ROOT/scripts/doctor.py"' in doctor_branch
    assert "command -v mise" in doctor_branch
    assert "MISE_AUTO_INSTALL=0 mise -C" in doctor_branch
    assert "env MISE_AUTO_INSTALL=0 mise -C" in doctor_branch
