#!/usr/bin/env python3
"""Create a solution and test skeleton for a LeetCode problem."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Sequence


class ScaffoldError(ValueError):
    """Raised when a scaffold request cannot be completed."""


LEETCODE_PROBLEM_URL = re.compile(r"^https://leetcode\.com/problems/[a-z0-9]+(?:-[a-z0-9]+)*/$")


def normalize_problem_id(value: str) -> str:
    """Return a positive numeric ID padded to at least four digits."""
    number = value.strip().removesuffix(".")
    if not number.isdecimal():
        raise ScaffoldError("problem number must be a positive integer")
    try:
        problem_id = int(number)
    except ValueError as error:
        raise ScaffoldError("problem number must be a positive integer") from error
    if problem_id <= 0:
        raise ScaffoldError("problem number must be a positive integer")
    return f"{problem_id:04d}"


def slugify(title: str) -> str:
    """Convert a title to an ASCII lowercase underscore slug."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_title.lower()).strip("_")
    if not slug:
        raise ScaffoldError("title must contain at least one letter or number")
    return slug


def normalize_display_title(title_parts: Sequence[str]) -> str:
    """Return a single-line title suitable for source comments and metadata."""
    title = re.sub(r"\s+", " ", " ".join(title_parts)).strip()
    if not title:
        raise ScaffoldError("title is required")
    return title


def validate_problem_url(value: str) -> str:
    """Return a canonical LeetCode problem URL or raise a helpful error."""
    url = value.strip()
    if not LEETCODE_PROBLEM_URL.fullmatch(url):
        raise ScaffoldError(
            "problem URL must be a canonical https://leetcode.com/problems/<slug>/ URL"
        )
    return url


def problem_stem(problem_id: str, slug: str) -> str:
    """Return the shared directory and source-file stem."""
    return f"p_{problem_id}_{slug}"


def suggested_branch(problem_id: str, slug: str) -> str:
    """Return the conventional branch name without creating it."""
    return f"feat/p-{problem_id}-{slug.replace('_', '-')}"


def solution_name(problem_id: str, slug: str) -> str:
    """Return a valid, descriptive TypeScript function name."""
    return f"p{problem_id}{''.join(word.title() for word in slug.split('_'))}"


def render_python_solution(problem_id: str, title: str, problem_url: str | None = None) -> str:
    """Render a syntactically valid Python solution placeholder."""
    url_comment = f"# Problem URL: {problem_url}" if problem_url else "# TODO: add problem URL"
    title_content = json.dumps(title, ensure_ascii=False)[1:-1]
    return f'''"""LeetCode {problem_id}."""

# Problem: {title}
{url_comment}

PROBLEM_TITLE = """{title_content}"""


class Solution:
    """TODO: implement the solution."""

    pass
'''


def render_python_test(stem: str) -> str:
    """Render a skipped Python test placeholder."""
    return f"""import pytest

from {stem} import Solution


@pytest.mark.skip(reason="TODO: add examples and edge cases")
def test_{stem}() -> None:
    assert Solution is not None
"""


def render_typescript_solution(
    problem_id: str, title: str, function_name: str, problem_url: str | None = None
) -> str:
    """Render a syntactically valid TypeScript solution placeholder."""
    url_comment = f"// Problem URL: {problem_url}" if problem_url else "// TODO: add problem URL"
    return f"""// LeetCode {problem_id}: {title}.
{url_comment}
/* time: TODO, space: TODO */
export function {function_name}(): void {{
    // TODO: implement the solution.
}}
"""


def render_typescript_test(stem: str, function_name: str) -> str:
    """Render a skipped TypeScript test placeholder."""
    return f"""import {{ {function_name} }} from "./{stem}.js";

test.skip("TODO: add examples and edge cases", () => {{
    {function_name}();
}});
"""


def build_paths(root: Path, language: str, problem_id: str, slug: str) -> tuple[Path, Path, Path]:
    """Return the target directory, source path, and test path."""
    stem = problem_stem(problem_id, slug)
    extension = "py" if language == "py" else "ts"
    directory = root / "src" / ("python" if language == "py" else "typescript") / stem
    test_name = f"test_{stem}.py" if language == "py" else f"{stem}.test.ts"
    return directory, directory / f"{stem}.{extension}", directory / test_name


def create_problem(
    root: Path,
    language: str,
    problem_number: str,
    title_parts: Sequence[str],
    problem_url: str | None = None,
) -> tuple[Path, Path, str]:
    """Create source and test templates, returning their paths and branch suggestion."""
    if language not in {"py", "ts"}:
        raise ScaffoldError("language must be 'py' or 'ts'")
    problem_id = normalize_problem_id(problem_number)
    title = normalize_display_title(title_parts)
    slug = slugify(title)
    if problem_url is not None:
        problem_url = validate_problem_url(problem_url)
    directory, source_path, test_path = build_paths(root, language, problem_id, slug)
    if directory.exists():
        raise ScaffoldError(f"target already exists: {directory}")

    stem = problem_stem(problem_id, slug)
    if language == "py":
        source = render_python_solution(problem_id, title, problem_url)
        test = render_python_test(stem)
    else:
        function_name = solution_name(problem_id, slug)
        source = render_typescript_solution(problem_id, title, function_name, problem_url)
        test = render_typescript_test(stem, function_name)

    directory.mkdir(parents=True)
    try:
        source_path.write_text(source, encoding="utf-8")
        test_path.write_text(test, encoding="utf-8")
    except OSError:
        for path in (source_path, test_path):
            path.unlink(missing_ok=True)
        directory.rmdir()
        raise
    return source_path, test_path, suggested_branch(problem_id, slug)


def parse_arguments(arguments: Sequence[str]) -> tuple[str, str, list[str], str | None]:
    """Parse CLI arguments while allowing an optional URL after the title."""
    if len(arguments) < 3:
        raise ScaffoldError("usage: new_problem.py <py|ts> <problem-number> <title...> [--url URL]")

    language, problem_number = arguments[:2]
    title_parts: list[str] = []
    problem_url: str | None = None
    position = 2
    while position < len(arguments):
        argument = arguments[position]
        if argument == "--url":
            if problem_url is not None:
                raise ScaffoldError("problem URL may only be provided once")
            if position + 1 == len(arguments):
                raise ScaffoldError("--url requires a URL")
            problem_url = arguments[position + 1]
            position += 2
        elif argument.startswith("--"):
            raise ScaffoldError(f"unknown option: {argument}")
        else:
            title_parts.append(argument)
            position += 1

    if not title_parts:
        raise ScaffoldError("title is required")
    return language, problem_number, title_parts, problem_url


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        language, problem_number, title_parts, problem_url = parse_arguments(arguments)
        source_path, test_path, branch = create_problem(
            Path(__file__).resolve().parents[1],
            language,
            problem_number,
            title_parts,
            problem_url,
        )
    except (ScaffoldError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2 if str(error).startswith("usage:") else 1

    root = Path(__file__).resolve().parents[1]
    print(f"Created: {source_path.relative_to(root)}")
    print(f"Created: {test_path.relative_to(root)}")
    print(f"Suggested branch: {branch}")
    print("Next steps:")
    print(f"  pnpm test:{language} {test_path.relative_to(root)}")
    print("  pnpm ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
