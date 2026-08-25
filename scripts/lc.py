#!/usr/bin/env python3
"""Provide one comfortable command for the complete local LeetCode workflow."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

try:
    from scripts.new_problem import (
        ProblemDetails,
        ScaffoldError,
        build_paths,
        create_problem,
        matching_problem_directories,
        normalize_problem_id,
        slugify,
        suggested_branch,
        validate_signature,
    )
except ModuleNotFoundError:
    from new_problem import (  # type: ignore[no-redef]
        ProblemDetails,
        ScaffoldError,
        build_paths,
        create_problem,
        matching_problem_directories,
        normalize_problem_id,
        slugify,
        suggested_branch,
        validate_signature,
    )

try:
    from scripts.config import ConfigError, load_config
except ModuleNotFoundError:
    try:
        from config import ConfigError, load_config  # type: ignore[no-redef]
    except ModuleNotFoundError:
        ConfigError = ValueError  # type: ignore[assignment,misc]

        def load_config(_root: Path) -> object:  # type: ignore[no-redef]
            return type("DefaultConfig", (), {"base_branch": "main", "primary_language": "ts"})()


try:
    from scripts.practice import (
        PracticeError,
        PracticeStore,
        Session,
        start_in_transaction,
        start_session,
    )
except ModuleNotFoundError:
    from practice import (  # type: ignore[no-redef]
        PracticeError,
        PracticeStore,
        Session,
        start_in_transaction,
        start_session,
    )


GRAPHQL_URL = "https://leetcode.com/graphql/"
GRAPHQL_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionFrontendId
    title
    titleSlug
    isPaidOnly
    difficulty
    topicTags {
      name
      slug
    }
    exampleTestcaseList
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
  lc URL                         create a TypeScript problem and branch
  lc py URL                      create a Python problem and branch
  lc new [ts|py] ID TITLE...     create a manual scaffold (TypeScript by default)
  lc start [ts|py] URL|ID        start or resume one problem (safe to repeat)
  lc resume [ts|py] [ID]         switch to an existing problem branch

Solve:
  lc current                     report the detected problem, branch, and paths
  lc test                        test the current problem (use `all` outside one)
  lc test [ts|py] ID             test one problem (TypeScript by default)
  lc test [ts|py] PATH           test one file
  lc watch [ts|py] [ID|PATH]     watch focused tests
  lc submit [ts|py] [ID]         check, then print judge-ready source
  lc copy [ts|py] [ID]           check, then copy without terminal noise

Practice:
  lc today [ts|py]               choose due work before unseen problems
  lc begin [ts|py] [ID]          start a timed new/review/mock session
  lc finish --result RESULT      record solved, hinted, or failed
  lc review [ts|py] [ID]         show due reviews or start one
  lc retry [ts|py] ID            make an isolated blank retry
  lc list [ts|py] [FILTERS]      show per-problem practice state
  lc stats [ts|py]               report progress and weak patterns

Quality:
  lc ready [--current|--changed|all]
                                require a complete, fully passing solution
  lc check                       run format checks, lint, types, and tests
  lc format [ts|py] [--check]    apply formatting, or only check it
  lc lint [ts|py]                run linters
  lc typecheck                   type-check TypeScript
  lc incomplete                  find untouched scaffold markers
  lc doctor                      verify the local setup
  lc compat                      check compatibility with the project contract

Short aliases: t=test, w=watch, s=submit, r=ready, c=check, fmt=format.
Languages default to TypeScript. Current problem detection uses the caller's problem
directory first, then a matching feat/p-####-* branch. Use COMMAND --help for this help.
"""
COMMAND_HELP = {
    "current": "usage: lc current\n\nReport the current branch and detected problem paths.",
    "start": (
        "usage: lc start [ts|py] URL|ID [--mode new|review|mock] [--no-timer] "
        "[--from-current] [--no-branch]\n\n"
        "Create a problem from a URL, or resume an existing local problem. Repeating the "
        "command is safe and continues its timer. New branches start from main by default."
    ),
    "resume": (
        "usage: lc resume [ts|py] [ID]\n\n"
        "Switch to the existing problem branch. With no ID, use the caller's detected problem."
    ),
    "test": (
        "usage: lc test [ts|py] [ID|PATH|all] [--watch] [-- RUNNER_ARGS...]\n\n"
        "Run a focused problem, language suite, or explicit all-suite. Outside a problem "
        "context, spell the all-suite as `lc test all`."
    ),
    "watch": (
        "usage: lc watch [ts|py] [ID|PATH|all] [-- RUNNER_ARGS...]\n\n"
        "Watch focused tests, or select a language and `all` for a complete watch suite."
    ),
    "ready": (
        "usage: lc ready [--current|--changed|all]\n\n"
        "Run the readiness gate for the current problem, changed problems, or all problems."
    ),
    "compat": "usage: lc compat\n\nCheck compatibility with the repository contract.",
    "doctor": "usage: lc doctor\n\nVerify the local setup without going through pnpm.",
    "today": "usage: lc today [ts|py] [--limit N]\n\nSelect due work before unseen work.",
    "begin": (
        "usage: lc begin [ts|py] [ID] [--mode new|review|mock]\n\n"
        "Start a timed practice session. With no ID, select today's first problem."
    ),
    "finish": (
        "usage: lc finish --result solved|hinted|failed [--confidence 1-4] "
        "[--elapsed SECONDS] [--notes TEXT]\n\n"
        "Finish the active timed session and schedule its review. --elapsed overrides the "
        "measured timer with a non-negative duration in seconds."
    ),
    "review": (
        "usage: lc review [ts|py] [ID] [--limit N]\n\n"
        "Show due reviews, or start the selected problem in review mode."
    ),
    "retry": (
        "usage: lc retry [ts|py] ID\n\n"
        "Create an isolated blank attempt under .lc with a focused test command."
    ),
    "list": (
        "usage: lc list [ts|py] [--due|--unseen|--filter STATE]\n\n"
        "List discovered problems and their practice state."
    ),
    "stats": "usage: lc stats [ts|py]\n\nReport timing, solve rates, and pattern coverage.",
    "submit": (
        "usage: lc submit [ts|py] [ID] [--copy|--copy-only] [--no-check]\n\n"
        "Run a focused preflight and emit judge-ready source."
    ),
    "copy": (
        "usage: lc copy [ts|py] [ID] [--no-check]\n\n"
        "Run a focused preflight and copy judge-ready source without printing it."
    ),
    "new": (
        "usage: lc new [ts|py] ID TITLE... [METADATA OPTIONS]\n\n"
        "Create an offline scaffold. URL workflows should normally use `lc start URL`."
    ),
}
DEFAULT_BASE_BRANCH = "main"
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
    difficulty: str | None = None
    topics: tuple[str, ...] = ()
    kind: str = "function"
    starter_code: str | None = None
    examples: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class LifecycleResult:
    """The selected problem and branch returned by ``start`` or ``resume``."""

    language: str
    problem_id: str
    directory: Path
    source_path: Path
    test_path: Path
    branch: str
    created: bool = False
    metadata: ProblemMetadata | None = None


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
    try:
        signature = (
            extract_typescript_signature(snippet)
            if language == "ts"
            else extract_python_signature(snippet)
        )
    except LeetError:
        # Design problems and signatures involving judge-provided types cannot be reduced to the
        # repository's small function template. Preserve the official starter verbatim instead.
        signature = None

    difficulty = question.get("difficulty")
    if difficulty is not None and (
        not isinstance(difficulty, str) or difficulty.lower() not in {"easy", "medium", "hard"}
    ):
        raise LeetError("LeetCode returned invalid problem difficulty metadata")
    raw_topics = question.get("topicTags", [])
    if not isinstance(raw_topics, list):
        raise LeetError("LeetCode returned invalid problem topic metadata")
    topics: list[str] = []
    for topic in raw_topics:
        if not isinstance(topic, dict):
            raise LeetError("LeetCode returned invalid problem topic metadata")
        label = topic.get("slug") or topic.get("name")
        if not isinstance(label, str) or not label.strip():
            raise LeetError("LeetCode returned invalid problem topic metadata")
        topics.append(label.strip())
    raw_examples = question.get("exampleTestcaseList", [])
    if not isinstance(raw_examples, list) or any(
        not isinstance(example, str) for example in raw_examples
    ):
        raise LeetError("LeetCode returned invalid example metadata")

    kind = "function"
    if signature is None:
        is_design_class = (
            re.search(r"(?m)^[ \t]*class[ \t]+", snippet) is not None
            if language == "ts"
            else PYTHON_SOLUTION_CLASS.search(snippet) is None
        )
        if is_design_class:
            kind = "design"
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
        difficulty=difficulty.title() if isinstance(difficulty, str) else None,
        topics=tuple(dict.fromkeys(topics)),
        kind=kind,
        starter_code=snippet if signature is None else None,
        examples=tuple(raw_examples),
    )


def _problem_details(metadata: ProblemMetadata) -> ProblemDetails:
    """Translate fetched metadata into the scaffold module's stable input shape."""
    return ProblemDetails(
        difficulty=metadata.difficulty,
        topics=metadata.topics,
        kind=metadata.kind,
        starter_code=metadata.starter_code,
        examples=metadata.examples,
    )


def _git_error(action: str, result: CommandResult) -> LeetError:
    detail = (result.stderr or result.stdout).strip()
    return LeetError(f"Git could not {action}{f': {detail}' if detail else ''}")


def _repository_branch(root: Path, run: GitRunner = run_command) -> str:
    """Require this repository root and return its attached branch without inspecting dirt."""
    repository = run(("git", "rev-parse", "--show-toplevel"), root)
    if repository.returncode != 0:
        raise _git_error("locate the repository", repository)
    try:
        is_root = Path(repository.stdout.strip()).resolve() == root.resolve()
    except OSError:
        is_root = False
    if not is_root:
        raise LeetError("lc must run for this repository's root worktree")

    current = run(("git", "branch", "--show-current"), root)
    if current.returncode != 0:
        raise _git_error("read the current branch", current)
    branch = current.stdout.strip()
    if not branch:
        raise LeetError("cannot create a problem branch from a detached HEAD")
    return branch


def preflight_git(root: Path, run: GitRunner = run_command) -> str:
    """Require the repository root, a clean worktree, and an attached branch."""
    branch = _repository_branch(root, run)
    status = run(("git", "status", "--porcelain"), root)
    if status.returncode != 0:
        raise _git_error("inspect the worktree", status)
    if status.stdout.strip():
        raise LeetError("worktree must be clean before creating a problem branch")
    return branch


def _require_new_branch(root: Path, branch: str, run: GitRunner) -> None:
    existing = run(("git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"), root)
    if existing.returncode == 0:
        raise LeetError(f"branch already exists: {branch}")
    if existing.returncode != 1:
        raise _git_error("check the target branch", existing)

    remote_refs = run(("git", "for-each-ref", "--format=%(refname)", "refs/remotes"), root)
    if remote_refs.returncode != 0:
        raise _git_error("check remote target branches", remote_refs)
    remote_suffix = f"/{branch}"
    if any(ref.strip().endswith(remote_suffix) for ref in remote_refs.stdout.splitlines()):
        raise LeetError(f"branch already exists on a remote: {branch}")


def _require_new_problem(root: Path, language: str, metadata: ProblemMetadata) -> None:
    slug = slugify(metadata.title)
    directory, _, _ = build_paths(root, language, metadata.problem_id, slug)
    existing = matching_problem_directories(directory.parent, metadata.problem_id)
    if existing:
        raise LeetError(f"problem ID already exists: {existing[0]}")
    if directory.exists():
        raise LeetError(f"target already exists: {directory}")


def _rollback_branch(root: Path, original: str, created: str, run: GitRunner) -> str | None:
    switched = run(("git", "switch", original), root)
    if switched.returncode != 0:
        return str(_git_error(f"restore branch {original!r}", switched))
    deleted = run(("git", "branch", "-D", created), root)
    if deleted.returncode != 0:
        return str(_git_error(f"delete rolled-back branch {created!r}", deleted))
    return None


def scaffold_from_url(
    root: Path,
    language: str,
    value: str,
    *,
    fetch: ProblemFetcher = fetch_problem_metadata,
    run: GitRunner = run_command,
    creator: ProblemCreator = create_problem,
    active_session: Session | None = None,
) -> ScaffoldResult:
    """Fetch, branch, and scaffold one problem as a single guarded workflow."""
    canonical_url, _ = canonicalize_problem_url(value)
    original_branch = preflight_git(root, run)
    metadata = fetch(language, canonical_url)
    _require_compatible_practice_session(active_session, metadata.problem_id, language)
    current_branch = preflight_git(root, run)
    if current_branch != original_branch:
        raise LeetError("current branch changed while LeetCode metadata was loading")
    branch = suggested_branch(metadata.problem_id, slugify(metadata.title))
    _require_new_branch(root, branch, run)
    _require_new_problem(root, language, metadata)

    switched = run(("git", "switch", "-c", branch), root)
    if switched.returncode != 0:
        raise _git_error(f"create and switch to branch {branch!r}", switched)
    try:
        source_path, test_path, _ = creator(
            root,
            language,
            metadata.problem_id,
            [metadata.title],
            metadata.canonical_url,
            metadata.signature,
            details=_problem_details(metadata),
        )
    except (LeetError, ScaffoldError, OSError) as error:
        rollback_error = _rollback_branch(root, original_branch, branch, run)
        if rollback_error:
            raise LeetError(f"{error}; automatic rollback failed: {rollback_error}") from error
        raise LeetError(f"could not create scaffold: {error}") from error
    return ScaffoldResult(metadata, source_path, test_path, branch)


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
    "begin-practice": "begin",
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


def _context_from_branch(root: Path, branch: str) -> ProblemContext | None:
    """Resolve a strict problem branch to one local problem directory."""
    branch_match = PROBLEM_BRANCH.fullmatch(branch.strip())
    if branch_match is None:
        return None
    try:
        problem_id = normalize_problem_id(branch_match["problem_id"])
    except ScaffoldError:
        return None
    directories = _available_problem_directories(root, problem_id)
    if not directories:
        return None
    preferred = _configured_primary_language(root)
    language = preferred if preferred in directories else ("ts" if "ts" in directories else "py")
    return ProblemContext(language, problem_id, directories[language])


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
    return _context_from_branch(root, current.stdout)


def _problem_file_paths(directory: Path, language: str) -> tuple[Path, Path]:
    """Return conventional source/test paths, preferring an existing Python test name."""
    extension = "py" if language == "py" else "ts"
    source_path = directory / f"{directory.name}.{extension}"
    if language == "py":
        test_candidates = (
            directory / f"test_{directory.name}.py",
            directory / f"test_{directory.name.removeprefix('p_')}.py",
        )
    else:
        test_candidates = (directory / f"{directory.name}.test.ts",)
    test_path = next((path for path in test_candidates if path.is_file()), test_candidates[0])
    return source_path, test_path


def _branch_name_for_directory(problem_id: str, directory: Path) -> str:
    """Return the conventional branch for a problem directory."""
    prefix = f"p_{problem_id}_"
    name = directory.name
    if name.startswith(prefix):
        slug = name[len(prefix) :]
    else:
        match = PROBLEM_DIRECTORY.fullmatch(name)
        slug = name.split("_", 2)[-1] if match is not None else name
    return suggested_branch(problem_id, slug)


def _current_branch(root: Path, run: GitRunner) -> str:
    """Read the attached branch or raise a user-facing Git error."""
    result = run(("git", "branch", "--show-current"), root)
    if result.returncode != 0:
        raise _git_error("read the current branch", result)
    branch = result.stdout.strip()
    if not branch:
        raise LeetError("cannot operate on a detached HEAD")
    return branch


def _branch_exists(root: Path, branch: str, run: GitRunner) -> bool:
    """Return whether a local branch exists, preserving Git failures."""
    result = run(("git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"), root)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise _git_error("check the target branch", result)


def _branch_for_problem_id(root: Path, problem_id: str, run: GitRunner) -> str | None:
    """Find one local conventional problem branch when its files are not checked out."""
    result = run(("git", "for-each-ref", "--format=%(refname:short)", "refs/heads"), root)
    if result.returncode != 0:
        raise _git_error("list local problem branches", result)
    matches: list[str] = []
    for value in result.stdout.splitlines():
        branch = value.strip()
        branch_match = PROBLEM_BRANCH.fullmatch(branch)
        if branch_match is None:
            continue
        try:
            branch_id = normalize_problem_id(branch_match["problem_id"])
        except ScaffoldError:
            continue
        if branch_id == problem_id:
            matches.append(branch)
    if len(matches) > 1:
        raise LeetError(f"multiple local branches found for ID {problem_id}: {', '.join(matches)}")
    return matches[0] if matches else None


def _switch_branch(root: Path, current: str, target: str, run: GitRunner) -> str:
    """Switch to ``target`` when needed and return the resulting branch."""
    if current == target:
        return current
    switched = run(("git", "switch", target), root)
    if switched.returncode != 0:
        raise _git_error(f"switch to branch {target!r}", switched)
    return target


def current_problem_status(
    root: Path,
    caller_cwd: Path,
    *,
    git_run: GitRunner = run_command,
) -> tuple[ProblemContext | None, str | None, Path | None, Path | None]:
    """Return detected problem, branch, and conventional source/test paths."""
    branch_result = git_run(("git", "branch", "--show-current"), root)
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
    context = _context_from_directory(root, caller_cwd)
    if context is None and branch is not None:
        context = _context_from_branch(root, branch)
    if context is None:
        return None, branch, None, None
    source_path, test_path = _problem_file_paths(context.directory, context.language)
    return context, branch, source_path, test_path


def _split_passthrough(arguments: Sequence[str]) -> tuple[list[str], list[str]]:
    values = list(arguments)
    if "--" not in values:
        return values, []
    separator = values.index("--")
    if "--" in values[separator + 1 :]:
        raise LcUsageError("-- may only be provided once")
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
    selected_language = explicit_language or inferred

    # A solution path is a useful thing to paste at the prompt, but runners
    # execute tests.  Translate only the conventional solution filename so
    # arbitrary fixture paths keep their existing behavior.
    directory = absolute.resolve().parent
    source_name = f"{directory.name}.{'py' if selected_language == 'py' else 'ts'}"
    if absolute.name == source_name:
        if selected_language == "py":
            candidates = (
                directory / f"test_{directory.name}.py",
                directory / f"test_{directory.name.removeprefix('p_')}.py",
            )
        else:
            candidates = (directory / f"{directory.name}.test.ts",)
        test_path = next(
            (candidate for candidate in candidates if candidate.is_file()),
            candidates[0],
        )
        normalized = test_path.relative_to(root.resolve()).as_posix()
    return selected_language, normalized


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
        if language is None and passthrough:
            raise LcUsageError("all-suite tests do not accept runner arguments; select a language")

    if target is not None and not target.removesuffix(".").isdecimal():
        selected_language, path = _test_path(root, caller_cwd, target, language)
        script = f"test:{selected_language}:watch" if watch else f"test:{selected_language}"
        return ("pnpm", "run", script, path, *passthrough)

    if target is not None:
        _normalized_problem_id(target)
        selected_language = language or _configured_primary_language(root)
        command = ["pnpm", "run", "test:one", selected_language, target]
        if watch:
            command.append("--watch")
        command.extend(passthrough)
        return tuple(command)

    if language is not None:
        script = f"test:{language}:watch" if watch else f"test:{language}"
        return ("pnpm", "run", script, *passthrough)

    context = None if explicit_all else detect_problem_context(root, caller_cwd, git_run=git_run)
    if context is not None:
        command = ["pnpm", "run", "test:one", context.language, context.problem_id]
        if watch:
            command.append("--watch")
        command.extend(passthrough)
        return tuple(command)
    if watch:
        if explicit_all:
            return ("pnpm", "run", "test:ts:watch", *passthrough)
        raise LcUsageError(
            "no current problem detected; use 'lc watch all' to watch all TypeScript tests"
        )
    if passthrough:
        raise LcUsageError("all-language tests do not accept runner arguments; select ts or py")
    if explicit_all:
        return ("pnpm", "run", "test")
    raise LcUsageError("no current problem detected; use 'lc test all' to run all tests")


def _existing_problem_directory(
    root: Path,
    problem_id: str,
    language: str | None = None,
) -> tuple[str, Path] | None:
    """Find one local problem directory, preferring TypeScript by default."""
    preferred = _configured_primary_language(root)
    languages = (
        (language,) if language is not None else (preferred, "py" if preferred == "ts" else "ts")
    )
    found: list[tuple[str, Path]] = []
    for selected_language in languages:
        directory = root / "src" / ("python" if selected_language == "py" else "typescript")
        matches = matching_problem_directories(directory, problem_id)
        if len(matches) > 1:
            names = ", ".join(path.name for path in matches)
            raise LeetError(
                f"multiple {selected_language} problem directories found for ID {problem_id}: "
                f"{names}"
            )
        if matches:
            found.append((selected_language, matches[0]))
    return found[0] if found else None


def _existing_problem_for_url(
    root: Path,
    canonical_url: str,
    language: str | None = None,
) -> tuple[str, str, Path] | None:
    """Find a complete local scaffold whose tracked metadata names this exact URL."""
    preferred = _configured_primary_language(root)
    languages = (
        (language,) if language is not None else (preferred, "py" if preferred == "ts" else "ts")
    )
    for selected_language in languages:
        language_directory = (
            root / "src" / ("python" if selected_language == "py" else "typescript")
        )
        if not language_directory.is_dir():
            continue
        matches: list[tuple[str, Path]] = []
        for directory in sorted(language_directory.iterdir()):
            directory_match = PROBLEM_DIRECTORY.fullmatch(directory.name)
            metadata_path = directory / "problem.toml"
            if directory_match is None or not directory.is_dir() or not metadata_path.is_file():
                continue
            try:
                document = tomllib.loads(metadata_path.read_text(encoding="utf-8"))
                values = document
                for table_name in ("problem", "metadata"):
                    table = document.get(table_name)
                    if isinstance(table, dict):
                        values = {**document, **table}
                        break
                problem_id = _normalized_problem_id(directory_match["problem_id"])
                metadata_id = _normalized_problem_id(str(values.get("id", "")))
            except LcUsageError, OSError, UnicodeError, tomllib.TOMLDecodeError:
                continue
            if metadata_id != problem_id or values.get("url") != canonical_url:
                continue
            source_path, test_path = _problem_file_paths(directory, selected_language)
            if source_path.is_file() and test_path.is_file():
                matches.append((problem_id, directory))
        if len(matches) > 1:
            directories = ", ".join(str(directory) for _, directory in matches)
            raise LeetError(f"multiple local problems use {canonical_url}: {directories}")
        if matches:
            problem_id, directory = matches[0]
            return selected_language, problem_id, directory
    return None


def _lifecycle_result(
    language: str,
    problem_id: str,
    directory: Path,
    branch: str,
    *,
    created: bool = False,
    metadata: ProblemMetadata | None = None,
) -> LifecycleResult:
    source_path, test_path = _problem_file_paths(directory, language)
    missing = [str(path) for path in (source_path, test_path) if not path.is_file()]
    if missing:
        raise LeetError("incomplete local problem scaffold; missing: " + ", ".join(missing))
    return LifecycleResult(
        language,
        problem_id,
        directory,
        source_path,
        test_path,
        branch,
        created,
        metadata,
    )


def _configured_primary_language(root: Path) -> str:
    """Return the configured default language, with TypeScript compatibility fallback."""
    try:
        configured = load_config(root)
    except ConfigError as error:
        raise LcUsageError(f"invalid lc.toml: {error}") from error
    except OSError:
        return "ts"
    language = getattr(configured, "primary_language", "ts")
    return language if language in {"py", "ts"} else "ts"


def _configured_base_branch(root: Path, value: str | None = None) -> str:
    """Read the configured base branch, defaulting to the repository's ``main``."""
    if value is None and os.environ.get("LC_BASE_BRANCH") is None:
        try:
            value = getattr(load_config(root), "base_branch", None)
        except ConfigError as error:
            raise LcUsageError(f"invalid lc.toml: {error}") from error
        except OSError:
            value = None
    branch = (value or os.environ.get("LC_BASE_BRANCH") or DEFAULT_BASE_BRANCH).strip()
    if not branch or any(character.isspace() for character in branch):
        raise LcUsageError("base branch must be a non-empty Git branch name")
    return branch


def _require_compatible_practice_session(
    active: Session | None,
    problem_id: str,
    language: str,
) -> None:
    """Reject a lifecycle mutation that would leave a different timer running."""
    if active is None:
        return
    if active.problem_id == problem_id and active.language == language:
        return
    raise LeetError(
        f"practice session {active.problem_id} ({active.language}) is already active; "
        "run 'lc finish' first"
    )


def start_problem(
    root: Path,
    language: str | None,
    value: str,
    *,
    fetch: ProblemFetcher = fetch_problem_metadata,
    run: GitRunner = run_command,
    creator: ProblemCreator = create_problem,
    from_current: bool = False,
    no_branch: bool = False,
    base_branch: str | None = None,
    active_session: Session | None = None,
) -> LifecycleResult:
    """Start or resume a problem without ever stacking a feature branch.

    ``value`` may be a URL (which can create a new scaffold) or a local
    problem ID (which can only select an existing scaffold).  Existing target
    branches are resumed idempotently.  New branches are based on ``main`` by
    default; ``--from-current`` deliberately opts into the caller's branch.
    """
    if language is not None and language not in {"py", "ts"}:
        raise LcUsageError("language must be 'py' or 'ts'")
    requested_language = language
    current_without_preflight = _repository_branch(root, run)
    metadata: ProblemMetadata | None = None
    problem_id: str
    directory: Path | None = None
    selected_language: str | None = None
    if _looks_like_url(value):
        canonical_url, _ = canonicalize_problem_url(value)
        selected_language = requested_language or _configured_primary_language(root)

        # A repeated URL start can run while the first invocation's scaffold is
        # still untracked.  Use the exact URL recorded by that scaffold and the
        # branch derived from its created directory, so a title/URL slug mismatch
        # cannot defeat the dirty-worktree repeat guard.
        local_problem = _existing_problem_for_url(root, canonical_url, requested_language)
        if local_problem is not None:
            selected_language, local_problem_id, directory = local_problem
            expected_branch = _branch_name_for_directory(local_problem_id, directory)
            if no_branch or current_without_preflight == expected_branch:
                _require_compatible_practice_session(
                    active_session, local_problem_id, selected_language
                )
                return _lifecycle_result(
                    selected_language,
                    local_problem_id,
                    directory,
                    current_without_preflight,
                )

        original_branch = preflight_git(root, run)
        metadata = fetch(selected_language, canonical_url)
        problem_id = metadata.problem_id
        preferred_slug = slugify(metadata.title)
        directory = build_paths(root, selected_language, problem_id, preferred_slug)[0]
        current_branch = preflight_git(root, run)
        if current_branch != original_branch:
            raise LeetError("current branch changed while LeetCode metadata was loading")
    else:
        problem_id = _normalized_problem_id(value)
        if (
            requested_language is None
            and active_session is not None
            and active_session.problem_id == problem_id
        ):
            requested_language = active_session.language
        existing = _existing_problem_directory(root, problem_id, requested_language)
        if existing is not None:
            selected_language, directory = existing
            if no_branch:
                _require_compatible_practice_session(active_session, problem_id, selected_language)
                return _lifecycle_result(
                    selected_language,
                    problem_id,
                    directory,
                    current_without_preflight,
                )
            target_branch = _branch_name_for_directory(problem_id, directory)
            if current_without_preflight == target_branch:
                _require_compatible_practice_session(active_session, problem_id, selected_language)
                return _lifecycle_result(
                    selected_language,
                    problem_id,
                    directory,
                    current_without_preflight,
                )
        original_branch = preflight_git(root, run)

    # An URL gives us a branch name before any local files are inspected.  This
    # is the key idempotence guard: a repeated start switches to that branch,
    # rather than creating a branch from whichever feature branch is checked
    # out at the time.
    target_branch: str | None = None
    if metadata is not None:
        target_branch = suggested_branch(problem_id, slugify(metadata.title))
    else:
        existing = _existing_problem_directory(root, problem_id, requested_language)
        if existing is None:
            target_branch = _branch_for_problem_id(root, problem_id, run)
            if target_branch is None:
                raise LcUsageError(
                    f"problem ID {problem_id} is not available locally; start by URL to create it"
                )
        else:
            selected_language, directory = existing
            target_branch = _branch_name_for_directory(problem_id, directory)

    if selected_language is None and active_session is not None:
        if active_session.problem_id != problem_id:
            raise LeetError(
                f"practice session {active_session.problem_id} ({active_session.language}) is "
                "already active; run 'lc finish' first"
            )
        selected_language = active_session.language
    if selected_language is not None:
        _require_compatible_practice_session(active_session, problem_id, selected_language)

    current = original_branch
    branch_exists = _branch_exists(root, target_branch, run)
    if branch_exists:
        if no_branch and current != target_branch:
            if directory is None or not directory.is_dir():
                raise LeetError(
                    f"target branch already exists: {target_branch}; omit --no-branch to resume it"
                )
        else:
            current = _switch_branch(root, current, target_branch, run)
            try:
                existing = _existing_problem_directory(
                    root, problem_id, requested_language or selected_language
                )
                if existing is not None:
                    selected_language, directory = existing
                    _require_compatible_practice_session(
                        active_session, problem_id, selected_language
                    )
                    return _lifecycle_result(
                        selected_language,
                        problem_id,
                        directory,
                        current,
                        metadata=metadata,
                    )
                if metadata is None:
                    raise LeetError(
                        f"branch {target_branch} has no local problem directory for ID {problem_id}"
                    )
                # A branch can exist after an interrupted scaffold.  Complete its
                # files in place instead of making a second branch.
                if selected_language is None:
                    raise LeetError("could not determine the problem language")
                directory = build_paths(
                    root, selected_language, problem_id, slugify(metadata.title)
                )[0]
                _require_new_problem(root, selected_language, metadata)
                try:
                    source_path, test_path, _ = creator(
                        root,
                        selected_language,
                        metadata.problem_id,
                        [metadata.title],
                        metadata.canonical_url,
                        metadata.signature,
                        details=_problem_details(metadata),
                    )
                except (LeetError, ScaffoldError, OSError) as error:
                    raise LeetError(f"could not create scaffold: {error}") from error
            except (LeetError, ScaffoldError, OSError) as error:
                if current != original_branch:
                    restored = run(("git", "switch", original_branch), root)
                    if restored.returncode != 0:
                        restore_error = _git_error(f"restore branch {original_branch!r}", restored)
                        raise LeetError(f"{error}; {restore_error}") from error
                raise
            return LifecycleResult(
                selected_language,
                problem_id,
                directory,
                source_path,
                test_path,
                current,
                True,
                metadata,
            )

    if directory is not None and directory.is_dir():
        # Existing files on the current branch can be adopted safely only
        # from the configured base branch, or with an explicit opt-in.  This
        # prevents ``lc start`` from silently stacking one feature branch on
        # another when a branch was not created conventionally.
        if no_branch:
            if selected_language is None:
                raise LeetError("could not determine the problem language")
            return _lifecycle_result(
                selected_language, problem_id, directory, current, metadata=metadata
            )
        base = current if from_current else _configured_base_branch(root, base_branch)
        if current != base:
            raise LeetError(
                f"problem {problem_id} exists on branch {current}; use --from-current to branch "
                "from here"
            )
        if selected_language is None:
            raise LeetError("could not determine the problem language")
        _require_new_branch(root, target_branch, run)
        result = _lifecycle_result(
            selected_language,
            problem_id,
            directory,
            target_branch,
            metadata=metadata,
        )
        switched = run(("git", "switch", "-c", target_branch), root)
        if switched.returncode != 0:
            raise _git_error(f"create and switch to branch {target_branch!r}", switched)
        return result

    if no_branch:
        if metadata is None:
            raise LcUsageError("--no-branch can only create a problem from a URL")
        if selected_language is None:
            raise LeetError("could not determine the problem language")
        _require_new_problem(root, selected_language, metadata)
        try:
            source_path, test_path, _ = creator(
                root,
                selected_language,
                metadata.problem_id,
                [metadata.title],
                metadata.canonical_url,
                metadata.signature,
                details=_problem_details(metadata),
            )
        except (LeetError, ScaffoldError, OSError) as error:
            raise LeetError(f"could not create scaffold: {error}") from error
        directory = source_path.parent
        return LifecycleResult(
            selected_language,
            problem_id,
            directory,
            source_path,
            test_path,
            current,
            True,
            metadata,
        )

    base = current if from_current else _configured_base_branch(root, base_branch)
    if current != base:
        current = _switch_branch(root, current, base, run)
    try:
        _require_new_branch(root, target_branch, run)
        if metadata is None:
            raise LeetError("cannot create a local scaffold without URL metadata")
        if selected_language is None:
            raise LeetError("could not determine the problem language")
        _require_new_problem(root, selected_language, metadata)

        switched = run(("git", "switch", "-c", target_branch), root)
        if switched.returncode != 0:
            raise _git_error(f"create and switch to branch {target_branch!r}", switched)
    except (LeetError, ScaffoldError, OSError) as error:
        if current != original_branch:
            restored = run(("git", "switch", original_branch), root)
            if restored.returncode != 0:
                restore_error = _git_error(f"restore branch {original_branch!r}", restored)
                raise LeetError(f"{error}; {restore_error}") from error
        raise
    try:
        source_path, test_path, _ = creator(
            root,
            selected_language,
            metadata.problem_id,
            [metadata.title],
            metadata.canonical_url,
            metadata.signature,
            details=_problem_details(metadata),
        )
    except (LeetError, ScaffoldError, OSError) as error:
        rollback_error = _rollback_branch(root, original_branch, target_branch, run)
        if rollback_error:
            raise LeetError(f"{error}; automatic rollback failed: {rollback_error}") from error
        raise LeetError(f"could not create scaffold: {error}") from error
    return LifecycleResult(
        selected_language,
        problem_id,
        source_path.parent,
        source_path,
        test_path,
        target_branch,
        True,
        metadata,
    )


def resume_problem(
    root: Path,
    problem_id: str | None = None,
    language: str | None = None,
    *,
    caller_cwd: Path | None = None,
    run: GitRunner = run_command,
    active_session: Session | None = None,
) -> LifecycleResult:
    """Resume an existing problem branch selected by ID or current context."""
    current = preflight_git(root, run)
    context: ProblemContext | None
    if problem_id is None:
        context = detect_problem_context(root, caller_cwd or root, git_run=run)
        if context is None:
            raise LcUsageError("no current problem detected; provide an ID")
        selected_language = context.language
        normalized_id = context.problem_id
        directory = context.directory
    else:
        normalized_id = _normalized_problem_id(problem_id)
        existing = _existing_problem_directory(root, normalized_id, language)
        if existing is None:
            target_branch = _branch_for_problem_id(root, normalized_id, run)
            if target_branch is None:
                raise LcUsageError(f"problem ID {normalized_id} is not available locally")
            selected_language = language
            directory = None
        else:
            selected_language, directory = existing
            target_branch = _branch_name_for_directory(normalized_id, directory)
    if problem_id is None:
        target_branch = _branch_name_for_directory(normalized_id, directory)
    if not _branch_exists(root, target_branch, run):
        raise LeetError(f"branch does not exist: {target_branch}")
    if active_session is not None:
        if active_session.problem_id != normalized_id:
            raise LeetError(
                f"practice session {active_session.problem_id} ({active_session.language}) is "
                "already active; run 'lc finish' first"
            )
        if selected_language is None:
            selected_language = active_session.language
        _require_compatible_practice_session(active_session, normalized_id, selected_language)
    original_branch = current
    current = _switch_branch(root, current, target_branch, run)
    try:
        if directory is None or not directory.is_dir():
            existing = _existing_problem_directory(root, normalized_id, selected_language)
            if existing is None:
                raise LeetError(
                    f"branch {target_branch} has no local problem directory for ID {normalized_id}"
                )
            selected_language, directory = existing
        _require_compatible_practice_session(active_session, normalized_id, selected_language)
        return _lifecycle_result(selected_language, normalized_id, directory, current)
    except LeetError as error:
        if current != original_branch:
            restored = run(("git", "switch", original_branch), root)
            if restored.returncode != 0:
                restore_error = _git_error(f"restore branch {original_branch!r}", restored)
                raise LeetError(f"{error}; {restore_error}") from error
        raise


def _submit_command(
    arguments: Sequence[str],
    root: Path,
    caller_cwd: Path,
    *,
    force_copy: bool = False,
    git_run: GitRunner = run_command,
) -> tuple[str, ...]:
    values = list(arguments)
    option_names = {"--copy", "--copy-only", "--no-check"}
    selected_options = [value for value in values if value in option_names]
    values = [value for value in values if value not in option_names]
    if force_copy:
        selected_options.append("--copy-only")
    for option in option_names:
        if selected_options.count(option) > 1:
            raise LcUsageError(f"{option} may only be provided once")
    if "--copy" in selected_options and "--copy-only" in selected_options:
        raise LcUsageError("--copy and --copy-only cannot be combined")
    unknown = next((value for value in values if value.startswith("-")), None)
    if unknown is not None:
        raise LcUsageError(f"unknown submit option: {unknown}")

    language: str | None = None
    if values and (selected := _canonical_language(values[0])) is not None:
        language = selected
        values.pop(0)
    if len(values) > 1:
        raise LcUsageError("usage: lc submit [ts|py] [ID] [--copy|--copy-only] [--no-check]")

    if values:
        problem_id = values[0]
        _normalized_problem_id(problem_id)
        selected_language = language or _configured_primary_language(root)
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
    for option in ("--copy", "--copy-only", "--no-check"):
        if option in selected_options:
            command.append(option)
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


def _ready_command(
    arguments: Sequence[str],
    root: Path,
    caller_cwd: Path,
    *,
    git_run: GitRunner = run_command,
) -> tuple[str, ...]:
    """Build the stable stdlib readiness-script interface."""
    values = list(arguments)
    if len(values) > 1:
        raise LcUsageError("usage: lc ready [--current|--changed|all]")
    scope = values[0] if values else "--current"
    if scope == "--current":
        context = detect_problem_context(root, caller_cwd, git_run=git_run)
        if context is None:
            if values:
                raise LcUsageError("no current problem detected; use 'lc ready --changed' or 'all'")
            return ("python", "scripts/ready.py", "changed")
        if caller_cwd.resolve() == root.resolve():
            problem_id = context.problem_id
            languages = [
                language
                for language, directory_name in (("ts", "typescript"), ("py", "python"))
                if matching_problem_directories(root / "src" / directory_name, problem_id)
            ]
            if len(languages) > 1:
                raise LcUsageError(
                    f"problem {problem_id} exists in both languages; run lc ready --changed or from a problem directory"
                )
        return ("python", "scripts/ready.py", "current", context.language, context.problem_id)
    if scope == "--changed":
        return ("python", "scripts/ready.py", "changed")
    if scope == "all":
        return ("python", "scripts/ready.py", "all")
    raise LcUsageError("ready scope must be --current, --changed, or all")


PRACTICE_COMMANDS = frozenset({"today", "begin", "finish", "review", "retry", "list", "stats"})


def _practice_command(command: str, arguments: Sequence[str], root: Path) -> tuple[str, ...]:
    """Build a direct practice command while accepting the lc language shorthand."""
    practice_command = "start" if command == "begin" else command
    values = list(arguments)
    if values and (language := _canonical_language(values[0])) is not None:
        values[:1] = ["--language", language]
    return (
        "python",
        "scripts/practice.py",
        practice_command,
        *values,
        "--human",
        "--root",
        str(root),
    )


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

    if command == "practice":
        if not rest:
            raise LcUsageError("usage: lc practice COMMAND [arguments]")
        nested = "begin" if rest[0] == "start" else rest[0]
        if nested not in PRACTICE_COMMANDS:
            raise LcUsageError(f"unknown practice command: {rest[0]}")
        return _practice_command(nested, rest[1:], root)
    if command in PRACTICE_COMMANDS:
        return _practice_command(command, rest, root)
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
        language = _configured_primary_language(root)
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

    if command == "doctor":
        if rest:
            raise LcUsageError("doctor does not accept arguments")
        return ("python", "scripts/doctor.py")
    if command == "ready":
        return _ready_command(rest, root, caller_cwd, git_run=git_run)
    if command == "compat":
        if rest:
            raise LcUsageError("compat does not accept arguments")
        return ("pnpm", "run", "compat")

    scripts = {
        "check": "check",
        "incomplete": "incomplete",
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


def _url_invocation(
    arguments: Sequence[str],
    *,
    default_language: str = "ts",
) -> tuple[str, str] | None:
    values = list(arguments)
    if values and COMMAND_ALIASES.get(values[0], values[0]) == "new":
        values.pop(0)
    if len(values) == 1 and _looks_like_url(values[0]):
        return default_language, values[0]
    if len(values) == 2:
        language = _canonical_language(values[0])
        if language is not None and _looks_like_url(values[1]):
            return language, values[1]
    return None


def _print_scaffold_result(result: ScaffoldResult, root: Path, language: str) -> None:
    print(f"LeetCode {result.metadata.problem_id}: {result.metadata.title}")
    print(f"Shape: {result.metadata.kind}")
    if result.metadata.signature is not None:
        print(f"Signature: {result.metadata.signature}")
    if result.metadata.difficulty is not None:
        print(f"Difficulty: {result.metadata.difficulty}")
    if result.metadata.topics:
        print(f"Topics: {', '.join(result.metadata.topics)}")
    print(f"Branch: {result.branch}")
    print(f"Created: {result.source_path.relative_to(root)}")
    print(f"Created: {result.test_path.relative_to(root)}")
    print(f"Created: {(result.source_path.parent / 'problem.toml').relative_to(root)}")
    print(f"Created: {(result.source_path.parent / 'notes.md').relative_to(root)}")
    print("Next steps:")
    print("  lc test")
    print("  lc watch")
    print("  lc ready")


def _print_lifecycle_result(result: LifecycleResult, root: Path) -> None:
    """Print one concise start/resume result with paths users can copy."""
    action = "Created" if result.created else "Resumed"
    print(f"Problem: {result.problem_id} ({result.language})")
    print(f"Branch: {result.branch}")
    print(f"Source: {result.source_path.relative_to(root)}")
    print(f"Test: {result.test_path.relative_to(root)}")
    print(f"{action}: {result.directory.relative_to(root)}")


def _read_active_practice_session(
    root: Path, *, store: PracticeStore | None = None
) -> Session | None:
    """Read the timer state and translate storage errors for the unified CLI."""
    try:
        return (store or PracticeStore(root)).read_active()
    except PracticeError as error:
        raise LeetError(f"could not read practice timer: {error}") from error


def _ensure_practice_session(
    root: Path,
    result: LifecycleResult,
    *,
    mode: str | None = None,
    store: PracticeStore | None = None,
) -> tuple[Session, bool]:
    """Start the problem timer, treating a repeated start of the same problem as resume."""
    try:
        active = _read_active_practice_session(root, store=store)
        if active is not None:
            if active.problem_id == result.problem_id and active.language == result.language:
                return active, False
            raise LeetError(
                f"practice session {active.problem_id} ({active.language}) is already active; "
                "run 'lc finish' first"
            )
        if store is not None:
            return (
                start_in_transaction(
                    store,
                    result.problem_id,
                    result.language,
                    mode,
                    None,
                ),
                True,
            )
        return start_session(root, result.problem_id, result.language, mode=mode), True
    except PracticeError as error:
        raise LeetError(f"could not start practice timer: {error}") from error


def _print_practice_session(session: Session, created: bool) -> None:
    verb = "Started" if created else "Continuing"
    print(f"Practice: {verb.lower()} {session.mode} timer at {session.started_at.isoformat()}")
    print("Finish: lc finish --result solved|hinted|failed --confidence 1-4")


def _print_current(root: Path, caller_cwd: Path) -> None:
    """Print the detected problem, branch, and conventional source/test paths."""
    context, branch, source_path, test_path = current_problem_status(root, caller_cwd)
    print(f"Problem: {context.problem_id} ({context.language})" if context else "Problem: none")
    print(f"Branch: {branch or 'detached/unknown'}")
    print(f"Source: {source_path.relative_to(root) if source_path else '-'}")
    print(f"Test: {test_path.relative_to(root) if test_path else '-'}")


def _parse_start_arguments(
    arguments: Sequence[str],
    _root: Path | None = None,
) -> tuple[str | None, str, bool, bool, str | None, str | None, bool]:
    """Parse ``start`` options while keeping the target positional."""
    values = list(arguments)
    from_current = False
    no_branch = False
    start_timer = True
    selected_base: str | None = None
    mode: str | None = None
    position = 0
    while position < len(values):
        value = values[position]
        if value == "--from-current":
            if from_current:
                raise LcUsageError("--from-current may only be provided once")
            from_current = True
            values.pop(position)
            continue
        if value == "--no-branch":
            if no_branch:
                raise LcUsageError("--no-branch may only be provided once")
            no_branch = True
            values.pop(position)
            continue
        if value == "--no-timer":
            if not start_timer:
                raise LcUsageError("--no-timer may only be provided once")
            start_timer = False
            values.pop(position)
            continue
        if value == "--mode":
            if mode is not None:
                raise LcUsageError("--mode may only be provided once")
            if position + 1 >= len(values):
                raise LcUsageError("--mode requires new, review, or mock")
            mode = values[position + 1]
            if mode not in {"new", "review", "mock"}:
                raise LcUsageError("--mode requires new, review, or mock")
            del values[position : position + 2]
            continue
        if value == "--base-branch":
            if selected_base is not None:
                raise LcUsageError("--base-branch may only be provided once")
            if position + 1 >= len(values):
                raise LcUsageError("--base-branch requires a branch name")
            selected_base = values[position + 1]
            del values[position : position + 2]
            continue
        if value.startswith("-"):
            raise LcUsageError(f"unknown start option: {value}")
        position += 1

    language: str | None = None
    if values and (selected_language := _canonical_language(values[0])) is not None:
        language = selected_language
        values.pop(0)
    if len(values) != 1:
        raise LcUsageError(
            "usage: lc start [ts|py] URL|ID [--mode new|review|mock] [--no-timer] "
            "[--from-current] [--no-branch]"
        )
    return language, values[0], from_current, no_branch, selected_base, mode, start_timer


def _parse_resume_arguments(arguments: Sequence[str]) -> tuple[str | None, str | None]:
    """Parse ``resume``'s optional language and problem ID."""
    values = list(arguments)
    if any(value.startswith("-") for value in values):
        unknown = next(value for value in values if value.startswith("-"))
        raise LcUsageError(f"unknown resume option: {unknown}")
    language: str | None = None
    if values and (selected_language := _canonical_language(values[0])) is not None:
        language = selected_language
        values.pop(0)
    if len(values) > 1:
        raise LcUsageError("usage: lc resume [ts|py] [ID]")
    return language, values[0] if values else None


def main(argv: Sequence[str] | None = None) -> int:
    """Run the unified local LeetCode command."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help", "help"}:
        print(HELP)
        return 0
    if any(argument in {"-h", "--help"} for argument in arguments[1:]):
        command = COMMAND_ALIASES.get(arguments[0], arguments[0])
        print(COMMAND_HELP.get(command, HELP))
        return 0
    root = Path(__file__).resolve().parents[1]
    caller_cwd = Path(os.environ.get("LC_CALLER_CWD", root))
    try:
        command = COMMAND_ALIASES.get(arguments[0], arguments[0])
        if command == "current":
            if len(arguments) != 1:
                raise LcUsageError("usage: lc current")
            _print_current(root, caller_cwd)
            return 0
        if command == "start":
            (
                language,
                value,
                from_current,
                no_branch,
                selected_base,
                mode,
                start_timer,
            ) = _parse_start_arguments(arguments[1:], root)
            store = PracticeStore(root)
            with store.session_transaction():
                active_session = _read_active_practice_session(root, store=store)
                result = start_problem(
                    root,
                    language,
                    value,
                    from_current=from_current,
                    no_branch=no_branch,
                    base_branch=selected_base,
                    active_session=active_session,
                )
                if start_timer:
                    session, created = _ensure_practice_session(
                        root,
                        result,
                        mode=mode,
                        store=store,
                    )
            _print_lifecycle_result(result, root)
            if start_timer:
                _print_practice_session(session, created)
            return 0
        if command == "resume":
            language, problem_id = _parse_resume_arguments(arguments[1:])
            store = PracticeStore(root)
            with store.session_transaction():
                result = resume_problem(
                    root,
                    problem_id,
                    language,
                    caller_cwd=caller_cwd,
                    active_session=_read_active_practice_session(root, store=store),
                )
            _print_lifecycle_result(result, root)
            return 0
        url_invocation = _url_invocation(
            arguments,
            default_language=_configured_primary_language(root),
        )
        if url_invocation is not None:
            language, problem_url = url_invocation
            store = PracticeStore(root)
            with store.session_transaction():
                result = scaffold_from_url(
                    root,
                    language,
                    problem_url,
                    active_session=_read_active_practice_session(root, store=store),
                )
            _print_scaffold_result(result, root, language)
            return 0
        command = build_command(arguments, root, caller_cwd)
        return run_interactive_command(command, root)
    except LcUsageError as error:
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
