"""Combined GraphQL comment-snapshot regressions for pr_guard."""

import unittest
from unittest import mock

from . import pr_guard_issue_comments
from . import pr_guard_threads


def comment(comment_id, author, created_at, body, updated_at=None, author_type="User"):
    return pr_guard_issue_comments.IssueComment(
        id=comment_id,
        author=author,
        author_type=author_type,
        created_at=created_at,
        updated_at=updated_at or created_at,
        body=body,
    )


class FindingReceiptTests(unittest.TestCase):
    def test_bot_follow_up_reopens_a_receipted_finding(self):
        # Given: a finding, trusted receipt, then bot follow-up. When: classified.
        # Then: the bot's last relevant word reopens the finding.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", author_type="Bot"),
                comment(2, "RachaelsDen", "2026-09-20T10:01:00Z", "Fixed comment=1."),
                comment(3, "chatgpt-codex-connector", "2026-09-20T10:02:00Z", "Still broken.", author_type="Bot"),
            ]
        )
        self.assertEqual(findings[0].classification, "DANGER")

    def test_latest_trusted_receipt_clears_bot_follow_up(self):
        # Given: a finding, receipt, bot follow-up, then newer receipt.
        # When: classified. Then: the newest relevant reply receipts it.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", author_type="Bot"),
                comment(2, "RachaelsDen", "2026-09-20T10:01:00Z", "Fixed comment=1."),
                comment(3, "chatgpt-codex-connector", "2026-09-20T10:02:00Z", "Still broken.", author_type="Bot"),
                comment(4, "RachaelsDen", "2026-09-20T10:03:00Z", "Fixed now, comment=1."),
            ]
        )
        self.assertEqual(findings[0].classification, "receipted")

    def test_receipt_without_later_bot_follow_up_clears_finding(self):
        # Given: a finding followed by one trusted receipt. When: classified.
        # Then: it remains receipted.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", author_type="Bot"),
                comment(2, "RachaelsDen", "2026-09-20T10:01:00Z", "Fixed comment=1."),
            ]
        )
        self.assertEqual(findings[0].classification, "receipted")

    def test_receipt_before_badge_edit_does_not_clear_finding(self):
        # Given: a receipt before a bot edits in its badge. When: classified.
        # Then: the stale receipt cannot clear the edited finding.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", "2026-09-20T10:02:00Z", "Bot"),
                comment(2, "RachaelsDen", "2026-09-20T10:01:00Z", "Fixed comment=1."),
            ]
        )
        self.assertEqual(findings[0].classification, "DANGER")

    def test_receipt_after_badge_edit_clears_finding(self):
        # Given: a badge edit then a receipt. When: classified.
        # Then: the post-edit receipt clears the finding.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", "2026-09-20T10:02:00Z", "Bot"),
                comment(2, "RachaelsDen", "2026-09-20T10:03:00Z", "Fixed comment=1."),
            ]
        )
        self.assertEqual(findings[0].classification, "receipted")

    def test_same_second_receipt_after_edited_finding_remains_danger(self):
        # Given: a finding edit and receipt with the same timestamp. When: classified.
        # Then: the ambiguous receipt cannot clear the finding.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", "2026-09-20T10:02:00Z", "Bot"),
                comment(2, "RachaelsDen", "2026-09-20T10:02:00Z", "Fixed comment=1."),
            ]
        )
        self.assertEqual(findings[0].classification, "DANGER")

    def test_unconfigured_bot_follow_up_does_not_reopen_receipt(self):
        # Given: a finding, receipt, then an unrelated Bot actor. When: classified.
        # Then: only configured bot logins can reopen the finding.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", author_type="Bot"),
                comment(2, "RachaelsDen", "2026-09-20T10:01:00Z", "Fixed comment=1."),
                comment(3, "dependabot[bot]", "2026-09-20T10:02:00Z", "Still broken.", author_type="Bot"),
            ]
        )
        self.assertEqual(findings[0].classification, "receipted")

    def test_bot_follow_up_edited_after_receipt_reopens_finding(self):
        # Given: a bot follow-up created before but edited after a receipt.
        # When: classified. Then: its edit reopens the finding.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", author_type="Bot"),
                comment(2, "chatgpt-codex-connector", "2026-09-20T10:01:00Z", "Still broken.", "2026-09-20T10:03:00Z", "Bot"),
                comment(3, "RachaelsDen", "2026-09-20T10:02:00Z", "Fixed comment=1."),
            ]
        )
        self.assertEqual(findings[0].classification, "DANGER")

    def test_bot_follow_up_edited_before_receipt_keeps_receipt(self):
        # Given: a bot follow-up edited before a later receipt. When: classified.
        # Then: the later receipt stands.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", author_type="Bot"),
                comment(2, "chatgpt-codex-connector", "2026-09-20T10:01:00Z", "Still broken.", "2026-09-20T10:02:00Z", "Bot"),
                comment(3, "RachaelsDen", "2026-09-20T10:03:00Z", "Fixed comment=1."),
            ]
        )
        self.assertEqual(findings[0].classification, "receipted")


class CombinedSnapshotTests(unittest.TestCase):
    def test_fetches_threads_and_comments_from_one_graphql_response(self):
        # Given: one GraphQL payload containing both PR connections.
        # When: fetched. Then: both lists come from one request.
        calls = []
        payload = {
            "repository": {
                "pullRequest": {
                    "updatedAt": "2026-09-20T10:00:00Z",
                    "reviewThreads": {
                        "totalCount": 1,
                        "pageInfo": {"endCursor": None, "hasNextPage": False},
                        "nodes": [{"id": "thread", "isResolved": True, "isOutdated": False, "head": {"nodes": [{"databaseId": 10}]}, "last": {"nodes": [{"databaseId": 11, "author": {"login": "RachaelsDen", "__typename": "User"}, "body": "Fixed."}]}}],
                    },
                    "comments": {
                        "totalCount": 1,
                        "pageInfo": {"endCursor": None, "hasNextPage": False},
                        "nodes": [{"databaseId": 12, "author": {"login": "chatgpt-codex-connector[bot]", "__typename": "Bot"}, "body": "P1 Badge", "createdAt": "2026-09-20T10:00:00Z", "updatedAt": "2026-09-20T10:00:00Z"}],
                    },
                }
            }
        }

        def fake_graphql(query, variables):
            calls.append((query, variables))
            return payload

        with mock.patch.object(pr_guard_threads, "gh_graphql", side_effect=fake_graphql):
            threads, comments = pr_guard_threads.fetch_threads(68)
        self.assertEqual([thread.node_id for thread in threads], ["thread"])
        self.assertEqual([(item.id, item.author, item.author_type) for item in comments], [(12, "chatgpt-codex-connector[bot]", "Bot")])
        self.assertEqual(len(calls), 2)

    def test_paginates_threads_and_comments_until_both_connections_finish(self):
        # Given: threads finish on page one while comments continue to page two.
        # When: fetched. Then: the second call advances only the comment cursor.
        calls = []
        pages = [
            {
                "repository": {
                    "pullRequest": {
                        "updatedAt": "2026-09-20T10:00:00Z",
                        "reviewThreads": {"totalCount": 0, "pageInfo": {"endCursor": "thread-end", "hasNextPage": False}, "nodes": []},
                        "comments": {"totalCount": 0, "pageInfo": {"endCursor": "comment-next", "hasNextPage": True}, "nodes": []},
                    }
                }
            },
            {
                "repository": {
                    "pullRequest": {
                        "updatedAt": "2026-09-20T10:00:00Z",
                        "comments": {"totalCount": 0, "pageInfo": {"endCursor": "comment-end", "hasNextPage": False}, "nodes": []},
                    }
                }
            },
            {
                "repository": {
                    "pullRequest": {
                        "updatedAt": "2026-09-20T10:00:00Z",
                        "reviewThreads": {"totalCount": 0, "pageInfo": {"endCursor": "thread-end", "hasNextPage": False}, "nodes": []},
                        "comments": {"totalCount": 0, "pageInfo": {"endCursor": "comment-end", "hasNextPage": False}, "nodes": []},
                    }
                }
            },
            {"repository": {"pullRequest": {"updatedAt": "2026-09-20T10:00:00Z"}}},
        ]

        def fake_graphql(query, variables):
            calls.append(variables)
            return pages.pop(0)

        with mock.patch.object(pr_guard_threads, "gh_graphql", side_effect=fake_graphql):
            threads, comments = pr_guard_threads.fetch_threads(68)
        self.assertEqual((threads, comments), ([], []))
        self.assertEqual(calls[1]["ccursor"], "comment-next")
        self.assertFalse(calls[1]["fetchThreads"])
        self.assertTrue(calls[1]["fetchComments"])

    def test_revalidates_comments_after_threads_continue_past_them(self):
        # Given: comments finish before a second thread page and a finding lands.
        # When: the combined snapshot completes. Then: revalidation refetches it.
        calls = []
        responses = iter([
            {
                "repository": {
                    "pullRequest": {
                        "updatedAt": "2026-09-20T10:00:00Z",
                        "reviewThreads": {"totalCount": 0, "pageInfo": {"endCursor": "thread-next", "hasNextPage": True}, "nodes": []},
                        "comments": {"totalCount": 1, "pageInfo": {"endCursor": "comment-end", "hasNextPage": False}, "nodes": [{"databaseId": 1, "author": {"login": "RachaelsDen", "__typename": "User"}, "body": "Fixed.", "createdAt": "2026-09-20T10:00:00Z", "updatedAt": "2026-09-20T10:00:00Z"}]},
                    }
                }
            },
            {
                "repository": {
                    "pullRequest": {
                        "updatedAt": "2026-09-20T10:00:00Z",
                        "reviewThreads": {"totalCount": 0, "pageInfo": {"endCursor": "thread-end", "hasNextPage": False}, "nodes": []},
                    }
                }
            },
            {
                "repository": {
                    "pullRequest": {
                        "updatedAt": "2026-09-20T10:00:00Z",
                        "reviewThreads": {"totalCount": 0, "pageInfo": {"endCursor": "thread-end", "hasNextPage": False}, "nodes": []},
                        "comments": {"totalCount": 2, "pageInfo": {"endCursor": "comment-end", "hasNextPage": False}, "nodes": [{"databaseId": 2, "updatedAt": "2026-09-20T10:02:00Z"}]},
                    }
                }
            },
            {
                "repository": {
                    "pullRequest": {
                        "updatedAt": "2026-09-20T10:00:00Z",
                        "reviewThreads": {"totalCount": 0, "pageInfo": {"endCursor": "thread-end", "hasNextPage": False}, "nodes": []},
                        "comments": {"totalCount": 2, "pageInfo": {"endCursor": "comment-end", "hasNextPage": False}, "nodes": [{"databaseId": 1, "author": {"login": "RachaelsDen", "__typename": "User"}, "body": "Fixed.", "createdAt": "2026-09-20T10:00:00Z", "updatedAt": "2026-09-20T10:00:00Z"}, {"databaseId": 2, "author": {"login": "chatgpt-codex-connector", "__typename": "Bot"}, "body": "P1 Badge", "createdAt": "2026-09-20T10:02:00Z", "updatedAt": "2026-09-20T10:02:00Z"}]},
                    }
                }
            },
            {
                "repository": {
                    "pullRequest": {
                        "updatedAt": "2026-09-20T10:00:00Z",
                        "reviewThreads": {"totalCount": 0, "pageInfo": {"endCursor": "thread-end", "hasNextPage": False}, "nodes": []},
                        "comments": {"totalCount": 2, "pageInfo": {"endCursor": "comment-end", "hasNextPage": False}, "nodes": [{"databaseId": 1, "updatedAt": "2026-09-20T10:00:00Z"}, {"databaseId": 2, "updatedAt": "2026-09-20T10:02:00Z"}]},
                    }
                }
            },
        ])

        def fake_graphql(query, variables):
            calls.append((query, variables))
            return next(responses)

        with mock.patch.object(pr_guard_threads, "gh_graphql", side_effect=fake_graphql):
            _, comments = pr_guard_threads.fetch_threads(68)
        self.assertEqual([item.id for item in comments], [1, 2])
        self.assertFalse(calls[1][1]["fetchComments"])
        from .pr_guard_thread_snapshot import REVISION_QUERY

        self.assertEqual(calls[2][0], REVISION_QUERY)


if __name__ == "__main__":
    unittest.main()
