import subprocess
from pathlib import Path

import pytest

from scripts import submission
from scripts.submission import (
    SubmissionError,
    TypeScriptLexer,
    clipboard_command,
    copy_to_clipboard,
    parse_arguments,
    read_submission,
    typescript_submission,
)


def make_source(root: Path, language: str, contents: str) -> Path:
    name = "p_0001_two_sum"
    directory = root / "src" / ("python" if language == "py" else "typescript") / name
    directory.mkdir(parents=True)
    path = directory / f"{name}.{'py' if language == 'py' else 'ts'}"
    path.write_text(contents, encoding="utf-8")
    return path


def test_parses_submission_arguments() -> None:
    assert parse_arguments(["py", "1"]) == ("py", "1", False)
    assert parse_arguments(["ts", "92", "--copy"]) == ("ts", "92", True)


@pytest.mark.parametrize(
    "arguments, message",
    [
        ([], "usage:"),
        (["go", "1"], "language"),
        (["py", "1", "--unknown"], "unknown option"),
        (["py", "1", "--copy", "--copy"], "only be provided once"),
    ],
)
def test_rejects_invalid_submission_arguments(arguments: list[str], message: str) -> None:
    with pytest.raises(SubmissionError, match=message):
        parse_arguments(arguments)


def test_python_submission_is_emitted_verbatim(tmp_path: Path) -> None:
    source = "class Solution:\n    pass\n"
    make_source(tmp_path, "py", source)

    assert read_submission(tmp_path, "py", "1") == source


def test_typescript_submission_reads_an_unpadded_legacy_problem_directory(tmp_path: Path) -> None:
    source = "export function solve(): number { return 1; }\n"
    directory = tmp_path / "src/typescript/p_457_circular_array_loop"
    directory.mkdir(parents=True)
    (directory / "p_457_circular_array_loop.ts").write_text(source, encoding="utf-8")

    assert read_submission(tmp_path, "ts", "457") == " function solve(): number { return 1; }\n"


def test_typescript_submission_removes_only_top_level_declaration_exports() -> None:
    source = """// export function comment() {}\nconst text = "export default";\nexport async function solve(): void {}\nexport type Input = number;\nexport const answer = 42;\nfunction nested(): void {\n    const value = "import hidden";\n    void value;\n}\n"""

    prepared = typescript_submission(source)

    assert "export async" not in prepared
    assert "export type" not in prepared
    assert "export const" not in prepared
    assert "async function solve" in prepared
    assert "type Input" in prepared
    assert "const answer" in prepared
    assert "// export function comment()" in prepared
    assert '"export default"' in prepared


def test_typescript_submission_ignores_export_and_import_words_in_regex_literals() -> None:
    source = (
        "const matcher = /export|import/;\nexport function solve(): RegExp { return matcher; }\n"
    )

    prepared = typescript_submission(source)

    assert (
        prepared
        == "const matcher = /export|import/;\n function solve(): RegExp { return matcher; }\n"
    )


def test_typescript_submission_handles_regex_after_return_with_template_characters() -> None:
    source = """export function solve(value: string): boolean {
    return /[`{}](?:export|import)/.test(value);
}
"""

    prepared = typescript_submission(source)

    assert (
        prepared
        == """ function solve(value: string): boolean {
    return /[`{}](?:export|import)/.test(value);
}
"""
    )


def test_typescript_submission_allows_division_after_postfix_non_null_assertion() -> None:
    source = """export function divide(value: number | undefined, divisor: number): number {
    return value! / divisor;
}
"""

    assert typescript_submission(source) == source.replace("export", "", 1)


def test_typescript_lexer_allows_regex_after_prefix_logical_not() -> None:
    tokens = TypeScriptLexer("const matches = !/value/.test(input);\n").tokenize()

    assert [(token.value, token.kind) for token in tokens if token.kind == "regex"] == [
        ("<regex>", "regex")
    ]


def test_typescript_submission_allows_templates_without_dependencies() -> None:
    source = """const label = `{import/export} and a \\` backtick: ${"value"}`;
export function solve(value: string): string {
    return `${label} (${value})`;
}
"""

    prepared = typescript_submission(source)

    assert (
        prepared
        == """const label = `{import/export} and a \\` backtick: ${"value"}`;
 function solve(value: string): string {
    return `${label} (${value})`;
}
"""
    )


def test_typescript_submission_allows_import_and_export_property_names() -> None:
    source = """type ImportOptions = {
    import: string;
};
interface ImportMethods {
    import(): string;
}
const values = {
    import: "local",
    export: "exported",
    require(path: string): string {
        return path;
    },
};
const methods: ImportMethods = {
    import(): string {
        return "method";
    },
};
const template = `${{ import: values.import }.import}`;
export function solve(): string {
    const optional = values?.export ?? "";
    return values.import + values.export + values.require("./helper.js") + methods.import() + optional + template;
}
"""

    prepared = typescript_submission(source)

    assert prepared == source.replace("export function", " function", 1)


@pytest.mark.parametrize(
    "directive",
    [
        'path="./helper.d.ts"',
        'types="node"',
        'lib="es2024"',
        'no-default-lib="true"',
    ],
)
def test_typescript_submission_rejects_triple_slash_reference_directives(directive: str) -> None:
    source = f"/// <reference {directive} />\nexport function solve() {{}}\n"

    with pytest.raises(SubmissionError, match="triple-slash reference directive"):
        typescript_submission(source)


def test_typescript_submission_ignores_non_reference_triple_slash_comments() -> None:
    source = "/// <references are ordinary comments>\nexport function solve() {}\n"

    assert (
        typescript_submission(source)
        == "/// <references are ordinary comments>\n function solve() {}\n"
    )


@pytest.mark.parametrize(
    "source, message",
    [
        (
            'import { helper } from "./helper.js";\nexport function solve() {}\n',
            "contains an import",
        ),
        ('import "./helper.js";\n', "contains an import"),
        ('import helper = require("./helper.js");\n', "contains an import"),
        ('type Helper = import("./helper.js").Helper;\n', "contains an import"),
        ("const url = import.meta.url;\n", "contains an import"),
        ("export default function solve() {}\n", "unsupported TypeScript export"),
        ("export { solve };\n", "unsupported TypeScript export"),
        ('export * from "./helper.js";\n', "unsupported TypeScript export"),
        ('export type { Input } from "./types.js";\n', "unsupported TypeScript export"),
        ("export async class Solution {}\n", "unsupported TypeScript export"),
        ('const value = `${import("./helper.js")}`;\n', "contains an import"),
        ('const value = `${import { helper } from "./helper.js"}`;\n', "contains an import"),
        ('const value = `${`${import("./helper.js")}`}`;\n', "contains an import"),
        ('const helper = require("./helper.js");\n', "CommonJS require"),
        ('const helper = require("package-name");\n', "CommonJS require"),
        ("const helper = require(`./helper.js`);\n", "CommonJS require"),
        ("const helper = require(moduleName);\n", "CommonJS require"),
        ("module.exports = solve;\n", "CommonJS export"),
        ("exports.solve = solve;\n", "CommonJS export"),
        ('exports["solve"] = solve;\n', "CommonJS export"),
    ],
)
def test_typescript_submission_rejects_dependencies_and_unsupported_exports(
    source: str, message: str
) -> None:
    with pytest.raises(SubmissionError, match=message):
        typescript_submission(source)


def test_clipboard_commands_cover_supported_platforms() -> None:
    assert clipboard_command("win32") == ["clip"]
    assert clipboard_command("darwin") == ["pbcopy"]
    assert clipboard_command(
        "linux", lambda command: "/bin/xclip" if command == "xclip" else None
    ) == [
        "xclip",
        "-selection",
        "clipboard",
    ]
    assert clipboard_command(
        "linux", lambda command: "/bin/xsel" if command == "xsel" else None
    ) == [
        "xsel",
        "--clipboard",
        "--input",
    ]
    assert clipboard_command(
        "linux", lambda command: "C:/Windows/System32/clip.exe" if command == "clip.exe" else None
    ) == ["clip.exe"]


def test_copy_to_clipboard_is_injectable_and_reports_missing_tool() -> None:
    calls: list[tuple[object, ...]] = []

    def fake_run(*arguments: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        assert kwargs == {"input": "source", "text": True, "check": True}
        return subprocess.CompletedProcess(arguments[0], 0, "", "")

    copy_to_clipboard("source", platform="darwin", run=fake_run)

    assert calls == [(["pbcopy"],)]
    with pytest.raises(SubmissionError, match="no supported clipboard command"):
        clipboard_command("linux", lambda _command: None)


def test_copy_to_clipboard_tries_later_linux_candidates_including_wsl() -> None:
    calls: list[list[str]] = []

    def fake_which(command: str) -> str:
        return f"/usr/bin/{command}"

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs == {"input": "source", "text": True, "check": True}
        if command[0] != "clip.exe":
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0, "", "")

    copy_to_clipboard("source", platform="linux", which=fake_which, run=fake_run)

    assert calls == [
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["clip.exe"],
    ]


def test_main_prints_prepared_source_and_can_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    make_source(tmp_path, "ts", "export function solve(): number { return 1; }\n")
    monkeypatch.setattr(submission, "__file__", str(tmp_path / "scripts" / "submission.py"))
    copied: list[str] = []
    monkeypatch.setattr(submission, "copy_to_clipboard", copied.append)

    assert submission.main(["ts", "1", "--copy"]) == 0

    assert capsys.readouterr().out == " function solve(): number { return 1; }\n"
    assert copied == [" function solve(): number { return 1; }\n"]
