import ast
import json
import subprocess
from pathlib import Path

import pytest

from scripts.examples import Example, extract_examples
from scripts.lc import fetch_problem_metadata, scaffold_from_url
from tests.test_lc import FakeResponse, PROBLEM_URL, graphql_document


def question():
    return {
        "content": "<pre><strong>Input:</strong> nums = [1,3,5,6], target = 5\n<strong>Output:</strong> 2\n</pre><pre><b>Input:</b> nums = [1,3,5,6], target = 2\n<b>Output:</b> 1\n<strong>Explanation:</strong> Before 3.</pre>",
        "exampleTestcases": "[1,3,5,6]\n5\n[1,3,5,6]\n2",
        "metaData": json.dumps(
            {
                "params": [
                    {"name": "nums", "type": "integer[]"},
                    {"name": "target", "type": "integer"},
                ],
                "return": {"type": "integer"},
            }
        ),
    }


def test_extracts_official_examples():
    examples, reason = extract_examples(question())
    assert reason is None
    assert examples == (Example(([1, 3, 5, 6], 5), 2), Example(([1, 3, 5, 6], 2), 1))


@pytest.mark.parametrize(
    "rule",
    [
        "Return the answers in any order.",
        "Modify the array in-place.",
        "Return any valid answer.",
        "Return in any <b>order</b>.",
        "Return in any\norder.",
        "The order does not matter.",
        "Absolute error below 0.1 is accepted.",
    ],
)
def test_special_judging_gets_template(rule):
    examples, reason = extract_examples(
        {**question(), "content": question()["content"] + f"<p>{rule}</p>"}
    )
    assert not examples and reason


@pytest.mark.parametrize("return_type", ["ListNode", "TreeNode", "void", "double"])
def test_nodes_mutation_and_special_outputs_get_template(return_type):
    data = question()
    metadata = json.loads(data["metaData"])
    metadata["return"]["type"] = return_type
    data["metaData"] = json.dumps(metadata)
    assert extract_examples(data)[1]


@pytest.mark.parametrize(
    "changes",
    [
        {"exampleTestcases": "[1,3,5,6]\n5"},
        {"exampleTestcases": "__import__('os').system('touch bad')"},
        {"metaData": "{}"},
        {"metaData": "null"},
        {"content": "<pre>Output: 2 or 3</pre>"},
        {"content": "<pre>Output: null</pre>"},
    ],
)
def test_unclear_examples_are_never_evaluated(changes):
    assert extract_examples({**question(), **changes})[1]


@pytest.mark.parametrize(
    "metadata",
    [
        {"params": [None], "return": {"type": "integer"}},
        {"params": [{"type": None}], "return": {"type": "integer"}},
        {"params": [{"type": "integer"}], "return": {"type": []}},
        {"params": "integer", "return": {"type": "integer"}},
        {"params": [{"type": "integer"}], "return": None},
    ],
)
def test_malformed_metadata_falls_back(metadata):
    assert extract_examples({**question(), "metaData": json.dumps(metadata)})[1]


def test_empty_arrays_do_not_hide_unsupported_types():
    data = {
        "content": "<pre>Output: []</pre>",
        "exampleTestcases": "[]",
        "metaData": json.dumps(
            {"params": [{"type": "TreeNode[]"}], "return": {"type": "integer[]"}}
        ),
    }
    assert extract_examples(data)[1]


@pytest.mark.parametrize("value", [str(2**53), "NaN", "Infinity", "2true"])
def test_unsafe_numbers_and_invalid_json_get_template(value):
    assert extract_examples({**question(), "exampleTestcases": f"[1]\n{value}\n[1]\n2"})[1]


@pytest.mark.parametrize("language", ["py", "ts"])
def test_special_judging_keeps_the_skipped_template(tmp_path, language):
    document = graphql_document()
    data = question()
    data["content"] += "<p>Modify the input in place.</p>"
    document["data"]["question"].update(data)
    metadata = fetch_problem_metadata(
        language, PROBLEM_URL, open_url=lambda *_a, **_kw: FakeResponse(document)
    )
    result = scaffold_from_url(tmp_path, language, PROBLEM_URL, fetch=lambda *_: metadata)
    assert "GENERATED_SCAFFOLD_TEST" in result.test_path.read_text()
    assert metadata.example_note


def test_string_boolean_and_nested_arrays():
    data = {
        "content": "<pre>Output: true</pre>",
        "exampleTestcases": '[["a", "b"]]\n"quote: \\""',
        "metaData": json.dumps(
            {"params": [{"type": "string[][]"}, {"type": "string"}], "return": {"type": "boolean"}}
        ),
    }
    examples, reason = extract_examples(data)
    assert reason is None and examples[0].expected is True
    assert examples[0].args[1] == 'quote: "'


@pytest.mark.parametrize("language", ["py", "ts"])
def test_scaffold_example_tests_run_against_a_real_solution(tmp_path, language):
    document = graphql_document()
    document["data"]["question"].update(question())
    metadata = fetch_problem_metadata(
        language, PROBLEM_URL, open_url=lambda *_a, **_kw: FakeResponse(document)
    )
    result = scaffold_from_url(tmp_path, language, PROBLEM_URL, fetch=lambda *_: metadata)
    source = result.test_path.read_text()
    assert "GENERATED_SCAFFOLD_TEST" not in source and ".skip" not in source
    if language == "py":
        ast.parse(source)
        result.source_path.write_text(
            "class Solution:\n    def searchInsert(self, nums, target):\n        return next((i for i, n in enumerate(nums) if n >= target), len(nums))\n"
        )
        runner = [
            str(Path(__file__).resolve().parents[1] / ".venv/bin/python"),
            "-m",
            "pytest",
            "-q",
            str(result.test_path),
        ]
        completed = subprocess.run(runner, cwd=tmp_path, capture_output=True, text=True)
        assert completed.returncode == 0, completed.stdout + completed.stderr
    else:
        # Node's built-in TypeScript support executes the generated assertions directly.
        result.source_path.with_suffix(".js").write_text(
            "export function searchInsert(nums, target) { const i = nums.findIndex(n => n >= target); return i < 0 ? nums.length : i; }\n"
        )
        harness = (
            "import { deepStrictEqual } from 'node:assert'; globalThis.test = { each: cases => (_, fn) => cases.forEach(fn) }; globalThis.expect = actual => ({toEqual: expected => deepStrictEqual(actual, expected)}); await import("
            + json.dumps(str(result.test_path))
            + ");"
        )
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", harness],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
