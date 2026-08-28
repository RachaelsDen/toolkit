"""pr_guard merge-act round-7 tests (PR #41 round 7).

Thread 3833360201: the post-ABSENT settling window — the queue entry
can vanish while the separately cached PR state still reads OPEN
(merge in flight), so ONE immediate recheck proves nothing. The
ABSENT branch therefore watches a bounded settling window: MERGED at
any probe reverts, a REAPPEARING entry resumes the ordinary queue
watch, and only OPEN persisting through the window with the entry
ABSENT at every probe converges (the persistent-OPEN convergence
itself is pinned by the updated round-5/round-6 fixtures; the
MID-window scenarios live here). Thread 3833540916 (PR #41 round 8)
later made the window DEADLINE-based with a final probe at/after it
(the full-window semantics live in pr_guard_merge_round8_test); the
fixtures here feed the deadline watch's reads. Thread 3833360219: an
interrupt during the advertised multi-minute completion wait runs the
bounded cancel path BEFORE the original exception propagates; a second
interrupt during that cancellation prints the both-contingency manual
instructions.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round7_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    GRAPHQL_ARGV,
    HEAD,
    POLL_ARGV,
    MergeHarness,
    merged,
    pending,
    queued_entry,
    revert_argv,
    thread,
)

RUNNER = MergeHarness()


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class AbsentSettlementTests(unittest.TestCase):
    def test_merge_landing_mid_window_reverts(self):
        # Given: the completion poll timed out still-OPEN, the disable
        # + 5s re-check converged, and the queue entry went ABSENT —
        # but the merge is IN FLIGHT: the cached PR state keeps
        # reading OPEN past the first settling probes (thread
        # 3833360201's exact scenario) and only flips to MERGED at the
        # third settling probe.
        surveys = iter([[thread("11", "resolved")]])

        # When: settling probes 1-2 read OPEN + ABSENT (5s sleeps
        # between) and probe 3's state read observes MERGED.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 33 + [merged()],
        )

        # Then: the mid-window landing goes straight through the
        # landed-during-cancel REVERT path — never a converged-cancel
        # claim, never MERGED CLEAN — with 3 GraphQL probes (the
        # outer one + the window's first two entry re-probes; the
        # MERGED probe needs no entry read), two 5s settling sleeps
        # past the 5s cancel re-check, and the revert argv on the
        # landed base.
        self.assertEqual(code, 1)
        self.assertIn("ABSENT SETTLE probe=1 elapsed=0s/60s", out)
        self.assertIn("ABSENT SETTLE probe=2 elapsed=5s/60s", out)
        self.assertIn("LANDED DURING CANCELLATION", out)
        self.assertIn("REVERT PR OPENED", out)
        self.assertNotIn("CANCELLED and verified gone", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 3)
        tail = RUNNER.revert_tail(argvs)
        expected = revert_argv("dev", RUNNER.revert_tmp)
        self.assertEqual(tail[:6], expected[:6])
        self.assertTrue(tail[5].startswith(expected[5]))
        self.assertEqual(
            RUNNER.clock.slept, [10.0] * 30 + [5.0] + [5.0] * 2
        )

    def test_entry_reappearing_mid_window_resumes_the_queue_watch(self):
        # Given: the queue entry reads ABSENT, but a re-queue (or the
        # first probe's own race) makes it REAPPEAR at the second
        # settling probe — thread 3833360201's "entry reappears → keep
        # the earlier semantics" branch: the ABSENT observation was
        # not durable, so the ordinary QUEUED watch resumes.
        surveys = iter([[thread("11", "resolved")]])

        # When: the window's first probe reads OPEN + ABSENT, its
        # second reads OPEN + QUEUED (reappeared), and the resumed
        # outer watch's next attempt settles OPEN + ABSENT through a
        # full deadline window. Thread 3835450362 (PR #41 round 29):
        # the resume is gated by the RE-PROBE — the settling watch's
        # None consumed part of the window, so the FRESH state/queue
        # pair (not the stale pre-watch ABSENT) feeds the branch.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 46,
            queue_entries=[None, None, queued_entry(), None],
        )

        # Then: the reappearance is announced, the round-29 RE-PROBE
        # reports the fresh post-window pair, the outer QUEUE WATCH
        # progress prints with its 10s sleep, and the convergence
        # (when it comes) is the SECOND outer attempt's — the earlier
        # semantics applied to the reappeared entry, never a converged
        # claim over a live one.
        self.assertEqual(code, 1)
        self.assertIn(
            "QUEUE ENTRY REAPPEARED at settling probe 2", out
        )
        self.assertIn("resuming the queue watch", out)
        self.assertIn("QUEUE RE-PROBE", out)
        self.assertIn("thread 3835450362", out)
        self.assertIn(
            "QUEUE WATCH probe=1 elapsed=5s/60s "
            "queue=ABSENT state=OPEN", out
        )
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn("queue-watch probe 2", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 18)
        self.assertEqual(
            RUNNER.clock.slept,
            [10.0] * 30 + [5.0] + [5.0] + [10.0] + [5.0] * 12,
        )


class InterruptReconciliationTests(unittest.TestCase):
    def test_interrupt_mid_wait_dispatches_disable_then_propagates(self):
        # Given: the merge request is dispatched and the completion
        # wait is polling — the operator hits Ctrl-C at the third poll
        # read (thread 3833360219: the OLD code exited here, leaving
        # the pending request to land unbackstopped).
        surveys = iter([[thread("11", "resolved")]])

        # When: KeyboardInterrupt raises inside the third completion
        # poll, and the reconciliation cancel converges (default clean
        # cancel reads; the settling window sees OPEN + ABSENT at all
        # its deadline-measured probes).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending(), pending(), KeyboardInterrupt()]
            + [pending()] * 13,
        )

        # Then: the interrupt banner printed, --disable-auto WAS
        # dispatched before the exit, the converged-cancel evidence
        # printed with the settling window, and the ORIGINAL
        # KeyboardInterrupt propagated (code None — the act exits
        # nonzero through the re-raise), never MERGED CLEAN.
        self.assertIsNone(code)
        self.assertIsInstance(RUNNER.raised, KeyboardInterrupt)
        self.assertIn("INTERRUPTED DURING THE COMPLETION WAIT", out)
        self.assertIn("thread 3833360219", out)
        self.assertIn(
            "gh pr merge 39 --disable-auto -R RachaelsDen/UR-lorebook",
            argvs,
        )
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn("STAYED OPEN through the FULL 60s", out)
        self.assertNotIn("MERGED CLEAN:", out)

    def test_second_interrupt_during_cancel_prints_manual_instructions(
        self,
    ):
        # Given: the first interrupt arrives mid-wait and the
        # reconciliation cancel is running its settling window when a
        # SECOND interrupt lands (thread 3833360219's both-contingency
        # branch — the reconciliation itself is now unfinished).
        surveys = iter([[thread("11", "resolved")]])

        # When: the completion wait raises at the third poll, and the
        # settling window's second state read raises again.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending(), pending(), KeyboardInterrupt()]
            + [pending(), KeyboardInterrupt()],
        )

        # Then: the disable was dispatched, the BOTH-CONTINGENCY
        # manual instructions printed (naming PR #39 and the web-UI
        # dequeue) instead of a silent death, and the ORIGINAL
        # interrupt still propagated (nonzero exit).
        self.assertIsNone(code)
        self.assertIsInstance(RUNNER.raised, KeyboardInterrupt)
        self.assertIn("INTERRUPTED DURING THE COMPLETION WAIT", out)
        self.assertIn(
            "THE INTERRUPT ARRIVED DURING THE CANCELLATION TOO", out
        )
        self.assertIn(
            "gh pr merge 39 --disable-auto -R RachaelsDen/UR-lorebook",
            argvs,
        )
        self.assertIn("CANCEL UNCONFIRMED", out)
        self.assertIn("BOTH contingencies are live", out)
        self.assertIn("PR #39", out)
        self.assertIn("DO NOT assume MERGED CLEAN", out)
        self.assertNotIn("CANCELLED and verified gone", out)
        self.assertNotIn("MERGED CLEAN:", out)


if __name__ == "__main__":
    unittest.main()
