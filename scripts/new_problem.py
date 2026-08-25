#!/usr/bin/env python3
"""Create a solution and test skeleton for a LeetCode problem."""

from __future__ import annotations

import ast
import keyword
import re
import sys
import unicodedata
from pathlib import Path
from typing import Sequence


class ScaffoldError(ValueError):
    """Raised when a scaffold request cannot be completed."""


LEETCODE_PROBLEM_URL = re.compile(r"^https://leetcode\.com/problems/[a-z0-9]+(?:-[a-z0-9]+)*/$")
TYPESCRIPT_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
PYTHON_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
TYPESCRIPT_RESERVED_IDENTIFIERS = frozenset(
    """
    abstract any as asserts async await bigint boolean break case catch class const continue
    debugger declare default delete do else enum export extends false finally for from function
    get if implements import in infer instanceof interface is keyof let module namespace never new
    null number object of package private protected public readonly require return set static string
    super switch symbol this throw true try type typeof undefined unique unknown var void while with
    yield
    """.split()
)
SIGNATURE_LINE_SEPARATORS = "\r\n\u2028\u2029"
TYPESCRIPT_FORBIDDEN_SIGNATURE_TOKENS = ("//", "/*", "*/", "#", ";", "{", "}", "=>")
PROBLEM_DIRECTORY_NAME = re.compile(r"^p_(?P<problem_number>[0-9]+)_.+$")


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


def invalid_signature(language: str) -> ScaffoldError:
    """Return a language-specific signature validation error."""
    expected = "name(args): return" if language == "ts" else "name(self, ...) -> return"
    return ScaffoldError(f"invalid {language} signature; expected {expected}")


def matching_delimiter(value: str, start: int, opening: str, closing: str) -> int | None:
    """Return the matching delimiter index, or none when the input is unbalanced."""
    depth = 0
    for index in range(start, len(value)):
        character = value[index]
        if character == opening:
            depth += 1
        elif character == closing:
            depth -= 1
            if depth == 0:
                return index
            if depth < 0:
                return None
    return None


def has_balanced_typescript_delimiters(value: str) -> bool:
    """Return whether the limited, opaque TypeScript signature delimiters balance."""
    opening_for = {")": "(", "]": "[", ">": "<"}
    stack: list[str] = []
    for character in value:
        if character in "([<":
            stack.append(character)
        elif character in opening_for:
            if not stack or stack.pop() != opening_for[character]:
                return False
    return not stack


def validate_typescript_signature(signature: str) -> tuple[str, str]:
    """Validate a safe TypeScript function declaration signature and return its name."""
    if any(token in signature for token in TYPESCRIPT_FORBIDDEN_SIGNATURE_TOKENS):
        raise invalid_signature("ts")

    name_match = TYPESCRIPT_IDENTIFIER.match(signature)
    if name_match is None:
        raise invalid_signature("ts")
    name = name_match.group()
    if name in TYPESCRIPT_RESERVED_IDENTIFIERS:
        raise invalid_signature("ts")

    position = name_match.end()
    while position < len(signature) and signature[position].isspace():
        position += 1
    if position < len(signature) and signature[position] == "<":
        generic_end = matching_delimiter(signature, position, "<", ">")
        if generic_end is None or generic_end == position + 1:
            raise invalid_signature("ts")
        position = generic_end + 1
    while position < len(signature) and signature[position].isspace():
        position += 1
    if position == len(signature) or signature[position] != "(":
        raise invalid_signature("ts")
    parameters_end = matching_delimiter(signature, position, "(", ")")
    if parameters_end is None:
        raise invalid_signature("ts")

    position = parameters_end + 1
    while position < len(signature) and signature[position].isspace():
        position += 1
    if position == len(signature) or signature[position] != ":":
        raise invalid_signature("ts")
    return_type = signature[position + 1 :].strip()
    if (
        not return_type
        or return_type[0] in ":,;)}]"
        or return_type[-1] in ":,;|&<>=?"
        or not has_balanced_typescript_delimiters(signature)
    ):
        raise invalid_signature("ts")
    return signature, name


def validate_python_signature(signature: str) -> tuple[str, str]:
    """Validate a Python Solution method header and return its name."""
    if "#" in signature:
        raise invalid_signature("py")

    name_match = PYTHON_IDENTIFIER.match(signature)
    if name_match is None or keyword.iskeyword(name_match.group()):
        raise invalid_signature("py")
    name = name_match.group()
    if not re.match(r"\s*\(", signature[name_match.end() :]):
        raise invalid_signature("py")

    try:
        module = ast.parse(
            f"class Solution:\n    def {signature}:\n        raise NotImplementedError\n"
        )
    except SyntaxError as error:
        raise invalid_signature("py") from error
    if (
        len(module.body) != 1
        or not isinstance(module.body[0], ast.ClassDef)
        or len(module.body[0].body) != 1
        or not isinstance(module.body[0].body[0], ast.FunctionDef)
        or module.body[0].body[0].name != name
    ):
        raise invalid_signature("py")
    positional_arguments = (
        module.body[0].body[0].args.posonlyargs + module.body[0].body[0].args.args
    )
    if (
        not positional_arguments
        or positional_arguments[0].arg != "self"
        or module.body[0].body[0].returns is None
    ):
        raise invalid_signature("py")
    return signature, name


def validate_signature(language: str, value: str) -> tuple[str, str]:
    """Return a safe, single-line callable signature and its leading identifier."""
    signature = value.strip()
    if not signature or any(separator in signature for separator in SIGNATURE_LINE_SEPARATORS):
        raise ScaffoldError("signature must be a single-line callable signature")
    if language == "ts":
        return validate_typescript_signature(signature)
    if language == "py":
        return validate_python_signature(signature)
    raise ScaffoldError("language must be 'py' or 'ts'")


def render_python_solution(
    problem_id: str,
    title: str,
    problem_url: str | None = None,
    signature: str | None = None,
) -> str:
    """Render a syntactically valid Python solution placeholder."""
    url_comment = f"# Problem URL: {problem_url}" if problem_url else "# TODO: add problem URL"
    solution_body = (
        f"    def {signature}:\n        raise NotImplementedError\n" if signature else "    pass\n"
    )
    return f'''"""LeetCode {problem_id}."""

# Problem: {title}
{url_comment}
# time: TODO, space: TODO


class Solution:
    """TODO: implement the solution."""

{solution_body}'''


def render_python_test(stem: str, function_name: str | None = None) -> str:
    """Render a skipped Python test placeholder."""
    if function_name:
        return f"""import pytest

from {stem} import Solution


# GENERATED_SCAFFOLD_TEST
TEST_CASES = [
    pytest.param((), None, id="TODO: add examples and edge cases"),
]


@pytest.mark.skip(reason="Generated scaffold test")
@pytest.mark.parametrize(("args", "expected"), TEST_CASES)
def test_{function_name}(args: tuple[object, ...], expected: object) -> None:
    assert Solution().{function_name}(*args) == expected
"""
    return f"""import pytest

from {stem} import Solution


# GENERATED_SCAFFOLD_TEST
@pytest.mark.skip(reason="Generated scaffold test")
def test_{stem}() -> None:
    assert Solution is not None
"""


def render_typescript_solution(
    problem_id: str,
    title: str,
    function_name: str,
    problem_url: str | None = None,
    signature: str | None = None,
) -> str:
    """Render a syntactically valid TypeScript solution placeholder."""
    url_comment = f"// Problem URL: {problem_url}" if problem_url else "// TODO: add problem URL"
    declaration = signature or f"{function_name}(): void"
    body = (
        '    throw new Error("TODO: implement the solution.");'
        if signature
        else "    // TODO: implement the solution."
    )
    return f"""// LeetCode {problem_id}: {title}.
{url_comment}
/* time: TODO, space: TODO */
export function {declaration} {{
{body}
}}
"""


def render_typescript_test(stem: str, function_name: str, has_signature: bool = False) -> str:
    """Render a skipped TypeScript test placeholder."""
    if has_signature:
        return f"""import {{ {function_name} }} from "./{stem}.js";

// GENERATED_SCAFFOLD_TEST
const cases: Array<{{
    name: string;
    args: Parameters<typeof {function_name}>;
    expected: ReturnType<typeof {function_name}>;
}}> = [
    {{
        name: "TODO: add examples and edge cases",
        args: [] as unknown as Parameters<typeof {function_name}>,
        expected: undefined as unknown as ReturnType<typeof {function_name}>,
    }},
];

test.skip.each(cases)("$name", ({{ args, expected }}) => {{
    expect({function_name}(...args)).toEqual(expected);
}});
"""
    return f"""import {{ {function_name} }} from "./{stem}.js";

// GENERATED_SCAFFOLD_TEST
test.skip("Generated scaffold test", () => {{
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


def matching_problem_directories(language_directory: Path, problem_id: str) -> list[Path]:
    """Return padded and legacy problem directories with the requested numeric ID."""
    if not language_directory.is_dir():
        return []

    matches: list[Path] = []
    for path in language_directory.iterdir():
        if not path.is_dir():
            continue
        name_match = PROBLEM_DIRECTORY_NAME.fullmatch(path.name)
        if name_match is None:
            continue
        try:
            existing_problem_id = normalize_problem_id(name_match["problem_number"])
        except ScaffoldError:
            continue
        if existing_problem_id == problem_id:
            matches.append(path)
    return sorted(matches)


def create_problem(
    root: Path,
    language: str,
    problem_number: str,
    title_parts: Sequence[str],
    problem_url: str | None = None,
    signature: str | None = None,
) -> tuple[Path, Path, str]:
    """Create source and test templates, returning their paths and branch suggestion."""
    if language not in {"py", "ts"}:
        raise ScaffoldError("language must be 'py' or 'ts'")
    problem_id = normalize_problem_id(problem_number)
    title = normalize_display_title(title_parts)
    slug = slugify(title)
    if problem_url is not None:
        problem_url = validate_problem_url(problem_url)
    function_name: str | None = None
    if signature is not None:
        signature, function_name = validate_signature(language, signature)
    directory, source_path, test_path = build_paths(root, language, problem_id, slug)
    language_directory = directory.parent
    existing_problems = matching_problem_directories(language_directory, problem_id)
    if existing_problems:
        raise ScaffoldError(f"problem ID already exists: {existing_problems[0]}")
    if directory.exists():
        raise ScaffoldError(f"target already exists: {directory}")

    stem = problem_stem(problem_id, slug)
    if language == "py":
        source = render_python_solution(problem_id, title, problem_url, signature)
        test = render_python_test(stem, function_name)
    else:
        function_name = function_name or solution_name(problem_id, slug)
        source = render_typescript_solution(
            problem_id, title, function_name, problem_url, signature
        )
        test = render_typescript_test(stem, function_name, signature is not None)

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


def parse_arguments(arguments: Sequence[str]) -> tuple[str, str, list[str], str | None, str | None]:
    """Parse CLI arguments while allowing optional metadata after the title."""
    if len(arguments) < 3:
        raise ScaffoldError(
            "usage: new_problem.py <py|ts> <problem-number> <title...> "
            "[--url URL] [--signature SIGNATURE]"
        )

    language, problem_number = arguments[:2]
    title_parts: list[str] = []
    problem_url: str | None = None
    signature: str | None = None
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
        elif argument == "--signature":
            if signature is not None:
                raise ScaffoldError("signature may only be provided once")
            if position + 1 == len(arguments):
                raise ScaffoldError("--signature requires a signature")
            signature = arguments[position + 1]
            position += 2
        elif argument.startswith("--"):
            raise ScaffoldError(f"unknown option: {argument}")
        else:
            title_parts.append(argument)
            position += 1

    if not title_parts:
        raise ScaffoldError("title is required")
    return language, problem_number, title_parts, problem_url, signature


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        language, problem_number, title_parts, problem_url, signature = parse_arguments(arguments)
        source_path, test_path, branch = create_problem(
            Path(__file__).resolve().parents[1],
            language,
            problem_number,
            title_parts,
            problem_url,
            signature,
        )
    except (ScaffoldError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2 if str(error).startswith("usage:") else 1

    root = Path(__file__).resolve().parents[1]
    print(f"Created: {source_path.relative_to(root)}")
    print(f"Created: {test_path.relative_to(root)}")
    print(f"Suggested branch: {branch}")
    print("Next steps:")
    normalized_id = normalize_problem_id(problem_number)
    print(f"  lc test {language} {normalized_id}")
    if language == "ts":
        print(f"  lc watch {normalized_id}")
    print("  lc ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
