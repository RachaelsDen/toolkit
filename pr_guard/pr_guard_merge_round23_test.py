"""pr_guard merge-act round-23 tests (PR #41 round 23).

Thread 3834988955's contiguous-suffix arm — the round-23 answer to
the advancement-then-rebase landing — was RETIRED at round 25
(threads 3835145976/3835145981/3835175506/3835175508) with the
classifier it extended: the suffix evidence was reproducible by a
foreign landing exactly like every signal before it, so the shape
now FAILS CLOSED by contract (parent is not the base tip) and the
three SuffixAdvancement suites were DELETED with the arm (the suite
count drops by design; the refit round-11/12 suites pin the
advancement fail-closed contract).

Thread 3834988957: when cancellation handles a QUEUED PR the
disable-auto rc is deliberately ignored (thread 3834590317) — the
converged banner now reports the OBSERVED rc with the
ignored-because-queued rationale instead of claiming "exited 0".

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round23_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    HEAD,
    MergeHarness,
    pending,
    queued_entry,
    thread,
)

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"
def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class QueueDisableRcBannerTests(unittest.TestCase):
    def test_queued_disable_rc_reported_in_converged_banner(self):
        # Given: thread 3834988957's exact finding — the completion
        # poll timed out still-OPEN on a QUEUED PR, the disable
        # legitimately exited 1 (no auto-merge request exists,
        # thread 3834590317), the rc was deliberately IGNORED, and
        # the dequeue plus the settling window then CONVERGED — the
        # round-22 banner nevertheless recorded "exited 0," false
        # cancellation evidence in the audit trail.
        surveys = iter([[thread("11", "resolved")]])

        def rc_for(argv):
            return 1 if "--disable-auto" in argv else 0

        # When: the converged banner renders the disable clause from
        # the OBSERVED rc threaded through the settlement.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 44,
            rc_for=rc_for,
            queue_entries=[queued_entry(), queued_entry(), None],
            dequeue_rc=0,
        )

        # Then: the banner reports the ATTEMPT and its rc with the
        # ignored-because-queued rationale and BOTH thread cites —
        # never the false exited-0 claim — beside the unchanged
        # convergence evidence.
        self.assertEqual(code, 1)
        self.assertIn("was DISPATCHED and exited 1", out)
        self.assertIn(
            "deliberately IGNORED because the queue probe read QUEUED",
            out,
        )
        self.assertIn("3834590317/3834988957", out)
        self.assertNotIn("--disable-auto exited 0", out)
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn("STAYED OPEN through the FULL 60s", out)

    def test_successful_disable_keeps_the_exited_zero_claim(self):
        # Given: the non-queued cancellation — the disable exited 0
        # (an auto-merge request existed and was disabled), the
        # queue entry read ABSENT, and the settling window held.
        surveys = iter([[thread("11", "resolved")]])

        # When: the converged banner renders the disable clause for
        # rc=0.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 44,
            queue_entries=[None],
        )

        # Then: the historical TRUTHFUL claim stands — exited 0,
        # never the ignored-rc clause.
        self.assertEqual(code, 1)
        self.assertIn("gh pr merge 39 --disable-auto exited 0", out)
        self.assertNotIn("was DISPATCHED", out)
        self.assertNotIn("deliberately IGNORED", out)
        self.assertIn("CANCELLED and verified gone", out)


if __name__ == "__main__":
    unittest.main()
