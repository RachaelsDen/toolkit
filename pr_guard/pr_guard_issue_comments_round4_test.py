"""Issue-comment ordering regressions."""

import unittest

from . import pr_guard_issue_comments

TIMESTAMP = "2026-09-20T10:00:00Z"


def comment(comment_id, author, created_at, body, updated_at=None):
    return pr_guard_issue_comments.IssueComment(
        id=comment_id,
        author=author,
        author_type="Bot" if author.startswith("chatgpt") else "User",
        created_at=created_at,
        updated_at=updated_at,
        body=body,
    )


class IssueCommentFindingTests(unittest.TestCase):
    def test_decorated_p0_to_p2_only_and_plain_p3_are_not_findings(self):
        # Given: decorated P1/P3 badges and a plain P3 badge. When: classified.
        # Then: only the supported decorated priority is a finding.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", TIMESTAMP, "**<sub><sub>![P1 Badge](https://example.test/p1)"),
                comment(2, "chatgpt-codex-connector", TIMESTAMP, "**<sub><sub>![P3 Badge](https://example.test/p3)"),
                comment(3, "chatgpt-codex-connector", TIMESTAMP, "P3 Badge"),
            ]
        )
        self.assertEqual([finding.id for finding in findings], [1])

    def test_edited_old_id_bot_reply_tied_with_receipt_is_danger(self):
        # Given: a pre-finding bot reply edited into the finding/receipt second.
        # When: classified. Then: the ambiguous equal-time bot reply fails closed.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(9, "chatgpt-codex-connector", "2026-09-20T09:00:00Z", "Still broken.", "2026-09-20T10:00:00Z"),
                comment(10, "chatgpt-codex-connector", TIMESTAMP, "P1 Badge"),
                comment(11, "RachaelsDen", TIMESTAMP, "Fixed comment=10."),
            ]
        )
        self.assertEqual(findings[0].classification, "DANGER")

    def test_unedited_old_id_bot_reply_does_not_displace_receipt(self):
        # Given: an older unedited bot reply followed by a finding and receipt.
        # When: classified. Then: creation-time ordering leaves the receipt authoritative.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(9, "chatgpt-codex-connector", "2026-09-20T09:00:00Z", "Still broken."),
                comment(10, "chatgpt-codex-connector", TIMESTAMP, "P1 Badge"),
                comment(11, "RachaelsDen", "2026-09-20T10:01:00Z", "Fixed comment=10."),
            ]
        )
        self.assertEqual(findings[0].classification, "receipted")


if __name__ == "__main__":
    unittest.main()
