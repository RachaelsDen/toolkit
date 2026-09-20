"""Issue-comment finding tests for pr_guard.

user-observed 2026-09-19: first codex finding posted as an issue comment,
invisible to reviewThreads. No network: subprocess is patched at the gh seam.
"""

import io
import json
import os
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import cli
from . import pr_guard_issue_comments
from . import pr_guard_threads


def comment(comment_id, author, created_at, body):
    return pr_guard_issue_comments.IssueComment(
        id=comment_id,
        author=author,
        created_at=created_at,
        body=body,
    )


def resolved_thread():
    return pr_guard_threads.Thread(
        node_id="PRRT_test",
        head_id=1,
        last_id=2,
        last_author="RachaelsDen",
        last_author_type="User",
        last_body="Fixed.",
        is_resolved=True,
        is_outdated=False,
    )


def receipted_thread():
    thread = pr_guard_threads.Thread(
        node_id="PRRT_receipt",
        head_id=1,
        last_id=2,
        last_author="RachaelsDen",
        last_author_type="User",
        last_body="Fixed.",
        is_resolved=False,
        is_outdated=False,
    )
    thread.classification = "receipted"
    return thread


class FindingClassificationTests(unittest.TestCase):
    def test_finding_badges_include_all_priorities_and_sub_prefix(self):
        # Given: bot comments carrying each real finding badge, a clean
        # summary, and the **<sub> Badge prefix shape. When: classified.
        # Then: only the actual findings appear.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-19T10:00:00Z", "P0 Badge"),
                comment(2, "chatgpt-codex-connector", "2026-09-19T10:01:00Z", "P1 Badge"),
                comment(3, "chatgpt-codex-connector", "2026-09-19T10:02:00Z", "P2 Badge"),
                comment(4, "chatgpt-codex-connector", "2026-09-19T10:03:00Z", "Didn't find any major issues. Bravo."),
                comment(5, "chatgpt-codex-connector", "2026-09-19T10:04:00Z", "**<sub>![Badge](https://example.test/badge)</sub>** finding"),
            ]
        )
        self.assertEqual([item.id for item in findings], [1, 2, 3, 5])
        self.assertTrue(all(item.classification == "DANGER" for item in findings))

    def test_later_trusted_receipt_clears_finding(self):
        # Given: a bot finding followed by the configured maintainer.
        # When: classified. Then: the finding is receipted.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-19T10:00:00Z", "P1 Badge"),
                comment(2, "RachaelsDen", "2026-09-19T10:01:00Z", "Fixed."),
            ]
        )
        self.assertEqual(findings[0].classification, "receipted")

    def test_later_untrusted_comment_does_not_clear_finding(self):
        # Given: a bot finding followed by an outside human comment.
        # When: classified. Then: the finding remains DANGER.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-19T10:00:00Z", "P1 Badge"),
                comment(2, "octocat", "2026-09-19T10:01:00Z", "Still broken."),
            ]
        )
        self.assertEqual(findings[0].classification, "DANGER")

    def test_findings_order_by_created_at(self):
        # Given: REST records returned out of timestamp order. When: classified.
        # Then: findings are ordered chronologically for reporting.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-19T10:02:00Z", "P2 Badge"),
                comment(2, "chatgpt-codex-connector", "2026-09-19T10:01:00Z", "P1 Badge"),
            ]
        )
        self.assertEqual([item.id for item in findings], [2, 1])

    def test_report_marks_danger_and_receipted_comments(self):
        # Given: one open and one receipted finding. When: reported.
        # Then: each line identifies its comment record and state.
        comments = [
            pr_guard_issue_comments.FindingComment(1, "bot", "t1", "P1 Badge", "DANGER"),
            pr_guard_issue_comments.FindingComment(2, "bot", "t2", "P2 Badge", "receipted"),
        ]
        out = io.StringIO()
        with redirect_stdout(out):
            pr_guard_issue_comments.report(comments)
        self.assertIn("DANGER-COMMENT comment=1 author=bot", out.getvalue())
        self.assertIn("receipted-COMMENT comment=2 author=bot", out.getvalue())


class FindingFetchTests(unittest.TestCase):
    def test_fetch_uses_paginated_slurped_issue_comments(self):
        # Given: two paginated REST pages with a bot finding then a receipt.
        # When: fetch_finding_comments runs. Then: it returns the receipted finding.
        calls = []
        pages = [
            [{"id": 1, "user": {"login": "chatgpt-codex-connector"}, "created_at": "2026-09-19T10:00:00Z", "body": "P1 Badge"}],
            [{"id": 2, "user": {"login": "RachaelsDen"}, "created_at": "2026-09-19T10:01:00Z", "body": "Fixed."}],
        ]

        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(pages), stderr="")

        with mock.patch.object(
            pr_guard_issue_comments.subprocess, "run", side_effect=fake_run
        ):
            findings = pr_guard_issue_comments.fetch_finding_comments(68)
        self.assertEqual([(item.id, item.classification) for item in findings], [(1, "receipted")])
        self.assertEqual(
            calls[0][0],
            [
                "gh",
                "api",
                "repos/RachaelsDen/UR-lorebook/issues/68/comments",
                "--paginate",
                "--slurp",
            ],
        )
        self.assertEqual(calls[0][1]["env"]["GH_HOST"], "github.com")


class SurveyAndGateTests(unittest.TestCase):
    def test_survey_summary_includes_zero_comment_findings(self):
        # Given: a clean review-thread snapshot with no finding comments.
        # When: survey runs bannerless. Then: its stable summary reports zero.
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_threads, "fetch_threads", return_value=[resolved_thread()]
        ), mock.patch.object(
            pr_guard_issue_comments, "fetch_finding_comments", return_value=[]
        ), redirect_stdout(out):
            snapshot = pr_guard_threads.survey(68, reaction=False)
        self.assertEqual(len(snapshot), 1)
        self.assertIn(
            "SUMMARY pr=68 total=1 resolved=1 receipted=0 DANGER=0 comment-findings=0",
            out.getvalue(),
        )

    def test_pre_merge_blocks_when_survey_contains_danger_comment(self):
        # Given: a clean thread plus an unreceipted finding comment.
        # When: pre_merge consumes that survey snapshot. Then: it blocks.
        finding = pr_guard_issue_comments.FindingComment(
            3,
            "chatgpt-codex-connector",
            "2026-09-19T10:00:00Z",
            "P1 Badge",
            "DANGER",
        )
        pr_read = {
            "head": {"sha": "8ed444e0d5b1ad3b3ff6c9d3e3b4a5c6d7e8f9a0"},
            "base": {"ref": "dev"},
        }
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"GH_HOST": ""}), mock.patch.object(
            cli, "survey", return_value=[resolved_thread(), finding]
        ), mock.patch.object(cli, "gh_rest_pr", return_value=pr_read), redirect_stdout(out):
            code = cli.pre_merge(68)
        self.assertEqual(code, 1)
        self.assertIn("BLOCKED: 1 unanswered finding(s)", out.getvalue())

    def test_resolve_never_resolves_receipted_issue_comments(self):
        # Given: a receipted review thread and receipted issue comment.
        # When: resolve runs. Then: only the review thread is mutated.
        thread = receipted_thread()
        finding = pr_guard_issue_comments.FindingComment(
            3,
            "chatgpt-codex-connector",
            "2026-09-19T10:00:00Z",
            "P1 Badge",
            "receipted",
        )
        out = io.StringIO()
        with mock.patch.object(
            cli, "survey", side_effect=[[thread, finding], [resolved_thread()]]
        ), mock.patch.object(
            cli, "refetch_thread", return_value=thread
        ), mock.patch.object(
            cli, "resolve_thread", return_value=True
        ) as resolve_thread, redirect_stdout(out):
            code = cli.resolve(68)
        self.assertEqual(code, 0)
        resolve_thread.assert_called_once_with(thread)
        self.assertIn("RESOLVE DONE: 1/1 thread(s)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
