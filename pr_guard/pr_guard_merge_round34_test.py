"""pr_guard merge-act round-34 tests (PR #45 round 1).

Thread 3835760162 (P1) — the ancestry-checked reuse arm still
admitted MERGE tips: `git rev-parse FETCH_HEAD^` names parent ONE
(gitrevisions), so an occupied candidate whose tip is a merge commit
with the expected base as FIRST parent and foreign commits through
the SECOND parent passed the ancestry probe; its first-parent
patch-id matched the local revert's, the branch was REUSED, and the
urgent revert PR carried the foreign second-parent history. The
reuse check now additionally requires the fetched tip to be a
SINGLE-PARENT commit (`git rev-parse FETCH_HEAD^2` must FAIL — a
merge has two parents); a merge tip takes the suffix path like any
other unproven candidate.

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act; the round-33 ancestry_answers fixture widened with a
FETCH_HEAD^2 answer (rc 0 + sha = a second parent exists; nonzero =
single-parent, refit at round 3 to REAL git's rc 128 +
missing-parent stderr signature per thread 3835846317, and refit
again at round 4 to the QUIET --verify shape — rc 1, no stderr at
all — per thread 3835877368's rc-only, locale-independent rule).

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round34_test -v
"""

import unittest

from .pr_guard_merge_fixtures import BASE_TIP, FOREIGN_PARENT
from .pr_guard_merge_harness import (
    HEAD,
    MERGE_SHA,
    MergeHarness,
    merged,
    thread,
)

RUNNER = MergeHarness()
BRANCH = f"revert/pr39-{MERGE_SHA[:7]}"
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"
OLD_REVERT = "0dda1f0000000000000000000000000000000000"
LOCAL_DIFF = (
    "diff --git a/src/server/gate.ts b/src/server/gate.ts\n"
    "--- a/src/server/gate.ts\n"
    "+++ b/src/server/gate.ts\n"
    "@@ -1,2 +1,1 @@\n"
    "-import { gate } from \"./gate\"\n"
    "-import { old } from \"./old\"\n"
)
PIDS = {
    LOCAL_DIFF.strip(): "111100000000000000000000000000000000aaaa",
}


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


# The round-33 ancestry fixture widened with the round-34 MERGE-TIP
# stage, refit at round 3 (thread 3835846317) and again at round 4
# (thread 3835877368): each remote branch name maps to (tip_parent,
# parent2_rc) — FETCH_HEAD^ answers the tip's FIRST parent and the
# QUIET --verify FETCH_HEAD^2 probe answers rc 0 (a SECOND parent
# exists: the merge shape) or rc 1 (PROVEN single-parent — the real
# quiet form's exit code, no stderr to localize). The patch-id
# stages always MATCH this attempt's revert (the attacker's shape:
# same first-parent patch, foreign history elsewhere).
def merge_tip_answers(remote_shapes: dict):
    fetched: list[tuple[str, int]] = []

    def answers(argv, stdin):
        g = ["git", *argv[3:]] if argv[1:2] == ["-C"] else argv
        if g[:2] == ["git", "fetch"]:
            shape = remote_shapes.get(
                g[3].removeprefix("refs/heads/"), ("", 1)
            )
            fetched.insert(0, shape)
            return (0, "")
        if g[:2] == ["git", "diff"]:
            if g[3] == "FETCH_HEAD":
                return (0, LOCAL_DIFF) if fetched else None
            return (0, LOCAL_DIFF)
        if g[:2] == ["git", "patch-id"]:
            pid = PIDS.get((stdin or "").strip())
            if pid is None:
                return None
            return (0, f"{pid} 0000000000000000000000000000000000000000\n")
        if g[:2] == ["git", "rev-parse"] and g[2:3] == ["FETCH_HEAD^"]:
            return (0, fetched[0][0] + "\n") if fetched else None
        if (
            g[:2] == ["git", "rev-parse"]
            and g[2:] == ["--verify", "--quiet", "FETCH_HEAD^2"]
        ):
            if not fetched:
                return None
            if fetched[0][1] != 0:
                return (1, "", "")
            return (0, FOREIGN_PARENT + "\n")
        return None

    return answers


class MergeTipRejectionTests(unittest.TestCase):
    def test_merge_tip_with_matching_first_parent_is_not_reused(self):
        # Given: the deterministic branch's tip is a MERGE commit —
        # its FIRST parent IS the base this attempt's revert was
        # built on (so FETCH_HEAD^ passes the round-2 ancestry probe)
        # and its first-parent diff's patch-id matches this attempt's
        # revert — while its SECOND parent carries foreign history —
        # thread 3835760162's exact shape (the old probe read `^` as
        # "the parent", but gitrevisions defines `^` as parent ONE
        # of two).
        surveys = iter([[thread("11", "resolved")]])

        # When: the rerun probes the occupied candidate — sha
        # differs, signature matches, parent-1 matches, and the
        # FETCH_HEAD^2 probe SUCCEEDS (a second parent exists).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_heads={BRANCH: OLD_REVERT},
            git_answers=merge_tip_answers({BRANCH: (BASE_TIP, 0)}),
        )

        # Then: NOT reused — no reuse banner over foreign history,
        # the ordinary first-free suffix push runs, the PR opens
        # against the suffix, and the ^2 merge probe ran (it rejects
        # BEFORE the parent-one ancestry probe, which stays
        # unreachable on this path).
        self.assertEqual(code, 1)
        self.assertNotIn("REVERT BRANCH REUSED", out)
        self.assertIn("REVERT BRANCH SUFFIXED", out)
        self.assertIn("3835760162", out)
        tmp = RUNNER.revert_tmp
        self.assertIn(
            f"git -C {tmp} rev-parse --verify --quiet FETCH_HEAD^2",
            argvs,
        )
        self.assertNotIn(f"git -C {tmp} rev-parse FETCH_HEAD^", argvs)
        self.assertIn(
            f"git -C {tmp} push origin HEAD:refs/heads/{BRANCH}-2",
            argvs,
        )
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(f"--head {BRANCH}-2", create)
        self.assertIn("REVERT PR OPENED", out)

    def test_single_parent_tip_is_still_reused_with_the_probe_run(self):
        # Given: the same matching-content, matching-first-parent
        # shape — but the tip is an ORDINARY single-parent revert
        # commit (FETCH_HEAD^2 fails: no second parent), the
        # legitimate earlier-retry branch the reuse arm exists for.
        surveys = iter([[thread("11", "resolved")]])

        # When: the ^2 probe FAILS (rc 1) and the ^ probe matches.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_heads={BRANCH: OLD_REVERT},
            git_answers=merge_tip_answers({BRANCH: (BASE_TIP, 1)}),
        )

        # Then: REUSED — the single-parent proof is cited beside the
        # patch-id and ancestry, no push argv exists, and the PR
        # opens against the existing branch.
        self.assertEqual(code, 1)
        self.assertIn(f"REVERT BRANCH REUSED: refs/heads/{BRANCH}", out)
        self.assertIn("patch-id", out)
        self.assertIn("3835714798", out)
        self.assertIn("SINGLE-PARENT", out)
        self.assertIn("3835760162", out)
        self.assertIn(
            f"git -C {RUNNER.revert_tmp} rev-parse --verify --quiet FETCH_HEAD^2",
            argvs,
        )
        self.assertNotIn("git push", " ".join(argvs))
        self.assertNotIn("REVERT BRANCH SUFFIXED", out)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(f"--head {BRANCH}", create)
        self.assertIn("REVERT PR OPENED", out)


if __name__ == "__main__":
    unittest.main()
