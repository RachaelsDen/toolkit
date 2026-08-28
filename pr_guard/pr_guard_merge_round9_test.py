"""pr_guard merge-act round-9 tests (PR #41 round 9, refit round 25).

Thread 3833671111: a single-parent landing is not always ONE commit —
under a rebase queue with a multi-commit PR, mergeCommit is only the
FINAL rebased commit while every earlier PR commit also landed on the
base, so reverting just the tip leaves the rest of the PR in place.
PR #41 round 25 (threads 3835145976/3835145981/3835175506/3835175508)
RETIRED the squash-vs-rebase classifier that grew from that finding —
every provenance heuristic fell to a reviewer counter-example — so the
single-parent revert is now automated ONLY for the unambiguous shape
(the landing's parent IS the current <remote>/<base> tip, harness
defaults landing_parent == base_tip) and EVERY other single-parent
landing fails closed to the manual banner carrying the frozen-snapshot
diagnostics. These suites pin both sides: the automated plain revert,
and the multi-commit landing that used to plan a RANGE revert and now
fails closed by contract.

Thread 3833671126: the merge DISPATCH itself is inside the
reconciliation envelope — an exception while `gh pr merge` is
returning (Ctrl-C, a subprocess error) used to exit before any
polling or cancellation although GitHub may already have accepted the
request. The dispatch exception is treated as the same UNKNOWN
outcome as a nonzero exit: the bounded reconcile poll runs (MERGED
continues the ordinary post-merge path; anything else runs the cancel
disposal) and the ORIGINAL exception re-raises after the disposal.
No network: the shared fake-gh/fake-clock harness drives the act;
merge_exc raises from the dispatch and pr_commits feeds the frozen
pre-dispatch commit-list snapshot.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round9_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    FOREIGN_PARENT,
    GUARD_ID,
    GUARD_NO_SIGN,
    HEAD,
    MERGE_ARGV,
    MERGE_SHA,
    POLL_ARGV,
    REPO_FLAG,
    MergeHarness,
    merged,
    pending,
    thread,
)

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"
PR_COMMIT = "aaaa000000000000000000000000000000000011"
RANGE_OLDEST = "bbbb000000000000000000000000000000000022"
RANGE_MIDDLE = "cccc000000000000000000000000000000000033"
RANGE_NEWEST = "dddd000000000000000000000000000000000044"
# Thread 3835145981 (round 21 pagination, round 25 freeze): the
# PRE-DISPATCH commit-list snapshot read (REST pulls/<n>/commits
# pages), taken before `gh pr merge` leaves and frozen for every
# later revert path.
COMMITS_ARGV = (
    f"gh api --method GET repos/RachaelsDen/UR-lorebook/pulls/39"
    f"/commits?per_page=100&page=1"
)
DISABLE_ARGV = f"gh pr merge 39 --disable-auto {REPO_FLAG}"


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class DispatchExceptionTests(unittest.TestCase):
    def test_dispatch_raising_runs_the_poll_and_cancels_on_open(self):
        # Given: the closing survey is clean and the dispatch goes out
        # — but Ctrl-C arrives while `gh pr merge` is returning
        # (thread 3833671126: the OLD code exited here, before any
        # polling or cancellation, leaving an accepted request to land
        # unbackstopped), and the PR then reads OPEN forever.
        surveys = iter([[thread("11", "resolved")]])

        # When: the dispatch raises KeyboardInterrupt and every
        # reconcile/settling read reports the still-pending PR.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 24,
            merge_exc=KeyboardInterrupt("ctrl-c during dispatch"),
        )

        # Then: the dispatch banner printed, the bounded reconcile
        # poll RAN (10 attempts + final check) and drained into the
        # cancel disposal — --disable-auto dispatched, the converged
        # cancel evidence printed — and the ORIGINAL KeyboardInterrupt
        # propagated after the disposal (code None = nonzero exit),
        # never MERGED CLEAN.
        self.assertIsNone(code)
        self.assertIsInstance(RUNNER.raised, KeyboardInterrupt)
        self.assertIn("MERGE DISPATCH RAISED (KeyboardInterrupt", out)
        self.assertIn("thread 3833671126", out)
        self.assertIn(MERGE_ARGV, argvs)
        self.assertIn(DISABLE_ARGV, argvs)
        self.assertEqual(argvs.count(POLL_ARGV), 24)
        self.assertIn("CANCELLED and verified gone", out)
        self.assertNotIn("MERGED CLEAN:", out)

    def test_dispatch_raising_with_landed_merge_banners_ambiguous(self):
        # Given: the dispatch raised — but GitHub HAD already accepted
        # the request, so the reconcile poll observes the completion
        # (thread 3833671126's "MERGED → post-merge path" branch).
        # Repinned at round 8 (thread 3836092104): the poll must
        # OBSERVE the transition — a first-read MERGED is the
        # ambiguous no-transition shape. Repinned again at round 9
        # (thread 3836149500): the crediting OPEN read is
        # POST-BASELINE (the baseline poll reads OPEN and a LATER
        # poll reads it still-OPEN before the MERGED read). Repinned
        # once more at round 10 (thread 3836217630): the baseline is
        # the first LIVE read (>= one real poll interval past the
        # dispatch), so the poll reads OPEN three times — the
        # pre-interval cache-suspect read, the live baseline, the
        # post-baseline credit — before the landing.
        surveys = iter(
            [[thread("11", "resolved")], [thread("11", "resolved")]]
        )

        # When: the dispatch raises and the reconcile poll reads the
        # still-OPEN PR three times before the completed merge.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending(), pending(), pending(), merged()],
            merge_exc=KeyboardInterrupt("ctrl-c during dispatch"),
        )

        # Then: the dispatch banner printed, and — repinned at
        # round 17 (thread 3836600782): the observed OPEN -> MERGED
        # sequence attributes NOTHING (no client-side observation
        # can; the chain proved every between-reads signal
        # reproducible by ordered cache snapshots of one historical
        # timeline) — the landing reports the uniform AMBIGUOUS
        # manual banner: NO assertions, NO quiet watch, NO revert,
        # exit 1 (the raised dispatch is satisfied by the nonzero
        # disposition, never re-raised over it).
        self.assertEqual(code, 1)
        self.assertIsNone(RUNNER.raised)
        self.assertIn("MERGE DISPATCH RAISED (KeyboardInterrupt", out)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("QUIET PERIOD cycle=1", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(argvs.count(POLL_ARGV), 4)
        self.assertNotIn(DISABLE_ARGV, argvs)
        self.assertNotIn("REVERT PR OPENED", out)


class SingleParentContractTests(unittest.TestCase):
    def test_parent_is_base_tip_reverts_the_landed_commit(self):
        # Given: the merge queue is configured for SQUASH — the landed
        # commit is single-parent — and the landing sits DIRECTLY on
        # the current base tip: the parent probe and the base-tip
        # probe answer the SAME sha (the harness defaults), the ONE
        # unambiguous single-parent shape of the round-25 contract.
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires with a single-commit
        # PR whose oid differs from the landed squash commit.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            pr_commits=[PR_COMMIT],
        )

        # Then: the two-case contract's probes ran (the landing's
        # parent, then the base tip), the revert argv is the plain
        # single revert of the LANDED commit (not the PR's pre-squash
        # oid), and the body documents the unambiguous-shape path.
        self.assertEqual(code, 1)
        self.assertIn(f"git rev-parse --verify {MERGE_SHA}^", argvs)
        self.assertIn("git rev-parse --verify origin/dev", argvs)
        self.assertIn(f"git -C {RUNNER.revert_tmp} {GUARD_ID} {GUARD_NO_SIGN} revert --no-gpg-sign --no-edit {MERGE_SHA}", argvs)
        self.assertNotIn(f"git -C {RUNNER.revert_tmp} {GUARD_NO_SIGN} revert --no-gpg-sign --no-edit {PR_COMMIT}", argvs)
        self.assertNotIn("^..", " ".join(argvs))
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn("SINGLE-PARENT landing whose parent IS the FROZEN", create)
        self.assertIn("plain `git revert --no-edit`", create)
        self.assertIn("3835145976", create)
        self.assertIn("REVERT PR OPENED", out)

    def test_multi_commit_landing_fails_closed_by_contract(self):
        # Given: the merge queue REBASED a THREE-commit PR onto a
        # foreign queue advancement — mergeCommit is only the FINAL
        # rebased commit (thread 3833671111's finding: reverting it
        # alone would leave the two earlier PR commits on the
        # protected base), so the landing's parent is a PR commit,
        # NOT the current base tip (landing_parent answers a foreign
        # sha). Rounds 9-24 planned an automated RANGE revert here;
        # thread 3835175506's counter-example (a foreign cherry-pick
        # beside a marker-free custom-subject squash satisfying every
        # provenance rule) proved that classifier spoofable, and round
        # 25 fails the shape closed BY CONTRACT.
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires on the multi-commit
        # single-parent landing whose parent is not the base tip.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=[RANGE_OLDEST, RANGE_MIDDLE, RANGE_NEWEST],
        )

        # Then: NO revert argv was ever dispatched and NO revert PR
        # opened — the fail-closed banner states the contract (neither
        # automated shape), carries the diagnostics (the landing's
        # parent beside the base tip, the landed-range count past the
        # fork, the frozen pre-dispatch commit count), and names the
        # manual obligation with the counter-example chain.
        self.assertEqual(code, 1)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn(f"{MERGE_SHA[:12]}", out)
        self.assertIn("SINGLE-PARENT", out)
        self.assertIn("NEITHER", out)
        self.assertIn(f"{FOREIGN_PARENT[:12]}", out)
        self.assertIn("the landed range past the fork point", out)
        self.assertIn("counts 1 commit(s)", out)
        self.assertIn("FROZEN pre-dispatch commit snapshot counts 3 commit(s)", out)
        self.assertIn("MUST be reverted manually", out)
        self.assertIn("3835175506", out)
        self.assertIn("3835175508", out)
        self.assertIn("3835145976", out)


if __name__ == "__main__":
    unittest.main()
