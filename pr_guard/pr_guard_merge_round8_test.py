"""pr_guard merge-act round-8 tests (PR #41 round 8).

Thread 3833540916: the absent-entry settling watch is measured by
ELAPSED TIME, not probe count — the round-7 form's 12 probes spanned
only 11 sleeps, so fast API reads converged at ~55s while the banner
claimed a FULL 60s watch, and a MERGED flip inside the missing final
interval exited unobserved and unreverted. The watch is now
DEADLINE-based (the quiet watch's thread-3832522300 discipline): a
monotonic deadline plus one FINAL probe at/after it, so instantaneous
reads still span the full window and the last-interval MERGED flip is
caught and reverts.

Thread 3833540921: the revert no longer assumes a two-parent merge
commit — merge queues configured for squash/rebase land single-parent
commits where the unconditional `git revert -m 1` fails or
mis-reverts. The landed commit's parent shape is probed (git
rev-parse --verify <sha>^2); the argv and the revert PR body both
carry the detected shape. No network: the shared fake-gh/fake-clock
harness drives the act; parent_probe_rc selects the landed shape.
PR #41 round 25 (threads 3835145976/3835145981/3835175506/3835175508)
retired the single-parent classifier: the single-parent revert is
automated ONLY when the landing's parent IS the current
<remote>/<base> tip (the harness defaults landing_parent == base_tip,
exactly that shape), and the PR commit list is SNAPSHOTTED pre-dispatch
(thread 3835145981 — the commits argv below is that frozen read, not
a post-merge one).

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round8_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    GUARD_ID,
    GUARD_NO_SIGN,
    HEAD,
    MERGE_SHA,
    POLL_ARGV,
    MergeHarness,
    merged,
    pending,
    thread,
)

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class DeadlineWatchTests(unittest.TestCase):
    def test_fast_reads_still_watch_the_full_window(self):
        # Given: the completion poll timed out still-OPEN, the disable
        # + 5s re-check converged, the queue entry went ABSENT, and
        # every API read returns INSTANTLY (the FakeClock advances only
        # via sleep — the fast-API extreme of thread 3833540916, where
        # the old probe COUNT converged one sleep early).
        surveys = iter([[thread("11", "resolved")]])

        # When: the settling window runs against the instant reads.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), poll_states=[pending()] * 44
        )

        # Then: convergence only AFTER the FULL 60s window — twelve 5s
        # cadence sleeps carry the watch to the deadline and the
        # converging probe is the one AT it (fake t=365 = 300 poll +
        # 5 re-check + 60 window), the banner claims exactly that, and
        # the window ran 13 state reads + 13 entry probes — never
        # probes-minus-one sleeps.
        self.assertEqual(code, 1)
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn("STAYED OPEN through the FULL 60s", out)
        self.assertIn("FINAL probe at/after the deadline", out)
        self.assertIn("ABSENT SETTLE probe=12 elapsed=55s/60s", out)
        self.assertEqual(
            RUNNER.clock.slept, [10.0] * 30 + [5.0] + [5.0] * 12
        )
        self.assertEqual(RUNNER.clock.monotonic(), 365.0)
        self.assertEqual(argvs.count(POLL_ARGV), 44)

    def test_merged_flip_during_the_final_interval_reverts(self):
        # Given: the queue entry drained and the PR stayed OPEN through
        # every cadence probe — but the merge in flight LANDS during
        # the final sleep, exactly the interval the round-7 probe
        # count used to skip (thread 3833540916's regression: the old
        # watch converged at 55s and exited without observing this).
        surveys = iter([[thread("11", "resolved")]])

        # When: the probe AFTER the last cadence sleep (the one at the
        # deadline) reads MERGED.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), poll_states=[pending()] * 43 + [merged()]
        )

        # Then: the final-interval landing goes straight through the
        # landed-during-cancel REVERT path — never a converged-cancel
        # claim, never MERGED CLEAN — after the FULL window of sleeps.
        self.assertEqual(code, 1)
        self.assertIn("ABSENT SETTLE probe=12 elapsed=55s/60s", out)
        self.assertIn("LANDED DURING CANCELLATION", out)
        self.assertIn("REVERT PR OPENED", out)
        self.assertNotIn("CANCELLED and verified gone", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            RUNNER.clock.slept, [10.0] * 30 + [5.0] + [5.0] * 12
        )


class ParentShapeRevertTests(unittest.TestCase):
    def test_two_parent_landing_reverts_with_dash_m_1(self):
        # Given: the request merged a head that moved after the merge
        # request (thread 3832522310) and the landed commit is a
        # genuine TWO-PARENT merge commit (the rev-parse probe exits
        # 0 — the default parent_probe_rc).
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires on the verified base.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), poll_states=[merged(head=PUSHED_HEAD)]
        )

        # Then: the parent probe ran between the checkout and the
        # revert, the revert argv carries -m 1 against the mainline
        # parent, and the revert PR body documents the two-parent
        # path and the probe (thread 3833540921).
        self.assertEqual(code, 1)
        self.assertIn(
            f"git -C {RUNNER.revert_tmp} rev-parse --verify {MERGE_SHA}^2",
            argvs,
        )
        self.assertIn(f"git -C {RUNNER.revert_tmp} {GUARD_ID} {GUARD_NO_SIGN} revert --no-gpg-sign -m 1 --no-edit {MERGE_SHA}", argvs)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn("TWO-PARENT merge commit", create)
        self.assertIn("git revert -m 1 --no-edit", create)
        self.assertIn(f"git rev-parse --verify {MERGE_SHA}^2", create)
        self.assertIn("thread 3833540921", create)

    def test_single_parent_landing_reverts_plain(self):
        # Given: the same head-mismatch landing, but the protected
        # branch's merge queue is configured for squash/rebase — the
        # landed commit is SINGLE-PARENT (the rev-parse probe exits
        # nonzero), where the unconditional -m 1 would fail outright
        # or reverse only the final rebased commit (thread 3833540921).
        surveys = iter([[thread("11", "resolved")]])

        # When: the revert fires with the probe reporting no second
        # parent.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
        )

        # Then: the probe still ran, the revert argv OMITS -m 1 (a
        # plain git revert of the landed commit), and the revert PR
        # body documents the single-parent path and why. Thread
        # 3835145981 (round 25): the commits read visible in the argv
        # is the PRE-DISPATCH frozen snapshot (thread 3834883632's
        # paginated REST read), taken beside the merge-request-time
        # head — never a post-merge re-read of the moved PR — and the
        # round-25 contract automates this landing because its parent
        # IS the current base tip (the harness defaults are equal).
        self.assertEqual(code, 1)
        self.assertIn(
            f"git -C {RUNNER.revert_tmp} rev-parse --verify {MERGE_SHA}^2",
            argvs,
        )
        self.assertIn(f"git -C {RUNNER.revert_tmp} {GUARD_ID} {GUARD_NO_SIGN} revert --no-gpg-sign --no-edit {MERGE_SHA}", argvs)
        self.assertNotIn(f"git -C {RUNNER.revert_tmp} {GUARD_ID} {GUARD_NO_SIGN} revert --no-gpg-sign -m 1 --no-edit {MERGE_SHA}", argvs)
        self.assertIn(
            f"gh api --method GET "
            f"repos/RachaelsDen/UR-lorebook/pulls/39/commits"
            f"?per_page=100&page=1",
            argvs,
        )
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn("SINGLE-PARENT landing whose parent IS the FROZEN", create)
        self.assertIn("plain `git revert --no-edit`", create)
        self.assertIn("unambiguous", create)
        self.assertIn("3833671111", create)


if __name__ == "__main__":
    unittest.main()
