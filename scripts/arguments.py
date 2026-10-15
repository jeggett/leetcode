"""Shared command options for lc and its low-level package scripts."""

import argparse
from collections.abc import Sequence

LANGUAGES = {"py": "py", "python": "py", "ts": "ts", "typescript": "ts"}


class UsageError(ValueError):
    """An invalid workflow invocation."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise UsageError(
            self.format_usage().strip()
            + "\n"
            + message.replace("unrecognized arguments", "unknown option")
        )


class Once(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"{option_string} may only be provided once")
        setattr(namespace, self.dest, True if self.nargs == 0 else values)


def parse(command: str, arguments: Sequence[str], *, scoped: bool = False) -> argparse.Namespace:
    """Parse options once; scoped commands may infer a language and problem."""
    parser = Parser(prog=f"lc {command}", add_help=False, allow_abbrev=False)
    if command == "new":
        parser.add_argument("--url", action=Once, metavar="URL")
        parser.add_argument("--signature", action=Once, metavar="SIGNATURE")
    elif command == "test":
        parser.add_argument("--watch", action=Once, nargs=0)
    elif command == "submit":
        for flag in ("--copy", "--copy-only", "--no-check"):
            parser.add_argument(flag, action=Once, nargs=0)
    elif command == "format":
        parser.add_argument("--check", action=Once, nargs=0)
    parser.add_argument("values", nargs="*", metavar="TARGET")
    options = parser.parse_intermixed_args(list(arguments))
    values = options.values
    options.language = LANGUAGES.get(values[0].lower()) if values else None
    if options.language:
        values.pop(0)
    elif not scoped or command in {"format", "lint"} and values:
        parser.error("language must be 'py' or 'ts'")
    if command == "new":
        if len(values) < 2:
            parser.error("provide a problem ID and title")
        options.problem_id, *options.title = values
    else:
        if len(values) > 1 or command in {"format", "lint"} and values:
            parser.error("expected one problem ID or path")
        options.problem_id = values[0] if values else None
    if not scoped and options.problem_id is None:
        parser.error("provide a problem ID")
    if command == "submit" and options.copy and options.copy_only:
        parser.error("--copy and --copy-only cannot be combined")
    return options


def split_runner_args(arguments: Sequence[str]) -> tuple[list[str], list[str]]:
    values = list(arguments)
    if "--" not in values:
        return values, []
    separator = values.index("--")
    return values[:separator], values[separator + 1 :]
