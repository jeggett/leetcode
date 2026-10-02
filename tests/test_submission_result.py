"""Result normalization excludes malformed fields and remote diagnostics."""

import pytest

from scripts.submission_result import normalize_result, result_summary


def test_metrics_and_whitelist():
    result = normalize_result(
        {
            "status_code": 10,
            "status_msg": "Accepted",
            "status_runtime": "0 ms",
            "memory": 1048576,
            "total_correct": 0,
            "total_testcases": "12",
            "runtime_percentile": 0,
            "memory_percentile": 100,
            "code": "private source",
            "full_compile_error": "private diagnostics",
        },
        "123",
    )
    assert result == {
        "status_code": 10,
        "verdict": "Accepted",
        "url": "https://leetcode.com/submissions/detail/123/",
        "runtime": "0 ms",
        "memory": "1.00 MiB",
        "passed": 0,
        "total": 12,
        "runtime_percentile": 0,
        "memory_percentile": 100,
    }


@pytest.mark.parametrize("value", [True, False, -1, "-1", float("nan"), float("inf"), {}, []])
def test_invalid_numbers_are_omitted(value):
    assert (
        normalize_result(
            {"memory": value, "total_correct": value, "runtime_percentile": value}, None
        )
        == {}
    )


def test_absent_and_malformed_text():
    assert normalize_result({}, None) == {}
    assert (
        normalize_result(
            {"status_runtime": "-1 ms", "status_memory": "error body", "status_msg": "body\nlog"},
            True,
        )
        == {}
    )
    result = normalize_result({"status_memory": "12 MB", "memory": 0}, "1")
    assert result["memory"] == "12 MB"


def test_old_attempt_summary():
    assert result_summary({"verdict": "Accepted", "submission_id": "123"}) == (
        "Accepted | https://leetcode.com/submissions/detail/123/"
    )


def test_saved_malformed_metrics_are_omitted():
    assert (
        result_summary(
            {
                "verdict": "Wrong Answer",
                "submission_id": "123",
                "result": {"runtime_percentile": "bad", "passed": True, "total": -1},
            }
        )
        == "Wrong Answer | https://leetcode.com/submissions/detail/123/"
    )
    assert result_summary({"status": "rejected"}) == "Unknown verdict"
