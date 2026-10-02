"""Browser transport contracts with isolated page doubles; live checks use the browser role."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.leetcode_browser import BrowserError, LeetCodeBrowser


def client():
    browser = LeetCodeBrowser(Path("/unused"), interactive=False)
    browser.page = Mock(url="https://leetcode.com/problems/two-sum/")
    return browser


def test_transport_keeps_credentials_in_same_origin_browser():
    browser = client()
    browser.page.evaluate.return_value = {"status": 200, "body": '{"submission_id": 123}'}
    assert browser.submit("two-sum", "py", "1", "class Solution: pass") == "123"
    script, payload = browser.page.evaluate.call_args.args
    assert "credentials: 'same-origin'" in script
    assert payload == {
        "path": "/problems/two-sum/submit/",
        "data": {
            "lang": "python3",
            "question_id": "1",
            "typed_code": "class Solution: pass",
        },
    }
    assert browser.page.evaluate.call_count == 1


def test_does_not_send_source_after_external_navigation():
    browser = client()
    browser.page.url = "https://example.com/"
    with pytest.raises(BrowserError, match="return to leetcode.com"):
        browser.submit("two-sum", "ts", "1", "secret source")
    browser.page.evaluate.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [
        {"status": 403, "body": "challenge"},
        {"status": 200, "body": "<html>challenge</html>"},
        {"status": 200, "body": '{"errors": [{"message": "bad"}]}'},
        {"status": 200, "body": "[]"},
    ],
)
def test_challenges_and_bad_responses_do_not_retry_post(response):
    browser = client()
    browser.page.evaluate.return_value = response
    with pytest.raises(BrowserError):
        browser.submit("two-sum", "ts", "1", "code")
    assert browser.page.evaluate.call_count == 1


def test_missing_submission_id_is_uncertain():
    browser = client()
    browser.request = Mock(return_value={"error": "throttled"})
    with pytest.raises(BrowserError, match="submission ID"):
        browser.submit("two-sum", "ts", "1", "code")
    assert browser.request.call_count == 1


def test_noninteractive_login_never_prompts(monkeypatch):
    browser = client()
    browser.graphql = Mock(return_value={"userStatus": {"isSignedIn": False}})
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("must not prompt"))
    with pytest.raises(BrowserError, match="login required"):
        browser.prepare("two-sum", "1")


def test_interactive_login_reuses_session(monkeypatch):
    browser = client()
    browser.interactive = True
    browser.graphql = Mock(
        side_effect=[
            {"userStatus": {"isSignedIn": False}},
            {"userStatus": {"isSignedIn": True}},
            {"question": {"questionId": "1", "questionFrontendId": "1", "titleSlug": "two-sum"}},
        ]
    )
    prompts = []
    monkeypatch.setattr("builtins.input", lambda text: prompts.append(text))
    assert browser.prepare("two-sum", "0001") == "1"
    assert prompts == []
    browser.page.wait_for_timeout.assert_called_once_with(1000)
    assert browser.page.goto.call_args_list[0].args[0].endswith("/accounts/login/")


def test_prepare_checks_problem_identity():
    browser = client()
    browser.graphql = Mock(
        side_effect=[
            {"userStatus": {"isSignedIn": True}},
            {"question": {"questionId": "2", "questionFrontendId": "2", "titleSlug": "two-sum"}},
        ]
    )
    with pytest.raises(BrowserError, match="identity"):
        browser.prepare("two-sum", "1")


def test_judging_waits_for_success(monkeypatch):
    browser = client()
    browser.request = Mock(
        side_effect=[
            {"state": "PENDING"},
            {"state": "STARTED"},
            {"state": "SUCCESS", "status_code": 10},
        ]
    )
    monkeypatch.setattr("scripts.leetcode_browser.time.sleep", lambda _: None)
    assert browser.wait("123")["status_code"] == 10
    assert browser.request.call_count == 3


def test_wait_timeout_leaves_resumable_id(monkeypatch):
    browser = client()
    browser.request = Mock(return_value={"state": "PENDING"})
    monkeypatch.setattr("scripts.leetcode_browser.time.monotonic", Mock(side_effect=[0, 0, 121]))
    monkeypatch.setattr("scripts.leetcode_browser.time.sleep", lambda _: None)
    with pytest.raises(BrowserError, match="timed out"):
        browser.wait("123")


@pytest.mark.parametrize(
    "changes",
    [{"code": "other"}, {"lang": {"name": "python3"}}, {"question": {"titleSlug": "other"}}],
)
def test_resume_verifies_source_language_and_problem(changes):
    browser = client()
    details = {"code": "code", "lang": {"name": "typescript"}, "question": {"titleSlug": "two-sum"}}
    browser.graphql = Mock(return_value={"submissionDetails": {**details, **changes}})
    with pytest.raises(BrowserError, match="does not match"):
        browser.verify_submission("123", "two-sum", "ts", "code")


def test_verify_submission_succeeds():
    browser = client()
    browser.page.evaluate.return_value = {
        "status": 200,
        "body": json.dumps(
            {
                "data": {
                    "submissionDetails": {
                        "code": "code\n",
                        "lang": {"name": "typescript"},
                        "question": {"titleSlug": "two-sum"},
                    }
                }
            }
        ),
    }
    browser.verify_submission("123", "two-sum", "ts", "code")
