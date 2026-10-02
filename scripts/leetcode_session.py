"""LeetCode HTTP requests using a session imported from the user's browser.

Only the two account cookies are stored. Requests never follow redirects or
retry a POST; the workflow records submission intent before calling submit.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import stat
import sys
import warnings
import webbrowser
from dataclasses import dataclass, field
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

try:
    from scripts.lc_state import write_state
    from scripts.leetcode_api import LeetCodeAPI, LeetCodeError as BrowserError
except ModuleNotFoundError:
    from lc_state import write_state
    from leetcode_api import LeetCodeAPI, LeetCodeError as BrowserError


ORIGIN = "https://leetcode.com"
COOKIE_NAMES = ("LEETCODE_SESSION", "csrftoken")
COOKIE_VALUE = re.compile(r"[\x21\x23-\x2b\x2d-\x3a\x3c-\x5b\x5d-\x7e]{1,16000}")
API_PATH = re.compile(
    r"/(?:graphql/|problems/[a-z0-9]+(?:-[a-z0-9]+)*/submit/|submissions/detail/[0-9]+/check/)"
)


@dataclass(frozen=True)
class Credentials:
    session: str = field(repr=False)
    csrf: str = field(repr=False)

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not COOKIE_VALUE.fullmatch(value)
            for value in (self.session, self.csrf)
        ):
            raise BrowserError("invalid session cookies; copy LEETCODE_SESSION and csrftoken again")

    def cookie_header(self) -> str:
        return f"LEETCODE_SESSION={self.session}; csrftoken={self.csrf}"


def parse_cookies(value: str) -> Credentials:
    if len(value) > 32768 or "\n" in value or "\r" in value:
        raise BrowserError("paste a single Cookie header, without line breaks")
    value = value.strip()
    if value.lower().startswith("cookie:"):
        value = value[7:].strip()
    cookies = {}
    for part in value.split(";"):
        name, separator, content = part.strip().partition("=")
        if name not in COOKIE_NAMES:
            continue
        if not separator or name in cookies:
            raise BrowserError("invalid or duplicate session cookies; copy them again")
        cookies[name] = content.strip()
    if any(name not in cookies for name in COOKIE_NAMES):
        raise BrowserError("both LEETCODE_SESSION and csrftoken are required; next: lc help login")
    return Credentials(cookies["LEETCODE_SESSION"], cookies["csrftoken"])


def session_path(root: Path, *, create: bool = False) -> Path:
    directory = root / ".lc"
    if create:
        directory.mkdir(exist_ok=True, mode=0o700)
    if directory.exists() or directory.is_symlink():
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise BrowserError(".lc must be a directory owned by you, not a symbolic link")
        if create:
            directory.chmod(0o700)
        elif info.st_mode & 0o077:
            raise BrowserError(".lc permissions are too open; next: chmod 700 .lc")
    return directory / "session.json"


def load_credentials(root: Path) -> Credentials:
    path = session_path(root)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        raise BrowserError("no saved LeetCode session; next: lc login") from None
    except OSError:
        raise BrowserError("cannot open the local session file; next: lc login") from None
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise BrowserError(
                    "session.json must be owned by you with mode 600; next: lc login"
                )
            document = json.loads(stream.read(32769))
        if not isinstance(document, dict) or document.get("version") != 1:
            raise ValueError
        return Credentials(document.get("LEETCODE_SESSION"), document.get("csrftoken"))
    except BrowserError:
        raise
    except ValueError, UnicodeError:
        raise BrowserError("invalid local session file; next: lc login") from None


def save_credentials(root: Path, credentials: Credentials) -> None:
    path = session_path(root, create=True)
    if path.is_symlink():
        raise BrowserError("session.json must not be a symbolic link")
    write_state(
        path,
        {"version": 1, "LEETCODE_SESSION": credentials.session, "csrftoken": credentials.csrf},
    )


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class LeetCodeSession(LeetCodeAPI):
    def __init__(self, root: Path, *, credentials: Credentials | None = None) -> None:
        self.root = root
        self.credentials = credentials
        self.opener = build_opener(NoRedirect())

    def __enter__(self) -> LeetCodeSession:
        if self.credentials is None:
            self.credentials = load_credentials(self.root)
        return self

    def __exit__(self, *_args) -> None:
        self.credentials = None
        self.opener.close()

    def request(self, path: str, data: dict | None = None) -> dict:
        if not API_PATH.fullmatch(path):
            raise BrowserError("refusing a request outside the supported LeetCode API")
        if self.credentials is None:
            raise BrowserError("no saved LeetCode session; next: lc login")
        request = Request(
            ORIGIN + path,
            data=None if data is None else json.dumps(data).encode("utf-8"),
            headers={
                "Cookie": self.credentials.cookie_header(),
                "X-CSRFToken": self.credentials.csrf,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Origin": ORIGIN,
                "Referer": ORIGIN
                + (path.removesuffix("submit/") if path.endswith("/submit/") else "/"),
                "User-Agent": "lc/1.0",
            },
            method="GET" if data is None else "POST",
        )
        try:
            with self.opener.open(request, timeout=20) as response:
                if response.status != 200:
                    raise BrowserError(
                        f"LeetCode returned HTTP {response.status}; next: lc login --check"
                    )
                body = response.read(2 * 1024 * 1024 + 1)
                if response.headers.get("cf-mitigated") == "challenge":
                    raise BrowserError(
                        "Cloudflare requires browser interaction. Open LeetCode in your normal "
                        "browser, then run lc login. A refreshed session may still be blocked."
                    )
        except HTTPError as error:
            code = error.code
            challenged = error.headers.get("cf-mitigated") == "challenge"
            error.close()
            if challenged or code == 403:
                raise BrowserError(
                    "LeetCode blocked this request (HTTP 403 or site challenge). "
                    "Open LeetCode in your normal browser, then run lc login. "
                    "A refreshed session may still be blocked."
                ) from None
            if code == 401:
                raise BrowserError("LeetCode session expired; next: lc login") from None
            if 300 <= code < 400:
                raise BrowserError("LeetCode redirected the request; next: lc login") from None
            raise BrowserError(f"LeetCode returned HTTP {code}; next: lc login --check") from None
        except URLError, OSError, HTTPException:
            raise BrowserError(
                "LeetCode request failed or timed out; a submission outcome may be unknown"
            ) from None
        if len(body) > 2 * 1024 * 1024:
            raise BrowserError("LeetCode response was too large to verify")
        try:
            document = json.loads(body)
        except ValueError, UnicodeError:
            raise BrowserError(
                "LeetCode returned a page instead of JSON; open LeetCode in your normal "
                "browser to check login or a site challenge, then run lc login"
            ) from None
        if not isinstance(document, dict) or document.get("errors"):
            raise BrowserError(
                "LeetCode returned an unexpected API response; next: lc login --check"
            )
        return document


def login_command(arguments: list[str], root: Path) -> int:
    if arguments == ["--check"]:
        with LeetCodeSession(root) as session:
            session.require_login()
        print("LeetCode session is valid. Next: lc done")
        return 0
    if arguments:
        raise BrowserError("usage: lc login [--check]; never pass cookies as command arguments")
    if not sys.stdin.isatty():
        raise BrowserError(
            "lc login needs a terminal for hidden input; next: run lc login in a terminal"
        )
    print(
        "Connect your LeetCode account\n\n"
        "1. In your normal browser, open https://leetcode.com/ and sign in.\n"
        "   Check that your account avatar appears. Passing Cloudflare alone is not account login.\n"
        "2. On that page, right-click → Inspect to open Developer Tools.\n"
        "3. In Chrome or Edge, select Application (look under >> if hidden).\n"
        "   In its left sidebar, expand Storage → Cookies → https://leetcode.com.\n"
        "   Firefox: use the Storage tab → Cookies → https://leetcode.com.\n"
        "4. Find the row named LEETCODE_SESSION. Double-click its Value cell and copy the value.\n"
        "   Paste it at the first terminal prompt below, then press Enter.\n"
        "5. Find the csrftoken row. Copy its Value, paste at the second prompt, and press Enter.\n\n"
        "If LEETCODE_SESSION is missing, finish account sign-in and reload the page.\n"
        "If you use the cookie table's filter, clear it before looking for the other cookie.\n"
        "Paste only the values, without names or quotes. Nothing appears while you paste;\n"
        "that is expected. Keep cookie values in this terminal. Ctrl-C cancels.\n",
        flush=True,
    )
    try:
        webbrowser.open(ORIGIN + "/accounts/login/")
    except webbrowser.Error:
        pass  # The printed URL remains usable if no default browser is configured.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            value = getpass.getpass("LEETCODE_SESSION value (hidden): ").strip()
            # Accept headers copied using the earlier login instructions as well.
            if "LEETCODE_SESSION=" in value or value.lower().startswith("cookie:"):
                credentials = parse_cookies(value)
            else:
                csrf = getpass.getpass("csrftoken value (hidden): ").strip()
                credentials = Credentials(value, csrf)
        except getpass.GetPassWarning:
            raise BrowserError(
                "hidden input is unavailable; run lc login in a local terminal"
            ) from None
    print("Checking your LeetCode session…", flush=True)
    with LeetCodeSession(root, credentials=credentials) as session:
        session.require_login()
    save_credentials(root, credentials)
    print("Session verified and saved. Next: lc done")
    return 0


def logout_command(arguments: list[str], root: Path) -> int:
    if arguments:
        raise BrowserError("usage: lc logout")
    session_path(root).unlink(missing_ok=True)
    print("Local LeetCode session removed. Your browser stays signed in. Next: lc login")
    return 0
