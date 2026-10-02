"""Generate assertions only when official examples have ordinary JSON semantics."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True)
class Example:
    args: tuple[object, ...]
    expected: object


class Description(HTMLParser):
    def __init__(self, content: str) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.text: list[str] = []
        self.current: list[str] | None = None
        self.feed(content)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "pre":
            self.current = []
        elif tag == "br":
            self.handle_data("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "pre" and self.current is not None:
            self.blocks.append("".join(self.current))
            self.current = None
        if tag in {"p", "pre", "div", "li"}:
            self.text.append("\n")

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if self.current is not None:
            self.current.append(data)


def json_values(text: str) -> list[object]:
    """Decode whitespace-separated JSON values without evaluating example code."""

    def reject_constant(value: str) -> None:
        raise ValueError(f"not a JSON value: {value}")

    decoder = json.JSONDecoder(parse_constant=reject_constant)
    result = []
    position = 0
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        value, position = decoder.raw_decode(text, position)
        result.append(value)
    return result


def ordinary_value(value: object, type_name: str) -> bool:
    if type_name.endswith("[]"):
        return isinstance(value, list) and all(
            ordinary_value(item, type_name[:-2]) for item in value
        )
    if type_name in {"integer", "long"}:
        return type(value) is int and abs(value) <= 2**53 - 1
    if type_name in {"string", "character"}:
        return isinstance(value, str) and (type_name == "string" or len(value) == 1)
    if type_name == "boolean":
        return type(value) is bool
    return False


def extract_examples(question: dict) -> tuple[tuple[Example, ...], str | None]:
    """Fall back to an editable template if any example or judging rule is unclear."""
    content = question.get("content")
    inputs = question.get("exampleTestcases")
    raw_metadata = question.get("metaData")
    if not all(isinstance(value, str) and value for value in (content, inputs, raw_metadata)):
        return (), "Official examples or judging metadata are unavailable."
    description = Description(content)
    text = "".join(description.text).lower()
    special_rules = (
        "in-place",
        "in place",
        "any order",
        "any valid",
        "any of the",
        "multiple answers",
        "relative error",
        "absolute error",
        "modify",
        "do not return",
        "random",
    )
    if any(rule in text for rule in special_rules):
        return (), "Adapt the examples for mutation or special judging rules."
    try:
        metadata = json.loads(raw_metadata)
        params = metadata["params"]
        return_type = metadata["return"]["type"]
        if metadata.get("systemdesign") or not params:
            raise ValueError("design or zero-argument problem")
        types = [param["type"] for param in params]
        arguments = json_values(inputs)
        outputs = []
        for block in description.blocks:
            match = re.search(r"\bOutput:\s*(.*?)(?=\bExplanation:|\Z)", block, re.S)
            if match:
                values = json_values(match[1].strip())
                if len(values) != 1:
                    raise ValueError("ambiguous output")
                outputs.append(values[0])
        if not outputs or len(arguments) != len(outputs) * len(types):
            raise ValueError("example counts differ")
        examples = []
        for index, output in enumerate(outputs):
            args = arguments[index * len(types) : (index + 1) * len(types)]
            if not ordinary_value(output, return_type) or not all(
                ordinary_value(value, type_name) for value, type_name in zip(args, types)
            ):
                raise ValueError("non-JSON signature")
            examples.append(Example(tuple(args), output))
        return tuple(examples), None
    except ValueError, KeyError, TypeError:
        return (), "Adapt the examples for nodes, design classes, or ambiguous return values."


def render_example_tests(language: str, stem: str, name: str, examples: tuple[Example, ...]) -> str:
    if language == "py":
        cases = "\n".join(
            f'    pytest.param({example.args!r}, {example.expected!r}, id="example {index}"),'
            for index, example in enumerate(examples, 1)
        )
        return f"""import pytest

from {stem} import Solution


@pytest.mark.parametrize(("args", "expected"), [
{cases}
])
def test_{name}(args: tuple[object, ...], expected: object) -> None:
    assert Solution().{name}(*args) == expected
"""
    cases = "\n".join(
        "    "
        + json.dumps(
            {"name": f"example {index}", "args": example.args, "expected": example.expected},
            ensure_ascii=True,
        )
        + ","
        for index, example in enumerate(examples, 1)
    )
    return f"""import {{ {name} }} from "./{stem}.js";

const cases: Array<{{
    name: string;
    args: Parameters<typeof {name}>;
    expected: ReturnType<typeof {name}>;
}}> = [
{cases}
];

test.each(cases)("$name", ({{ args, expected }}) => {{
    expect({name}(...args)).toEqual(expected);
}});
"""
