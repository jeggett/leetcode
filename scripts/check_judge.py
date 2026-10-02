#!/usr/bin/env python3
"""Check rendered submissions and tests against the pinned LeetCode toolchain."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    from scripts.problem_paths import ProblemPathError, language_directory, resolve_problem_paths
    from scripts.submission import SubmissionError, read_submission
except ModuleNotFoundError:
    from problem_paths import ProblemPathError, language_directory, resolve_problem_paths
    from submission import SubmissionError, read_submission

JUDGE_TYPESCRIPT = "5.7.3"
Runner = Callable[..., subprocess.CompletedProcess[str]]


class JudgeCheckError(ValueError):
    """An unavailable or mismatched judge toolchain."""


def judge_node(root: Path, *, run: Runner = subprocess.run) -> Path:
    """Locate an already-installed runtime and verify its exact version."""
    version = (root / ".judge-node-version").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise JudgeCheckError(".judge-node-version must contain one exact Node version")
    remedy = f"run mise install node@{version} (or ./bin/setup --trust)"
    try:
        located = run(
            ["mise", "where", f"node@{version}"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if located.returncode or not located.stdout.strip():
            raise JudgeCheckError(f"judge Node {version} is unavailable; {remedy}")
        node = Path(located.stdout.strip()) / "bin" / "node"
        result = run(
            [str(node), "--version"], cwd=root, capture_output=True, text=True, check=False
        )
    except OSError as error:
        raise JudgeCheckError(f"cannot run judge Node {version}: {error}; {remedy}") from error
    if result.returncode or result.stdout.strip() != f"v{version}":
        raise JudgeCheckError(
            f"expected judge Node {version}, found {result.stdout.strip() or 'unavailable'}; {remedy}"
        )
    return node


def render_submissions(root: Path, destination: Path) -> list[Path]:
    """Use the normal renderer and path resolver for canonical and legacy problems."""
    problem_ids = set()
    for directory in sorted(language_directory(root, "ts").glob("p_*")):
        match = re.fullmatch(r"p_(\d+)_.+", directory.name)
        if directory.is_dir() and match:
            problem_ids.add(match.group(1))
    files = []
    for problem_id in sorted(problem_ids, key=int):
        paths = resolve_problem_paths(root, "ts", problem_id)
        output = destination / f"{paths.stem}.ts"
        output.write_text(read_submission(root, "ts", problem_id), encoding="utf-8")
        files.append(output)
    return files


def check_judge(root: Path, *, run: Runner = subprocess.run) -> int:
    """Typecheck isolated real submissions before running tests with judge Node."""
    node = judge_node(root, run=run)
    compiler = root / "node_modules/typescript-judge/bin/tsc"
    manifest = root / "node_modules/typescript-judge/package.json"
    vitest = root / "node_modules/vitest/vitest.mjs"
    try:
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise JudgeCheckError(
            "judge TypeScript is missing; run pnpm install --frozen-lockfile"
        ) from error
    if (
        not isinstance(metadata, dict)
        or metadata.get("name") != "typescript"
        or metadata.get("version") != JUDGE_TYPESCRIPT
    ):
        raise JudgeCheckError(
            f"judge TypeScript must be {JUDGE_TYPESCRIPT}; run pnpm install --frozen-lockfile"
        )
    if not compiler.is_file() or not vitest.is_file():
        raise JudgeCheckError(
            "judge compiler or Vitest is missing; run pnpm install --frozen-lockfile"
        )
    with TemporaryDirectory(prefix="leetcode-judge-") as temporary:
        destination = Path(temporary)
        files = render_submissions(root, destination)
        config = destination / "tsconfig.json"
        config.write_text(
            json.dumps(
                {
                    "compilerOptions": {
                        "alwaysStrict": True,
                        "strictBindCallApply": True,
                        "strictFunctionTypes": True,
                        "target": "ES2024",
                        "moduleDetection": "force",
                        "types": [],
                        "noEmit": True,
                    },
                    "files": [str(root / "src/typescript/judge-types.d.ts"), *map(str, files)],
                }
            ),
            encoding="utf-8",
        )
        print(f"Judge TypeScript {JUDGE_TYPESCRIPT}: {len(files)} rendered submissions", flush=True)
        result = run([str(node), str(compiler), "--project", str(config)], cwd=root, check=False)
        if result.returncode:
            return result.returncode
    print("Judge Node: running TypeScript tests", flush=True)
    return run([str(node), str(vitest), "run"], cwd=root, check=False).returncode


def main(argv: Sequence[str] | None = None) -> int:
    """Run the compatibility gate without installing tools or changing sources."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        print("usage: check_judge.py", file=sys.stderr)
        return 2
    try:
        return check_judge(Path(__file__).resolve().parents[1])
    except (JudgeCheckError, ProblemPathError, SubmissionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
