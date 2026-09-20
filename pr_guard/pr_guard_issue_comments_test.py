"""Issue-comment finding tests for pr_guard.

user-observed 2026-09-19: first codex finding posted as an issue comment,
invisible to reviewThreads. No network: subprocess is patched at the gh seam.
"""

import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import cli
from . import pr_guard_issue_comments
from . import pr_guard_reaction_banner
from . import pr_guard_threads


def comment(comment_id, author, created_at, body, author_type=None, updated_at=None):
    return pr_guard_issue_comments.IssueComment(
        id=comment_id,
        author=author,
        author_type=author_type,
        created_at=created_at,
        updated_at=updated_at,
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
                comment(5, "chatgpt-codex-connector", "2026-09-19T10:04:00Z", "**<sub>![P1 Badge](https://example.test/badge)</sub>** finding"),
            ]
        )
        self.assertEqual([item.id for item in findings], [1, 2, 3, 5])
        self.assertTrue(all(item.classification == "DANGER" for item in findings))

    def test_codex_login_normalization_matches_only_configured_bot(self):
        # Given: GraphQL and REST Codex names, an unrelated bot, and a
        # deleted actor. When: finding comments are classified. Then:
        # only the two configured Codex identities become findings.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-19T10:00:00Z", "P1 Badge", "Bot"),
                comment(2, "chatgpt-codex-connector[bot]", "2026-09-19T10:01:00Z", "P1 Badge", "Bot"),
                comment(3, "dependabot[bot]", "2026-09-19T10:02:00Z", "P1 Badge", "Bot"),
                comment(4, None, "2026-09-19T10:03:00Z", "P1 Badge"),
            ]
        )
        self.assertEqual([item.id for item in findings], [1, 2])

    def test_later_trusted_receipt_clears_finding(self):
        # Given: a bot finding followed by the configured maintainer.
        # When: classified. Then: the finding is receipted.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-19T10:00:00Z", "P1 Badge"),
                comment(2, "RachaelsDen", "2026-09-19T10:01:00Z", "Fixed comment=1."),
            ]
        )
        self.assertEqual(findings[0].classification, "receipted")

    def test_explicit_receipt_reference_clears_only_its_finding(self):
        # Given: two findings and one receipt naming the first comment.
        # When: classified. Then: only that finding is receipted.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-19T10:00:00Z", "P1 Badge"),
                comment(2, "chatgpt-codex-connector", "2026-09-19T10:01:00Z", "P2 Badge"),
                comment(3, "RachaelsDen", "2026-09-19T10:02:00Z", "Fixed comment=1."),
            ]
        )
        self.assertEqual([item.classification for item in findings], ["receipted", "DANGER"])

    def test_all_findings_receipt_clears_every_finding(self):
        # Given: two findings and a trusted explicit all-findings receipt.
        # When: classified. Then: both findings are receipted.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-19T10:00:00Z", "P1 Badge"),
                comment(2, "chatgpt-codex-connector", "2026-09-19T10:01:00Z", "P2 Badge"),
                comment(3, "RachaelsDen", "2026-09-19T10:02:00Z", "Fixed. receipt:all findings"),
            ]
        )
        self.assertEqual([item.classification for item in findings], ["receipted", "receipted"])

    def test_negated_all_findings_prose_does_not_receipt_findings(self):
        # Given: two findings and a trusted comment that negates completion.
        # When: classified. Then: both findings remain DANGER.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-19T10:00:00Z", "P1 Badge"),
                comment(2, "chatgpt-codex-connector", "2026-09-19T10:01:00Z", "P2 Badge"),
                comment(3, "RachaelsDen", "2026-09-19T10:02:00Z", "Not all findings are fixed yet."),
            ]
        )
        self.assertEqual([item.classification for item in findings], ["DANGER", "DANGER"])

    def test_neutral_trusted_reply_clears_no_findings(self):
        # Given: two findings and a trusted reply with no receipt target.
        # When: classified. Then: neither finding is receipted.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-19T10:00:00Z", "P1 Badge"),
                comment(2, "chatgpt-codex-connector", "2026-09-19T10:01:00Z", "P2 Badge"),
                comment(3, "RachaelsDen", "2026-09-19T10:02:00Z", "Fixed both."),
            ]
        )
        self.assertEqual([item.classification for item in findings], ["DANGER", "DANGER"])

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

    def test_referencing_bot_follow_up_joins_only_target_finding_stream(self):
        # Given: findings 1+3 receipted, bot posts `comment=3 is still broken`.
        # When: classified. Then: finding 3 reopens, finding 1 stays receipted.
        # When: receipt for 3 lands. Then: finding 3 is re-cleared.
        # When: a non-referencing bot follow-up lands. Then: all findings reopen.
        base_comments = [
            comment(1, "chatgpt-codex-connector", "2026-09-19T10:00:00Z", "P1 Badge"),
            comment(2, "RachaelsDen", "2026-09-19T10:01:00Z", "Fixed comment=1."),
            comment(3, "chatgpt-codex-connector", "2026-09-19T10:02:00Z", "P2 Badge"),
            comment(4, "RachaelsDen", "2026-09-19T10:03:00Z", "Fixed comment=3."),
        ]
        bot_ref_3 = comment(5, "chatgpt-codex-connector", "2026-09-19T10:04:00Z", "comment=3 is still broken", author_type="Bot")
        findings = pr_guard_issue_comments.classify_finding_comments(base_comments + [bot_ref_3])
        self.assertEqual([(f.id, f.classification) for f in findings], [(1, "receipted"), (3, "DANGER")])

        receipt_3 = comment(6, "RachaelsDen", "2026-09-19T10:05:00Z", "Fixed comment=3.")
        findings = pr_guard_issue_comments.classify_finding_comments(base_comments + [bot_ref_3, receipt_3])
        self.assertEqual([(f.id, f.classification) for f in findings], [(1, "receipted"), (3, "receipted")])

        bot_no_ref = comment(7, "chatgpt-codex-connector", "2026-09-19T10:06:00Z", "still broken", author_type="Bot")
        findings = pr_guard_issue_comments.classify_finding_comments(base_comments + [bot_ref_3, receipt_3, bot_no_ref])
        self.assertEqual([(f.id, f.classification) for f in findings], [(1, "DANGER"), (3, "DANGER")])

    def test_unmatched_reference_bot_follow_up_acts_as_global_follow_up(self):
        # Given: findings 1+3 receipted, bot posts `Still broken; see #42` (no finding 42).
        # When: classified. Then: both findings reopen (DANGER).
        base_comments = [
            comment(1, "chatgpt-codex-connector", "2026-09-19T10:00:00Z", "P1 Badge"),
            comment(2, "RachaelsDen", "2026-09-19T10:01:00Z", "Fixed comment=1."),
            comment(3, "chatgpt-codex-connector", "2026-09-19T10:02:00Z", "P2 Badge"),
            comment(4, "RachaelsDen", "2026-09-19T10:03:00Z", "Fixed comment=3."),
        ]
        bot_unmatched_ref = comment(5, "chatgpt-codex-connector", "2026-09-19T10:04:00Z", "Still broken; see #42", author_type="Bot")
        findings = pr_guard_issue_comments.classify_finding_comments(base_comments + [bot_unmatched_ref])
        self.assertEqual([(f.id, f.classification) for f in findings], [(1, "DANGER"), (3, "DANGER")])

    def test_referencing_receipt_for_nonexistent_id_is_global_noop(self):
        # Given: findings 1+3 open (DANGER), maintainer posts `Fixed #42.` (no finding 42).
        # When: classified. Then: neither finding is cleared (both stay DANGER).
        base_comments = [
            comment(1, "chatgpt-codex-connector", "2026-09-19T10:00:00Z", "P1 Badge"),
            comment(3, "chatgpt-codex-connector", "2026-09-19T10:02:00Z", "P2 Badge"),
        ]
        receipt_unmatched_ref = comment(5, "RachaelsDen", "2026-09-19T10:04:00Z", "Fixed #42.")
        findings = pr_guard_issue_comments.classify_finding_comments(base_comments + [receipt_unmatched_ref])
        self.assertEqual([(f.id, f.classification) for f in findings], [(1, "DANGER"), (3, "DANGER")])

    def test_same_second_bot_edited_finding_and_receipt_is_danger(self):
        # Given: bot comment created and edited at T, and receipt created at T (same second).
        # When: classified. Then: timestamp tie is ambiguous -> DANGER.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", author_type="Bot", updated_at="2026-09-20T10:00:00Z"),
                comment(2, "RachaelsDen", "2026-09-20T10:00:00Z", "Fixed comment=1."),
            ]
        )
        self.assertEqual(findings[0].classification, "DANGER")

    def test_same_second_bot_unedited_finding_and_receipt_is_danger(self):
        # Given: bot comment created at T with no edit evidence, and receipt created at T.
        # When: classified. Then: same-second tie is ambiguous -> DANGER.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", author_type="Bot"),
                comment(2, "RachaelsDen", "2026-09-20T10:00:00Z", "Fixed comment=1."),
            ]
        )
        self.assertEqual(findings[0].classification, "DANGER")

    def test_receipt_strictly_after_bot_finding_is_receipted(self):
        # Given: bot comment created at T and receipt created at T+1s.
        # When: classified. Then: strictly-later receipt clears finding -> receipted.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "P1 Badge", author_type="Bot"),
                comment(2, "RachaelsDen", "2026-09-20T10:00:01Z", "Fixed comment=1."),
            ]
        )
        self.assertEqual(findings[0].classification, "receipted")

    def test_edited_bot_reply_strictly_after_receipt_reopens(self):
        # Given: bot finding at T-1, receipt at T, and bot reply edited at T+1s.
        # When: classified. Then: bot follow-up reopens finding -> DANGER.
        findings = pr_guard_issue_comments.classify_finding_comments(
            [
                comment(1, "chatgpt-codex-connector", "2026-09-20T09:59:59Z", "P1 Badge", author_type="Bot"),
                comment(2, "RachaelsDen", "2026-09-20T10:00:00Z", "Fixed comment=1."),
                comment(3, "chatgpt-codex-connector", "2026-09-20T10:00:00Z", "Still broken.", updated_at="2026-09-20T10:00:01Z", author_type="Bot"),
            ]
        )
        self.assertEqual(findings[0].classification, "DANGER")


class SurveyAndGateTests(unittest.TestCase):
    def test_banner_names_issue_comment_findings_without_review_threads(self):
        # Given: a DANGER issue comment and no review threads. When: surveyed.
        # Then: the banner names issue-comment findings as authority.
        out = io.StringIO()
        finding = comment(
            3,
            "chatgpt-codex-connector",
            "2026-09-20T10:00:00Z",
            "P1 Badge",
            "Bot",
        )
        with mock.patch.object(
            pr_guard_threads, "fetch_threads", return_value=([], [finding])
        ), mock.patch.object(
            pr_guard_reaction_banner.pr_guard_reaction,
            "bot_review_reaction",
            return_value="ACTIVE",
        ), redirect_stdout(out):
            pr_guard_threads.survey(68)
        self.assertIn("issue-comment findings comment=3 are the authority", out.getvalue())
    def test_gate_survey_fetches_one_combined_snapshot(self):
        # Given: a bannerless gate survey whose combined fetch records calls.
        # When: the survey runs. Then: it consumes one server snapshot.
        calls = []

        def fetch_threads(pr):
            calls.append("snapshot")
            return [resolved_thread()], []

        with mock.patch.object(
            pr_guard_threads, "fetch_threads", side_effect=fetch_threads
        ), redirect_stdout(io.StringIO()):
            pr_guard_threads.survey(68, reaction=False)
        self.assertEqual(calls, ["snapshot"])

    def test_survey_summary_includes_zero_comment_findings(self):
        # Given: a clean review-thread snapshot with no finding comments.
        # When: survey runs bannerless. Then: its stable summary reports zero.
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_threads, "fetch_threads", return_value=([resolved_thread()], [])
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
