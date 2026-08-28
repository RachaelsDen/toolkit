"""pr_guard merge-act round-3 tests (PR #40).

The deadline-based quiet watch (thread 3832522300) and the landed-head
verification (thread 3832522310). Split from the watch suite at the
250 pure-LOC ceiling. No network and no real sleeps: the shared
harness fake clock makes sleep() advance monotonic(), so elapsed-time
assertions are exact — quiet_secs maps to fake seconds 1:1. The
harness is a PLAIN non-TestCase class since thread 3832660856 (PR #40
round 4), so importing it adds nothing to unittest discovery.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round3_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    HEAD,
    HEAD_ARGV,
    SNAPSHOT_ARGV,
    MERGE_ARGV,
    POLL_ARGV,
    MergeHarness,
    merged,
    revert_argv,
    thread,
)

PUSHED_HEAD = "e7c2d94f10ab3c55d0927f81e6b4a3df0c9ee111"
RUNNER = MergeHarness()


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class DeadlineWatchTests(unittest.TestCase):
    def test_default_window_surveys_first_at_zero_and_last_at_deadline(self):
        # Given: the default-scale 900s quiet window and a bot that
        # never lands a last word inside it; the round-2 bug (thread
        # 3832522300) counted SURVEYS — 15 cycles span only 14 sleeps,
        # so the window declared clean at 840s with the tail unwatched.
        surveys = iter([[thread("11", "resolved")] for _ in range(17)])

        # When: the watch runs the full window on the fake clock.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), quiet_secs=900
        )

        # Then: the first post-merge survey runs at t=0, the FINAL one
        # at t>=900 (exactly 900 — the last gap sleeps only the 60s
        # remaining, never a full interval past the deadline), 16
        # watch surveys across 15 full sleeps, and MERGED CLEAN prints
        # only after that final survey.
        self.assertEqual(code, 0)
        self.assertEqual(RUNNER.survey_times[1], 0)
        self.assertGreaterEqual(RUNNER.survey_times[-1], 900)
        self.assertEqual(RUNNER.survey_times[1:], [60.0 * i for i in range(16)])
        self.assertEqual(RUNNER.clock.slept, [60.0] * 15)
        self.assertIn("QUIET PERIOD cycle=16 elapsed=900s/900s", out)
        self.assertIn("MERGED CLEAN", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)] * 17
        )

    def test_small_window_sleeps_only_the_remaining_gap(self):
        # Given: --quiet-secs 1 — the round-2 math collapsed this to a
        # single immediate snapshot (1//60 == 0 cycles, thread
        # 3832522300), watching nothing at all.
        surveys = iter([[thread("11", "resolved")] for _ in range(3)])

        # When: the watch runs a 1s window on the fake clock.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), quiet_secs=1
        )

        # Then: an IMMEDIATE survey at t=0, one gap sleep of exactly
        # the 1s remaining (never the full 60s interval), and the
        # final survey at/after the deadline before clean prints.
        self.assertEqual(code, 0)
        self.assertEqual(RUNNER.survey_times, [0, 0, 1])
        self.assertEqual(RUNNER.clock.slept, [1.0])
        self.assertIn("QUIET PERIOD cycle=1 elapsed=0s/1s", out)
        self.assertIn("QUIET PERIOD cycle=2 elapsed=1s/1s", out)
        self.assertIn("MERGED CLEAN", out)


class LandedHeadTests(unittest.TestCase):
    def test_final_head_equal_to_the_surveyed_head_is_clean(self):
        # Given: the completion poll reports MERGED on the verified
        # base with a merge commit AND a final headRefOid equal to the
        # surveyed head — nothing was pushed after the merge request.
        surveys = iter([[thread("11", "resolved")], [thread("11", "resolved")]])

        # When: the guarded merge runs (single-snapshot window).
        code, out, argvs, events = RUNNER.run_guarded(surveys, pinned())

        # Then: the poll's field list carries headRefOid (thread
        # 3832522310) and the matching final head does not trip
        # anything — clean exit with the ordinary gh sequence.
        self.assertEqual(code, 0)
        self.assertIn("headRefOid", POLL_ARGV)
        self.assertEqual(
            [a for a in argvs if a.startswith("gh")],
            [HEAD_ARGV, SNAPSHOT_ARGV, MERGE_ARGV, POLL_ARGV],
        )
        self.assertIn("MERGED CLEAN", out)

    def test_pushed_head_merged_via_pending_auto_merge_reverts(self):
        # Given: `gh pr merge` enabled auto-merge (checks pending) and
        # the author pushed a NEW head while it was pending — the
        # request then merged the pushed, unsurveyed head, so the
        # completion poll reports MERGED on a MOVED headRefOid (thread
        # 3832522310: --match-head-commit bound only at request time).
        surveys = iter([[thread("11", "resolved")]])

        # When: the poll lands MERGED on the pushed head.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), poll_states=[merged(head=PUSHED_HEAD)]
        )

        # Then: POST-MERGE HEAD MISMATCH — the revert argv fires on
        # the landed base, no quiet-period survey is consumed (the
        # mismatch is caught before the watch starts), exit 1, never
        # a clean banner over unsurveyed content.
        self.assertEqual(code, 1)
        self.assertIn("POST-MERGE HEAD MISMATCH", out)
        self.assertIn("never surveyed", out)
        self.assertNotIn("MERGED CLEAN", out)
        tail = RUNNER.revert_tail(argvs)
        expected = revert_argv("dev", RUNNER.revert_tmp)
        self.assertEqual(tail[:6], expected[:6])
        self.assertTrue(tail[5].startswith(expected[5]))
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )

    def test_head_moved_during_the_closing_survey_blocks_dispatch(self):
        # Given: the author pushed between the closing survey and the
        # merge request — the request-time headRefOid capture (thread
        # 3832522310) reads a head that no longer matches the surveyed
        # one.
        surveys = iter([[thread("11", "resolved")]])

        # When: the act captures the merge-request-time head.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), head_reads=[PUSHED_HEAD]
        )

        # Then: BLOCKED before ANY merge dispatch — exactly the one
        # head-capture call ran, no merge request, no watch survey,
        # exit 1.
        self.assertEqual(code, 1)
        self.assertEqual(argvs, [HEAD_ARGV])
        self.assertIn("BLOCKED", out)
        self.assertIn("thread 3832522310", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )


if __name__ == "__main__":
    unittest.main()
