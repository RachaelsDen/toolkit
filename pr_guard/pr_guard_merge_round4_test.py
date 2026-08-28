"""pr_guard merge-act round-4 tests (PR #40).

Thread 3832660859: the post-loop final completion check (a merge
landing during the LAST poll interval is observed as MERGED, never
bounced to the cancel/revert path). Thread 3832660852: the quiet-watch
sleep clamp (a deadline crossing between the loop's check and the
sleep arithmetic must sleep ZERO, never a negative duration whose
ValueError the broad handler would misread as a failed survey).
Thread 3832660865: the guarded merge act refuses bases outside the
narrowed main/dev protected list. The harness is the shared PLAIN
non-TestCase class (thread 3832660856), so importing it adds nothing
to unittest discovery.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round4_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    HEAD,
    HEAD_ARGV,
    SNAPSHOT_ARGV,
    MERGE_ARGV,
    POLL_ARGV,
    FakeClock,
    MergeHarness,
    merged,
    pending,
    thread,
)

RUNNER = MergeHarness()


def pinned(base: str = "dev"):
    return iter([{"head": {"sha": HEAD}, "base": {"ref": base}}])


# Thread 3832660852: monotonic() itself advances a step per read, so
# the deadline can cross between the watch's deadline check and the
# sleep arithmetic — and sleep() raises ValueError on negatives
# exactly like time.sleep, which the broad handler would misread.
class SteadyTickClock(FakeClock):
    def __init__(self, step: float):
        super().__init__()
        self._step = step

    def monotonic(self):
        now = self.now
        self.now += self._step
        return now

    def sleep(self, secs):
        if secs < 0:
            raise ValueError(f"negative sleep duration {secs}")
        super().sleep(secs)


class FinalCompletionPollTests(unittest.TestCase):
    def test_merge_landing_in_the_final_interval_is_observed(self):
        # Given: the merge queue drains during the LAST bounded poll
        # interval — all 30 in-loop polls report OPEN, sleep after
        # attempt 30 runs, and only the thread-3832660859 post-loop
        # final check (no sleep) observes state=MERGED. The old code
        # cancelled here, sending a clean landing to the revert path.
        surveys = iter([[thread("11", "resolved")], [thread("11", "resolved")]])

        # When: the guarded merge runs against that late drain.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 30 + [merged()],
        )

        # Then: exit 0 via the final check — 31 completion polls (30
        # interval-spaced + the final no-sleep one), NEVER a
        # --disable-auto cancel, and the clean backstop survey runs.
        self.assertEqual(code, 0)
        self.assertEqual(
            [a for a in argvs if a.startswith("gh")],
            [HEAD_ARGV, SNAPSHOT_ARGV, MERGE_ARGV] + [POLL_ARGV] * 31,
        )
        self.assertNotIn("--disable-auto", " ".join(argvs))
        self.assertIn("MERGED CLEAN", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)] * 2
        )

    def test_final_check_observing_closed_reports_did_not_land(self):
        # Given: the PR is closed without merging right after the last
        # in-loop poll — the final check (thread 3832660859) reads
        # state=CLOSED, which must take the ordinary did-not-land
        # verdict, never the cancel path.
        surveys = iter([[thread("11", "resolved")]])

        # When: the final check reads CLOSED.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 30
            + [{"state": "CLOSED", "mergeCommit": None,
                "baseRefName": "dev", "headRefOid": HEAD}],
        )

        # Then: the did-not-land banner, exit 1, no cancel plumbing.
        self.assertEqual(code, 1)
        self.assertIn("MERGE DID NOT LAND", out)
        self.assertIn("nothing to revert", out)
        self.assertNotIn("--disable-auto", " ".join(argvs))


class ClampedQuietSleepTests(unittest.TestCase):
    def test_deadline_crossing_between_check_and_sleep_stays_clean(self):
        # Given: a 150s quiet window on a clock whose monotonic()
        # advances 40s per read — the cycle-1 deadline check still sees
        # time left, but the sleep arithmetic's read has crossed the
        # deadline (remaining = -10s). time.sleep raises ValueError on
        # negatives (thread 3832660852), and the broad handler would
        # revert an otherwise clean merge over it.
        surveys = iter([[thread("11", "resolved")] for _ in range(3)])
        clock = SteadyTickClock(40)

        # When: the watch hits the raced cycle.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), quiet_secs=150, clock_cls=lambda: clock
        )

        # Then: the raced sleep is clamped to exactly 0.0s (never
        # negative), the next cycle's check breaks at/after the
        # deadline, and the watch ends MERGED CLEAN — no revert.
        self.assertEqual(code, 0)
        self.assertIn("MERGED CLEAN", out)
        self.assertEqual(clock.slept, [0.0])
        self.assertNotIn("POST-MERGE SURVEY FAILED", out)
        self.assertNotIn("git revert", " ".join(argvs))


class GuardedBaseTests(unittest.TestCase):
    def test_release_base_shape_is_refused_up_front(self):
        # Given: pre-merge verified a PR whose base is a release branch
        # (thread 3832660865: 'refs/heads/release/**' left the
        # protected list because release branches double as PR HEADS —
        # PR #35 ran from release/m6-to-main — and gating them blocked
        # review-fix pushes).
        surveys = iter([[thread("11", "resolved")]])

        # When: the guarded merge act is asked to merge into it.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned("release/m6-to-main"), base="release/m6-to-main"
        )

        # Then: BLOCKED before ANY dispatch, survey, or gate fetch —
        # the message names the narrowed protected list and the thread,
        # never the misleading "re-run harden" remedy.
        self.assertEqual(code, 1)
        self.assertEqual(argvs, [])
        self.assertEqual(events, [])
        self.assertIn("BLOCKED", out)
        self.assertIn("not a protected base", out)
        self.assertIn("(refs/heads/main, refs/heads/dev)", out)
        self.assertIn("thread 3832660865", out)
        self.assertNotIn("re-run harden", out)


if __name__ == "__main__":
    unittest.main()
