"""Bridge Python workflow commands to the shared TypeScript parser."""

import subprocess
from pathlib import Path


def typescript_command(operation: str, source: str) -> str:
    result = subprocess.run(
        ["node", str(Path(__file__).with_suffix(".mjs")), operation],
        input=source,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or "TypeScript parsing failed")
    return result.stdout
