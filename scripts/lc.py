#!/usr/bin/env python3
"""Provide one comfortable command for the complete local LeetCode workflow."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from scripts.arguments import LANGUAGES, UsageError, parse, split_runner_args
from scripts.new_problem import (
    ScaffoldError,
    create_problem,
    slugify,
    validate_signature,
)
from scripts.problem_paths import (
    ProblemPathError,
    matching_problem_directories,
    normalize_problem_id,
    resolve_test_path,
)
from scripts.test_one import TestOneError, focused_command
from scripts.typescript import typescript_command

GRAPHQL_URL = "https://leetcode.com/graphql/"
GRAPHQL_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionFrontendId
    title
    titleSlug
    isPaidOnly
    codeSnippets {
      langSlug
      code
    }
  }
}
""".strip()
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
NETWORK_TIMEOUT_SECONDS = 20
USAGE = "usage: lc [command] [arguments]"
HELP = """\
lc — the local LeetCode workflow

Create:
  lc URL                         scaffold a TypeScript problem
  lc py URL                      scaffold a Python problem
  lc new [ts|py] ID TITLE...     create a manual scaffold (TypeScript by default)

Solve:
  lc test                        test the current problem, or all when undetected
  lc test [ts|py] ID             test one problem (TypeScript by default)
  lc test [ts|py] PATH           test a solution or test file
  lc watch [ID|PATH]             watch TypeScript tests
  lc submit [ts|py] [ID]         print judge-ready source
  lc copy [ts|py] [ID]           submit and copy to the clipboard

Quality:
  lc ready                       require a complete, fully passing solution
  lc check                       run format checks, lint, types, and tests
  lc format [ts|py] [--check]    apply formatting, or only check it
  lc lint [ts|py]                run linters
  lc typecheck                   type-check TypeScript
  lc incomplete                  find untouched scaffold markers
  lc doctor                      find missing setup prerequisites

Submit options: --copy, --copy-only, --no-check.
Short aliases: t=test, w=watch, s=submit, r=ready, c=check, fmt=format.
Languages default to TypeScript. Current problem detection uses the caller's problem
directory first, then a matching feat/p-####-* branch. Use COMMAND --help for this help.
"""
PROBLEM_PATH = re.compile(r"^/problems/(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)(?:/description)?/?$")
PROBLEM_DIRECTORY = re.compile(r"^p_(?P<problem_id>[0-9]+)_.+$")
PROBLEM_BRANCH = re.compile(r"^feat/p-(?P<problem_id>[0-9]{4,})-[a-z0-9]+(?:-[a-z0-9]+)*$")
PYTHON_SOLUTION_CLASS = re.compile(r"(?m)^class[ \t]+Solution(?:\([^\n]*\))?[ \t]*:")
PYTHON_METHOD = re.compile(r"(?m)^[ \t]+def[ \t]+(?P<header>[^\n]+):[ \t]*$")


class LeetError(ValueError):
    """Raised when URL scaffolding cannot complete safely."""


LcUsageError = UsageError


@dataclass(frozen=True)
class ProblemMetadata:
    """The official metadata needed by the local scaffold."""

    problem_id: str
    title: str
    title_slug: str
    canonical_url: str
    signature: str


@dataclass(frozen=True)
class ScaffoldResult:
    """Paths and a branch suggestion for a URL scaffold."""

    metadata: ProblemMetadata
    source_path: Path
    test_path: Path
    branch: str


@dataclass(frozen=True)
class ProblemContext:
    """A problem inferred from the caller's directory or current branch."""

    language: str
    problem_id: str
    directory: Path


GitRunner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]
ProblemFetcher = Callable[[str, str], ProblemMetadata]


def run_command(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a Git command without invoking a shell."""
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
    )


def canonicalize_problem_url(value: str) -> tuple[str, str]:
    """Return a canonical LeetCode problem URL and its safe title slug."""
    raw_url = value.strip()
    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except ValueError as error:
        raise LeetError("invalid LeetCode problem URL") from error

    if (
        parsed.scheme != "https"
        or parsed.hostname != "leetcode.com"
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise LeetError("URL must use https://leetcode.com/problems/<slug>/")

    path_match = PROBLEM_PATH.fullmatch(parsed.path)
    if path_match is None:
        raise LeetError("URL must point to one LeetCode problem")
    slug = path_match["slug"]
    return f"https://leetcode.com/problems/{slug}/", slug


class _PythonAnnotationNormalizer(ast.NodeTransformer):
    """Convert LeetCode typing aliases to dependency-free built-in annotations."""

    BUILTIN_ALIASES = {
        "Any": "object",
        "Dict": "dict",
        "FrozenSet": "frozenset",
        "List": "list",
        "Set": "set",
        "Tuple": "tuple",
        "Type": "type",
    }

    def visit_Name(self, node: ast.Name) -> ast.expr:  # noqa: N802
        replacement = self.BUILTIN_ALIASES.get(node.id)
        return (
            ast.copy_location(ast.Name(id=replacement, ctx=node.ctx), node) if replacement else node
        )

    def visit_Subscript(self, node: ast.Subscript) -> ast.expr:  # noqa: N802
        if isinstance(node.value, ast.Name) and node.value.id == "Optional":
            value = self.visit(node.slice)
            return ast.copy_location(
                ast.BinOp(left=value, op=ast.BitOr(), right=ast.Constant(value=None)),
                node,
            )
        if isinstance(node.value, ast.Name) and node.value.id == "Union":
            values = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            normalized = [self.visit(value) for value in values]
            expression = normalized[0]
            for value in normalized[1:]:
                expression = ast.BinOp(left=expression, op=ast.BitOr(), right=value)
            return ast.copy_location(expression, node)
        return self.generic_visit(node)


def _annotation_names(function: ast.FunctionDef) -> set[str]:
    annotations: list[ast.expr] = []
    for argument in function.args.posonlyargs + function.args.args + function.args.kwonlyargs:
        if argument.annotation is not None:
            annotations.append(argument.annotation)
    if function.args.vararg and function.args.vararg.annotation is not None:
        annotations.append(function.args.vararg.annotation)
    if function.args.kwarg and function.args.kwarg.annotation is not None:
        annotations.append(function.args.kwarg.annotation)
    if function.returns is not None:
        annotations.append(function.returns)
    return {
        node.id
        for annotation in annotations
        for node in ast.walk(annotation)
        if isinstance(node, ast.Name)
    }


def extract_python_signature(source: str) -> str:
    """Extract and modernize the official Python3 ``Solution`` method signature."""
    class_match = PYTHON_SOLUTION_CLASS.search(source)
    if class_match is None:
        raise LeetError("Python metadata is not an ordinary Solution method; use pnpm new manually")
    method_match = PYTHON_METHOD.search(source, class_match.end())
    if method_match is None:
        raise LeetError("LeetCode Python3 snippet has no callable method signature")

    header = method_match["header"].strip()
    try:
        parsed = ast.parse(f"class Solution:\n    def {header}:\n        pass\n")
    except SyntaxError as error:
        raise LeetError("LeetCode returned an unsupported Python3 signature") from error
    function = parsed.body[0].body[0]
    if not isinstance(function, ast.FunctionDef) or function.returns is None:
        raise LeetError("LeetCode Python3 signature has no return annotation")

    function = _PythonAnnotationNormalizer().visit(function)
    ast.fix_missing_locations(function)
    allowed_names = {
        "bool",
        "bytes",
        "complex",
        "dict",
        "float",
        "frozenset",
        "int",
        "list",
        "object",
        "range",
        "set",
        "str",
        "tuple",
        "type",
    }
    unsupported_names = sorted(_annotation_names(function) - allowed_names)
    if unsupported_names:
        names = ", ".join(unsupported_names)
        raise LeetError(
            f"Python signature needs unsupported judge type(s): {names}; use pnpm new manually"
        )

    declaration = ast.unparse(function).splitlines()[0]
    signature = declaration.removeprefix("def ").removesuffix(":")
    try:
        return validate_signature("py", signature)[0]
    except ScaffoldError as error:
        raise LeetError(f"LeetCode returned an unsupported Python3 signature: {error}") from error


def extract_typescript_signature(source: str) -> str:
    """Extract an ordinary function header using the shared TypeScript parser."""
    try:
        return json.loads(typescript_command("extract-signature", source))[0]
    except ValueError as error:
        raise LeetError(f"{error}; use lc new manually") from error


def _read_graphql_response(response: object) -> bytes:
    status = getattr(response, "status", 200)
    if status != 200:
        raise LeetError(f"LeetCode metadata request failed with HTTP {status}")
    body = response.read(MAX_RESPONSE_BYTES + 1)  # type: ignore[attr-defined]
    if len(body) > MAX_RESPONSE_BYTES:
        raise LeetError("LeetCode metadata response is unexpectedly large")
    return body


def fetch_problem_metadata(
    language: str,
    value: str,
    *,
    open_url: Callable[..., object] = urlopen,
) -> ProblemMetadata:
    """Fetch official metadata and derive the selected language's callable signature."""
    if language not in {"py", "ts"}:
        raise LeetError("language must be 'py' or 'ts'")
    canonical_url, requested_slug = canonicalize_problem_url(value)
    payload = json.dumps(
        {
            "query": GRAPHQL_QUERY,
            "variables": {"titleSlug": requested_slug},
        }
    ).encode()
    request = Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Referer": canonical_url,
            "User-Agent": "leetcode-local-scaffold/1.0",
        },
        method="POST",
    )
    try:
        response = open_url(request, timeout=NETWORK_TIMEOUT_SECONDS)
        with response:  # type: ignore[attr-defined]
            raw_response = _read_graphql_response(response)
    except HTTPError as error:
        raise LeetError(f"LeetCode metadata request failed with HTTP {error.code}") from error
    except (URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        raise LeetError(f"could not reach LeetCode: {reason}") from error

    try:
        document = json.loads(raw_response)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise LeetError("LeetCode returned malformed metadata") from error
    if not isinstance(document, dict):
        raise LeetError("LeetCode returned malformed metadata")
    errors = document.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        message = first.get("message") if isinstance(first, dict) else None
        raise LeetError(f"LeetCode metadata error: {message or 'unknown GraphQL error'}")
    data = document.get("data")
    question = data.get("question") if isinstance(data, dict) else None
    if not isinstance(question, dict):
        raise LeetError(f"LeetCode problem not found: {requested_slug}")
    if question.get("isPaidOnly") is True:
        raise LeetError("premium problem metadata is unavailable without authentication")

    problem_number = question.get("questionFrontendId")
    title = question.get("title")
    returned_slug = question.get("titleSlug")
    snippets = question.get("codeSnippets")
    if (
        not isinstance(problem_number, str)
        or not problem_number.isdecimal()
        or not isinstance(title, str)
        or not title.strip()
        or returned_slug != requested_slug
        or not isinstance(snippets, list)
    ):
        raise LeetError("LeetCode returned incomplete or inconsistent problem metadata")

    language_slug = "typescript" if language == "ts" else "python3"
    snippet = next(
        (
            item.get("code")
            for item in snippets
            if isinstance(item, dict) and item.get("langSlug") == language_slug
        ),
        None,
    )
    if not isinstance(snippet, str) or not snippet.strip():
        raise LeetError(f"LeetCode has no {language_slug} starter code for this problem")
    signature = (
        extract_typescript_signature(snippet)
        if language == "ts"
        else extract_python_signature(snippet)
    )
    try:
        problem_id = normalize_problem_id(problem_number)
        slugify(title)
    except (ProblemPathError, ScaffoldError) as error:
        raise LeetError("LeetCode returned invalid problem metadata") from error
    return ProblemMetadata(
        problem_id=problem_id,
        title=title.strip(),
        title_slug=requested_slug,
        canonical_url=canonical_url,
        signature=signature,
    )


def scaffold_from_url(
    root: Path,
    language: str,
    value: str,
    *,
    fetch: ProblemFetcher = fetch_problem_metadata,
) -> ScaffoldResult:
    """Fetch official metadata and create files without changing Git state."""
    metadata = fetch(language, value)
    try:
        source_path, test_path, branch = create_problem(
            root,
            language,
            metadata.problem_id,
            [metadata.title],
            metadata.canonical_url,
            metadata.signature,
        )
    except (ProblemPathError, ScaffoldError, OSError) as error:
        raise LeetError(f"could not create scaffold: {error}") from error
    return ScaffoldResult(metadata, source_path, test_path, branch)


COMMAND_ALIASES = {
    "a": "new",
    "add": "new",
    "c": "check",
    "d": "doctor",
    "f": "format",
    "fc": "format-check",
    "fmt": "format",
    "n": "new",
    "r": "ready",
    "s": "submit",
    "submission": "submit",
    "t": "test",
    "test-all": "test-all",
    "types": "typecheck",
    "w": "watch",
}


def _canonical_language(value: str) -> str | None:
    return LANGUAGES.get(value.lower())


def _normalized_problem_id(value: str) -> str:
    try:
        return normalize_problem_id(value)
    except ProblemPathError as error:
        raise LcUsageError("problem ID must be a positive integer") from error


def _context_from_directory(root: Path, caller_cwd: Path) -> ProblemContext | None:
    try:
        relative = caller_cwd.resolve().relative_to(root.resolve())
    except OSError, ValueError:
        return None
    parts = relative.parts
    if len(parts) < 3 or parts[0] != "src":
        return None
    language = {"python": "py", "typescript": "ts"}.get(parts[1])
    directory_match = PROBLEM_DIRECTORY.fullmatch(parts[2])
    if language is None or directory_match is None:
        return None
    try:
        problem_id = normalize_problem_id(directory_match["problem_id"])
    except ProblemPathError:
        return None
    if directory_match["problem_id"] != problem_id:
        return None
    return ProblemContext(language, problem_id, root.resolve().joinpath(*parts[:3]))


def _available_problem_directories(root: Path, problem_id: str) -> dict[str, Path] | None:
    directories = {
        "ts": root / "src" / "typescript",
        "py": root / "src" / "python",
    }
    matches = {
        language: matching_problem_directories(directories[language], problem_id)
        for language in ("ts", "py")
    }
    if any(len(paths) > 1 for paths in matches.values()):
        return None
    return {language: paths[0] for language, paths in matches.items() if paths}


def detect_problem_context(
    root: Path,
    caller_cwd: Path,
    *,
    git_run: GitRunner = run_command,
) -> ProblemContext | None:
    """Infer the current problem from the caller's directory, then its Git branch."""
    directory_context = _context_from_directory(root, caller_cwd)
    if directory_context is not None:
        return directory_context

    current = git_run(("git", "branch", "--show-current"), root)
    if current.returncode != 0:
        return None
    branch_match = PROBLEM_BRANCH.fullmatch(current.stdout.strip())
    if branch_match is None:
        return None
    try:
        problem_id = normalize_problem_id(branch_match["problem_id"])
    except ProblemPathError:
        return None
    directories = _available_problem_directories(root, problem_id)
    if not directories:
        return None
    language = "ts" if "ts" in directories else "py"
    return ProblemContext(language, problem_id, directories[language])


def _test_command(
    arguments: Sequence[str],
    root: Path,
    caller_cwd: Path,
    *,
    force_watch: bool = False,
    git_run: GitRunner = run_command,
) -> tuple[str, ...]:
    values, passthrough = split_runner_args(arguments)
    if force_watch:
        values.append("--watch")
    options = parse("test", values, scoped=True)
    language, target = options.language, options.problem_id
    watch = bool(options.watch)
    explicit_all = target == "all"

    if explicit_all:
        target = None
    elif target is None and language is None:
        context = detect_problem_context(root, caller_cwd, git_run=git_run)
        if context is not None:
            language, target = context.language, context.problem_id

    path: str | None = None
    if target is not None and not target.removesuffix(".").isdecimal():
        try:
            language, path = resolve_test_path(root, caller_cwd, target, language)
        except ProblemPathError as error:
            raise LcUsageError(str(error)) from error
        target = None
    if language is None and (target is not None or watch):
        language = "ts"
    if watch and language == "py":
        raise LcUsageError("--watch is only supported for TypeScript tests")

    if target is not None:
        try:
            return tuple(focused_command(root, language, target, watch, runner_args=passthrough))
        except (ProblemPathError, TestOneError) as error:
            raise LcUsageError(str(error)) from error
    if language is not None:
        script = "test:ts:watch" if watch else f"test:{language}"
        return ("pnpm", "run", script, *([path] if path else []), *passthrough)
    if passthrough:
        raise LcUsageError("all-language tests do not accept runner arguments; select ts or py")
    return ("pnpm", "run", "test")


def _submit_command(
    arguments: Sequence[str],
    root: Path,
    caller_cwd: Path,
    *,
    force_copy: bool = False,
    git_run: GitRunner = run_command,
) -> tuple[str, ...]:
    options = parse("submit", arguments, scoped=True)
    if force_copy and not options.copy_only:
        options.copy = True
    if options.problem_id:
        problem_id = options.problem_id
        _normalized_problem_id(problem_id)
        language = options.language or "ts"
    else:
        context = detect_problem_context(root, caller_cwd, git_run=git_run)
        if context is None:
            raise LcUsageError("no current problem detected; provide a problem ID")
        problem_id = context.problem_id
        language = options.language or context.language
    command = ["uv", "run", "python", "-m", "scripts.submission", language, problem_id]
    for flag in ("copy", "copy_only", "no_check"):
        if getattr(options, flag):
            command.append("--" + flag.replace("_", "-"))
    return tuple(command)


def _scoped_quality_command(
    script: str,
    arguments: Sequence[str],
    *,
    allow_check: bool = False,
) -> tuple[str, ...]:
    values = ["--check" if allow_check and value == "check" else value for value in arguments]
    options = parse(script, values, scoped=True)
    check = allow_check and options.check
    effective_script = f"{script}:check" if check else script
    if options.language:
        effective_script += f":{options.language}"
    return ("pnpm", "run", effective_script)


def build_command(
    arguments: Sequence[str],
    root: Path,
    caller_cwd: Path,
    *,
    git_run: GitRunner = run_command,
) -> tuple[str, ...]:
    """Build one fixed, shell-free command for a non-URL lc invocation."""
    if not arguments:
        raise LcUsageError(USAGE)
    command = COMMAND_ALIASES.get(arguments[0], arguments[0])
    rest = list(arguments[1:])

    if command == "test":
        return _test_command(rest, root, caller_cwd, git_run=git_run)
    if command == "watch":
        return _test_command(rest, root, caller_cwd, force_watch=True, git_run=git_run)
    if command == "test-all":
        if rest:
            raise LcUsageError("test-all does not accept arguments")
        return ("pnpm", "run", "test")
    if command == "submit":
        return _submit_command(rest, root, caller_cwd, git_run=git_run)
    if command == "copy":
        return _submit_command(rest, root, caller_cwd, force_copy=True, git_run=git_run)
    if command == "new":
        options = parse("new", rest, scoped=True)
        _normalized_problem_id(options.problem_id)
        forwarded = [options.language or "ts", options.problem_id, *options.title]
        for flag in ("url", "signature"):
            if getattr(options, flag) is not None:
                forwarded.extend(["--" + flag, getattr(options, flag)])
        return ("pnpm", "run", "new", *forwarded)
    if command in {"format", "lint"}:
        return _scoped_quality_command(
            command,
            rest,
            allow_check=command == "format",
        )
    if command == "format-check":
        return _scoped_quality_command("format", [*rest, "--check"], allow_check=True)

    scripts = {
        "check": "check",
        "doctor": "doctor",
        "incomplete": "incomplete",
        "ready": "ready",
        "typecheck": "typecheck",
    }
    script = scripts.get(command)
    if script is not None:
        if rest:
            raise LcUsageError(f"{command} does not accept arguments")
        return ("pnpm", "run", script)
    raise LcUsageError(f"unknown command: {arguments[0]}; run 'lc help'")


def run_interactive_command(command: Sequence[str], cwd: Path) -> int:
    """Run a known project command with inherited terminal streams and return its status."""
    completed = subprocess.run(command, cwd=cwd, check=False)
    return completed.returncode if completed.returncode >= 0 else 128 - completed.returncode


def _looks_like_url(value: str) -> bool:
    return "://" in value


def _url_invocation(arguments: Sequence[str]) -> tuple[str, str] | None:
    values = list(arguments)
    if values and COMMAND_ALIASES.get(values[0], values[0]) == "new":
        values.pop(0)
    if len(values) == 1 and _looks_like_url(values[0]):
        return "ts", values[0]
    if len(values) == 2:
        language = _canonical_language(values[0])
        if language is not None and _looks_like_url(values[1]):
            return language, values[1]
    return None


def _print_scaffold_result(result: ScaffoldResult, root: Path, language: str) -> None:
    print(f"LeetCode {result.metadata.problem_id}: {result.metadata.title}")
    print(f"Signature: {result.metadata.signature}")
    print(f"Suggested branch: {result.branch}")
    print(f"Created: {result.source_path.relative_to(root)}")
    print(f"Created: {result.test_path.relative_to(root)}")
    print("Next steps:")
    print(f"  lc test {language} {result.metadata.problem_id}")
    if language == "ts":
        print(f"  lc watch {result.metadata.problem_id}")
    print("  lc ready")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the unified local LeetCode command."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help", "help"}:
        print(HELP)
        return 0
    wrapper_arguments = arguments[: arguments.index("--")] if "--" in arguments else arguments
    if any(argument in {"-h", "--help"} for argument in wrapper_arguments[1:]):
        print(HELP)
        return 0
    root = Path(__file__).resolve().parents[1]
    caller_cwd = Path(os.environ.get("LC_CALLER_CWD", root))
    try:
        url_invocation = _url_invocation(arguments)
        if url_invocation is not None:
            language, problem_url = url_invocation
            result = scaffold_from_url(root, language, problem_url)
            _print_scaffold_result(result, root, language)
            return 0
        command = build_command(arguments, root, caller_cwd)
        return run_interactive_command(command, root)
    except (LcUsageError, ProblemPathError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except LeetError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2 if str(error).startswith("usage:") else 1
    except KeyboardInterrupt:
        return 130
    except OSError as error:
        print(f"error: could not start project command: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
