"""pr_guard merge-act round-19 tests (PR #41 round 19, refit 25).

Thread 3834761215: a whitespace-conflict rebase preserves every
stable patch-id while CHANGING the landed content, so the round-19
plan reverted the LANDED oid chain (<landed-oldest>^..<merge_sha>),
never the PR's ORIGINAL pre-rebase range — reverse-applying the
original diffs against the landed tree conflicts, so no branch and no
revert PR would ever be produced while the unsafe merge stays.

Thread 3834761209: patch-id membership, count, complete maps, and a
contiguous parent chain are all UNORDERED evidence — a foreign queue
commit duplicating one PR patch beside a squash duplicating another
satisfies every one of them, so the round-19 arm added the landed
patch-id ORDER.

PR #41 round 25 (threads 3835145976/3835145981/3835175506/3835175508)
RETIRED both arms with the classifier they belonged to: every
provenance signal — ORDER included — was shown reproducible by a
foreign landing, so even the genuine whitespace-drift rebase (the
exact landing the landed-range revert was built for) now FAILS
CLOSED by contract: its parent is not the current base tip, and the
banner carries the fork/range/count diagnostics for the human who
must revert it manually. The landed-OID fetch suite and the
ordered-sequence suites were DELETED with the arms (the suite count
drops by design; the refit round-11/14 suites already pin the
fail-closed banner and the no-provenance-pipes guarantees).

No network: the shared fake-gh/fake-git/fake-clock harness drives the
act; landing_probes serves the landed-range diagnostic.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round19_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    FOREIGN_PARENT,
    HEAD,
    MERGE_SHA,
    MergeHarness,
    landing_probes,
    merged,
    thread,
)

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"
COMMIT_X = "bbbb0000000000000000000000000000000000aa"
COMMIT_Y = "cccc0000000000000000000000000000000000bb"


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class LandedRangeRetirementTests(unittest.TestCase):
    def test_whitespace_drift_rebase_fails_closed_by_contract(self):
        # Given: a genuine two-commit REBASE whose conflict resolution
        # changed only WHITESPACE — the exact landing thread
        # 3834761215 built the landed-range revert for (reverting the
        # ORIGINAL X/Y range conflicts; only the LANDED shas
        # reverse-apply cleanly). Round 25 retires that plan: the
        # landing's parent is the first rebased PR commit, NOT the
        # current base tip, and no provenance signal may license the
        # range revert any more — threads 3835175506/3835145976
        # proved every such signal spoofable, so the human reverts
        # this manually with the banner's numbers.
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires on the
        # whitespace-drift rebase landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=[COMMIT_X, COMMIT_Y],
            git_answers=landing_probes(MERGE_SHA, landed=2),
        )

        # Then: NO revert argv — neither the LANDED range revert the
        # round-19 plan built nor a one-commit revert — was
        # dispatched, and no revert PR opened; the banner names the
        # contract, the range count, and the frozen commit count.
        self.assertEqual(code, 1)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn("NEITHER", out)
        self.assertIn("counts 2 commit(s)", out)
        self.assertIn("FROZEN pre-dispatch commit snapshot counts 2 commit(s)", out)
        self.assertIn("MUST be reverted manually", out)
        self.assertIn("3835175506", out)


if __name__ == "__main__":
    unittest.main()
