"""pr_guard merge-act round-13 tests (PR #41 round 13).

Thread 3834093635, refit at round 25 (threads 3835145976/3835145981/
3835175506/3835175508): the landed-range discriminator and its
count/patch-id arms are RETIRED — every provenance signal fell to a
reviewer counter-example — so the range count past the fork is now a
DIAGNOSTIC of the fail-closed banner, never a classifier. The PR
head REF is still ensured by a refspec fetch when the banner's
fork-point diagnostic needs it (a fail-closed landing whose parent is
not the base tip), and an unresolvable ref degrades only the
diagnostics. The mismatched-count suite was DELETED as redundant
with the refit round-11/12 fail-closed suites (the suite count drops
by design).

Thread 3834093639: the queue watch is DEADLINE-measured — six probes
spanned only five sleeps, so fast API reads ended the round-12 watch
at ~50s while its banners computed the full 60s window, and a queued
merge landing inside the missing final interval exited unobserved
into the manual banner instead of the revert path. The full-window
expiry (7 probes, 6 sleeps, measured 60s banner) is asserted in the
refit round-5 ambiguous-expire test; the regression here is the
FINAL-INTERVAL LANDING.

No network: the shared fake-gh/fake-clock harness drives the act.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round13_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    FOREIGN_PARENT,
    HEAD,
    MERGE_SHA,
    PR_HEAD_REF,
    MergeHarness,
    landing_probes,
    merged,
    pending,
    queued_entry,
    thread,
)

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000000000f00"
RANGE_OLDEST = "bbbb000000000000000000000000000000000022"
RANGE_MIDDLE = "cccc000000000000000000000000000000000033"
RANGE_NEWEST = "dddd000000000000000000000000000000000044"
FOREIGN_SHA = "eeee0000000000000000000000000000000000f1"
ENSURING_FETCH = f"git fetch origin +{PR_HEAD_REF}:{PR_HEAD_REF}"


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


def clean() -> dict:
    return {"autoMergeRequest": None, "state": "OPEN"}


def landed() -> dict:
    return {"autoMergeRequest": None, "state": "MERGED"}


class ForkDiagnosticRefTests(unittest.TestCase):
    def test_missing_pr_head_ref_is_fetched_before_probing(self):
        # Given: a FAIL-CLOSED single-parent landing (the parent is
        # not the current base tip) whose PR head REF does not resolve
        # locally — the fork-point DIAGNOSTIC reads the ref itself, so
        # the ref is ensured by a refspec fetch before the merge-base
        # probe runs.
        surveys = iter([[thread("11", "resolved")]])
        fetched = {"seen": False}

        def rc_for(argv):
            if argv[:2] == ["git", "fetch"] and argv[-1] == (
                f"+{PR_HEAD_REF}:{PR_HEAD_REF}"
            ):
                fetched["seen"] = True
            return 0

        def rev_rc(rev):
            if rev == PR_HEAD_REF:
                return 0 if fetched["seen"] else 1
            return 1 if rev == f"{MERGE_SHA}^2" else 0

        # When: the fail-closed banner's fork diagnostic finds the
        # ref missing and runs the ensuring REFSPEC fetch, then lists
        # the landed range past the fork.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=[RANGE_OLDEST, RANGE_MIDDLE, RANGE_NEWEST],
            rc_for=rc_for,
            rev_rc_for=rev_rc,
            git_answers=landing_probes(MERGE_SHA, landed=1),
        )

        # Then: the ref was fetched WITH a refspec (so it resolves
        # afterwards), the diagnostic probes ran against the fetched
        # ref, and the landing still FAILED CLOSED by contract — the
        # numbers are banner diagnostics, never a license.
        self.assertEqual(code, 1)
        self.assertIn(ENSURING_FETCH, argvs)
        self.assertIn("git merge-base refs/pull/39/head origin/dev", argvs)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn("counts 1 commit(s)", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)

    def test_unresolvable_pr_head_ref_degrades_the_diagnostics(self):
        # Given: a fail-closed landing whose PR head ref will not
        # resolve even after the ensuring fetch (the remote refuses
        # the ref, or the refspace is unreadable) — the fork point,
        # and with it the landed-range count, cannot be derived at
        # all. The old round-13 code BLOCKED here; the round-25
        # contract already failed closed on the SHAPE (parent is not
        # the tip), so the unresolvable ref only takes the range
        # count out of the banner.
        surveys = iter([[thread("11", "resolved")]])

        def rev_rc(rev):
            if rev == PR_HEAD_REF:
                return 1
            return 1 if rev == f"{MERGE_SHA}^2" else 0

        # When: the ensuring fetch runs but the ref still fails.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=[RANGE_OLDEST, RANGE_MIDDLE, RANGE_NEWEST],
            rev_rc_for=rev_rc,
        )

        # Then: the fail-closed banner still fired on the contract
        # and reports the range count as UNAVAILABLE; no fork probe
        # ran past the unresolvable ref, no revert argv was
        # dispatched, no PR opened.
        self.assertEqual(code, 1)
        self.assertIn(ENSURING_FETCH, argvs)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn("landed-range count is UNAVAILABLE", out)
        self.assertIn("MUST be reverted manually", out)
        self.assertNotIn("git merge-base", " ".join(argvs))
        self.assertNotIn("git rev-list", " ".join(argvs))
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)


class QueueWatchDeadlineTests(unittest.TestCase):
    def test_final_interval_landing_is_observed_and_reverted(self):
        # Given: the queued entry stays live through the whole watch
        # and the merge LANDS inside the watch's FINAL interval — the
        # exact gap of thread 3834093639: the round-12 counted loop
        # (six probes, five sleeps) had already fallen to the manual
        # banner at ~50s when a landing at the 60s mark went
        # unobserved and unreverted.
        surveys = iter([[thread("11", "resolved")]])

        # When: probes 1-6 read OPEN + QUEUED and the SEVENTH probe —
        # the one AT the deadline the old loop never ran — reads
        # MERGED.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 31,
            cancel_reads=[clean() for _ in range(8)] + [landed()],
            queue_entries=[queued_entry()],
        )

        # Then: the full window was slept through (six 10s sleeps),
        # the final-interval MERGED read is OBSERVED, and the landing
        # goes straight through the revert path — never the
        # both-contingency manual banner.
        self.assertEqual(code, 1)
        self.assertIn("QUEUE WATCH probe=6 elapsed=50s/60s", out)
        self.assertIn("LANDED DURING CANCELLATION", out)
        self.assertIn("REVERT PR OPENED", out)
        self.assertNotIn("CANCEL UNCONFIRMED", out)
        self.assertEqual(
            RUNNER.clock.slept, [10.0] * 30 + [5.0] + [10.0] * 6
        )


if __name__ == "__main__":
    unittest.main()
