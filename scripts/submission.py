#!/usr/bin/env python3
"""Print a LeetCode-ready solution and optionally copy it to the clipboard."""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

try:
    from scripts.problem_paths import ProblemPathError, require_source_path, resolve_problem_paths
except ModuleNotFoundError:
    from problem_paths import ProblemPathError, require_source_path, resolve_problem_paths


class SubmissionError(ValueError):
    """Raised when a source file cannot safely be prepared for submission."""


SAFE_EXPORT_DECLARATIONS = {"class", "const", "enum", "function", "interface", "let", "type", "var"}
REGEX_PREFIX_KEYWORDS = {
    "await",
    "case",
    "delete",
    "do",
    "else",
    "extends",
    "in",
    "instanceof",
    "new",
    "of",
    "return",
    "throw",
    "typeof",
    "void",
    "yield",
}
CONTROL_PAREN_KEYWORDS = {"catch", "for", "if", "switch", "while", "with"}
MULTI_CHARACTER_PUNCTUATORS = tuple(
    sorted(
        {
            "!==",
            "**=",
            "&&=",
            "...",
            "<<=",
            "===",
            ">>=",
            ">>>",
            "??=",
            ">>>=",
            "=>",
            "!=",
            "&&",
            "**",
            "+=",
            "--",
            "-=",
            "?.",
            "/=",
            "<<",
            "<=",
            "==",
            ">=",
            ">>",
            "++",
            "||",
            "|=",
            "&=",
            "%=",
            "*=",
            "^=",
            "??",
        },
        key=len,
        reverse=True,
    )
)


@dataclass(frozen=True)
class TypeScriptToken:
    """A meaningful TypeScript token, with its brace depth before the token."""

    value: str
    start: int
    end: int
    depth: int
    kind: str = "punctuator"


class TypeScriptLexer:
    """Small, conservative lexer for the constructs the submission renderer needs.

    This intentionally is not a TypeScript parser or transpiler.  It only needs to
    distinguish executable tokens from comments and literals while retaining enough
    expression context to identify regular-expression literals.  That lets the
    renderer reject dependencies without treating their spelling inside a string,
    regular expression, or template text as code.
    """

    def __init__(self, source: str) -> None:
        self.source = source
        self.length = len(source)
        self.tokens: list[TypeScriptToken] = []
        self.brace_depth = 0
        self.parentheses: list[bool] = []
        self.brackets = 0
        self.last_value: str | None = None
        self.regex_allowed = True

    def tokenize(self) -> list[TypeScriptToken]:
        """Tokenize source, rejecting malformed literal/nesting syntax conservatively."""
        self._scan_code(0)
        if self.parentheses:
            raise SubmissionError("TypeScript submission has an unclosed parenthesis")
        if self.brackets:
            raise SubmissionError("TypeScript submission has an unclosed bracket")
        if self.brace_depth:
            raise SubmissionError("TypeScript submission has an unclosed brace")
        return self.tokens

    def _scan_code(self, index: int, *, template_depth: int | None = None) -> int:
        while index < self.length:
            character = self.source[index]
            next_character = self.source[index + 1] if index + 1 < self.length else ""

            if character.isspace():
                index += 1
                continue
            if character == "/" and next_character == "/":
                if self._is_triple_slash_reference_directive(index):
                    raise SubmissionError(
                        "TypeScript submission contains a triple-slash reference directive"
                    )
                newline = self.source.find("\n", index + 2)
                index = self.length if newline == -1 else newline
                continue
            if character == "/" and next_character == "*":
                comment_end = self.source.find("*/", index + 2)
                if comment_end == -1:
                    raise SubmissionError("TypeScript submission has an unclosed block comment")
                index = comment_end + 2
                continue
            if character in {"'", '"'}:
                literal_start = index
                index = self._scan_string(index)
                self._emit("<string>", literal_start, index, kind="string")
                self._finish_literal()
                continue
            if character == "`":
                index = self._scan_template(index)
                continue
            if character == "/" and self.regex_allowed:
                literal_start = index
                index = self._scan_regular_expression(index)
                self._emit("<regex>", literal_start, index, kind="regex")
                self._finish_literal()
                continue
            if self._is_identifier_start(character):
                index = self._scan_identifier(index)
                continue
            if character.isdigit() or (character == "." and next_character.isdigit()):
                literal_start = index
                index = self._scan_number(index)
                self._emit("<number>", literal_start, index, kind="number")
                self._finish_literal()
                continue
            if character == "\\":
                raise SubmissionError(
                    "TypeScript submission has an escaped identifier and cannot be safely verified"
                )
            if (
                character == "}"
                and template_depth is not None
                and self.brace_depth == template_depth + 1
            ):
                self._emit("}", index, index + 1)
                self.brace_depth -= 1
                self._finish_punctuator("}")
                return index + 1
            if character == "}":
                if self.brace_depth == 0:
                    raise SubmissionError("TypeScript submission has an unmatched closing brace")
                self._emit("}", index, index + 1)
                self.brace_depth -= 1
                self._finish_punctuator("}")
                index += 1
                continue
            if character == "(":
                self.parentheses.append(self.last_value in CONTROL_PAREN_KEYWORDS)
                self._emit("(", index, index + 1)
                self._finish_punctuator("(")
                index += 1
                continue
            if character == ")":
                if not self.parentheses:
                    raise SubmissionError(
                        "TypeScript submission has an unmatched closing parenthesis"
                    )
                starts_statement = self.parentheses.pop()
                self._emit(")", index, index + 1)
                self._finish_punctuator(")", starts_statement=starts_statement)
                index += 1
                continue
            if character == "[":
                self.brackets += 1
                self._emit("[", index, index + 1)
                self._finish_punctuator("[")
                index += 1
                continue
            if character == "]":
                if self.brackets == 0:
                    raise SubmissionError("TypeScript submission has an unmatched closing bracket")
                self.brackets -= 1
                self._emit("]", index, index + 1)
                self._finish_punctuator("]")
                index += 1
                continue
            if character == "{":
                self._emit("{", index, index + 1)
                self.brace_depth += 1
                self._finish_punctuator("{")
                index += 1
                continue

            punctuator = self._punctuator_at(index)
            self._emit(punctuator, index, index + len(punctuator))
            self._finish_punctuator(punctuator)
            index += len(punctuator)

        if template_depth is not None:
            raise SubmissionError("TypeScript submission has an unclosed template expression")
        return index

    def _scan_string(self, index: int) -> int:
        quote = self.source[index]
        index += 1
        while index < self.length:
            character = self.source[index]
            if character == "\\":
                index = self._skip_escape(index)
            elif character == quote:
                return index + 1
            elif character in "\r\n":
                raise SubmissionError("TypeScript submission has an unclosed string literal")
            else:
                index += 1
        raise SubmissionError("TypeScript submission has an unclosed string literal")

    def _scan_template(self, index: int) -> int:
        index += 1
        while index < self.length:
            character = self.source[index]
            if character == "\\":
                index = self._skip_escape(index)
            elif character == "`":
                self._finish_literal()
                return index + 1
            elif character == "$" and index + 1 < self.length and self.source[index + 1] == "{":
                template_depth = self.brace_depth
                self._emit("{", index + 1, index + 2)
                self.brace_depth += 1
                self.last_value = None
                self.regex_allowed = True
                index = self._scan_code(index + 2, template_depth=template_depth)
            else:
                index += 1
        raise SubmissionError("TypeScript submission has an unclosed template literal")

    def _scan_regular_expression(self, index: int) -> int:
        index += 1
        in_character_class = False
        while index < self.length:
            character = self.source[index]
            if character == "\\":
                index = self._skip_escape(index)
            elif character in "\r\n":
                raise SubmissionError(
                    "TypeScript submission has an unclosed regular-expression literal"
                )
            elif character == "[":
                in_character_class = True
                index += 1
            elif character == "]":
                in_character_class = False
                index += 1
            elif character == "/" and not in_character_class:
                index += 1
                while index < self.length and self._is_identifier_part(self.source[index]):
                    index += 1
                return index
            else:
                index += 1
        raise SubmissionError("TypeScript submission has an unclosed regular-expression literal")

    def _scan_identifier(self, index: int) -> int:
        start = index
        index += 1
        while index < self.length and self._is_identifier_part(self.source[index]):
            index += 1
        value = self.source[start:index]
        self._emit(value, start, index, kind="identifier")
        self.last_value = value
        self.regex_allowed = value in REGEX_PREFIX_KEYWORDS
        return index

    def _scan_number(self, index: int) -> int:
        if (
            self.source[index] == "0"
            and index + 1 < self.length
            and self.source[index + 1] in "bBoOxX"
        ):
            index += 2
            while index < self.length and (
                self.source[index].isalnum() or self.source[index] == "_"
            ):
                index += 1
            return index

        while index < self.length and (self.source[index].isdigit() or self.source[index] == "_"):
            index += 1
        if index < self.length and self.source[index] == ".":
            index += 1
            while index < self.length and (
                self.source[index].isdigit() or self.source[index] == "_"
            ):
                index += 1
        if index < self.length and self.source[index] in "eE":
            index += 1
            if index < self.length and self.source[index] in "+-":
                index += 1
            while index < self.length and (
                self.source[index].isdigit() or self.source[index] == "_"
            ):
                index += 1
        if index < self.length and self.source[index] == "n":
            index += 1
        return index

    def _skip_escape(self, index: int) -> int:
        if index + 1 >= self.length:
            raise SubmissionError("TypeScript submission has an incomplete escape sequence")
        if (
            self.source[index + 1] == "\r"
            and index + 2 < self.length
            and self.source[index + 2] == "\n"
        ):
            return index + 3
        return index + 2

    def _punctuator_at(self, index: int) -> str:
        for punctuator in MULTI_CHARACTER_PUNCTUATORS:
            if self.source.startswith(punctuator, index):
                return punctuator
        return self.source[index]

    def _emit(self, value: str, start: int, end: int, *, kind: str = "punctuator") -> None:
        self.tokens.append(TypeScriptToken(value, start, end, self.brace_depth, kind))

    def _is_triple_slash_reference_directive(self, index: int) -> bool:
        if not self.source.startswith("///", index):
            return False
        line_end = self.source.find("\n", index + 3)
        line_end = self.length if line_end == -1 else line_end
        directive = self.source[index + 3 : line_end].lstrip(" \t")
        return directive.startswith("<reference") and (
            len(directive) == len("<reference") or directive[len("<reference")] in " \t/>"
        )

    def _finish_literal(self) -> None:
        self.last_value = "<literal>"
        self.regex_allowed = False

    def _finish_punctuator(self, value: str, *, starts_statement: bool = False) -> None:
        self.last_value = value
        if value == ")":
            self.regex_allowed = starts_statement
        elif value == "!" and not self.regex_allowed:
            # A postfix non-null assertion follows an expression; a prefix logical-not does not.
            self.regex_allowed = False
        elif value in {".", "?.", "++", "--", "]", "}"}:
            self.regex_allowed = False
        else:
            self.regex_allowed = True

    @staticmethod
    def _is_identifier_start(character: str) -> bool:
        return character in {"$", "_"} or character.isalpha()

    @staticmethod
    def _is_identifier_part(character: str) -> bool:
        return character in {"$", "_"} or character.isalnum()


def parse_arguments(arguments: Sequence[str]) -> tuple[str, str, bool]:
    """Parse ``submission <py|ts> <id> [--copy]``."""
    if len(arguments) < 2:
        raise SubmissionError("usage: submission <py|ts> <id> [--copy]")
    language, problem_id, *options = arguments
    if language not in {"py", "ts"}:
        raise SubmissionError("language must be 'py' or 'ts'")
    if any(option != "--copy" for option in options):
        unknown = next(option for option in options if option != "--copy")
        raise SubmissionError(f"unknown option: {unknown}")
    if options.count("--copy") > 1:
        raise SubmissionError("--copy may only be provided once")
    return language, problem_id, "--copy" in options


def is_property_access(tokens: Sequence[TypeScriptToken], index: int) -> bool:
    """Return whether a keyword-shaped token is the name in a member access."""
    return index > 0 and tokens[index - 1].value in {".", "?."}


def matching_parenthesis(tokens: Sequence[TypeScriptToken], opening_index: int) -> int | None:
    """Find the close parenthesis matching a token known to be an opening parenthesis."""
    depth = 0
    for index in range(opening_index, len(tokens)):
        value = tokens[index].value
        if value == "(":
            depth += 1
        elif value == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def is_member_method_declaration(tokens: Sequence[TypeScriptToken], index: int) -> bool:
    """Recognize an object, class, or type-literal method declaration."""
    opening_index = index + 1
    if opening_index >= len(tokens) or tokens[opening_index].value != "(":
        return False
    closing_index = matching_parenthesis(tokens, opening_index)
    if closing_index is None or closing_index + 1 >= len(tokens):
        return False
    return tokens[closing_index + 1].value in {":", "{"}


def has_import_declaration_tail(tokens: Sequence[TypeScriptToken], binding_index: int) -> bool:
    """Recognize the ``from`` or ``=`` tail of a static TypeScript import binding."""
    depth = tokens[binding_index].depth
    for token in tokens[binding_index + 1 :]:
        if token.depth < depth:
            return False
        if token.depth != depth:
            continue
        if token.value in {"from", "="}:
            return True
        if token.value in {";", "}"}:
            return False
    return False


def is_static_import_declaration(tokens: Sequence[TypeScriptToken], index: int) -> bool:
    """Recognize the narrow set of static and TypeScript-specific import declarations."""
    following_index = index + 1
    if following_index >= len(tokens):
        return False
    following = tokens[following_index]
    if following.kind == "string" or following.value in {"{", "*"}:
        return True
    if following.value == "type":
        following_index += 1
        if following_index >= len(tokens):
            return False
        following = tokens[following_index]
        if following.value in {"{", "*"}:
            return True
    if following.kind == "identifier":
        return has_import_declaration_tail(tokens, following_index)
    return False


def is_import_dependency(tokens: Sequence[TypeScriptToken], index: int) -> bool:
    """Return whether an ``import`` token is module syntax rather than a property name."""
    if is_property_access(tokens, index):
        return False
    following_index = index + 1
    if following_index >= len(tokens):
        return False
    following = tokens[following_index]
    if following.value == "(":
        return not is_member_method_declaration(tokens, index)
    if following.value == ".":
        return following_index + 1 < len(tokens) and tokens[following_index + 1].value == "meta"
    return is_static_import_declaration(tokens, index)


def is_commonjs_require_call(tokens: Sequence[TypeScriptToken], index: int) -> bool:
    """Return whether a token begins an unqualified CommonJS ``require`` call."""
    if is_property_access(tokens, index) or is_member_method_declaration(tokens, index):
        return False
    opening_index = index + 1
    if opening_index < len(tokens) and tokens[opening_index].value == "?.":
        opening_index += 1
    return opening_index < len(tokens) and tokens[opening_index].value == "("


def is_commonjs_export(tokens: Sequence[TypeScriptToken], index: int) -> bool:
    """Return whether a token starts unsupported CommonJS export syntax."""
    if is_property_access(tokens, index):
        return False
    following = tokens[index + 1 : index + 3]
    if tokens[index].value == "module":
        return (
            len(following) == 2
            and following[0].value in {".", "?."}
            and following[1].value == "exports"
        )
    if tokens[index].value == "exports":
        return bool(following) and following[0].value in {".", "?.", "[", "="}
    return False


def typescript_submission(source: str) -> str:
    """Strip declaration exports while rejecting dependencies and export forms LeetCode cannot use."""
    tokens = TypeScriptLexer(source).tokenize()

    removals: list[tuple[int, int]] = []
    for index, token in enumerate(tokens):
        value = token.value
        if value == "import" and is_import_dependency(tokens, index):
            raise SubmissionError(
                "TypeScript submission contains an import and cannot be self-contained"
            )
        if value == "require" and is_commonjs_require_call(tokens, index):
            raise SubmissionError(
                "TypeScript submission contains a CommonJS require and cannot be self-contained"
            )
        if value in {"module", "exports"} and is_commonjs_export(tokens, index):
            raise SubmissionError(
                "TypeScript submission contains a CommonJS export and cannot be self-contained"
            )
        if value != "export" or token.depth != 0 or is_property_access(tokens, index):
            continue

        following = index + 1
        if following >= len(tokens):
            raise SubmissionError("unsupported TypeScript export at end of file")
        declaration = tokens[following].value
        if declaration == "async":
            following += 1
            if following >= len(tokens):
                raise SubmissionError("unsupported TypeScript export: export async")
            declaration = tokens[following].value
            if declaration != "function":
                raise SubmissionError(f"unsupported TypeScript export: export async {declaration}")
        elif declaration == "declare":
            following += 1
            if following >= len(tokens):
                raise SubmissionError("unsupported TypeScript export: export declare")
            declaration = tokens[following].value

        if declaration not in SAFE_EXPORT_DECLARATIONS:
            raise SubmissionError(f"unsupported TypeScript export: export {declaration}")
        if declaration == "type" and following + 1 < len(tokens):
            if tokens[following + 1].value in {"{", "*"}:
                raise SubmissionError("unsupported TypeScript export: export type re-export")
        removals.append((token.start, token.end))

    output = source
    for start, end in reversed(removals):
        output = output[:start] + output[end:]
    return output


def read_submission(root: Path, language: str, problem_id: str) -> str:
    """Read the requested solution and transform it only when TypeScript requires it."""
    paths = resolve_problem_paths(root, language, problem_id)
    source = require_source_path(paths).read_text(encoding="utf-8")
    return source if language == "py" else typescript_submission(source)


def clipboard_command(
    platform: str, which: Callable[[str], str | None] = shutil.which
) -> list[str]:
    """Return an available native clipboard command for the given platform."""
    return clipboard_commands(platform, which)[0]


def clipboard_commands(
    platform: str, which: Callable[[str], str | None] = shutil.which
) -> list[list[str]]:
    """Return usable clipboard candidates, ordered by the native preference."""
    if platform.startswith("win"):
        return [["clip"]]
    if platform == "darwin":
        return [["pbcopy"]]
    commands: list[list[str]] = []
    for command in ("wl-copy", "xclip", "xsel", "clip.exe"):
        if which(command):
            if command == "xclip":
                commands.append([command, "-selection", "clipboard"])
            elif command == "xsel":
                commands.append([command, "--clipboard", "--input"])
            else:
                commands.append([command])
    if commands:
        return commands
    raise SubmissionError(
        "no supported clipboard command found (tried wl-copy, xclip, xsel, and clip.exe)"
    )


def copy_to_clipboard(
    content: str,
    *,
    platform: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    """Copy text using the platform's native clipboard tool."""
    effective_platform = sys.platform if platform is None else platform
    errors: list[OSError | subprocess.CalledProcessError] = []
    for command in clipboard_commands(effective_platform, which):
        try:
            run(command, input=content, text=True, check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            errors.append(error)
        else:
            return
    error = errors[-1]
    raise SubmissionError(f"failed to copy submission to clipboard: {error}") from error


def main(argv: Sequence[str] | None = None) -> int:
    """Run the submission command-line interface."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        language, problem_id, should_copy = parse_arguments(arguments)
        source = read_submission(Path(__file__).resolve().parents[1], language, problem_id)
        if should_copy:
            copy_to_clipboard(source)
    except (ProblemPathError, SubmissionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2 if str(error).startswith("usage:") else 1
    sys.stdout.write(source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
