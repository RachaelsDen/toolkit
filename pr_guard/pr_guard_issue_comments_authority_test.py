"""Issue-comment finding-authority regressions."""

import unittest

from . import pr_guard_issue_comments


def comment(comment_id: int, author: str, created_at: str, body: str) -> pr_guard_issue_comments.IssueComment:
    return pr_guard_issue_comments.IssueComment(
        id=comment_id,
        author=author,
        author_type="Bot" if author.endswith("[bot]") or author.startswith("chatgpt") else "User",
        created_at=created_at,
        updated_at=created_at,
        body=body,
    )


class FindingAuthorityTests(unittest.TestCase):
    def test_renovate_badge_is_not_a_finding(self) -> None:
        # Given: Renovate posts a badge-looking issue comment. When: classified.
        # Then: only the dedicated review-bot allowlist can originate a finding.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [comment(1, "renovate[bot]", "2026-09-20T10:00:00Z", "P1 Badge")]
        )
        self.assertEqual(findings, [])

    def test_renovate_follow_up_does_not_reopen_a_receipted_finding(self) -> None:
        # Given: a Codex finding, trusted receipt, and Renovate follow-up.
        # When: classified. Then: Renovate lacks finding-reopen authority.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge"),
                comment(2, "RachaelsDen", "2026-09-20T10:01:00Z", "Fixed comment=1."),
                comment(3, "renovate[bot]", "2026-09-20T10:02:00Z", "Still broken."),
            ]
        )
        self.assertEqual(findings[0].classification, "receipted")

    def test_codex_login_forms_remain_finding_authoritative(self) -> None:
        # Given: both Codex login forms follow a trusted receipt. When: classified.
        # Then: either authoritative follow-up reopens the finding.
        for login in ("chatgpt-codex-connector", "chatgpt-codex-connector[bot]"):
            with self.subTest(login=login):
                findings = pr_guard_issue_comments.classify_finding_comments(
                    [
                        comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge"),
                        comment(2, "RachaelsDen", "2026-09-20T10:01:00Z", "Fixed comment=1."),
                        comment(3, login, "2026-09-20T10:02:00Z", "Still broken."),
                    ]
                )
                self.assertEqual(findings[0].classification, "DANGER")
