"""Session import, credential boundaries, and HTTP failure recovery contracts."""

import io
import json
import stat
import warnings
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from scripts import leetcode_session as auth


@pytest.fixture
def credentials():
    return auth.Credentials("session-secret", "csrf-secret")


def response(body, *, status=200, headers=None):
    result = Mock(status=status, headers=headers or {})
    result.read.return_value = json.dumps(body).encode() if isinstance(body, dict) else body
    context = Mock()
    context.__enter__ = Mock(return_value=result)
    context.__exit__ = Mock(return_value=False)
    return context


@pytest.fixture
def client(tmp_path, credentials):
    session = auth.LeetCodeSession(tmp_path, credentials=credentials)
    session.opener = Mock()
    return session


def test_cookie_import_keeps_only_account_cookies(credentials):
    imported = auth.parse_cookies(
        "Cookie: unrelated=discard; csrftoken=csrf-secret; "
        "LEETCODE_SESSION=session-secret; cf_clearance=discard-too"
    )
    assert imported == credentials
    assert "secret" not in repr(imported)
    assert imported.cookie_header() == "LEETCODE_SESSION=session-secret; csrftoken=csrf-secret"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "LEETCODE_SESSION=only",
        "csrftoken=only",
        "LEETCODE_SESSION=; csrftoken=x",
        "LEETCODE_SESSION=a; LEETCODE_SESSION=b; csrftoken=c",
        "LEETCODE_SESSION=a; csrftoken=c\r\nInjected: bad",
        'LEETCODE_SESSION="a"; csrftoken=c',
        "LEETCODE_SESSION=with space; csrftoken=c",
        "LEETCODE_SESSION=☃; csrftoken=c",
        "x" * 32769,
    ],
)
def test_invalid_cookie_input_is_redacted(value):
    with pytest.raises(auth.BrowserError) as error:
        auth.parse_cookies(value)
    assert not value or value not in str(error.value)


def test_saved_session_is_private_and_contains_only_required_fields(tmp_path, credentials):
    directory = tmp_path / ".lc"
    directory.mkdir(mode=0o755)
    auth.save_credentials(tmp_path, credentials)
    path = directory / "session.json"
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert set(json.loads(path.read_text())) == {"version", "LEETCODE_SESSION", "csrftoken"}
    assert auth.load_credentials(tmp_path) == credentials


def test_loading_refuses_insecure_file_or_directory(tmp_path, credentials):
    auth.save_credentials(tmp_path, credentials)
    path = tmp_path / ".lc/session.json"
    path.chmod(0o644)
    with pytest.raises(auth.BrowserError, match="mode 600"):
        auth.load_credentials(tmp_path)
    path.chmod(0o600)
    path.parent.chmod(0o755)
    with pytest.raises(auth.BrowserError, match="chmod 700"):
        auth.load_credentials(tmp_path)


def test_session_symlinks_are_not_followed(tmp_path, credentials):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".lc").symlink_to(outside, target_is_directory=True)
    with pytest.raises(auth.BrowserError, match="symbolic link"):
        auth.save_credentials(tmp_path, credentials)
    (tmp_path / ".lc").unlink()
    auth.save_credentials(tmp_path, credentials)
    path = tmp_path / ".lc/session.json"
    path.unlink()
    target = outside / "secret"
    target.write_text("do not touch")
    path.symlink_to(target)
    with pytest.raises(auth.BrowserError):
        auth.load_credentials(tmp_path)
    with pytest.raises(auth.BrowserError, match="symbolic link"):
        auth.save_credentials(tmp_path, credentials)
    assert target.read_text() == "do not touch"


def test_malformed_storage_does_not_expose_its_contents(tmp_path, credentials):
    auth.save_credentials(tmp_path, credentials)
    (tmp_path / ".lc/session.json").write_text("broken session-secret")
    with pytest.raises(auth.BrowserError, match="invalid local session file") as error:
        auth.load_credentials(tmp_path)
    assert "session-secret" not in str(error.value)


def test_submit_sends_authenticated_json_once(client, credentials):
    client.opener.open.return_value = response({"submission_id": 123})
    assert client.submit("two-sum", "py", "1", "class Solution: pass") == "123"
    call = client.opener.open.call_args
    request = call.args[0]
    assert request.full_url == "https://leetcode.com/problems/two-sum/submit/"
    assert request.method == "POST"
    assert request.get_header("Cookie") == credentials.cookie_header()
    assert request.get_header("X-csrftoken") == credentials.csrf
    assert json.loads(request.data) == {
        "lang": "python3",
        "question_id": "1",
        "typed_code": "class Solution: pass",
    }
    assert call.kwargs == {"timeout": 20}
    client.opener.open.assert_called_once()


@pytest.mark.parametrize(
    "path", ["https://example.com/", "//example.com/", "/../", "/graphql/?secret=1"]
)
def test_http_credentials_cannot_be_sent_to_other_paths(client, path):
    with pytest.raises(auth.BrowserError, match="outside"):
        client.request(path, {"source": "private"})
    client.opener.open.assert_not_called()


@pytest.mark.parametrize(
    "code, expected",
    [(401, "expired"), (403, "blocked"), (302, "redirected"), (429, "HTTP 429"), (500, "HTTP 500")],
)
def test_http_errors_never_retry_or_echo_secrets(client, code, expected):
    body = io.BytesIO(b"session-secret csrf-secret")
    client.opener.open.side_effect = HTTPError("https://leetcode.com/", code, "private", {}, body)
    with pytest.raises(auth.BrowserError, match=expected) as error:
        client.submit("two-sum", "ts", "1", "code")
    client.opener.open.assert_called_once()
    assert "secret" not in str(error.value)
    assert body.closed


def test_redirect_handler_never_replays_credentials():
    assert (
        auth.NoRedirect().redirect_request(None, None, 307, "", {}, "https://example.com") is None
    )


@pytest.mark.parametrize(
    "body",
    [
        b"<html>challenge session-secret</html>",
        b"[]",
        b'"value"',
        b"\xff",
        b'{"errors":[{"message":"session-secret"}]}',
    ],
)
def test_unexpected_responses_are_redacted_without_retry(client, body):
    client.opener.open.return_value = response(body)
    with pytest.raises(auth.BrowserError) as error:
        client.submit("two-sum", "ts", "1", "code")
    assert "secret" not in str(error.value)
    client.opener.open.assert_called_once()


def test_challenge_header_has_explicit_message(client):
    client.opener.open.return_value = response(b"challenge", headers={"cf-mitigated": "challenge"})
    with pytest.raises(auth.BrowserError, match="Cloudflare"):
        client.require_login()


def test_connection_failure_is_uncertain_and_not_retried(client):
    client.opener.open.side_effect = URLError("session-secret")
    with pytest.raises(auth.BrowserError, match="outcome may be unknown") as error:
        client.submit("two-sum", "ts", "1", "code")
    assert "secret" not in str(error.value)
    client.opener.open.assert_called_once()


def test_prepare_checks_login_and_problem_before_submission(client):
    client.opener.open.side_effect = [
        response({"data": {"userStatus": {"isSignedIn": True}}}),
        response(
            {
                "data": {
                    "question": {
                        "questionId": "1",
                        "questionFrontendId": "1",
                        "titleSlug": "two-sum",
                    }
                }
            }
        ),
    ]
    assert client.prepare("two-sum", "0001") == "1"
    assert all(
        call.args[0].full_url.endswith("/graphql/") for call in client.opener.open.call_args_list
    )


@pytest.mark.parametrize("status", [None, {}, {"isSignedIn": False}])
def test_logged_out_session_stops_before_problem_request(client, status):
    client.opener.open.return_value = response({"data": {"userStatus": status}})
    with pytest.raises(auth.BrowserError, match="lc login"):
        client.prepare("two-sum", "1")
    client.opener.open.assert_called_once()


def test_login_never_prompts_without_terminal(tmp_path, monkeypatch):
    monkeypatch.setattr(auth.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(auth.getpass, "getpass", lambda *_: pytest.fail("must not prompt"))
    monkeypatch.setattr(auth.webbrowser, "open", lambda *_: pytest.fail("must not open browser"))
    with pytest.raises(auth.BrowserError, match="needs a terminal"):
        auth.login_command([], tmp_path)


@pytest.mark.parametrize(
    "cookie_input",
    [["new-secret", "new-csrf"], ["LEETCODE_SESSION=new-secret; csrftoken=new-csrf"]],
)
def test_login_validates_before_saving_and_keeps_old_session_on_failure(
    tmp_path, monkeypatch, credentials, capsys, cookie_input
):
    auth.save_credentials(tmp_path, credentials)
    monkeypatch.setattr(auth.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(auth.webbrowser, "open", Mock(return_value=True))
    monkeypatch.setattr(auth.getpass, "getpass", Mock(side_effect=cookie_input * 2))
    monkeypatch.setattr(
        auth.LeetCodeSession, "require_login", Mock(side_effect=auth.BrowserError("blocked"))
    )
    with pytest.raises(auth.BrowserError, match="blocked"):
        auth.login_command([], tmp_path)
    assert auth.load_credentials(tmp_path) == credentials
    monkeypatch.setattr(auth.LeetCodeSession, "require_login", Mock())
    assert auth.login_command([], tmp_path) == 0
    assert auth.load_credentials(tmp_path) == auth.Credentials("new-secret", "new-csrf")
    assert "new-secret" not in capsys.readouterr().out


def test_check_is_noninteractive_and_logout_only_removes_local_session(
    tmp_path, monkeypatch, credentials
):
    auth.save_credentials(tmp_path, credentials)
    unrelated = tmp_path / ".lc/active.json"
    unrelated.write_text("{}")
    monkeypatch.setattr(auth.LeetCodeSession, "require_login", Mock())
    monkeypatch.setattr(auth.webbrowser, "open", lambda *_: pytest.fail("must not open browser"))
    monkeypatch.setattr(auth.getpass, "getpass", lambda *_: pytest.fail("must not prompt"))
    assert auth.login_command(["--check"], tmp_path) == 0
    assert auth.logout_command([], tmp_path) == 0
    assert auth.logout_command([], tmp_path) == 0
    assert unrelated.exists()
    with pytest.raises(auth.BrowserError, match="no saved"):
        auth.load_credentials(tmp_path)


def test_session_context_drops_credentials_on_failure(client):
    with pytest.raises(RuntimeError), client:
        raise RuntimeError
    assert client.credentials is None
    client.opener.close.assert_called_once()


@pytest.mark.parametrize("changes", [{"code": None}, {"question": None}, {"lang": []}])
def test_resume_rejects_malformed_remote_details(client, changes):
    details = {"code": "source", "question": {"titleSlug": "two-sum"}, "lang": {"name": "python3"}}
    client.graphql = Mock(return_value={"submissionDetails": {**details, **changes}})
    with pytest.raises(auth.BrowserError, match="does not match"):
        client.verify_submission("1", "two-sum", "py", "source")


def test_login_refuses_getpass_fallback_that_would_echo_input(tmp_path, monkeypatch):
    monkeypatch.setattr(auth.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(auth.webbrowser, "open", Mock())

    def unavailable(_prompt):
        warnings.warn("cannot hide input", getpass_warning)
        pytest.fail("must stop before reading visible input")

    getpass_warning = auth.getpass.GetPassWarning
    monkeypatch.setattr(auth.getpass, "getpass", unavailable)
    with pytest.raises(auth.BrowserError, match="hidden input is unavailable"):
        auth.login_command([], tmp_path)
    assert not (tmp_path / ".lc/session.json").exists()
