"""pr_guard merge-act round-15 tests (PR #41 round 15).

Thread 3834375737: a QUEUED merge-queue entry is DEQUEUED, not merely
watched — the dequeuePullRequest GraphQL mutation (live-schema
verified: DequeuePullRequestInput { id: ID! } = the PR node id; no
MergeQueueInput/action shape exists) runs once with the node id from
the existing pinned PR view; a success is re-verified by the probe
(entry gone + PR OPEN goes through the settling window), and a
failure falls back to the bounded watch whose terminal banner
documents the attempt. Thread 3834375731's empty-landing patch-id
arm — and the complete-map tightening of thread 3834400951 — were
RETIRED at round 25 (threads 3835145976/3835145981/3835175506/
3835175508): every exotic-landing shape those suites built now fails
closed BY CONTRACT (the landing's parent is not the current base
tip), so the three EmptyLandingPatchId suites were DELETED as
redundant with the refit round-11/12/14 fail-closed suites (the
suite count drops by design).

No network: the shared fake-gh/fake-clock harness drives the act;
dequeue_rc selects the mutation's outcome.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round15_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    DEQUEUE_ARGV,
    GRAPHQL_ARGV,
    HEAD,
    NODE_ID_ARGV,
    POLL_ARGV,
    MergeHarness,
    pending,
    queued_entry,
    thread,
)

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"
RANGE_OLDEST = "bbbb000000000000000000000000000000000022"
RANGE_MIDDLE = "cccc000000000000000000000000000000000033"
RANGE_NEWEST = "dddd000000000000000000000000000000000044"
FOREIGN_SHA = "eeee0000000000000000000000000000000000f1"
REBASED_FIRST = "eeee0000000000000000000000000000000000b1"
REBASED_SECOND = "eeee0000000000000000000000000000000000b2"
PR_COMMITS = [RANGE_OLDEST, RANGE_MIDDLE, RANGE_NEWEST]


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


def clean():
    return {"autoMergeRequest": None, "state": "OPEN"}


class QueueDequeueTests(unittest.TestCase):
    def test_queued_dequeue_success_reverified_and_converges(self):
        # Given: the completion poll timed out still-OPEN, the disable
        # + re-check converged, and the queue probe reports a LIVE
        # mergeQueueEntry (thread 3834375737's exact finding: the
        # round-14 code only WATCHED it, so the entry could merge
        # after the guard exited, bypassing every assertion).
        surveys = iter([[thread("11", "resolved")]])

        # When: probe 1 reads QUEUED, the dequeuePullRequest mutation
        # exits 0, the re-probe reads ABSENT with the PR still OPEN,
        # and the settling window then sees OPEN + ABSENT at every
        # one of its deadline probes (the 32nd-44th POLL reads).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 44,
            queue_entries=[queued_entry(), None],
            dequeue_rc=0,
        )

        # Then: the dequeue ran through the pinned node-id view and
        # the mutation argv EXACTLY ONCE, the removal was re-verified
        # by the probe and the settling window (never trusted from the
        # mutation's response alone), and the CONVERGED banner reports
        # HOW the entry left — exit 1, no watch progress line, no
        # clean claim, no 10s queue-watch sleep.
        self.assertEqual(code, 1)
        self.assertEqual(argvs.count(NODE_ID_ARGV), 1)
        self.assertEqual(argvs.count(DEQUEUE_ARGV), 1)
        self.assertIn("QUEUE ENTRY DEQUEUED", out)
        self.assertIn("queue-watch probe 1", out)
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn(
            "REMOVED by the dequeuePullRequest mutation at queue-watch "
            "probe 1",
            out,
        )
        self.assertIn("STAYED OPEN through the FULL 60s", out)
        self.assertNotIn("QUEUE WATCH probe=", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 15)
        self.assertEqual(argvs.count(POLL_ARGV), 44)
        self.assertEqual(
            RUNNER.clock.slept, [10.0] * 30 + [5.0] + [5.0] * 12
        )

    def test_queued_dequeue_failure_watches_and_banners_the_attempt(
        self,
    ):
        # Given: the same LIVE entry but the mutation CANNOT remove it
        # (gh exits 1) — the bounded watch (thread 3834073940's
        # monitoring) remains the fallback, and the entry stays live
        # at every probe through the full deadline window. Thread
        # 3834590319 (round 17) refit: the dequeue is now RETRIED
        # while probes stay QUEUED (the round-15 one-shot guard
        # suppressed every later attempt), so all THREE bounded
        # attempts run before the banner.
        surveys = iter([[thread("11", "resolved")]])

        # When: every queue probe reads QUEUED, the three bounded
        # dequeue attempts all fail (probes 1-3), and the deadline
        # expires on the 7th probe.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 31,
            queue_entries=[queued_entry()],
        )

        # Then: exactly THREE dequeue attempts ran (the node-id view
        # and the mutation argv three times each — probes 4-7 stay
        # QUEUED with the budget spent, no ping-pong beyond the bound),
        # the watch carried the full measured window, and the
        # BOTH-CONTINGENCY banner documents the LAST attempt's
        # outcome WITH the bounded attempt count — never a converged
        # or clean claim, never a silent live entry.
        self.assertEqual(code, 1)
        self.assertEqual(argvs.count(NODE_ID_ARGV), 3)
        self.assertEqual(argvs.count(DEQUEUE_ARGV), 3)
        self.assertIn(
            "DEQUEUE FAILED: the dequeuePullRequest mutation for PR "
            "#39 exited 1",
            out,
        )
        self.assertIn(
            "QUEUE WATCH probe=1 elapsed=0s/60s "
            "queue=QUEUED state=OPEN",
            out,
        )
        self.assertIn(
            "was attempted at queue-watch probe 3 and FAILED", out
        )
        self.assertIn("3 bounded attempt(s) in total", out)
        self.assertIn("3834590319", out)
        self.assertIn("CANCEL UNCONFIRMED", out)
        self.assertIn("BOTH contingencies are live", out)
        self.assertIn("the bounded 60s watch expired", out)
        self.assertIn("remove it manually in the web UI", out)
        self.assertNotIn("CANCELLED and verified gone", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 7)
        self.assertEqual(
            RUNNER.clock.slept, [10.0] * 30 + [5.0] + [10.0] * 6
        )


if __name__ == "__main__":
    unittest.main()
