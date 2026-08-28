"""pr_guard merge-act round-2/3 tests (PR #40).

Split from pr_guard_merge_test.py at the 250 pure-LOC ceiling: the
poll-timeout pending-merge cancel (threads 3832418151/3832522306) and
the quiet-period watch (threads 3832418158/3832522300). Round 3
(thread 3832522306): the cancel verifies BOTH the auto-merge and the
merge-queue contingencies — disable + autoMergeRequest null + OPEN,
plus a delayed re-check (gh 2.97.0 exposes no queue field) — and
reverts immediately when a verification reports MERGED. No network:
every gh/git call, every fetch, and every sleep run on the shared
fake-clock harness — a PLAIN non-TestCase class since thread
3832660856 (PR #40 round 4), so importing it adds nothing to unittest
discovery and these tests run exactly once.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_watch_test -v
"""

import unittest
from unittest import mock

from . import cli
from . import pr_guard_merge
from .pr_guard_merge_harness import (
    GRAPHQL_ARGV,
    HEAD,
    HEAD_ARGV,
    SNAPSHOT_ARGV,
    MERGE_ARGV,
    POLL_ARGV,
    REPO_FLAG,
    MergeHarness,
    pending,
    revert_argv,
    thread,
)

DISABLE_ARGV = f"gh pr merge 39 --disable-auto {REPO_FLAG}"
# Thread 3836501981 (PR #45 round 15): the cancel read's argv
# renders CANCEL_FIELDS (updatedAt joined it for the landing
# corroboration) — one source of truth with the reads.
from .pr_guard_common import CANCEL_FIELDS
CANCEL_ARGV = f"gh pr view 39 --json {CANCEL_FIELDS} {REPO_FLAG}"
RUNNER = MergeHarness()


def queued() -> dict:
    return {"autoMergeRequest": {"mergeMethod": "MERGE"}, "state": "OPEN"}


def clean() -> dict:
    return {"autoMergeRequest": None, "state": "OPEN"}


def landed() -> dict:
    return {"autoMergeRequest": None, "state": "MERGED"}


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class CancelPendingMergeTests(unittest.TestCase):
    def test_cancel_retries_until_verification_converges(self):
        # Given: the poll timed out and the first --disable-auto ran,
        # but the verification read still shows a pending
        # autoMergeRequest (thread 3832418151's retry requirement);
        # the second attempt reads clean and its thread-3832522306
        # delayed re-check still reads OPEN. Thread 3833073940 (PR
        # #41): the converged verdict additionally settles the QUEUE
        # contingency — the GraphQL mergeQueueEntry probe reads ABSENT
        # (one extra state read feeds the settlement's first attempt),
        # thread 3833251675 (PR #41 round 6) re-reads the PR state
        # STILL OPEN after the ABSENT probe, and thread 3833360201
        # (PR #41 round 7) keeps that OPEN under the settling window —
        # which thread 3833540916 (PR #41 round 8) now measures by
        # DEADLINE: 13 probes, the last at/after the 60s deadline —
        # before converging.
        surveys = iter([[thread("11", "resolved")]])

        # When: the retry converges on the second attempt.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 44,
            cancel_reads=[queued(), clean(), clean()],
        )

        # Then: the disable ran twice and the verification read
        # SEVENTEEN times (read + converged read + its re-check + the
        # queue settlement's first state read + thread 3833762320's
        # autoMergeRequest re-read at each of the settling window's 13
        # probes) plus the ABSENT queue probe and the settling
        # window's 13 deadline-measured state reads + 13 entry
        # re-probes (threads 3833360201/3833540916), the retry
        # progress printed, and the converged banner names the
        # re-check, the probed-ABSENT queue entry, and the OPEN that
        # STAYED OPEN through the full settling window while still
        # failing closed with the manual-revert warning.
        self.assertEqual(code, 1)
        self.assertEqual(argvs.count(DISABLE_ARGV), 2)
        self.assertEqual(argvs.count(CANCEL_ARGV), 17)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 14)
        self.assertIn("CANCEL PENDING attempt=1/3", out)
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn("probed ABSENT", out)
        self.assertIn("re-check", out)
        self.assertIn("DO NOT assume MERGED CLEAN", out)
        self.assertNotIn("MERGED CLEAN:", out)

    def test_failing_disable_prints_both_contingencies(self):
        # Given: the poll timed out and --disable-auto itself FAILS
        # every attempt (thread 3832418151's both-fail fallback) — the
        # pending request's fate is unknown, auto-merge OR queue.
        surveys = iter([[thread("11", "resolved")]])

        def rc_for(argv):
            return 1 if "--disable-auto" in argv else 0

        # When: all three bounded attempts fail.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), poll_states=[pending()] * 31, rc_for=rc_for
        )

        # Then: exit 1 with instructions covering BOTH contingencies —
        # cancel manually (the queue one names removing the PR from
        # the merge queue, thread 3832522306) AND revert if landed —
        # never the cancelled banner, never MERGED CLEAN.
        self.assertEqual(code, 1)
        self.assertEqual(argvs.count(DISABLE_ARGV), 3)
        self.assertEqual(argvs.count(CANCEL_ARGV), 3)
        self.assertIn("CANCEL UNCONFIRMED", out)
        self.assertIn("BOTH contingencies are live", out)
        self.assertIn("CANCEL the merge manually", out)
        self.assertIn("remove the PR from the merge queue", out)
        self.assertIn("revert it there", out)
        self.assertIn("DO NOT assume MERGED CLEAN", out)
        self.assertNotIn("CANCELLED and verified gone", out)
        self.assertNotIn("MERGED CLEAN:", out)

    def test_verification_showing_merged_reverts_the_landed_merge(self):
        # Given: the merge landed despite the stalled poll — the cancel
        # verification reports state=MERGED (thread 3832522306: the
        # merge landed while we were cancelling), which must go
        # straight to the revert path, never be reported as cancelled.
        surveys = iter([[thread("11", "resolved")]])

        # When: the verification read reports MERGED.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 31,
            cancel_reads=[landed()],
        )

        # Then: the landed-during-cancel banner prints, the merge
        # commit is re-fetched and the revert argv fires on the landed
        # base, and no cancelled/clean banner ever does.
        self.assertEqual(code, 1)
        self.assertIn("LANDED DURING CANCELLATION", out)
        self.assertIn("REVERT PR OPENED", out)
        self.assertNotIn("CANCELLED and verified gone", out)
        self.assertNotIn("MERGED CLEAN:", out)
        tail = RUNNER.revert_tail(argvs)
        expected = revert_argv("dev", RUNNER.revert_tmp)
        self.assertEqual(tail[:6], expected[:6])
        self.assertTrue(tail[5].startswith(expected[5]))
        self.assertEqual(argvs.count(DISABLE_ARGV), 1)
        self.assertEqual(argvs.count(CANCEL_ARGV), 1)

    def test_recheck_flipping_to_merged_reverts_the_landed_merge(self):
        # Given: the first verification reads clean, but the
        # thread-3832522306 delayed re-check catches the merge landing
        # inside the re-check delay (the queue entry drained late).
        surveys = iter([[thread("11", "resolved")]])

        # When: the re-check reports MERGED.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 31,
            cancel_reads=[clean(), landed()],
        )

        # Then: one disable, two verification reads (initial +
        # re-check), then the revert — never a cancelled claim over a
        # merge that landed during cancellation.
        self.assertEqual(code, 1)
        self.assertIn("LANDED DURING CANCELLATION", out)
        self.assertNotIn("CANCELLED and verified gone", out)
        self.assertNotIn("MERGED CLEAN:", out)
        tail = RUNNER.revert_tail(argvs)
        expected = revert_argv("dev", RUNNER.revert_tmp)
        self.assertEqual(tail[:6], expected[:6])
        self.assertTrue(tail[5].startswith(expected[5]))
        self.assertEqual(argvs.count(DISABLE_ARGV), 1)
        self.assertEqual(argvs.count(CANCEL_ARGV), 2)


class QuietPeriodWatchTests(unittest.TestCase):
    def test_danger_on_late_quiet_cycle_reverts_without_clean_banner(self):
        # Given: the merge completed clean, the first two 60s-spaced
        # surveys of a 300s quiet window pass, but the bot's final
        # round lands before the third (thread 3832418158 — the
        # documented production failure mode: rounds arriving minutes
        # after merge).
        surveys = iter(
            [
                [thread("11", "resolved")],
                [thread("11", "resolved")],
                [thread("11", "resolved")],
                [thread("11", "DANGER")],
            ]
        )

        # When: the watch surveys cycle 3 (fake t=120).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), quiet_secs=300
        )

        # Then: revert argv fires on the verified base at cycle 3 with
        # the elapsed time named, MERGED CLEAN is never printed, and
        # the act stops surveying the moment the DANGER appears (4
        # surveys total).
        self.assertEqual(code, 1)
        self.assertIn("POST-MERGE DANGER", out)
        self.assertIn(
            "caught at quiet-period cycle 3, 120s into the 300s window", out
        )
        self.assertNotIn("MERGED CLEAN", out)
        # Thread 3835290443 (round 26): the PRE-DISPATCH base-tip
        # snapshot adds git argvs before the dispatch (remote -v,
        # fetch, rev-parse), so the revert sequence is read AFTER the
        # merge dispatch, not from the top of the run.
        dispatch_at = argvs.index(MERGE_ARGV)
        tail = [
            a
            for a in argvs[dispatch_at:]
            if a.startswith("git") or a.startswith("gh pr create")
        ]
        expected = revert_argv("dev", RUNNER.revert_tmp)
        self.assertEqual(tail[:6], expected[:6])
        self.assertTrue(tail[5].startswith(expected[5]))
        gh = [a for a in argvs if a.startswith("gh")]
        self.assertEqual(
            gh[:4],
            [HEAD_ARGV, SNAPSHOT_ARGV, MERGE_ARGV, POLL_ARGV],
        )
        self.assertTrue(gh[4].startswith("gh pr create"))
        self.assertEqual(len(gh), 5)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)] * 4
        )

    def test_zero_danger_across_full_quiet_period_exits_zero(self):
        # Given: a 300s quiet window and a bot that never lands a last
        # word inside it.
        surveys = iter(
            [[thread("11", "resolved")] for _ in range(7)]
        )

        # When: the watch runs the FULL window to its deadline.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), quiet_secs=300
        )

        # Then: exit 0 only after the final survey AT the deadline —
        # surveys at fake t=0,60,...,300 with five 60s sleeps between,
        # progress printed per cycle with the elapsed time, no
        # git/revert plumbing, and the MERGED CLEAN banner names the
        # residual window truth.
        self.assertEqual(code, 0)
        for cycle, elapsed in (
            (1, 0), (2, 60), (3, 120), (4, 180), (5, 240), (6, 300)
        ):
            self.assertIn(
                f"QUIET PERIOD cycle={cycle} elapsed={elapsed}s/300s", out
            )
        self.assertIn("MERGED CLEAN", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertEqual(
            [a for a in argvs if a.startswith("gh")],
            [HEAD_ARGV, SNAPSHOT_ARGV, MERGE_ARGV, POLL_ARGV],
        )
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)] * 7
        )
        self.assertEqual(
            RUNNER.survey_times, [0, 0, 60, 120, 180, 240, 300]
        )
        self.assertEqual(RUNNER.clock.slept, [60.0] * 5)

    def test_quiet_secs_zero_collapses_to_single_backstop_snapshot(self):
        # Given: --quiet-secs 0 — the documented escape hatch that
        # keeps the workflow usable when a bounded wait cannot be
        # afforded (thread 3832418158); the PR #39 single-survey
        # backstop still must run.
        surveys = iter([[thread("11", "resolved")], [thread("11", "resolved")]])

        # When: the guarded merge runs with a zero window.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), quiet_secs=0
        )

        # Then: exactly ONE post-merge survey (plus the closing one)
        # at the deadline-equals-start instant, zero sleeps, and exit 0
        # after it classifies clean.
        self.assertEqual(code, 0)
        self.assertIn("QUIET PERIOD cycle=1 elapsed=0s/0s", out)
        self.assertIn("MERGED CLEAN", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)] * 2
        )
        self.assertEqual(RUNNER.clock.slept, [])


class QuietSecsFlagTests(unittest.TestCase):
    def test_flag_overrides_the_default_window(self):
        # Given/When: merge mode invoked with --quiet-secs 120.
        with (
            mock.patch.object(cli, "merge_guarded", return_value=0)
        ) as act:
            code = cli.main(
                ["pr_guard.py", "merge", "39", HEAD, "dev",
                 "--quiet-secs", "120"]
            )

        # Then: the override reaches the act verbatim.
        self.assertEqual(code, 0)
        act.assert_called_once_with(39, HEAD, "dev", 120)

    def test_omitted_flag_defaults_to_fifteen_minutes(self):
        # Given/When: merge mode invoked bare.
        with (
            mock.patch.object(cli, "merge_guarded", return_value=0)
        ) as act:
            code = cli.main(["pr_guard.py", "merge", "39", HEAD, "dev"])

        # Then: the default window is the 15-minute constant.
        self.assertEqual(code, 0)
        act.assert_called_once_with(
            39, HEAD, "dev", pr_guard_merge.DEFAULT_QUIET_SECS
        )

    def test_non_digit_flag_is_a_usage_error(self):
        # Given/When: --quiet-secs with a non-numeric value.
        with mock.patch.object(cli, "merge_guarded") as act:
            code = cli.main(
                ["pr_guard.py", "merge", "39", HEAD, "dev",
                 "--quiet-secs", "abc"]
            )

        # Then: usage exit 2, nothing dispatched.
        self.assertEqual(code, 2)
        act.assert_not_called()


if __name__ == "__main__":
    unittest.main()
