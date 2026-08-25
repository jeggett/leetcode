"""Install repository hooks when running inside a Git worktree."""

from __future__ import annotations

import subprocess
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    worktree = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if worktree.returncode != 0 or worktree.stdout.strip() != "true":
        return 0
    return subprocess.run(
        ["lefthook", "install", "--reset-hooks-path"], cwd=root, check=False
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
