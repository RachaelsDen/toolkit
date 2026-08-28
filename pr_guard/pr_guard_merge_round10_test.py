"""pr_guard merge-act round-10 tests (PR #41 round 10, refit 25).

Thread 3833762316's fetch-before-fallback obligation was RETIRED at
round 25 (threads 3835145976/3835145981/3835175506/3835175508): the
per-commit fallback and the range arms it served died with the
provenance classifier, and the two-case single-parent plan probes
only the landing's parent and the base tip — both guaranteed local by
the pre-revert base fetch — so the FetchBeforeFallbackTests were
deleted with the arms (the suite count drops by design).

Thread 3833762325: every git operation in the revert path (base
fetch, revert-branch checkout, push) is pinned to the CANONICAL
remote resolved from `git remote -v` — from a fork checkout the
revert never fetches from or pushes to the fork while the surveys
target RachaelsDen/UR-lorebook; no canonical remote is a hard block.

Thread 3833762320: each settling-watch probe ALSO reads
autoMergeRequest — a re-enabled request re-dispatches --disable-auto
(bounded to 2 re-disables, window extended per re-disable); a
persistent one ends in the both-contingency banner, never the
converged-cancel claim.

No network: the shared fake-gh/fake-clock harness drives the act;
rev_rc_for makes objects unavailable before/after a fetch and
remote_v selects the fork/canonical checkout shapes.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round10_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    CANONICAL_REMOTE_V,
    HEAD,
    MERGE_SHA,
    MergeHarness,
    merged,
    pending,
    thread,
)

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000000000f00"
FORK_REMOTE_V = (
    "origin\tgit@github.com:contributor/UR-lorebook.git (fetch)\n"
    "origin\tgit@github.com:contributor/UR-lorebook.git (push)\n"
    "upstream\thttps://github.com/RachaelsDen/UR-lorebook.git (fetch)\n"
    "upstream\thttps://github.com/RachaelsDen/UR-lorebook.git (push)\n"
)
FORK_ONLY_REMOTE_V = (
    "origin\tgit@github.com:contributor/UR-lorebook.git (fetch)\n"
    "origin\tgit@github.com:contributor/UR-lorebook.git (push)\n"
)


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


def clean():
    return {"autoMergeRequest": None, "state": "OPEN"}


def auto_enabled():
    return {"autoMergeRequest": {"mergeMethod": "MERGE"}, "state": "OPEN"}


class CanonicalRemoteTests(unittest.TestCase):
    def test_fork_checkout_pins_git_ops_to_the_canonical_remote(self):
        # Given: the guard runs from a FORK checkout — origin is the
        # contributor's fork and the canonical repository sits under
        # the `upstream` remote (thread 3833762325's exact shape: the
        # old argv fetched the fork's base and pushed the revert
        # branch to the fork while every gh command targeted
        # RachaelsDen/UR-lorebook).
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires from the fork checkout.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_v=FORK_REMOTE_V,
        )

        # Then: every git operation names the CANONICAL upstream —
        # the base fetch, the worktree build, and the push — never
        # the fork origin, while the revert PR is still created
        # against the pinned canonical repository.
        self.assertEqual(code, 1)
        self.assertIn("git fetch upstream dev", argvs)
        tmp = RUNNER.revert_tmp
        self.assertIn(f"git worktree add --detach {tmp} upstream/dev", argvs)
        self.assertNotIn("git checkout -B", " ".join(argvs))
        self.assertIn(
            f"git -C {tmp} push upstream "
            f"HEAD:refs/heads/revert/pr39-{MERGE_SHA[:7]}",
            argvs,
        )
        self.assertNotIn("git fetch origin dev", argvs)
        self.assertNotIn("git push -u origin", argvs)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn("-R RachaelsDen/UR-lorebook", create)
        self.assertIn("canonical remote 'upstream'", create)
        self.assertIn("REVERT PR OPENED", out)

    def test_no_canonical_remote_blocks_the_revert(self):
        # Given: the checkout knows ONLY the fork — no remote URL
        # names RachaelsDen/UR-lorebook, so the canonical repository
        # the surveys targeted cannot be fetched from or pushed to.
        surveys = iter([[thread("11", "resolved")]])

        # When: the revert fires from the fork-only checkout.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_v=FORK_ONLY_REMOTE_V,
        )

        # Then: the hard error names the missing canonical remote and
        # the manual-revert obligation with setup instructions — NO
        # fetch, checkout, push, or revert PR ever ran against the
        # fork.
        self.assertEqual(code, 1)
        self.assertIn("NO CANONICAL REMOTE", out)
        self.assertIn("RachaelsDen/UR-lorebook", out)
        self.assertIn("MUST be reverted manually", out)
        self.assertIn("git remote add upstream", out)
        self.assertIn("thread 3833762325", out)
        joined = " ".join(argvs)
        self.assertNotIn("git fetch", joined)
        self.assertNotIn("git push", joined)
        self.assertNotIn("git checkout", joined)
        self.assertNotIn("git revert", joined)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn(CANONICAL_REMOTE_V, joined)


class SettleAutoMergeRecheckTests(unittest.TestCase):
    def test_reenabled_auto_merge_is_redisabled_and_still_converges(self):
        # Given: the cancel converged and the settling window is
        # watching OPEN + ABSENT — but another operator re-enables
        # auto-merge between settling probes 1 and 2 (thread
        # 3833762320: the round-9 watch polled only state + queue, so
        # it converged with the live request able to land later
        # unbackstopped). The re-disable takes and the reads go clean.
        surveys = iter([[thread("11", "resolved")]])

        # When: probe 2's autoMergeRequest read is non-null and every
        # later read is clean again.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 60,
            cancel_reads=[
                clean(),
                clean(),
                clean(),
                clean(),
                auto_enabled(),
                clean(),
            ],
        )

        # Then: the re-disable WAS re-dispatched (the original + ONE
        # re-disable), the settling window EXTENDED past its original
        # 60s deadline before converging, and the converged banner
        # reports the bounded re-disable — never a silent convergence
        # over a live request.
        self.assertEqual(code, 1)
        self.assertEqual(argvs.count(
            "gh pr merge 39 --disable-auto -R RachaelsDen/UR-lorebook"
        ), 2)
        self.assertIn("AUTO-MERGE RE-ENABLED at settling probe 2", out)
        self.assertIn("re-dispatching --disable-auto (1/2)", out)
        self.assertIn("thread 3833762320", out)
        self.assertIn("extending the settling window by 60s", out)
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn("1 bounded auto-merge re-disable(s)", out)
        self.assertNotIn("MERGED CLEAN:", out)

    def test_persistent_reenable_exhausts_the_budget_into_both_banner(
        self,
    ):
        # Given: the competing automation re-enables auto-merge after
        # EVERY disable — the bounded re-disable budget (2) cannot
        # win, and converging would claim cancellation over a request
        # that keeps coming back.
        surveys = iter([[thread("11", "resolved")]])

        # When: every settling-probe autoMergeRequest read is
        # non-null.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 40,
            cancel_reads=[clean(), clean(), clean(), auto_enabled()],
        )

        # Then: TWO bounded re-disables ran (beside the original
        # disable) and the THIRD re-enabled read ends the watch in the
        # BOTH-CONTINGENCY manual instructions — never the converged
        # claim.
        self.assertEqual(code, 1)
        self.assertEqual(argvs.count(
            "gh pr merge 39 --disable-auto -R RachaelsDen/UR-lorebook"
        ), 3)
        self.assertIn("AUTO-MERGE RE-ENABLED at settling probe 1", out)
        self.assertIn("AUTO-MERGE RE-ENABLED at settling probe 2", out)
        self.assertIn(
            "AUTO-MERGE STILL RE-ENABLED at settling probe 3", out
        )
        self.assertIn("thread 3833762320", out)
        self.assertIn("CANCEL UNCONFIRMED", out)
        self.assertIn("BOTH contingencies are live", out)
        self.assertNotIn("CANCELLED and verified gone", out)
        self.assertNotIn("MERGED CLEAN:", out)


if __name__ == "__main__":
    unittest.main()
