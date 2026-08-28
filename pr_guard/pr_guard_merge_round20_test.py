"""pr_guard merge-act round-20 tests (PR #41 round 20).

Thread 3834819188's author/subject correlation arm — like every
provenance signal before and after it — was RETIRED at round 25
(threads 3835145976/3835145981/3835175506/3835175508): metadata is
REPRODUCIBLE (a cherry-pick preserves patch-id, author, and subject
exactly), so the arm licensed nothing a foreign landing could not
satisfy. The three AuthorSubjectProvenance suites were DELETED with
the arm (the suite count drops by design; the refit round-11/14/19
suites already pin the fail-closed contract and the
no-provenance-pipes guarantees).

Thread 3834819191: the revert worktree must never check out the
DETERMINISTIC branch name — the caller's checkout may still have it
active (an earlier guard left the operator on it), and git refuses
one branch in two worktrees, so the old `checkout -B` aborted the
revert before any commit existed. The worktree stays DETACHED at the
fetched base and the push lands the commit directly as
HEAD:refs/heads/<name> — no local branch anywhere.

No network: the shared fake-gh/fake-git/fake-clock harness drives the
act.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round20_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    HEAD,
    MERGE_SHA,
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
LANDED_OLDEST = "eeee000000000000000000000000000000000b01"
# Thread 3834819188: the foreign duplicate in the SAME-ORDER spoof —
# a LINEAR queue advancement carrying the PR's OLDER patch X under a
# FOREIGN author and subject; this PR's squash lands Y after it.
FOREIGN_DUP = "eeee0000000000000000000000000000000000d1"
FOREIGN_META = "Foreign Author <foreign@example.invalid>|dup of X"
BRANCH = f"revert/pr39-{MERGE_SHA[:7]}"


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class DetachedWorktreePushTests(unittest.TestCase):
    def test_caller_active_branch_name_never_blocks_the_revert(self):
        # Given: the INVOKING checkout still has the deterministic
        # revert branch checked out (an earlier guard left the
        # operator on it) — thread 3834819191's exact finding: git
        # refuses to check one branch out in two worktrees, so the
        # old `git -C <tmp> checkout -B revert/pr...` aborted the
        # automatic revert before any commit existed.
        surveys = iter([[thread("11", "resolved")]])

        # When: the revert fires with that branch active elsewhere.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
        )

        # Then: the revert SUCCEEDS without ever checking a branch
        # out — the worktree is DETACHED at the fetched base, the
        # commit is built on the detached HEAD, and the push creates
        # the remote branch directly (HEAD:refs/heads/<name>, no -u,
        # no local branch argv anywhere); the PR opens against the
        # deterministic name.
        self.assertEqual(code, 1)
        tmp = RUNNER.revert_tmp
        joined = " ".join(argvs)
        self.assertIn(f"git worktree add --detach {tmp} origin/dev", argvs)
        self.assertNotIn("checkout -B", joined)
        self.assertNotIn("git checkout ", joined)
        self.assertNotIn("git branch ", joined)
        self.assertIn(
            f"git -C {tmp} push origin HEAD:refs/heads/{BRANCH}", argvs
        )
        self.assertNotIn("push -u", joined)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(f"--head {BRANCH}", create)
        self.assertIn("3834819191", create)
        self.assertIn("REVERT PR OPENED", out)


if __name__ == "__main__":
    unittest.main()
