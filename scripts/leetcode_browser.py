"""LeetCode requests in a dedicated, persistent Playwright browser session.

Login and site challenges are handled by the user in the normal browser window.
Mutating requests are never retried here: the caller journals them before sending.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.parse import urlsplit


try:
    from scripts.leetcode_api import LeetCodeAPI, LeetCodeError as BrowserError
except ModuleNotFoundError:
    from leetcode_api import LeetCodeAPI, LeetCodeError as BrowserError


class LeetCodeBrowser(LeetCodeAPI):
    def __init__(self, root: Path, *, interactive: bool | None = None) -> None:
        self.profile = root / ".lc" / "browser"
        self.interactive = sys.stdin.isatty() if interactive is None else interactive
        self.manager = None
        self.context = None

    def __enter__(self) -> LeetCodeBrowser:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise BrowserError("Playwright is missing; next: ./bin/setup --trust") from error
        self.profile.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.manager = sync_playwright().start()
            self.context = self.manager.chromium.launch_persistent_context(
                str(self.profile),
                headless=not self.interactive,
            )
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self.page.goto("https://leetcode.com/", wait_until="domcontentloaded", timeout=30000)
            return self
        except Exception as error:
            self.__exit__()
            raise BrowserError(
                f"could not open the LeetCode browser: {error}; next: ./bin/setup --trust"
            ) from error

    def __exit__(self, exception_type=None, _exception=None, _traceback=None) -> None:
        close_error = None
        try:
            if self.context:
                self.context.close()
        except Exception as error:
            close_error = error
        finally:
            if self.manager:
                self.manager.stop()
        if close_error and exception_type is None:
            raise BrowserError(
                "browser cleanup failed; retry lc done to resume recorded progress"
            ) from close_error

    def navigate(self, url: str) -> None:
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as error:
            raise BrowserError(
                "could not load LeetCode; check the browser, then retry lc done"
            ) from error

    def request(self, path: str, data: dict | None = None) -> dict:
        """Use same-origin fetch; session cookies stay in the browser profile."""
        location = urlsplit(self.page.url)
        if location.scheme != "https" or location.netloc != "leetcode.com":
            raise BrowserError("return to leetcode.com in the browser before continuing")
        try:
            response = self.page.evaluate(
                """async ({path, data}) => {
                    const controller = new AbortController();
                    const timer = setTimeout(() => controller.abort(), 20000);
                    try {
                        const csrf = document.cookie.split('; ').find(c => c.startsWith('csrftoken='));
                        const result = await fetch(path, {
                            method: data === null ? 'GET' : 'POST',
                            credentials: 'same-origin',
                            headers: {'Content-Type': 'application/json',
                                      'X-CSRFToken': csrf ? decodeURIComponent(csrf.slice(10)) : ''},
                            body: data === null ? undefined : JSON.stringify(data),
                            signal: controller.signal,
                        });
                        return {status: result.status, body: await result.text()};
                    } finally { clearTimeout(timer); }
                }""",
                {"path": path, "data": data},
            )
        except Exception as error:
            raise BrowserError(
                "LeetCode request was interrupted; its outcome may be unknown"
            ) from error
        if response["status"] != 200:
            raise BrowserError(
                f"LeetCode returned HTTP {response['status']}; login or a site challenge may need attention"
            )
        import json

        try:
            document = json.loads(response["body"])
        except (TypeError, ValueError) as error:
            raise BrowserError(
                "LeetCode returned a page instead of JSON; complete any site challenge in the browser"
            ) from error
        if not isinstance(document, dict) or document.get("errors"):
            raise BrowserError(
                "LeetCode returned an unexpected response; inspect the problem in the browser"
            )
        return document

    def prepare(self, slug: str, problem_id: str) -> str:
        """Authenticate before any submission intent is recorded."""
        deadline = time.monotonic() + 300
        login_opened = False
        announced = False
        while True:
            try:
                status = self.graphql("query { userStatus { isSignedIn } }")
                if status.get("userStatus", {}).get("isSignedIn") is True:
                    break
                if self.interactive and not login_opened:
                    self.navigate("https://leetcode.com/accounts/login/")
                    login_opened = True
            except BrowserError as error:
                if not self.interactive:
                    raise BrowserError(f"{error}; next: run lc done in a terminal") from error
            if not self.interactive:
                raise BrowserError("LeetCode login required; next: run lc done in a terminal")
            if not announced:
                print(
                    "Complete login or the site challenge in the browser. "
                    "The command continues after sign-in; Ctrl-C cancels.",
                    flush=True,
                )
                announced = True
            if time.monotonic() >= deadline:
                raise BrowserError("login timed out; next: retry lc done after signing in")
            # Keep Playwright's event loop running while the user changes pages.
            # Blocking input()/sleep() can leave frame events queued until the next request.
            try:
                self.page.wait_for_timeout(1000)
            except Exception as error:
                raise BrowserError(
                    "browser closed or interrupted during login; retry lc done"
                ) from error
        question_id = self.question_id(slug, problem_id)
        self.navigate(f"https://leetcode.com/problems/{slug}/")
        return question_id
