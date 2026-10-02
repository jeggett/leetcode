"""Whitelist displayable judge metrics for durable submission results."""

import math
import re


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError, OverflowError:
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _count(value):
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def submission_url(submission_id):
    value = str(submission_id)
    if value.isascii() and value.isdecimal() and int(value) > 0:
        return f"https://leetcode.com/submissions/detail/{value}/"
    return None


def normalize_result(verdict, submission_id):
    result = {}
    code = _count(verdict.get("status_code"))
    if code is not None:
        result["status_code"] = code
    label = verdict.get("status_msg")
    if isinstance(label, str) and re.fullmatch(r"[A-Za-z][A-Za-z -]{0,79}", label):
        result["verdict"] = label
    elif code is not None:
        result["verdict"] = str(code)
    url = submission_url(submission_id)
    if url:
        result["url"] = url
    for remote, local, units in (
        ("status_runtime", "runtime", r"ms|s"),
        ("status_memory", "memory", r"B|KB|MB|GB|KiB|MiB|GiB"),
    ):
        value = verdict.get(remote)
        if (
            isinstance(value, str)
            and len(value) <= 40
            and re.fullmatch(rf"\d+(?:\.\d+)? *(?:{units})", value)
            and _number(re.match(r"\d+(?:\.\d+)?", value)[0]) is not None
        ):
            result[local] = value
    if "memory" not in result:
        memory = _number(verdict.get("memory"))
        if memory is not None:
            result["memory"] = f"{memory / (1024 * 1024):.2f} MiB"
    for remote, local in (("total_correct", "passed"), ("total_testcases", "total")):
        count = _count(verdict.get(remote))
        if count is not None:
            result[local] = count
    for key in ("runtime_percentile", "memory_percentile"):
        number = _number(verdict.get(key))
        if number is not None and number <= 100:
            result[key] = number
    return result


def result_summary(attempt):
    saved = attempt.get("result")
    saved = saved if isinstance(saved, dict) else {}
    result = normalize_result(
        {
            "status_msg": saved.get("verdict", attempt.get("verdict")),
            "status_code": saved.get("status_code"),
            "status_runtime": saved.get("runtime"),
            "status_memory": saved.get("memory"),
            "total_correct": saved.get("passed"),
            "total_testcases": saved.get("total"),
            "runtime_percentile": saved.get("runtime_percentile"),
            "memory_percentile": saved.get("memory_percentile"),
        },
        attempt.get("submission_id"),
    )
    parts = [result.get("verdict", "Unknown verdict")]
    for key in ("runtime", "memory"):
        if key in result:
            parts.append(f"{key}: {result[key]}")
    if "passed" in result and "total" in result:
        parts.append(f"tests: {result['passed']}/{result['total']}")
    for key in ("runtime_percentile", "memory_percentile"):
        if key in result:
            parts.append(f"{key.removesuffix('_percentile')} percentile: {result[key]:g}%")
    url = submission_url(attempt.get("submission_id"))
    if url:
        parts.append(url)
    return " | ".join(parts)
