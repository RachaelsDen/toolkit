"""pr_guard merge-act tests.

PR #39 follow-up (thread 3829356723): the post-merge re-survey and the
automatic revert backstop. PR #40 round 1: the merge-completion poll
(thread 3832321683), the post-merge base re-assertion (thread
3832321698), and the fail-closed survey/revert wrappers (thread
3832321706). Thread 3832660856 (PR #40 round 4): the fakes and the
runner live in pr_guard_merge_harness — a PLAIN class, never a
TestCase — so importing them cannot re-discover these tests elsewhere.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    GRAPHQL_ARGV,
    HEAD,
    HEAD_ARGV,
    SNAPSHOT_ARGV,
    MERGE_ARGV,
    MERGE_SHA,
    POLL_ARGV,
    REPO_FLAG,
    REVERT_PR_URL,
    MergeHarness,
    merged,
    pending,
    revert_argv,
    thread,
)

HARNESS = MergeHarness()


class MergeGuardedTests(unittest.TestCase):
    def run_guarded(self, *args, **kwargs):
        return HARNESS.run_guarded(*args, **kwargs)

    def revert_tail(self, argvs: list[str]) -> list[str]:
        return HARNESS.revert_tail(argvs)

    def test_post_merge_danger_opens_revert_pr_and_exits_nonzero(self):
        # Given: the PR is pinned at head/base with the gate covering
        # the base; the closing survey is clean, the merge completes,
        # but a bot landed a last word on an ALREADY-RESOLVED thread
        # inside the survey->merge window (thread 3829356723) — it
        # passes the server ruleset too, so only the post-merge
        # re-survey can see it.
        surveys = iter([[thread("11", "resolved")], [thread("11", "DANGER")]])
        pr_reads = iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])

        # When: the guarded merge runs.
        code, out, argvs, events = self.run_guarded(surveys, pr_reads)

        # Then: the merge dispatched, the completion poll confirmed
        # MERGED on the verified base, the re-survey caught the DANGER
        # thread, the revert ran the exact argv sequence and opened a
        # revert PR whose URL is printed loudly, and the act exits
        # nonzero even though the revert PR opened cleanly.
        self.assertEqual(code, 1)
        self.assertIn(MERGE_ARGV, argvs)
        self.assertIn(POLL_ARGV, argvs)
        tail = self.revert_tail(argvs)
        expected = revert_argv("dev", HARNESS.revert_tmp)
        self.assertEqual(tail[:6], expected[:6])
        self.assertTrue(tail[5].startswith(expected[5]))
        self.assertIn("POST-MERGE DANGER", out)
        self.assertIn("REVERT PR OPENED", out)
        self.assertIn(REVERT_PR_URL.strip(), out)

    def test_clean_post_merge_survey_exits_zero_without_reverting(self):
        # Given: the same pinned PR with the gate covering the base,
        # and NO bot follow-up — the closing survey and the post-merge
        # re-survey both classify every thread safe (thread 3829356723's
        # clean path), with the merge already completed.
        surveys = iter([[thread("11", "resolved")], [thread("11", "resolved")]])
        pr_reads = iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])

        # When: the guarded merge runs.
        code, out, argvs, events = self.run_guarded(surveys, pr_reads)

        # Then: exactly THREE gh calls (the merge-request-time head
        # capture of thread 3832522310, the merge request, and ONE
        # completion poll) — no git plumbing, no revert PR — and the
        # act exits 0 after the clean re-survey.
        self.assertEqual(code, 0)
        self.assertEqual(
            [a for a in argvs if a.startswith("gh")],
            [HEAD_ARGV, SNAPSHOT_ARGV, MERGE_ARGV, POLL_ARGV],
        )
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertIn("MERGED CLEAN", out)

    def test_danger_in_closing_survey_blocks_before_the_merge(self):
        # Given: a DANGER thread already visible in the closing survey.
        surveys = iter([[thread("11", "DANGER")]])
        pr_reads = iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])

        # When: the guarded merge runs.
        code, out, argvs, events = self.run_guarded(surveys, pr_reads)

        # Then: BLOCKED — nothing is dispatched (not even the head
        # capture, which runs only after a clean closing survey), exit 1.
        self.assertEqual(code, 1)
        self.assertEqual(argvs, [])
        self.assertIn("BLOCKED", out)

    def test_backstop_survey_waits_for_merge_queue_completion(self):
        # Given: `gh pr merge` exits 0 but has only QUEUED the PR
        # (thread 3832321683) — two polls still report OPEN before the
        # third confirms MERGED on the verified base.
        surveys = iter([[thread("11", "resolved")], [thread("11", "resolved")]])
        pr_reads = iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])

        # When: the guarded merge runs against that queue drain.
        code, out, argvs, events = self.run_guarded(
            surveys, pr_reads, poll_states=[pending(), pending(), merged()]
        )

        # Then: exit 0 — but only after three polls with progress
        # output naming state AND base, and the backstop survey runs
        # strictly AFTER the poll that reported MERGED (never while
        # the race window was still open).
        self.assertEqual(code, 0)
        self.assertEqual(
            [a for a in argvs if a.startswith("gh pr view")],
            [HEAD_ARGV] + [POLL_ARGV] * 3,
        )
        self.assertIn(
            "MERGE PENDING attempt=1/30 state=OPEN base=dev", out
        )
        surveys_at = [i for i, ev in enumerate(events) if ev == ("survey",)]
        merged_poll_at = max(
            i
            for i, ev in enumerate(events)
            if ev[0] == "run" and ev[1] == tuple(POLL_ARGV.split())
        )
        self.assertEqual(len(surveys_at), 2)
        self.assertLess(merged_poll_at, surveys_at[1])
        self.assertIn("MERGED CLEAN", out)

    def test_merge_never_completing_fails_closed_without_clean_banner(self):
        # Given: the merge request is accepted but the PR never reaches
        # state=MERGED — every bounded poll AND the thread-3832660859
        # post-loop final check report OPEN (queue stalled; thread
        # 3832321683's timeout path) — and thread 3832418151 (PR #40
        # round 2) adds the pending-merge CANCEL: --disable-auto plus
        # the autoMergeRequest/state verification read (initial +
        # delayed re-check, thread 3832522306). Thread 3833073940 (PR
        # #41): the converged verdict additionally settles the queue
        # contingency — the settlement's first attempt reads OPEN once
        # more and the GraphQL mergeQueueEntry probe reads ABSENT —
        # thread 3833251675 (PR #41 round 6) re-reads the PR state
        # STILL OPEN after the ABSENT probe, and thread 3833360201
        # (PR #41 round 7) keeps watching: that OPEN must STAY OPEN
        # through the full settling window (entry ABSENT at every
        # probe, the last one at/after the deadline — thread
        # 3833540916, PR #41 round 8) before the cancelled-and-
        # verified banner prints.
        surveys = iter([[thread("11", "resolved")]])
        pr_reads = iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])

        # When: the guarded merge runs out of poll attempts.
        code, out, argvs, events = self.run_guarded(
            surveys, pr_reads, poll_states=[pending()] * 44
        )

        # Then: exit 1 with the cancelled-and-verified banner — no
        # backstop survey, no MERGED CLEAN — and the gh sequence is the
        # head capture, the merge request, the 30 bounded polls PLUS
        # the final no-sleep check (thread 3832660859), the
        # --disable-auto cancel, the verification read TWICE
        # (read + re-check), the settlement's one extra state read, the
        # ABSENT queue probe, and the settling window's 13 deadline
        # probes (threads 3833360201/3833540916: a state read + an
        # ABSENT re-probe + an autoMergeRequest re-read each — thread
        # 3833762320 keeps every settling probe rejecting a re-enabled
        # auto-merge — the FINAL probe at/after the 60s deadline), in
        # that order — every gh pr argv pinned with
        # -R RachaelsDen/UR-lorebook (thread 3833073952).
        self.assertEqual(code, 1)
        self.assertIn("MERGE UNVERIFIED", out)
        self.assertIn("MERGE PENDING final check", out)
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn("STAYED OPEN through the FULL 60s", out)
        self.assertIn("DO NOT assume MERGED CLEAN", out)
        self.assertNotIn("MERGED CLEAN:", out)
        from .pr_guard_common import CANCEL_FIELDS
        # Thread 3836501981 (PR #45 round 15): updatedAt joined
        # CANCEL_FIELDS for the landing corroboration.
        cancel_view = (
            f"gh pr view 39 --json {CANCEL_FIELDS} "
            "-R RachaelsDen/UR-lorebook"
        )
        self.assertEqual(
            [a for a in argvs if a.startswith("gh")],
            [HEAD_ARGV, SNAPSHOT_ARGV, MERGE_ARGV]
            + [POLL_ARGV] * 31
            + ["gh pr merge 39 --disable-auto -R RachaelsDen/UR-lorebook"]
            + [cancel_view] * 3
            + [GRAPHQL_ARGV]
            + [POLL_ARGV, GRAPHQL_ARGV, cancel_view] * 13,
        )
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )

    def test_retargeted_base_after_the_merge_reverts_on_landed_base(self):
        # Given: the PR is retargeted between the base check and the
        # merge (thread 3832321698 — GitHub's merge API accepts no base
        # lock, so --match-head-commit cannot pin the destination); the
        # merge succeeds and the completion poll reports MERGED on an
        # UNPROTECTED base instead of the verified dev.
        surveys = iter([[thread("11", "resolved")]])
        pr_reads = iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])

        # When: the guarded merge runs and the poll lands on the
        # retargeted destination.
        code, out, argvs, events = self.run_guarded(
            surveys, pr_reads, poll_states=[merged(base="feature/unprotected")]
        )

        # Then: POST-MERGE BASE MISMATCH — the revert targets the
        # LANDED base (that is where the escaped merge lives), no
        # post-merge survey is consumed (surveys held only the closing
        # one), and the act exits 1 with no MERGED CLEAN.
        self.assertEqual(code, 1)
        self.assertIn("POST-MERGE BASE MISMATCH", out)
        tail = self.revert_tail(argvs)
        expected = revert_argv("feature/unprotected", HARNESS.revert_tmp)
        self.assertEqual(tail[:6], expected[:6])
        self.assertTrue(
            tail[5].startswith(expected[5])
        )
        self.assertNotIn("MERGED CLEAN", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )

    def test_dying_post_merge_survey_fails_closed_through_revert(self):
        # Given: the merge completed cleanly, but the backstop survey's
        # GraphQL call DIES — gh_graphql's die raises SystemExit(2)
        # (thread 3832321706) — which must not bypass the backstop and
        # print MERGED CLEAN over an unverified merge.
        surveys = iter([[thread("11", "resolved")], SystemExit(2)])
        pr_reads = iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])

        # When: the guarded merge runs and the re-survey dies.
        code, out, argvs, events = self.run_guarded(surveys, pr_reads)

        # Then: POST-MERGE SURVEY FAILED — no MERGED CLEAN, and the
        # same revert argv sequence fires (revert branch + revert PR
        # on the verified base), exiting 1.
        self.assertEqual(code, 1)
        self.assertIn("POST-MERGE SURVEY FAILED (SystemExit: 2)", out)
        self.assertNotIn("MERGED CLEAN", out)
        tail = self.revert_tail(argvs)
        expected = revert_argv("dev", HARNESS.revert_tmp)
        self.assertEqual(tail[:6], expected[:6])
        self.assertTrue(tail[5].startswith(expected[5]))
        self.assertIn("REVERT PR OPENED", out)

    def test_dying_revert_after_dying_survey_names_the_merge_sha(self):
        # Given: the dying post-merge survey (thread 3832321706) AND a
        # revert path that itself blows up — the git revert step RAISES
        # instead of exiting nonzero.
        surveys = iter([[thread("11", "resolved")], SystemExit(2)])
        pr_reads = iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])

        def rc_for(argv):
            # Thread 3835345690 (round 27): the revert argv now
            # carries the identity flags between `-C <tmp>` and the
            # subcommand — match on the subcommand ELEMENT, not its
            # position (the only argv element "revert" before this
            # step is the revert command itself).
            if argv[:1] == ["git"] and "revert" in argv:
                raise RuntimeError("git exploded")
            return 0

        # When: the guarded merge runs.
        code, out, argvs, events = self.run_guarded(
            surveys, pr_reads, rc_for=rc_for
        )

        # Then: the guarded wrapper catches it and prints the explicit
        # manual-revert instructions naming the merge SHA — exit 1,
        # never MERGED CLEAN, no revert PR claim.
        self.assertEqual(code, 1)
        self.assertIn("AUTOMATIC REVERT FAILED (RuntimeError: git exploded)", out)
        self.assertIn(f"merge {MERGE_SHA[:12]} of PR #39", out)
        self.assertIn("MANUALLY", out)
        self.assertNotIn("MERGED CLEAN", out)
        self.assertNotIn("REVERT PR OPENED", out)


if __name__ == "__main__":
    unittest.main()
