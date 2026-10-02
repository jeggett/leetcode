"""Shared LeetCode API operations for HTTP and browser transports."""

from __future__ import annotations

import time


class LeetCodeError(ValueError):
    """A LeetCode request could not be completed or trusted."""


class LeetCodeAPI:
    def request(self, path: str, data: dict | None = None) -> dict:
        raise NotImplementedError

    def require_login(self) -> None:
        data = self.graphql("query { userStatus { isSignedIn } }")
        status = data.get("userStatus")
        if not isinstance(status, dict) or status.get("isSignedIn") is not True:
            raise LeetCodeError("LeetCode login required; next: lc login")

    def question_id(self, slug: str, problem_id: str) -> str:
        question = self.graphql(
            "query($slug: String!) { question(titleSlug: $slug) { questionId questionFrontendId titleSlug } }",
            {"slug": slug},
        ).get("question")
        if (
            not isinstance(question, dict)
            or question.get("titleSlug") != slug
            or str(question.get("questionFrontendId")) != str(int(problem_id))
        ):
            raise LeetCodeError("LeetCode problem identity does not match the local problem")
        question_id = question.get("questionId")
        if not isinstance(question_id, str) or not question_id.isdecimal():
            raise LeetCodeError("LeetCode returned an invalid question ID")
        return question_id

    def prepare(self, slug: str, problem_id: str) -> str:
        self.require_login()
        return self.question_id(slug, problem_id)

    def graphql(self, query: str, variables: dict | None = None) -> dict:
        response = self.request("/graphql/", {"query": query, "variables": variables or {}})
        data = response.get("data")
        if not isinstance(data, dict):
            raise LeetCodeError("LeetCode returned incomplete GraphQL data")
        return data

    def submit(self, slug: str, language: str, question_id: str, source: str) -> str:
        result = self.request(
            f"/problems/{slug}/submit/",
            {
                "lang": "typescript" if language == "ts" else "python3",
                "question_id": question_id,
                "typed_code": source,
            },
        )
        submission_id = result.get("submission_id")
        if isinstance(submission_id, bool) or not str(submission_id).isdecimal():
            raise LeetCodeError("LeetCode did not return a submission ID; check submission history")
        return str(submission_id)

    def verify_submission(self, submission_id: str, slug: str, language: str, source: str) -> None:
        details = self.graphql(
            "query($id: Int!) { submissionDetails(submissionId: $id) { code lang { name } question { titleSlug } } }",
            {"id": int(submission_id)},
        ).get("submissionDetails")
        expected_language = "typescript" if language == "ts" else "python3"
        if (
            not isinstance(details, dict)
            or not isinstance(details.get("code"), str)
            or not isinstance(details.get("question"), dict)
            or not isinstance(details.get("lang"), dict)
            or details["code"].strip() != source.strip()
            or details["question"].get("titleSlug") != slug
            or details["lang"].get("name") != expected_language
        ):
            raise LeetCodeError(
                "submission ID does not match this problem, language, and exact source"
            )

    def wait(self, submission_id: str, *, timeout: float = 120) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.request(f"/submissions/detail/{submission_id}/check/")
            if "submission_id" in result and str(result["submission_id"]) != submission_id:
                raise LeetCodeError("LeetCode returned a verdict for a different submission")
            if result.get("state") == "SUCCESS":
                if not isinstance(result.get("status_code"), int):
                    raise LeetCodeError(
                        "LeetCode returned an incomplete verdict; retry lc done to resume"
                    )
                return result
            if result.get("state") not in {"PENDING", "STARTED"}:
                raise LeetCodeError(
                    "LeetCode returned an unknown judging state; retry lc done to resume"
                )
            time.sleep(2)
        raise LeetCodeError("judging timed out; retry lc done to resume this submission")
