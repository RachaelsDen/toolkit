"""pr_guard merge-act round-21 tests (PR #41 round 21, refit 25).

Thread 3834883632: the PR commit-list read PAGINATES — `gh pr view
--json commits` serves only the inspected `commits(first: 100)`
GraphQL page with no cursor loop, so a >100-commit PR silently
truncated at 100 oids. The read walks the REST commit endpoint page
by page (per_page=100&page=<k>) until a SHORT page. PR #41 round 25
(threads 3835145976/3835145981/3835175506/3835175508) moved the
read to the PRE-DISPATCH snapshot (thread 3835145981: read once
beside the merge-request-time head, frozen for the revert-path
diagnostics, never re-read against a moved refs/pull/<n>/head) — a
malformed page now WARNS and degrades the banner diagnostics
instead of blocking anything (the merge gate never depended on the
list). The rewritten-tip and delta-invariance suites were DELETED
with the classifier arms they served (the suite count drops by
design; the refit round-11/19 suites pin the fail-closed contract).

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round21_test -v
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
# Thread 3834883633: the REWRITTEN tip — conflict resolution
# substantively changed the final commit's diff, so its stable
# patch-id matches NO PR commit while every earlier commit landed.
PATCH_TIP = "ppid0000rewritten"
LANDED_OLDEST = "eeee000000000000000000000000000000000b01"
# Thread 3834883628: a foreign duplicate in the same-metadata
# coincidence — a CHERRY-PICK of the PR's X (same patch-id, same
# author+subject) landing beside this PR's squash of Y whose
# author+subject equal Y's (the PR title often IS that subject).
FOREIGN_DUP = "eeee0000000000000000000000000000000000d1"
# Thread 3834934170 (round 22): a delta id that is NOT the PR head
# side's — the landing whose net change over the fork diverges from
# the PR's (a foreign coincidence that did NOT reproduce it, or a
# content-divergent drift).
OTHER_DELTA = "88880000000000000000000000000000000000ee"


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class CommitPaginationTests(unittest.TestCase):
    def test_two_page_commit_snapshot_is_fully_consumed(self):
        # Given: a 101-COMMIT PR — the truncated round-20 read saw
        # only the first GraphQL page (100 oids, thread 3834883632);
        # the round-25 pre-dispatch snapshot walks the REST endpoint
        # page by page and must consume the whole list BEFORE the
        # merge is dispatched.
        surveys = iter(
            [[thread("11", "resolved")], [thread("11", "resolved")]]
        )
        commits = [f"{i:040x}" for i in range(1, 102)]

        # When: the act snapshots the commit list pre-dispatch —
        # page one serves 100 entries, the short SECOND page serves
        # the 101st, and the cursor stops there; the merge then
        # completes clean (two-parent default) through the quiet
        # watch.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged()],
            pr_commits=commits,
        )

        # Then: BOTH pages were consumed (page=1 AND page=2 GETs,
        # never a page=3 — the short page stops the cursor), the
        # snapshot ran BEFORE the merge dispatch argv, no snapshot
        # warning printed, and the act completed MERGED CLEAN (the
        # snapshot feeds diagnostics only — it never gates).
        self.assertEqual(code, 0)
        root = "repos/RachaelsDen/UR-lorebook/pulls/39/commits"
        self.assertIn(
            f"gh api --method GET {root}?per_page=100&page=1", argvs
        )
        self.assertIn(
            f"gh api --method GET {root}?per_page=100&page=2", argvs
        )
        self.assertFalse(any("page=3" in argv for argv in argvs))
        self.assertLess(
            argvs.index(f"gh api --method GET {root}?per_page=100&page=2"),
            argvs.index(MERGE_ARGV),
        )
        self.assertNotIn("PR COMMIT SNAPSHOT", out)
        self.assertIn("MERGED CLEAN", out)

    def test_malformed_entry_warns_and_degrades_the_diagnostics(self):
        # Given: the REST snapshot read answers with an entry that
        # carries NO sha. The old planner failed closed HERE (the
        # list fed the classifier); the round-25 snapshot is
        # diagnostics-only, so the read WARNS and the merge proceeds
        # — but the fail-closed banner of a later single-parent
        # revert reports the snapshot as UNAVAILABLE (thread
        # 3835145981: the list is never re-read post-merge).
        surveys = iter([[thread("11", "resolved")]])

        # When: the first snapshot page contains the malformed entry
        # and the landing is single-parent with a parent that is NOT
        # the current base tip.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=[""],
        )

        # Then: the snapshot warning fired pre-dispatch, NO second
        # page was fetched, the merge WAS dispatched anyway, and the
        # fail-closed banner reports the PR-commit-count diagnostic
        # as UNAVAILABLE — never a number from the bad page.
        self.assertEqual(code, 1)
        self.assertIn("PR COMMIT SNAPSHOT UNREADABLE", out)
        self.assertFalse(any("page=2" in argv for argv in argvs))
        self.assertIn(MERGE_ARGV, argvs)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn("pre-dispatch commit snapshot is UNAVAILABLE", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)


if __name__ == "__main__":
    unittest.main()
