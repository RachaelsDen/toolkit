"""pr_guard merge-act round-30 tests (PR #41 round 30).

Two P1s, one remediation round:

Thread 3835501549 — the pre-existing-merge gate on the CANCEL/INTERRUPT
paths: round 29 snapshotted the pre-dispatch merge identity and
reconciled it in merge_guarded AFTER the completion poll returns, but a
stale invocation on an already-merged PR whose completion reads stay
unreadable to the timeout (or an operator interrupt during the wait)
reaches cancel_pending_merge, whose MERGED verdict went straight
through revert_landed_during_cancel — auto-reverting the HISTORICAL
merge before the late identity check ever ran. The identity now rides
wait_for_merge_completion -> cancel_pending_merge ->
settle_queue_contingency -> the settling watch and the dequeue flow,
and revert_landed_during_cancel gates FIRST: an observed mergeCommit
equal to the pre-dispatch snapshot (or an already-merged pre-dispatch
state) prints the shared PRE-EXISTING MERGE banner and exits nonzero
with NO revert, exactly the reconciliation path's disposition.

Thread 3835501550 — re-enter settlement after an absent re-probe: an
expired settling watch that saw the entry REAPPEAR, followed by a
re-probe reading ABSENT (the entry may be mid-consumption), fell
straight to the timeout banner while the outer deadline was already
spent — the merge could finish after the stale state read with no
revert. The watch now returns a REAPPEARED sentinel, and
settle_queue_contingency re-enters ONE fresh bounded 30s re-settlement
window (bounded total re-entries: 1) instead of enforcing the spent
deadline; a MERGED read anywhere inside it still reverts.

PR #43 round 2 (thread 3835714800) refit: the identity arm's
open-record sha-equal shape is superseded — an OPEN PR's REST
merge_commit_sha is GitHub's synthetic TEST merge commit, never
pre-merged evidence, so the equal-sha-on-open-record test now pins
the ORDINARY revert (the gate rides the merged-record shape alone;
see pr_guard_merge_round33 and the round-29 refit).

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round30_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    DEQUEUE_ARGV,
    GRAPHQL_ARGV,
    HEAD,
    MERGE_SHA,
    NODE_ID_ARGV,
    MergeHarness,
    merged,
    pending,
    queued_entry,
    thread,
)

RUNNER = MergeHarness()


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


def pre_merged_record():
    # Thread 3835501549: the REST shape of an ALREADY-MERGED PR (the
    # round-29 fixture) — head/base never move post-merge, so the act's
    # validation passes on a stale retry.
    return {
        "head": {"sha": HEAD},
        "base": {"ref": "dev"},
        "state": "closed",
        "merged": True,
        "merge_commit_sha": MERGE_SHA,
    }


def open_record(merge_commit_sha: str = ""):
    return {
        "head": {"sha": HEAD},
        "base": {"ref": "dev"},
        "state": "open",
        "merged": False,
        "merge_commit_sha": merge_commit_sha,
    }


MERGED_CANCEL_READ = {"autoMergeRequest": None, "state": "MERGED"}


class PreExistingCancelGateTests(unittest.TestCase):
    def test_stale_invocation_timeout_cancel_banners_without_reverting(
        self,
    ):
        # Given: the operator retries a stale invocation for a PR that
        # is ALREADY MERGED (thread 3835501549) — the dispatch exits
        # nonzero, and the reconcile poll's completion reads stay
        # UNREADABLE to the bounded window's end (still-pending every
        # attempt), so the timeout hands the HISTORICAL MERGED state to
        # the cancel path — the exact bypass of round-29's late check.
        surveys = iter([[thread("11", "resolved")]])

        # When: the cancel verification observes MERGED and the landed
        # sha read resolves to the historical merge.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([pre_merged_record()]),
            poll_states=[pending()] * 11 + [merged()],
            merge_rc=1,
            cancel_reads=[MERGED_CANCEL_READ],
        )

        # Then: the cancel-path PRE-EXISTING gate fires BEFORE any
        # landed-during-cancel claim or revert — the shared banner (the
        # state-flags identity arm), a nonzero exit, and NO revert
        # plumbing at all.
        self.assertEqual(code, 1)
        self.assertIn("PRE-EXISTING MERGE", out)
        self.assertIn("thread 3835501549", out)
        self.assertIn("thread 3835450367", out)
        self.assertIn("state=MERGED before the dispatch", out)
        self.assertNotIn("LANDED DURING CANCELLATION", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)

    def test_interrupt_variant_banners_without_reverting(self):
        # Given: the same stale invocation, but the operator interrupts
        # the completion wait (thread 3835501549's second arm) — the
        # reconciliation cancel runs before the original exception is
        # re-raised, and ITS MERGED verdict is the historical state.
        surveys = iter([[thread("11", "resolved")]])

        # When: KeyboardInterrupt raises at the third completion poll
        # and the reconciliation cancel then observes MERGED.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([pre_merged_record()]),
            poll_states=[
                pending(), pending(), KeyboardInterrupt(), merged()
            ],
            merge_rc=1,
            cancel_reads=[MERGED_CANCEL_READ],
        )

        # Then: the SAME gate disposition on the interrupt path — the
        # banner prints, NO revert runs, and the ORIGINAL interrupt
        # still propagates (nonzero exit through the re-raise).
        self.assertIsNone(code)
        self.assertIsInstance(RUNNER.raised, KeyboardInterrupt)
        self.assertIn("INTERRUPTED DURING THE COMPLETION WAIT", out)
        self.assertIn("PRE-EXISTING MERGE", out)
        self.assertIn("thread 3835501549", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)

    def test_cancel_open_record_test_merge_sha_still_reverts(self):
        # Given: the pre-dispatch REST record is a genuinely OPEN PR
        # whose merge_commit_sha names GitHub's synthetic TEST merge
        # commit — thread 3835714800 (PR #43 round 2) refit of the
        # round-30 identity arm: the old test treated an equal sha on
        # an open record as pre-existing evidence, but the dispatched
        # merge can land REUSING that commit object, so the sha alone
        # can never attribute a landing to the past.
        surveys = iter([[thread("11", "resolved")]])

        # When: the completion poll times out still-pending (the
        # dispatched request never settles) and the cancel verification
        # observes MERGED with the SAME sha the open record exposed.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record(MERGE_SHA)]),
            poll_states=[pending()] * 31 + [merged()],
            cancel_reads=[MERGED_CANCEL_READ],
        )

        # Then: NOT pre-existing — the identity snapshot trusts only
        # the merged flags, so the cancel path treats the landing as
        # this invocation's own and runs the ORDINARY revert (the
        # pre-existing gate survives through the merged-record shape
        # alone).
        self.assertEqual(code, 1)
        self.assertIn("LANDED DURING CANCELLATION", out)
        self.assertIn("REVERT PR OPENED", out)
        self.assertNotIn("PRE-EXISTING MERGE", out)

    def test_new_merge_commit_on_cancel_still_reverts(self):
        # Given: a genuinely OPEN pre-dispatch snapshot whose sha
        # DIFFERS from the observed landing — the dispatch WAS accepted
        # and landed while the poll/cancel was in flight (the ordinary
        # landed-during-cancel scenario the gate must not suppress).
        surveys = iter([[thread("11", "resolved")]])

        # When: the cancel verification observes MERGED with a NEW
        # mergeCommit (never the snapshot's own).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("a" * 40)]),
            poll_states=[pending()] * 31 + [merged()],
            cancel_reads=[MERGED_CANCEL_READ],
        )

        # Then: the ORDINARY revert path — the landed-during-cancel
        # banner, the revert argv, the revert PR — never the
        # pre-existing banner.
        self.assertEqual(code, 1)
        self.assertIn("LANDED DURING CANCELLATION", out)
        self.assertIn("REVERT PR OPENED", out)
        self.assertNotIn("PRE-EXISTING MERGE", out)


class AbsentResettleTests(unittest.TestCase):
    def test_reappearance_absent_reprobe_enters_resettle_then_merged(
        self,
    ):
        # Given: the completion poll timed out still-OPEN, the cancel
        # converged into the settlement, and the settling watch held
        # OPEN + ABSENT through probes 1-12 — but the entry REAPPEARS
        # on the window's FINAL probe, exactly when the outer
        # queue-watch deadline is spent, and the round-29 re-probe then
        # reads it ABSENT again (thread 3835501550: the entry may be
        # mid-consumption — removed to merge right now).
        surveys = iter([[thread("11", "resolved")]])

        # When: the reappearance->ABSENT re-probe re-enters the bounded
        # 30s re-settlement window, and its THIRD probe reads MERGED
        # (the mid-consumption merge completing).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 46 + [merged()],
            queue_entries=[None] * 13
            + [queued_entry(), None, None, None],
        )

        # Then: the RE-SETTLE is announced, the re-settlement window
        # RUNS (two of its probes read OPEN + ABSENT first), and the
        # MERGED flip goes straight through the revert path — never a
        # timeout banner over a landing in progress, and no dequeue
        # ever dispatched (no QUEUED observation followed it).
        self.assertEqual(code, 1)
        self.assertIn("QUEUE ENTRY REAPPEARED at settling probe 13", out)
        self.assertIn("QUEUE RE-PROBE", out)
        self.assertIn("RE-SETTLING", out)
        self.assertIn("thread 3835501550", out)
        self.assertIn("30s settlement window", out)
        self.assertIn("LANDED DURING CANCELLATION", out)
        self.assertIn("REVERT PR OPENED", out)
        self.assertNotIn("CANCEL UNCONFIRMED", out)
        self.assertEqual(argvs.count(NODE_ID_ARGV), 0)
        self.assertEqual(argvs.count(DEQUEUE_ARGV), 0)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 17)
        self.assertEqual(
            RUNNER.clock.slept,
            [10.0] * 30 + [5.0] + [5.0] * 12 + [5.0] * 2,
        )

    def test_second_expiry_converges_with_reentry_noted(self):
        # Given: the same reappearance->ABSENT re-probe at the spent
        # outer deadline, but the entry truly drained — the OPEN stays
        # OPEN and the entry ABSENT through the ENTIRE re-settlement
        # window (the fresh evidence the re-entry exists to gather).
        surveys = iter([[thread("11", "resolved")]])

        # When: the re-settlement window runs its full bounded span
        # with OPEN + ABSENT at every probe.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 51,
            queue_entries=[None] * 13
            + [queued_entry()]
            + [None] * 8,
        )

        # Then: the convergence banner names the window ACTUALLY run
        # (FULL 30s, never the ordinary 60s) and NOTES the bounded
        # re-entry that preceded it — the honest evidence trail.
        self.assertEqual(code, 1)
        self.assertIn("RE-SETTLING", out)
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn("STAYED OPEN through the FULL 30s", out)
        self.assertIn(
            "re-settlement window (thread 3835501550)", out
        )
        self.assertNotIn("CANCEL UNCONFIRMED", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 22)
        self.assertEqual(
            RUNNER.clock.slept,
            [10.0] * 30 + [5.0] + [5.0] * 12 + [5.0] * 6,
        )

    def test_reentry_is_bounded_once(self):
        # Given: the bounded re-settlement budget is ONE (thread
        # 3835501550) — an automation that keeps re-enqueueing the
        # entry must not ping-pong the guard through endless fresh
        # windows.
        surveys = iter([[thread("11", "resolved")]])

        # When: the re-settlement window's OWN final probe sees the
        # entry REAPPEAR again, and the following re-probe reads ABSENT
        # once more.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 51,
            queue_entries=[None] * 13
            + [queued_entry()]
            + [None] * 7
            + [queued_entry(), None],
        )

        # Then: exactly ONE re-settlement ever ran, and the spent
        # deadline is enforced with the timeout banner — which REPORTS
        # the used re-entry as part of its honest residual.
        self.assertEqual(code, 1)
        self.assertEqual(out.count("RE-SETTLING"), 1)
        self.assertIn("QUEUE ENTRY REAPPEARED at settling probe 7", out)
        self.assertIn("CANCEL UNCONFIRMED", out)
        self.assertIn(
            "1 bounded 30s re-settlement window (thread 3835501550) "
            "was entered after the reappearance->ABSENT re-probe and "
            "ALSO expired without a verdict",
            out,
        )
        self.assertNotIn("CANCELLED and verified gone", out)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 23)
        self.assertEqual(
            RUNNER.clock.slept,
            [10.0] * 30 + [5.0] + [5.0] * 12 + [5.0] * 6,
        )


if __name__ == "__main__":
    unittest.main()
