"""pr_guard merge-act round-32 tests (PR #43 round 1).

Thread 3835653121 (P2) — a retry REBUILDS the revert with a fresh
committer timestamp, so its sha differs from the pushed branch's
even though both reverse the same merge: the reuse-by-head sha
equality never matched, and every retry minted another -2, -3, ...
suffix toward the 50-name budget (repeated transient `gh pr create`
failures could exhaust it while a reusable branch sat remote). The
reuse rule now compares CONTENT SIGNATURES after sha equality —
`git patch-id --stable` of the freshly-built local revert's
first-parent diff vs the FETCHED branch tip's — so a same-content
different-sha remote branch is REUSED regardless of sha, and a
different-content tip still fails closed to the suffix push.

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act; the git_answers fixture serves the piped diff/patch-id
stages by their INPUT (the landing_probes precedent) and the
destination-less candidate fetch by its argv, while remote_heads
serves ls-remote.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round32_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    HEAD,
    MERGE_SHA,
    REVERT_HEAD,
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
OTHER_DIFF = (
    "diff --git a/src/server/other.ts b/src/server/other.ts\n"
    "--- a/src/server/other.ts\n"
    "+++ b/src/server/other.ts\n"
    "@@ -1 +1 @@\n"
    "-x\n"
    "+y\n"
)
PIDS = {
    LOCAL_DIFF.strip(): "111100000000000000000000000000000000aaaa",
    OTHER_DIFF.strip(): "222200000000000000000000000000000000bbbb",
}


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


# The piped content-signature stages, served by INPUT (diff/patch-id)
# and by the fetched candidate name (FETCH_HEAD answers the LAST
# fetch): local probes always yield LOCAL_DIFF — the freshly-built
# revert — and each remote branch name maps to the diff its fetched
# tip carries.
def patch_id_answers(remote_diffs: dict):
    fetched: list[str] = []

    def answers(argv, stdin):
        g = ["git", *argv[3:]] if argv[1:2] == ["-C"] else argv
        if g[:2] == ["git", "fetch"]:
            fetched.insert(
                0, remote_diffs.get(g[3].removeprefix("refs/heads/"), "")
            )
            return (0, "")
        if g[:2] == ["git", "diff"]:
            if g[3] == "FETCH_HEAD":
                return (0, fetched[0]) if fetched else None
            return (0, LOCAL_DIFF)
        if g[:2] == ["git", "patch-id"]:
            pid = PIDS.get((stdin or "").strip())
            if pid is None:
                return None
            return (0, f"{pid} 0000000000000000000000000000000000000000\n")
        return None

    return answers


class ContentSignatureReuseTests(unittest.TestCase):
    def test_same_content_different_sha_branch_is_reused(self):
        # Given: a PRIOR attempt pushed the deterministic branch
        # carrying a revert whose CONTENT equals this attempt's but
        # whose COMMIT differs — thread 3835653121's exact scenario
        # (the retry rebuilt the same reversed merge under a new
        # timestamp, so the sha-equality check could never match and
        # the old code minted suffixes toward the 50-name budget).
        surveys = iter([[thread("11", "resolved")]])

        # When: the rerun's ls-remote reports the different-sha head
        # and the fetched tip's patch-id equals the local revert's.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_heads={BRANCH: OLD_REVERT},
            git_answers=patch_id_answers({BRANCH: LOCAL_DIFF}),
        )

        # Then: the branch is REUSED by content signature — the
        # local diff/patch-id probe, the candidate fetch, and the
        # FETCH_HEAD diff all ran; NO push argv exists; the PR opens
        # straight against the existing branch.
        self.assertEqual(code, 1)
        self.assertIn(f"REVERT BRANCH REUSED: refs/heads/{BRANCH}", out)
        self.assertIn("revert CONTENT", out)
        self.assertIn("patch-id", out)
        self.assertIn("3835653121", out)
        tmp = RUNNER.revert_tmp
        self.assertIn(f"git -C {tmp} diff HEAD^ HEAD", argvs)
        self.assertIn(f"git -C {tmp} patch-id --stable", argvs)
        self.assertIn(f"git -C {tmp} fetch origin refs/heads/{BRANCH}", argvs)
        self.assertIn(f"git -C {tmp} diff FETCH_HEAD^ FETCH_HEAD", argvs)
        self.assertNotIn("git push", " ".join(argvs))
        self.assertNotIn("REVERT BRANCH SUFFIXED", out)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(f"--head {BRANCH}", create)
        self.assertIn("REVERT PR OPENED", out)

    def test_same_content_different_sha_suffix_is_reused(self):
        # Given: the same rebuilt-revert shape, but the deterministic
        # name is occupied by an UNRELATED commit and the earlier
        # retry's same-content revert sits at the `-2` suffix.
        surveys = iter([[thread("11", "resolved")]])

        # When: both candidates are probed — the deterministic tip's
        # patch-id DIFFERS, the -2 tip's EQUALS the local one.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_heads={
                BRANCH: "dead0000000000000000000000000000000000ff",
                f"{BRANCH}-2": OLD_REVERT,
            },
            git_answers=patch_id_answers(
                {BRANCH: OTHER_DIFF, f"{BRANCH}-2": LOCAL_DIFF}
            ),
        )

        # Then: the suffix is REUSED by content signature — no push,
        # no further suffix minted, the PR opens against `-2`.
        self.assertEqual(code, 1)
        self.assertIn(
            f"REVERT BRANCH REUSED: refs/heads/{BRANCH}-2", out
        )
        self.assertIn("3835653121", out)
        self.assertIn(
            f"git ls-remote origin refs/heads/{BRANCH}-2", argvs
        )
        self.assertIn(
            f"git -C {RUNNER.revert_tmp} fetch origin "
            f"refs/heads/{BRANCH}-2",
            argvs,
        )
        self.assertNotIn("git push", " ".join(argvs))
        self.assertNotIn("REVERT BRANCH SUFFIXED", out)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(f"--head {BRANCH}-2", create)
        self.assertIn("REVERT PR OPENED", out)

    def test_different_content_tip_still_gets_the_suffix_push(self):
        # Given: the deterministic name is occupied by a DIFFERENT
        # revert (the base moved between attempts — a genuinely
        # different reversed patch), and `-2` is free.
        surveys = iter([[thread("11", "resolved")]])

        # When: the fetched tip's patch-id DIFFERS from the local
        # revert's.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_heads={BRANCH: OLD_REVERT},
            git_answers=patch_id_answers({BRANCH: OTHER_DIFF}),
        )

        # Then: NO content-signature reuse (a different patch is
        # never treated as this attempt's revert) — the first free
        # suffix gets the ordinary push and the PR opens against it.
        self.assertEqual(code, 1)
        self.assertNotIn("REVERT BRANCH REUSED", out)
        self.assertIn("REVERT BRANCH SUFFIXED", out)
        tmp = RUNNER.revert_tmp
        self.assertIn(
            f"git -C {tmp} push origin HEAD:refs/heads/{BRANCH}-2",
            argvs,
        )
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(f"--head {BRANCH}-2", create)
        self.assertIn("REVERT PR OPENED", out)


if __name__ == "__main__":
    unittest.main()
