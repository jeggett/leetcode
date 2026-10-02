#!/usr/bin/env python3
"""Provide one comfortable command for the complete local LeetCode workflow."""

from __future__ import annotations

import ast
import difflib
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

try:
    from scripts.new_problem import (
        ScaffoldError,
        create_problem,
        matching_problem_directories,
        normalize_problem_id,
        slugify,
        validate_signature,
    )
    from scripts.examples import Example, extract_examples, render_example_tests
    from scripts.lc_state import StateError, read_state, write_state
    from scripts.problem_paths import (
        ProblemPathError,
        require_source_path,
        require_test_path,
        resolve_problem_paths,
    )
except ModuleNotFoundError:
    from new_problem import (  # type: ignore[no-redef]
        ScaffoldError,
        create_problem,
        matching_problem_directories,
        normalize_problem_id,
        slugify,
        validate_signature,
    )
    from examples import Example, extract_examples, render_example_tests
    from lc_state import StateError, read_state, write_state
    from problem_paths import (
        ProblemPathError,
        require_source_path,
        require_test_path,
        resolve_problem_paths,
    )


GRAPHQL_URL = "https://leetcode.com/graphql/"
GRAPHQL_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionFrontendId
    questionId
    title
    titleSlug
    isPaidOnly
    content
    exampleTestcases
    metaData
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

Start → solve → lc done. Run lc in a terminal for the guided menu.

  lc new                        prompt for a URL and language
  lc URL / lc py URL            start or reopen a problem on main
  lc test [ts|py] [ID|PATH]      test the active problem (or all if none)
  lc live [ID|PATH]             rerun TypeScript tests on changes
  lc done [ts|py] [ID]          check, submit, commit, and push after Accepted
  lc login [--check]           import or validate a saved cookie session
  lc logout                    remove saved local credentials
  lc list [ts|py] [URL]         import or show an ordered practice list
  lc next [ts|py]               start the first problem without Accepted
  lc copy [ts|py] [ID]          copy judge-ready source
  lc show [ts|py] [ID]          print judge-ready source
  lc help [COMMAND]            show help

Selection: explicit target → caller's problem directory → remembered problem
→ legacy problem branch. New problems default to TypeScript.

Also: ready, check, format, lint, typecheck, incomplete, doctor, test-all.
Compatibility: watch=live, submit=show, finish=done; t, w, s, r, c, fmt,
n/add/a, d, f, fc, submission, types still work.
Runner options: lc test -- -k boundary (Python), lc test -- -t boundary (Vitest).
Manual fallback: lc new [ts|py] ID TITLE... [--url URL] [--signature SIG]
Setup: ./bin/setup --trust
"""
COMMAND_HELP = {
    "list": "lc list [ts|py] URL / lc list / lc list --refresh\nImport one problem-list in website order, show progress, or refresh its saved URL.\nImport requires lc login. Next: lc next",
    "next": "lc next [ts|py]\nStart or reopen the first unsolved problem in the saved practice list.\nOnly Accepted advances the list, in either language. Next: lc test",
    "new": "lc new [ts|py] [URL]\nPrompt for a URL and language, or reopen an existing problem.\nManual: lc new [ts|py] ID TITLE... [--url URL] [--signature SIG]\nNext: lc test",
    "test": "lc test [ts|py] [ID|PATH|all] [--watch] [-- RUNNER_ARGS...]\nTest the active problem. Use all for the full suite.\nExamples: lc test -- -k boundary; lc test ts 35 -- -t example\nNext: lc done",
    "live": "lc live [ts] [ID|PATH] [-- RUNNER_ARGS...]\nRerun TypeScript tests on changes; Ctrl-C stops.\nNext: lc done",
    "show": "lc show [ts|py] [ID] [--copy]\nCheck the focused tests and print judge-ready source.\nNext: lc done",
    "copy": "lc copy [ts|py] [ID]\nCheck the focused tests and copy judge-ready source.\nNext: paste into LeetCode, or run lc done",
    "login": "lc login [--check]\nSign in at leetcode.com in your normal browser.\nIn Developer Tools, open Application → Storage → Cookies → https://leetcode.com.\nCopy the Value of LEETCODE_SESSION, then csrftoken, into the two hidden terminal prompts.\nPress Enter after each paste; no characters appear while pasting.\nIf LEETCODE_SESSION is missing, finish account sign-in and reload the page.\n--check validates the saved session without prompting or opening a browser.",
    "logout": "lc logout\nRemove saved local credentials; this does not sign out on LeetCode.",
    "done": "lc done [ts|py] [ID] [--browser] [--resume SUBMISSION_ID | --retry-uncertain]\nRequire main, format this problem, run lc ready, submit, and wait.\nAfter Accepted: commit only this problem and push to origin/main.\nRetries resume judging or saving. First run lc login in a local terminal.\nDefault: saved cookie session over HTTP; --browser uses dedicated Playwright.\nRecovery: --resume verifies a submission's source, language, and problem.\nUse --retry-uncertain only after checking LeetCode history shows no submission.\nNext after rejection: edit the solution, then lc test",
}
PROBLEM_PATH = re.compile(r"^/problems/(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)(?:/description)?/?$")
PROBLEM_DIRECTORY = re.compile(r"^p_(?P<problem_id>[0-9]+)_.+$")
PROBLEM_BRANCH = re.compile(r"^feat/p-(?P<problem_id>[0-9]{4,})-[a-z0-9]+(?:-[a-z0-9]+)*$")
TYPESCRIPT_FUNCTION = re.compile(r"(?m)^[ \t]*function[ \t]+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)")
TYPESCRIPT_DECLARATION = re.compile(
    r"(?m)^[ \t]*(?:type|interface|class|enum)[ \t]+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)"
)
PYTHON_SOLUTION_CLASS = re.compile(r"(?m)^class[ \t]+Solution(?:\([^\n]*\))?[ \t]*:")
PYTHON_METHOD = re.compile(r"(?m)^[ \t]+def[ \t]+(?P<header>[^\n]+):[ \t]*$")


class LeetError(ValueError):
    """Raised when URL scaffolding cannot complete safely."""


class LcUsageError(ValueError):
    """Raised when a unified-command invocation is invalid."""


@dataclass(frozen=True)
class ProblemMetadata:
    """The official metadata needed by the local scaffold."""

    problem_id: str
    title: str
    title_slug: str
    canonical_url: str
    signature: str | None
    examples: tuple[Example, ...] = ()
    template_reason: str | None = None
    starter: str | None = None


@dataclass(frozen=True)
class CommandResult:
    """The subset of a Git command result needed by this module."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ScaffoldResult:
    """Paths and branch produced by a successful URL scaffold."""

    metadata: ProblemMetadata
    source_path: Path
    test_path: Path
    branch: str
    reopened: bool = False


@dataclass(frozen=True)
class ProblemContext:
    """A problem inferred from the caller's directory or current branch."""

    language: str
    problem_id: str
    directory: Path


GitRunner = Callable[[Sequence[str], Path], CommandResult]
ProblemFetcher = Callable[[str, str], ProblemMetadata]
ProblemCreator = Callable[..., tuple[Path, Path, str]]


def run_command(command: Sequence[str], cwd: Path) -> CommandResult:
    """Run a Git command without invoking a shell."""
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


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
        "ListNode",
        "TreeNode",
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
    """Extract an ordinary top-level function signature from an official TS snippet."""
    function_match = TYPESCRIPT_FUNCTION.search(source)
    if function_match is None:
        raise LeetError("TypeScript metadata is not an ordinary function; use pnpm new manually")
    body_start = source.find("{", function_match.end())
    if body_start == -1:
        raise LeetError("LeetCode TypeScript snippet has no function body")

    signature = re.sub(
        r"\s+",
        " ",
        source[function_match.start("name") : body_start].strip(),
    )
    declared_names = {
        match["name"] for match in TYPESCRIPT_DECLARATION.finditer(source[: function_match.start()])
    }
    required_declarations = sorted(
        name for name in declared_names if re.search(rf"\b{re.escape(name)}\b", signature)
    )
    if required_declarations:
        names = ", ".join(required_declarations)
        raise LeetError(
            f"TypeScript signature needs omitted declaration(s): {names}; use pnpm new manually"
        )
    try:
        return validate_signature("ts", signature)[0]
    except ScaffoldError as error:
        raise LeetError(
            f"LeetCode returned an unsupported TypeScript signature: {error}"
        ) from error


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
    starter = None
    try:
        signature = (
            extract_typescript_signature(snippet)
            if language == "ts"
            else extract_python_signature(snippet)
        )
    except LeetError:
        signature = None
        starter = snippet
    examples, template_reason = extract_examples(question)
    if signature is None:
        examples = ()
        template_reason = "Use the official starter below and adapt the test for this API."
    try:
        problem_id = normalize_problem_id(problem_number)
        slugify(title)
    except ScaffoldError as error:
        raise LeetError("LeetCode returned invalid problem metadata") from error
    return ProblemMetadata(
        problem_id=problem_id,
        title=title.strip(),
        title_slug=requested_slug,
        canonical_url=canonical_url,
        signature=signature,
        examples=examples,
        template_reason=template_reason,
        starter=starter,
    )


def _git_error(action: str, result: CommandResult) -> LeetError:
    detail = (result.stderr or result.stdout).strip()
    return LeetError(f"Git could not {action}{f': {detail}' if detail else ''}")


def preflight_git(root: Path, run: GitRunner = run_command) -> str:
    """Require this worktree's main branch without disturbing unrelated edits."""
    repository = run(("git", "rev-parse", "--show-toplevel"), root)
    if repository.returncode != 0:
        raise _git_error("locate the repository", repository)
    if Path(repository.stdout.strip()).resolve() != root.resolve():
        raise LeetError("lc must run for this repository's root worktree")
    current = run(("git", "branch", "--show-current"), root)
    if current.returncode != 0:
        raise _git_error("read the current branch", current)
    if current.stdout.strip() != "main":
        raise LeetError("start problems on main; next: git switch main")
    return "main"


def activate_problem(
    root: Path, language: str, problem_id: str, problem_url: str | None = None
) -> None:
    paths = resolve_problem_paths(root, language, problem_id)
    if problem_url:
        canonical_url, _ = canonicalize_problem_url(problem_url)
        write_state(
            root / ".lc" / "problems" / f"{language}-{paths.problem_id}.json",
            {"url": canonical_url},
        )
    write_state(
        root / ".lc" / "active.json",
        {
            "language": paths.language,
            "problem_id": paths.problem_id,
        },
    )


def scaffold_from_url(
    root: Path,
    language: str,
    value: str,
    *,
    fetch: ProblemFetcher = fetch_problem_metadata,
    run: GitRunner = run_command,
    creator: ProblemCreator = create_problem,
) -> ScaffoldResult:
    """Start on main, or activate existing files without overwriting them."""
    canonical_url, requested_slug = canonicalize_problem_url(value)
    preflight_git(root, run)
    # Reopen known URLs even when LeetCode is offline.
    language_path = root / "src" / ("python" if language == "py" else "typescript")
    for directory in sorted(language_path.glob("p_*")):
        source_path = directory / f"{directory.name}.{language}"
        if not source_path.is_file():
            continue
        content = source_path.read_text(encoding="utf-8")
        match = PROBLEM_DIRECTORY.fullmatch(directory.name)
        if match:
            problem_id = normalize_problem_id(match["problem_id"])
            remembered = read_state(root / ".lc" / "problems" / f"{language}-{problem_id}.json")
            if remembered.get("url") == canonical_url or re.search(
                rf"Problem URL: {re.escape(canonical_url)}(?:\s|$)", content
            ):
                paths = resolve_problem_paths(root, language, problem_id)
                metadata = ProblemMetadata(
                    problem_id,
                    requested_slug.replace("-", " "),
                    requested_slug,
                    canonical_url,
                    None,
                )
                activate_problem(root, language, problem_id, canonical_url)
                return ScaffoldResult(
                    metadata, require_source_path(paths), require_test_path(paths), "main", True
                )
    metadata = fetch(language, canonical_url)
    preflight_git(root, run)
    existing = matching_problem_directories(language_path, metadata.problem_id)
    if existing:
        paths = resolve_problem_paths(root, language, metadata.problem_id)
        source_path, test_path = require_source_path(paths), require_test_path(paths)
    else:
        try:
            source_path, test_path, _ = creator(
                root,
                language,
                metadata.problem_id,
                [metadata.title],
                metadata.canonical_url,
                metadata.signature,
            )
            if metadata.starter:
                from_starter = render_starter(language, metadata, source_path.read_text())
                source_path.write_text(from_starter, encoding="utf-8")
            if metadata.examples and metadata.signature:
                name = validate_signature(language, metadata.signature)[1]
                test_path.write_text(
                    render_example_tests(language, source_path.stem, name, metadata.examples),
                    encoding="utf-8",
                )
            elif metadata.template_reason:
                comment = "#" if language == "py" else "//"
                test_path.write_text(
                    f"{comment} {metadata.template_reason}\n" + test_path.read_text(),
                    encoding="utf-8",
                )
        except (ScaffoldError, OSError) as error:
            raise LeetError(f"could not create scaffold: {error}") from error
    activate_problem(root, language, metadata.problem_id, metadata.canonical_url)
    return ScaffoldResult(metadata, source_path, test_path, "main", bool(existing))


def render_starter(language: str, metadata: ProblemMetadata, fallback: str) -> str:
    """Preserve unusual official APIs as an editable, commented reference."""
    comment = "#" if language == "py" else "//"
    reference = "\n".join(f"{comment} {line}" for line in (metadata.starter or "").splitlines())
    return f"{comment} Official starter: replace the placeholder with this API.\n{reference}\n\n{fallback}"


def parse_arguments(arguments: Sequence[str]) -> tuple[str, str]:
    """Parse ``lc [ts|py] <problem-url>``, defaulting to TypeScript."""
    if len(arguments) == 1:
        if arguments[0] in {"py", "ts"}:
            raise LeetError(USAGE)
        return "ts", arguments[0]
    if len(arguments) != 2:
        raise LeetError(USAGE)
    language, problem_url = arguments
    if language not in {"py", "ts"}:
        raise LeetError("language must be 'py' or 'ts'")
    return language, problem_url


LANGUAGE_ALIASES = {
    "py": "py",
    "python": "py",
    "ts": "ts",
    "typescript": "ts",
}
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
    "t": "test",
    "test-all": "test-all",
    "types": "typecheck",
    "w": "live",
    "watch": "live",
    "submit": "show",
    "s": "show",
    "submission": "show",
    "finish": "done",
}


def _canonical_language(value: str) -> str | None:
    return LANGUAGE_ALIASES.get(value.lower())


def _normalized_problem_id(value: str) -> str:
    try:
        return normalize_problem_id(value)
    except ScaffoldError as error:
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
    except ScaffoldError:
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
    """Resolve the caller directory, remembered selection, then legacy branches."""
    directory_context = _context_from_directory(root, caller_cwd)
    if directory_context is not None:
        return directory_context

    active = read_state(root / ".lc" / "active.json")
    if active:
        try:
            paths = resolve_problem_paths(root, active["language"], active["problem_id"])
            return ProblemContext(paths.language, paths.problem_id, paths.directory)
        except KeyError, TypeError, AttributeError, ProblemPathError:
            pass  # A removed problem does not hide a usable legacy branch.

    current = git_run(("git", "branch", "--show-current"), root)
    if current.returncode != 0:
        return None
    branch_match = PROBLEM_BRANCH.fullmatch(current.stdout.strip())
    if branch_match is None:
        return None
    try:
        problem_id = normalize_problem_id(branch_match["problem_id"])
    except ScaffoldError:
        return None
    directories = _available_problem_directories(root, problem_id)
    if not directories:
        return None
    language = "ts" if "ts" in directories else "py"
    return ProblemContext(language, problem_id, directories[language])


def _split_passthrough(arguments: Sequence[str]) -> tuple[list[str], list[str]]:
    values = list(arguments)
    if "--" not in values:
        return values, []
    separator = values.index("--")
    return values[:separator], values[separator + 1 :]


def _test_path(
    root: Path,
    caller_cwd: Path,
    value: str,
    explicit_language: str | None,
) -> tuple[str, str]:
    path = Path(value)
    absolute = path if path.is_absolute() else caller_cwd / path
    try:
        relative = absolute.resolve().relative_to(root.resolve())
    except (OSError, ValueError) as error:
        raise LcUsageError("test path must be inside this repository") from error
    normalized = relative.as_posix()
    inferred = "py" if normalized.endswith(".py") else "ts" if normalized.endswith(".ts") else None
    if inferred is None:
        raise LcUsageError("test path must end in .py or .ts")
    if explicit_language is not None and explicit_language != inferred:
        raise LcUsageError("test path extension does not match the selected language")
    return explicit_language or inferred, normalized


def _test_command(
    arguments: Sequence[str],
    root: Path,
    caller_cwd: Path,
    *,
    force_watch: bool = False,
    git_run: GitRunner = run_command,
) -> tuple[str, ...]:
    values, passthrough = _split_passthrough(arguments)
    watch_count = values.count("--watch") + int(force_watch)
    values = [value for value in values if value != "--watch"]
    if watch_count > 1:
        raise LcUsageError("--watch may only be provided once")
    unknown = next((value for value in values if value.startswith("--")), None)
    if unknown is not None:
        raise LcUsageError(f"unknown test option: {unknown}")

    language: str | None = None
    if values and (selected := _canonical_language(values[0])) is not None:
        language = selected
        values.pop(0)
    if len(values) > 1:
        raise LcUsageError("usage: lc test [ts|py] [ID|PATH] [--watch]")
    target = values[0] if values else None
    watch = watch_count == 1
    explicit_all = target == "all"

    if explicit_all:
        target = None
        if language is None and not watch:
            if passthrough:
                raise LcUsageError("test-all does not accept runner arguments")
            return ("pnpm", "run", "test")

    if target is not None and not target.removesuffix(".").isdecimal():
        selected_language, path = _test_path(root, caller_cwd, target, language)
        if watch and selected_language == "py":
            raise LcUsageError("--watch is only supported for TypeScript tests")
        script = "test:ts:watch" if watch else f"test:{selected_language}"
        return ("pnpm", "run", script, path, *passthrough)

    if target is not None:
        _normalized_problem_id(target)
        selected_language = language or "ts"
        if watch and selected_language == "py":
            raise LcUsageError("--watch is only supported for TypeScript tests")
        command = ["pnpm", "run", "test:one", selected_language, target]
        if watch:
            command.append("--watch")
        if passthrough:
            command.extend(["--", *passthrough])
        return tuple(command)

    if language is not None:
        if watch and language == "py":
            raise LcUsageError("--watch is only supported for TypeScript tests")
        script = "test:ts:watch" if watch else f"test:{language}"
        return ("pnpm", "run", script, *passthrough)

    context = None if explicit_all else detect_problem_context(root, caller_cwd, git_run=git_run)
    if context is not None:
        if watch and context.language == "py":
            raise LcUsageError("--watch is only supported for TypeScript tests")
        command = ["pnpm", "run", "test:one", context.language, context.problem_id]
        if watch:
            command.append("--watch")
        if passthrough:
            command.extend(["--", *passthrough])
        return tuple(command)
    if watch:
        return ("pnpm", "run", "test:ts:watch", *passthrough)
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
    values = list(arguments)
    copy_count = values.count("--copy") + int(force_copy)
    values = [value for value in values if value != "--copy"]
    if copy_count > 1:
        raise LcUsageError("--copy may only be provided once")
    unknown = next((value for value in values if value.startswith("-")), None)
    if unknown is not None:
        raise LcUsageError(f"unknown show option: {unknown}")

    language: str | None = None
    if values and (selected := _canonical_language(values[0])) is not None:
        language = selected
        values.pop(0)
    if len(values) > 1:
        raise LcUsageError("usage: lc show [ts|py] [ID] [--copy]")

    if values:
        problem_id = values[0]
        _normalized_problem_id(problem_id)
        selected_language = language or "ts"
    else:
        context = detect_problem_context(root, caller_cwd, git_run=git_run)
        if context is None:
            raise LcUsageError("no current problem detected; provide a problem ID")
        problem_id = context.problem_id
        selected_language = language or context.language

    command = [
        "uv",
        "run",
        "python",
        "scripts/submission.py",
        selected_language,
        problem_id,
    ]
    if copy_count == 1:
        command.append("--copy")
    return tuple(command)


def _scoped_quality_command(
    script: str,
    arguments: Sequence[str],
    *,
    allow_check: bool = False,
) -> tuple[str, ...]:
    values = list(arguments)
    if allow_check:
        values = ["--check" if value == "check" else value for value in values]
    check_count = values.count("--check")
    values = [value for value in values if value != "--check"]
    if check_count and not allow_check:
        raise LcUsageError(f"{script} does not support --check")
    if check_count > 1:
        raise LcUsageError("--check may only be provided once")
    if len(values) > 1:
        raise LcUsageError(f"usage: lc {script} [ts|py]{' [--check]' if allow_check else ''}")
    language = _canonical_language(values[0]) if values else None
    if values and language is None:
        raise LcUsageError("language must be 'py' or 'ts'")
    effective_script = f"{script}:check" if check_count else script
    if language is not None:
        effective_script = f"{effective_script}:{language}"
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
    if command == "live":
        return _test_command(rest, root, caller_cwd, force_watch=True, git_run=git_run)
    if command == "test-all":
        if rest:
            raise LcUsageError("test-all does not accept arguments")
        return ("pnpm", "run", "test")
    if command == "show":
        return _submit_command(rest, root, caller_cwd, git_run=git_run)
    if command == "copy":
        return _submit_command(rest, root, caller_cwd, force_copy=True, git_run=git_run)
    if command == "new":
        language = "ts"
        if rest and (selected := _canonical_language(rest[0])) is not None:
            language = selected
            rest.pop(0)
        if len(rest) < 2:
            raise LcUsageError("usage: lc new [ts|py] ID TITLE... [--url URL] [--signature SIG]")
        _normalized_problem_id(rest[0])
        return ("pnpm", "run", "new", language, *rest)
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
    candidates = [*COMMAND_HELP, *scripts, "format", "lint", "format-check", *COMMAND_ALIASES]
    match = difflib.get_close_matches(arguments[0], candidates, n=1, cutoff=0.55)
    hint = f"; did you mean 'lc {match[0]}'?" if match else "; next: lc help"
    raise LcUsageError(f"unknown command: {arguments[0]}{hint}")


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
    print(f"LeetCode {result.metadata.problem_id}: {result.metadata.title} ({language})")
    if result.metadata.signature:
        print(f"Signature: {result.metadata.signature}")
    verb = "Opened" if result.reopened else "Created"
    print(f"{verb}: {result.source_path.relative_to(root)}")
    print(f"{verb}: {result.test_path.relative_to(root)}")
    if not result.reopened and result.metadata.template_reason:
        print(result.metadata.template_reason)
    print("Next: edit the solution, then lc test" + (" (or lc live)" if language == "ts" else ""))
    print("When ready: lc done")


def command_help(command: str) -> str:
    canonical = COMMAND_ALIASES.get(command, command)
    if canonical in COMMAND_HELP:
        return COMMAND_HELP[canonical]
    quality = {
        "ready": "Require completed scaffolds, then run the full quality gate.",
        "check": "Run formatting checks, lint, types, judge compatibility, and all tests.",
        "format": "lc format [ts|py] [--check] — format files or check formatting.",
        "format-check": "lc format-check [ts|py] — check formatting.",
        "lint": "lc lint [ts|py] — run linters.",
        "typecheck": "Type-check TypeScript.",
        "incomplete": "List unfinished scaffold markers.",
        "doctor": "Inspect tools, dependencies, and hooks. Next: ./bin/setup --trust",
        "test-all": "Run all tests in both languages.",
    }
    if canonical in quality:
        return f"lc {canonical}\n{quality[canonical]}"
    raise LcUsageError(f"unknown command: {command}; next: lc help")


def prompt_new(language: str | None = None) -> list[str]:
    if not sys.stdin.isatty():
        raise LcUsageError("lc new needs a URL without a terminal; next: lc new URL")
    url = input("Problem URL (blank cancels): ").strip()
    if not url:
        return []
    if language is None:
        selected = input("Language [ts/py, default ts]: ").strip() or "ts"
        language = _canonical_language(selected)
        if language is None:
            raise LcUsageError("language must be ts or py; next: lc new")
    return [language, url]


def select_problem(root: Path) -> None:
    choices = []
    for language, folder in (("ts", "typescript"), ("py", "python")):
        for directory in sorted((root / "src" / folder).glob("p_*")):
            match = PROBLEM_DIRECTORY.fullmatch(directory.name)
            if directory.is_dir() and match:
                choices.append((language, match["problem_id"], directory.name))
    if not choices:
        print("No problems yet. Next: lc new")
        return
    for index, (language, problem_id, name) in enumerate(choices, 1):
        title = name.split("_", 2)[2].replace("_", " ")
        print(f"{index}. {problem_id} {title} ({language})")
    choice = input("Problem number (blank cancels): ").strip()
    if not choice:
        return
    if not choice.isdecimal() or not 1 <= int(choice) <= len(choices):
        raise LcUsageError("choose a displayed problem number")
    language, problem_id, _ = choices[int(choice) - 1]
    activate_problem(root, language, problem_id)


def menu(root: Path, caller_cwd: Path) -> int:
    # Explicit selections inside the menu override the directory it was opened from.
    context = detect_problem_context(root, caller_cwd)
    if context:
        activate_problem(root, context.language, context.problem_id)
    while True:
        context = detect_problem_context(root, root)
        label = (
            f"{context.problem_id} {context.directory.name.split('_', 2)[2].replace('_', ' ')} ({context.language})"
            if context
            else "none"
        )
        print(f"\nActive problem: {label}")
        print(
            "1. New problem\n2. Select problem\n3. Test\n4. Live tests (TypeScript)\n"
            "5. Done — submit, commit, and push\n6. Copy source\n7. Show source\n8. Help\n9. Login\n10. Logout\n11. List\n12. Next problem\n0. Quit"
        )
        try:
            choice = input("Choose an action: ").strip().lower()
            if choice in {"0", "q", "quit"}:
                return 0
            if not choice:
                continue
            if choice in {"2", "select"}:
                select_problem(root)
                continue
            actions = {
                "1": "new",
                "3": "test",
                "4": "live",
                "5": "done",
                "6": "copy",
                "7": "show",
                "8": "help",
                "9": "login",
                "10": "logout",
                "11": "list",
                "12": "next",
            }
            action = actions.get(choice, choice)
            if action not in {*actions.values(), "new"}:
                print("Choose a displayed number or action name.")
                continue
            if action == "list":
                list_menu(root)
            else:
                dispatch([action], root, root)
        except (LcUsageError, LeetError, StateError, ProblemPathError, OSError) as error:
            print(f"error: {error}\nNext: lc help", file=sys.stderr)
        except EOFError, KeyboardInterrupt:
            return 0


def dispatch(arguments: list[str], root: Path, caller_cwd: Path) -> int:
    canonical = COMMAND_ALIASES.get(arguments[0], arguments[0])
    if canonical == "help":
        print(command_help(arguments[1]) if len(arguments) > 1 else HELP)
        return 0
    if canonical in {"list", "next"}:
        return practice_command(canonical, arguments[1:], root)
    if canonical == "new" and (
        len(arguments) == 1 or (len(arguments) == 2 and _canonical_language(arguments[1]))
    ):
        arguments = prompt_new(_canonical_language(arguments[1]) if len(arguments) > 1 else None)
        if not arguments:
            return 0
    url_invocation = _url_invocation(arguments)
    if url_invocation is not None:
        language, problem_url = url_invocation
        result = scaffold_from_url(root, language, problem_url)
        _print_scaffold_result(result, root, language)
        return 0
    if canonical in {"login", "logout"}:
        try:
            from scripts.leetcode_session import BrowserError, login_command, logout_command
        except ModuleNotFoundError:
            from leetcode_session import BrowserError, login_command, logout_command
        try:
            handler = login_command if canonical == "login" else logout_command
            return handler(arguments[1:], root)
        except BrowserError as error:
            raise LeetError(str(error)) from error
    if canonical == "done":
        try:
            from scripts.done import done_command, DoneError
        except ModuleNotFoundError:
            from done import done_command, DoneError
        try:
            return done_command(arguments[1:], root, caller_cwd)
        except DoneError as error:
            raise LeetError(str(error)) from error
    command = build_command(arguments, root, caller_cwd)
    if canonical == "new":
        preflight_git(root)
        language, problem_id = command[3:5]
        folder = root / "src" / ("python" if language == "py" else "typescript")
        if matching_problem_directories(folder, _normalized_problem_id(problem_id)):
            paths = resolve_problem_paths(root, language, problem_id)
            require_source_path(paths)
            require_test_path(paths)
            activate_problem(root, language, problem_id)
            print(f"Opened: {paths.directory.relative_to(root)} ({language})\nNext: lc test")
            return 0
    result = run_interactive_command(command, root)
    if result:
        print(f"Next: lc help {canonical}", file=sys.stderr)
    return result


def list_menu(root: Path) -> None:
    try:
        from scripts.practice import PracticeError, load_list
    except ModuleNotFoundError:
        from practice import PracticeError, load_list
    try:
        saved = load_list(root)
    except (PracticeError, StateError) as error:
        print(f"error: {error}", file=sys.stderr)
        saved = {}
    if saved:
        dispatch(["list"], root, root)
    print("1. Import a list\n2. Refresh saved list\n0. Back")
    choice = input("List action (blank cancels): ").strip().lower()
    if choice in {"", "0", "back"}:
        return
    if choice in {"2", "refresh"}:
        dispatch(["list", "--refresh"], root, root)
        return
    if choice not in {"1", "import"}:
        raise LcUsageError("choose a displayed list action")
    url = input("Practice list URL (blank cancels): ").strip()
    if not url:
        return
    language = input("Language [ts/py, default ts]: ").strip() or "ts"
    dispatch(["list", language, url], root, root)


def practice_command(command: str, arguments: list[str], root: Path) -> int:
    try:
        from scripts import practice
        from scripts.leetcode_session import BrowserError
    except ModuleNotFoundError:
        import practice
        from leetcode_session import BrowserError
    usage = (
        "usage: lc list [ts|py] URL | lc list [--refresh]"
        if command == "list"
        else "usage: lc next [ts|py]"
    )
    try:
        if command == "next":
            if len(arguments) > 1 or (arguments and arguments[0] not in {"ts", "py"}):
                raise LcUsageError(usage)
            state = practice.load_list(root)
            if not state:
                raise LcUsageError("no saved practice list; next: lc list URL")
            question = practice.next_question(root, state)
            if question is None:
                print("Practice list complete. All problems have Accepted.")
                return 0
            language = arguments[0] if arguments else state["language"]
            result = scaffold_from_url(
                root, language, f"https://leetcode.com/problems/{question['titleSlug']}/"
            )
            _print_scaffold_result(result, root, language)
            return 0
        if arguments == ["--refresh"]:
            state = practice.load_list(root)
            if not state:
                raise LcUsageError("no saved practice list; next: lc list URL")
            state = practice.import_list(root, state["url"], state["language"])
        elif arguments:
            if (
                len(arguments) == 1
                and arguments[0] not in {"ts", "py"}
                and not arguments[0].startswith("-")
            ):
                language, url = "ts", arguments[0]
            elif len(arguments) == 2 and arguments[0] in {"ts", "py"}:
                language, url = arguments
            else:
                raise LcUsageError(usage)
            state = practice.import_list(root, url, language)
        else:
            state = practice.load_list(root)
            if not state:
                if not sys.stdin.isatty():
                    raise LcUsageError("no saved practice list; next: lc list URL")
                url = input("Practice list URL (blank cancels): ").strip()
                if not url:
                    return 0
                language = input("Language [ts/py, default ts]: ").strip() or "ts"
                state = practice.import_list(root, url, language)
        practice.show_list(root, state)
        return 0
    except (practice.PracticeError, BrowserError) as error:
        raise LeetError(str(error)) from error


def main(argv: Sequence[str] | None = None) -> int:
    """Run commands without prompts unless the user opens the menu or asks for new."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parents[1]
    caller_cwd = Path(os.environ.get("LC_CALLER_CWD", Path.cwd()))
    try:
        options, _ = _split_passthrough(arguments)
        if options and options[0] in {"-h", "--help"}:
            print(HELP)
            return 0
        if any(argument in {"-h", "--help"} for argument in options[1:]):
            print(command_help(options[0]))
            return 0
        if not arguments:
            if sys.stdin.isatty():
                return menu(root, caller_cwd)
            context = detect_problem_context(root, caller_cwd)
            print(
                f"Active problem: {context.problem_id} ({context.language})"
                if context
                else "Active problem: none"
            )
            print(HELP)
            return 0
        return dispatch(arguments, root, caller_cwd)
    except (LcUsageError, LeetError, StateError, ProblemPathError, ScaffoldError) as error:
        print(f"error: {error}\nNext: lc help", file=sys.stderr)
        return 2 if isinstance(error, LcUsageError) else 1
    except KeyboardInterrupt, EOFError:
        return 130
    except OSError as error:
        print(f"error: {error}\nNext: ./bin/setup --trust, then retry", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
