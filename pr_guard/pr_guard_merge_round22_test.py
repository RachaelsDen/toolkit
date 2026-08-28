"""pr_guard merge-act round-22 tests (PR #41 round 22, refit 25).

Thread 3834934167: the REST commits endpoint DOCUMENTS a 250-commit
representability cap ("Lists a maximum of 250 commits for a pull
request") that page iteration cannot bypass — a 251-commit PR's
100+100+50 page shape is byte-identical to an exactly-250 PR's, so
completeness can never be proven at the cap. The round-22 read
FAILED CLOSED on the at-cap list because the classifier planned
from it; PR #41 round 25 (threads 3835145976/3835145981/3835175506/
3835175508) retired the classifier and moved the read to the
PRE-DISPATCH snapshot (thread 3835145981), so an at-cap list is now
DISCARDED with a loud pre-dispatch warning (a truncated count must
not misreport in the fail-closed banner's diagnostics) while the
merge itself proceeds — the gate never depended on the list. The
delta-equality suites of threads 3834934170/3834934169 were DELETED
with the arms they served (the suite count drops by design).

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round22_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    FOREIGN_PARENT,
    HEAD,
    MERGE_ARGV,
    MergeHarness,
    merged,
    thread,
)

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"
COMMIT_X = "bbbb0000000000000000000000000000000000aa"
COMMIT_Y = "cccc0000000000000000000000000000000000bb"
PATCH_X = "ppid0000x"
PATCH_Y = "ppid0000y"
# Thread 3834934169: the REWRITTEN tip — a conflict-rewritten squash
# lands with a new stable patch-id matching no PR commit while the
# foreign cherry-pick beside it carries the first commit's exact id.
PATCH_TIP = "ppid0000rewritten"
LANDED_OLDEST = "eeee000000000000000000000000000000000b01"
# Thread 3834934169: the FOREIGN CHERRY-PICK of the PR's first
# commit in the rewritten-tip coincidence (same patch-id, author,
# and subject as the PR's own first commit).
FOREIGN_DUP = "eeee0000000000000000000000000000000000d1"
# Thread 3834934170: a delta id that is NOT the PR head side's — a
# landing whose net change over the fork diverges from the PR's.
OTHER_DELTA = "88880000000000000000000000000000000000ee"


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class CommitCapTests(unittest.TestCase):
    def test_at_cap_snapshot_is_discarded_with_a_warning(self):
        # Given: a 250-COMMIT PR — the REST read's pages are
        # 100+100+50, the last page FILLING the snapshot to exactly
        # the endpoint's documented 250-commit cap; a 251-commit PR
        # serves the byte-identical page shape, so completeness can
        # never be proven at the cap. The snapshot is DIAGNOSTICS-
        # only now (thread 3835145981), so the at-cap list is
        # DISCARDED with a warning instead of blocking the merge.
        surveys = iter([[thread("11", "resolved")]])

        # When: the pre-dispatch snapshot reaches the cap and the
        # landing is single-parent with a parent that is NOT the
        # current base tip.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=[f"{i:040x}" for i in range(1, 251)],
        )

        # Then: the pre-dispatch DISCARD warning fired naming the
        # documented cap (no fourth page fetched), the merge WAS
        # dispatched anyway, and the fail-closed banner reports the
        # PR-commit-count diagnostic as UNAVAILABLE — never a
        # possibly-truncated 250.
        self.assertEqual(code, 1)
        self.assertIn("PR COMMIT SNAPSHOT DISCARDED", out)
        self.assertIn("250-COMMIT CAP", out)
        self.assertIn("3834934167", out)
        self.assertIn(MERGE_ARGV, argvs)
        root = "repos/RachaelsDen/UR-lorebook/pulls/39/commits"
        self.assertIn(
            f"gh api --method GET {root}?per_page=100&page=3", argvs
        )
        self.assertFalse(any("page=4" in argv for argv in argvs))
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn("pre-dispatch commit snapshot is UNAVAILABLE", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)

    def test_249_commit_snapshot_proceeds(self):
        # Given: a 249-COMMIT PR — one commit BELOW the documented
        # 250-commit cap, so the 100+100+49 page shape proves the
        # snapshot complete and the read must NOT discard it.
        surveys = iter([[thread("11", "resolved")]])
        commits = [f"{i:040x}" for i in range(1, 250)]

        # When: the pre-dispatch snapshot consumes the complete list
        # and the fail-closed revert fires on a non-tip parent.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=commits,
        )

        # Then: NO cap warning, the merge proceeded, and the
        # fail-closed banner's diagnostics carry the COMPLETE frozen
        # count — 249, proven by the short final page.
        self.assertEqual(code, 1)
        self.assertNotIn("PR COMMIT SNAPSHOT DISCARDED", out)
        self.assertIn(MERGE_ARGV, argvs)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn(
            "FROZEN pre-dispatch commit snapshot counts 249 commit(s)",
            out,
        )
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)


if __name__ == "__main__":
    unittest.main()
