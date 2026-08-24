from pathlib import Path

import pytest

from scripts.config import ConfigError, LcConfig, load_config


def test_config_uses_defaults_when_file_is_absent(tmp_path: Path) -> None:
    assert load_config(tmp_path) == LcConfig()


def test_config_reads_repository_and_practice_preferences(tmp_path: Path) -> None:
    (tmp_path / "lc.toml").write_text(
        """
[repository]
base_branch = "trunk"
[practice]
primary_language = "py"
default_minutes = 40
history_directory = ".lc/python-practice"
""",
        encoding="utf-8",
    )

    assert load_config(tmp_path) == LcConfig("trunk", "py", 40, ".lc/python-practice")


@pytest.mark.parametrize(
    "contents",
    [
        '[practice]\nprimary_language = "go"\n',
        "[practice]\ndefault_minutes = 0\n",
        '[practice]\nhistory_directory = "../outside"\n',
        '[practice]\nhistory_directory = ".local-practice"\n',
    ],
)
def test_config_rejects_unsafe_values(tmp_path: Path, contents: str) -> None:
    (tmp_path / "lc.toml").write_text(contents, encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_config_rejects_history_symlink_that_escapes_repository(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-practice"
    outside.mkdir()
    (tmp_path / ".lc").symlink_to(outside, target_is_directory=True)
    (tmp_path / "lc.toml").write_text('[practice]\nhistory_directory = ".lc"\n', encoding="utf-8")

    with pytest.raises(ConfigError, match="symlink"):
        load_config(tmp_path)
