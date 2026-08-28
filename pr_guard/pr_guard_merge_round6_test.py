"""pr_guard merge-act round-6 tests (PR #41 round 6).

Thread 3833251675: a queued PR that dequeues-and-MERGES between the
cancel's OPEN read and the GraphQL queue probe is ABSENT on the probe
BECAUSE it merged — the stale OPEN read used to declare the pending
request cancelled while it had actually landed, skipping every landed
assertion and the revert watch. The convergence verdict now RE-READS
the PR state (the shared read_landed_state) after observing the queue
removal: MERGED goes straight through the revert path; still OPEN
settles the cancellation; anything else keeps watching. PR #41 round
7 (thread 3833360201) extended the still-OPEN branch from ONE re-read
into the 12-probe settling window (see pr_guard_merge_round7_test for
the mid-window scenarios); the fixtures here feed the window's reads.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round6_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    GRAPHQL_ARGV,
    HEAD,
    POLL_ARGV,
    MergeHarness,
    merged,
    pending,
    revert_argv,
    thread,
)

RUNNER = MergeHarness()


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class MidReadMergeRecheckTests(unittest.TestCase):
    def test_entry_vanishing_because_the_pr_merged_reverts(self):
        # Given: the completion poll timed out still-OPEN, the disable
        # + 5s re-check converged, and the queued PR dequeues-and-
        # MERGES in the gap between the settlement's OPEN read and the
        # GraphQL probe (thread 3833251675) — the entry is ABSENT on
        # the probe BECAUSE it merged.
        surveys = iter([[thread("11", "resolved")]])

        # When: the probe reads ABSENT but the post-ABSENT re-read
        # observes state=MERGED (the 32nd POLL read).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), poll_states=[pending()] * 31 + [merged()]
        )

        # Then: the landing goes straight through the
        # landed-during-cancel REVERT path — NEVER a cancelled claim or
        # a clean one — with the merge-commit fetch and revert argv on
        # the landed base, exit 1, exactly one queue probe, and no
        # queue-watch sleeps (the recheck caught it immediately).
        self.assertEqual(code, 1)
        self.assertIn("LANDED DURING CANCELLATION", out)
        self.assertIn("REVERT PR OPENED", out)
        self.assertNotIn("CANCELLED and verified gone", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 1)
        tail = RUNNER.revert_tail(argvs)
        expected = revert_argv("dev", RUNNER.revert_tmp)
        self.assertEqual(tail[:6], expected[:6])
        self.assertTrue(tail[5].startswith(expected[5]))
        self.assertEqual(RUNNER.clock.slept, [10.0] * 30 + [5.0])

    def test_recheck_still_open_after_absent_settles_the_cancel(self):
        # Given: the queue entry truly drained (a human removed it in
        # the web UI) and the PR is still open — the re-read must
        # confirm it, not assume it (thread 3833251675), and thread
        # 3833360201 (PR #41 round 7) demands the OPEN then SURVIVE
        # the full settling window before any converged claim — with
        # thread 3833540916 (round 8) measuring that window by
        # DEADLINE (13 probes, the last at/after the 60s mark).
        surveys = iter([[thread("11", "resolved")]])

        # When: the probe reads ABSENT and the settling window sees
        # OPEN + ABSENT at every one of its probes (the 32nd-44th
        # POLL reads).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), poll_states=[pending()] * 44
        )

        # Then: the converged-cancel banner names the RE-READ and the
        # settling window as its evidence, exit 1, the outer probe
        # plus the window's 13 entry re-probes, no revert argv.
        self.assertEqual(code, 1)
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn("RE-READ STILL OPEN after the ABSENT probe", out)
        self.assertIn("STAYED OPEN through the FULL 60s", out)
        self.assertIn("thread 3833360201", out)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 14)
        self.assertEqual(argvs.count(POLL_ARGV), 44)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            RUNNER.clock.slept, [10.0] * 30 + [5.0] + [5.0] * 12
        )

    def test_recheck_reading_an_unexpected_state_keeps_watching(self):
        # Given: the settling window's first state read returns
        # neither MERGED nor OPEN (an unreadable or unexpected state)
        # — the settlement must NOT declare convergence on weaker
        # evidence (thread 3833251675's fail-closed branch, carried
        # into the window by thread 3833360201).
        surveys = iter([[thread("11", "resolved")]])

        # When: the window's first probe reads CLOSED, the outer watch
        # resumes (10s sleep) — thread 3835450362 (PR #41 round 29)
        # re-probes the state/queue pair after the window's None — and
        # attempt 2's window settles on OPEN + ABSENT through its
        # deadline-measured probes (thread 3833540916).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 31
            + [
                {"state": "CLOSED", "mergeCommit": None,
                 "baseRefName": "dev", "headRefOid": "x"}
            ]
            + [pending()] * 13,
            queue_entries=[None, None],
        )

        # Then: the first window did NOT converge (the QUEUE WATCH
        # progress printed instead, fed by the round-29 RE-PROBE's
        # fresh values), one 10s watch sleep ran, and the SECOND
        # attempt's settling window completed the convergence.
        self.assertEqual(code, 1)
        self.assertIn(
            "QUEUE WATCH probe=1 elapsed=0s/60s "
            "queue=ABSENT state=OPEN", out
        )
        self.assertIn("QUEUE RE-PROBE", out)
        self.assertIn("thread 3835450362", out)
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn("queue-watch probe 2", out)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 16)
        self.assertEqual(
            RUNNER.clock.slept,
            [10.0] * 30 + [5.0, 10.0] + [5.0] * 12,
        )


if __name__ == "__main__":
    unittest.main()
