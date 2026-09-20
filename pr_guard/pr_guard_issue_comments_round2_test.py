"""Round-two issue-comment snapshot and receipt-ordering regressions."""

import io
import unittest
from contextlib import redirect_stderr
from unittest import mock

from . import pr_guard_issue_comments, pr_guard_threads


def comment(comment_id, author, created_at, body, updated_at=None, author_type="User"):
    return pr_guard_issue_comments.IssueComment(
        id=comment_id,
        author=author,
        author_type=author_type,
        created_at=created_at,
        updated_at=updated_at or created_at,
        body=body,
    )


def comment_node(comment_id, updated_at):
    return {
        "databaseId": comment_id,
        "author": {"login": "RachaelsDen", "__typename": "User"},
        "body": "Fixed.",
        "createdAt": "2026-09-20T10:00:00Z",
        "updatedAt": updated_at,
    }


def thread_node(last_author="RachaelsDen", last_body="Fixed."):
    return {
        "id": "thread",
        "isResolved": True,
        "isOutdated": False,
        "head": {"nodes": [{"databaseId": 10}]},
        "last": {
            "nodes": [
                {
                    "databaseId": 11,
                    "author": {"login": last_author, "__typename": "Bot" if last_author == "chatgpt-codex-connector" else "User"},
                    "body": last_body,
                }
            ]
        },
    }


def page(
    threads=None,
    comments=None,
    threads_more=False,
    comments_more=False,
    updated_at="2026-09-20T10:00:00Z",
    thread_total_count=None,
    comment_total_count=None,
):
    connections = {}
    if threads is not None:
        connections["reviewThreads"] = {
            "totalCount": len(threads) if thread_total_count is None else thread_total_count,
            "pageInfo": {"endCursor": "thread-next", "hasNextPage": threads_more},
            "nodes": threads,
        }
    if comments is not None:
        connections["comments"] = {
            "totalCount": len(comments) if comment_total_count is None else comment_total_count,
            "pageInfo": {"endCursor": "comment-next", "hasNextPage": comments_more},
            "nodes": comments,
        }
    connections["updatedAt"] = updated_at
    return {"repository": {"pullRequest": connections}}


class SnapshotRevalidationTests(unittest.TestCase):
    def test_same_second_finding_addition_restarts_the_snapshot(self):
        # Given: a bot finding lands after the first walk in the same API second.
        # When: the composite sentinel changes. Then: the retry returns DANGER.
        calls = []
        finding = comment_node(2, "2026-09-20T10:00:00Z")
        finding["author"] = {
            "login": "chatgpt-codex-connector",
            "__typename": "Bot",
        }
        finding["body"] = "P1 Badge: still broken"
        responses = iter(
            [
                page([thread_node()], []),
                page([thread_node()], [finding]),
                page([thread_node()], [finding]),
                page([thread_node()], [finding]),
            ]
        )

        def fake_graphql(query, variables):
            calls.append((query, variables))
            return next(responses)

        with mock.patch.object(
            pr_guard_threads, "gh_graphql", side_effect=fake_graphql
        ):
            _, comments = pr_guard_threads.fetch_threads(68)
        findings = pr_guard_issue_comments.classify_finding_comments(comments)
        self.assertEqual([item.classification for item in findings], ["DANGER"])
        self.assertEqual(len(calls), 4)

    def test_same_second_stable_fast_snapshot_does_not_retry(self):
        # Given: two identical reads within one API timestamp second.
        # When: the composite sentinel is stable. Then: the first walk proceeds.
        calls = []
        responses = iter([page([thread_node()], []), page([thread_node()], [])])

        def fake_graphql(query, variables):
            calls.append((query, variables))
            return next(responses)

        with mock.patch.object(
            pr_guard_threads, "gh_graphql", side_effect=fake_graphql
        ):
            threads, comments = pr_guard_threads.fetch_threads(68)
        self.assertEqual(([item.node_id for item in threads], comments), (["thread"], []))
        self.assertEqual(len(calls), 2)

    def test_thread_follow_up_during_comment_pagination_is_refetched(self):
        # Given: threads finish while comments paginate and a bot follows up.
        # When: the snapshot is fetched. Then: the fresh thread is returned.
        responses = iter([
            page([thread_node()], [], comments_more=True),
            page(comments=[]),
            page([thread_node("chatgpt-codex-connector", "Still broken.")], []),
            page([thread_node("chatgpt-codex-connector", "Still broken.")], []),
            page([thread_node("chatgpt-codex-connector", "Still broken.")], []),
        ])

        def fake_graphql(query, variables):
            return next(responses)

        with mock.patch.object(
            pr_guard_threads, "gh_graphql", side_effect=fake_graphql
        ):
            threads, _ = pr_guard_threads.fetch_threads(68)
        self.assertEqual(pr_guard_threads.classify(threads[0]), "DANGER")

    def test_mid_list_comment_edit_during_pagination_is_refetched(self):
        # Given: an earlier comment changes while a later comments page arrives.
        # When: the snapshot is fetched. Then: its bumped update time is returned.
        responses = iter([
            page(
                [],
                [comment_node(1, "2026-09-20T10:00:00Z")],
                comments_more=True,
                comment_total_count=2,
            ),
            page(comments=[comment_node(2, "2026-09-20T10:02:00Z")]),
            page([], [comment_node(1, "2026-09-20T10:01:00Z"), comment_node(2, "2026-09-20T10:02:00Z")]),
            page([], [comment_node(1, "2026-09-20T10:01:00Z"), comment_node(2, "2026-09-20T10:02:00Z")]),
            page([], [comment_node(1, "2026-09-20T10:01:00Z"), comment_node(2, "2026-09-20T10:02:00Z")]),
        ])

        def fake_graphql(query, variables):
            return next(responses)

        with mock.patch.object(
            pr_guard_threads, "gh_graphql", side_effect=fake_graphql
        ):
            _, comments = pr_guard_threads.fetch_threads(68)
        self.assertEqual(comments[0].updated_at, "2026-09-20T10:01:00Z")

    def test_stable_sentinel_keeps_held_paginated_snapshot(self):
        # Given: a stable PR updatedAt across the snapshot and revalidation.
        # When: the complete walk finishes. Then: the held data proceeds.
        calls = []
        responses = [
            page(
                [thread_node()],
                [comment_node(1, "2026-09-20T10:00:00Z")],
                comments_more=True,
                comment_total_count=2,
            ),
            page(comments=[comment_node(2, "2026-09-20T10:01:00Z")]),
            page(
                [thread_node()],
                [
                    comment_node(1, "2026-09-20T10:00:00Z"),
                    comment_node(2, "2026-09-20T10:01:00Z"),
                ],
            ),
        ]

        def fake_graphql(query, variables):
            calls.append((query, variables))
            return responses.pop(0)

        with mock.patch.object(
            pr_guard_threads, "gh_graphql", side_effect=fake_graphql
        ):
            _, comments = pr_guard_threads.fetch_threads(68)
        self.assertEqual([item.id for item in comments], [1, 2])
        self.assertEqual(len(calls), 3)

    def test_sentinel_bump_after_first_page_restarts_full_snapshot(self):
        # Given: a mutation lands after page one and bumps pullRequest.updatedAt.
        # When: the ending sentinel observes it. Then: a fresh snapshot returns it.
        calls = []
        responses = [
            page(
                [thread_node()],
                [comment_node(1, "2026-09-20T10:00:00Z")],
                comments_more=True,
                updated_at="2026-09-20T10:00:00Z",
            ),
            page([], [], updated_at="2026-09-20T10:01:00Z"),
            page(
                [thread_node()],
                [comment_node(1, "2026-09-20T10:00:00Z")],
                updated_at="2026-09-20T10:01:00Z",
            ),
            page(
                [thread_node()],
                [
                    comment_node(1, "2026-09-20T10:01:00Z"),
                    comment_node(2, "2026-09-20T10:01:00Z"),
                ],
                updated_at="2026-09-20T10:01:00Z",
            ),
            page(
                [thread_node()],
                [
                    comment_node(1, "2026-09-20T10:01:00Z"),
                    comment_node(2, "2026-09-20T10:01:00Z"),
                ],
                updated_at="2026-09-20T10:01:00Z",
            ),
        ]

        def fake_graphql(query, variables):
            calls.append((query, variables))
            return responses.pop(0)

        with mock.patch.object(
            pr_guard_threads, "gh_graphql", side_effect=fake_graphql
        ):
            _, comments = pr_guard_threads.fetch_threads(68)
        self.assertEqual([item.id for item in comments], [1, 2])
        self.assertEqual(comments[0].updated_at, "2026-09-20T10:01:00Z")
        self.assertIsNone(calls[3][1]["ccursor"])

    def test_changing_sentinel_fails_closed_after_three_attempts(self):
        # Given: every full snapshot sees a newer PR revision at its end.
        # When: all retry attempts are exhausted. Then: the gate fails closed.
        snapshot_calls = 0
        sentinel_calls = 0

        def fake_graphql(query, variables):
            nonlocal sentinel_calls, snapshot_calls
            if query == pr_guard_threads.THREADS_QUERY:
                snapshot_calls += 1
                return page(
                    [thread_node()],
                    [],
                    updated_at=f"before-{snapshot_calls}",
                )
            sentinel_calls += 1
            return page(
                [thread_node()],
                [],
                updated_at=f"after-{sentinel_calls}",
            )

        error = io.StringIO()
        with mock.patch.object(
            pr_guard_threads, "gh_graphql", side_effect=fake_graphql
        ), redirect_stderr(error), self.assertRaises(SystemExit):
            pr_guard_threads.fetch_threads(68)
        self.assertIn("stable snapshot", error.getvalue())
        self.assertEqual(snapshot_calls, 3)
        self.assertEqual(sentinel_calls, 3)


class FindingReceiptOrderingTests(unittest.TestCase):
    def test_trusted_comment_edited_after_finding_is_not_a_receipt(self):
        # Given: a trusted comment created before a finding but edited later.
        # When: classified. Then: editing it cannot receipt the finding.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "RachaelsDen", "2026-09-20T10:00:00Z", "Fixed.", "2026-09-20T10:02:00Z"),
                comment(2, "chatgpt-codex-connector", "2026-09-20T10:01:00Z", "P1 Badge", author_type="Bot"),
            ]
        )
        self.assertEqual(findings[0].classification, "DANGER")

    def test_trusted_comment_created_after_finding_is_a_receipt(self):
        # Given: a trusted comment posted after a finding. When: classified.
        # Then: the finding is receipted.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", author_type="Bot"),
                comment(2, "RachaelsDen", "2026-09-20T10:01:00Z", "Fixed.", "2026-09-20T10:02:00Z"),
            ]
        )
        self.assertEqual(findings[0].classification, "receipted")

    def test_clean_pass_summary_does_not_reopen_receipted_finding(self):
        # Given: a finding, receipt, then Codex's clean-pass summary.
        # When: classified. Then: the summary is only a round marker.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", author_type="Bot"),
                comment(2, "RachaelsDen", "2026-09-20T10:01:00Z", "Fixed."),
                comment(3, "chatgpt-codex-connector", "2026-09-20T10:02:00Z", "### 💡 Codex Review\nDidn't find any major issues. Bravo.", author_type="Bot"),
            ]
        )
        self.assertEqual(findings[0].classification, "receipted")

    def test_badged_bot_follow_up_still_reopens_receipted_finding(self):
        # Given: a finding, receipt, then a later badged bot follow-up.
        # When: classified. Then: the original finding is DANGER again.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", author_type="Bot"),
                comment(2, "RachaelsDen", "2026-09-20T10:01:00Z", "Fixed."),
                comment(3, "chatgpt-codex-connector", "2026-09-20T10:02:00Z", "P2 Badge: still broken", author_type="Bot"),
            ]
        )
        self.assertEqual(findings[0].classification, "DANGER")

    def test_same_second_edited_bot_follow_up_does_not_lose_to_receipt(self):
        # Given: an edited bot reply and receipt share one timestamp.
        # When: classified. Then: the ambiguous reply fails closed.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", author_type="Bot"),
                comment(2, "chatgpt-codex-connector", "2026-09-20T10:01:00Z", "Still broken.", "2026-09-20T10:03:00Z", "Bot"),
                comment(3, "RachaelsDen", "2026-09-20T10:03:00Z", "Fixed."),
            ]
        )
        self.assertEqual(findings[0].classification, "DANGER")

    def test_receipt_strictly_after_edited_bot_follow_up_receipts_finding(self):
        # Given: an edited bot reply followed by a later receipt.
        # When: classified. Then: the strictly later receipt prevails.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", author_type="Bot"),
                comment(2, "chatgpt-codex-connector", "2026-09-20T10:01:00Z", "Still broken.", "2026-09-20T10:03:00Z", "Bot"),
                comment(3, "RachaelsDen", "2026-09-20T10:04:00Z", "Fixed."),
            ]
        )
        self.assertEqual(findings[0].classification, "receipted")


if __name__ == "__main__":
    unittest.main()
