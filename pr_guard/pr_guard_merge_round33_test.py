"""pr_guard merge-act round-33 tests (PR #43 round 2).

Thread 3835714798 (P1) — the patch-id reuse arm now proves ANCESTRY:
patch-id compares only the fetched tip's FIRST-PARENT diff, not the
branch history, so a collaborator could precreate the deterministic
revert branch as `unrelated changes + a matching revert` and the
round-1 arm reused it — pushing no commit of our own and opening the
urgent PR on a branch whose PARENT carries the foreign history. The
reuse check additionally requires the fetched tip's parent
(rev-parse FETCH_HEAD^) to BE the base this attempt's revert was
built on (the local HEAD^); a mismatch — or any unreadable probe —
is not reusable and takes the suffix path.

Thread 3835714804 (P2) — the settling watch's final paced exhaustion
probe reads MERGED through the broad != "AUTO" branch (the
propagation arm) and discarded the definitive landing observation; a
stale later state read could then end the flow in a cancellation
banner with no revert. MERGED at the exhaustion probe now goes
straight through the pre-existing-gated revert path.

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act; the git_answers fixture serves the piped diff/patch-id
stages by INPUT and the ancestry probes by argv (the round-32
patch_id_answers precedent, widened with per-branch tip parents).

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round33_test -v
"""

import unittest

from .pr_guard_merge_fixtures import BASE_TIP, FOREIGN_PARENT
from .pr_guard_merge_harness import (
    HEAD,
    MERGE_SHA,
    MergeHarness,
    merged,
    pending,
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


# The round-32 content-signature stages widened with the round-33
# ANCESTRY stage: each remote branch name maps to (diff, tip_parent)
# — the fetched tip's first-parent diff and its PARENT sha — and an
# optional rc makes the FETCH_HEAD^ probe UNREADABLE (fail-closed).
# The local probes always yield LOCAL_DIFF built on BASE_TIP (the
# worktree sits at the fetched base).
def ancestry_answers(
    remote_shapes: dict, parent_rc: int = 0
):
    fetched: list[tuple[str, str]] = []

    def answers(argv, stdin):
        g = ["git", *argv[3:]] if argv[1:2] == ["-C"] else argv
        if g[:2] == ["git", "fetch"]:
            shape = remote_shapes.get(
                g[3].removeprefix("refs/heads/"), ("", "")
            )
            fetched.insert(0, shape)
            return (0, "")
        if g[:2] == ["git", "diff"]:
            if g[3] == "FETCH_HEAD":
                return (0, fetched[0][0]) if fetched else None
            return (0, LOCAL_DIFF)
        if g[:2] == ["git", "patch-id"]:
            pid = PIDS.get((stdin or "").strip())
            if pid is None:
                return None
            return (0, f"{pid} 0000000000000000000000000000000000000000\n")
        if g[:2] == ["git", "rev-parse"] and g[2:3] == ["FETCH_HEAD^"]:
            if parent_rc != 0:
                return (parent_rc, "")
            return (0, fetched[0][1] + "\n") if fetched else None
        return None

    return answers


class AncestryCheckedReuseTests(unittest.TestCase):
    def test_foreign_parent_tip_is_not_reused(self):
        # Given: the deterministic branch's tip carries a revert whose
        # CONTENT equals this attempt's (the fetched diff's patch-id
        # matches) but whose PARENT is a FOREIGN commit — thread
        # 3835714798's exact shape (patch-id sees only the tip's
        # first-parent diff, so a collaborator's `unrelated changes +
        # matching revert` branch signatures as reusable while the
        # urgent PR would carry the foreign history).
        surveys = iter([[thread("11", "resolved")]])

        # When: the rerun probes the occupied candidate — signature
        # matches, ancestry does not (FETCH_HEAD^ answers the foreign
        # parent, the local revert's HEAD^ the fetched base).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_heads={BRANCH: OLD_REVERT},
            git_answers=ancestry_answers(
                {BRANCH: (LOCAL_DIFF, FOREIGN_PARENT)}
            ),
        )

        # Then: NOT reused — no reuse banner, the ordinary first-free
        # suffix push runs, and the PR opens against the suffix; the
        # ancestry probe itself ran (FETCH_HEAD^ was rev-parsed).
        self.assertEqual(code, 1)
        self.assertNotIn("REVERT BRANCH REUSED", out)
        self.assertIn("REVERT BRANCH SUFFIXED", out)
        tmp = RUNNER.revert_tmp
        self.assertIn(f"git -C {tmp} rev-parse HEAD^", argvs)
        self.assertIn(f"git -C {tmp} rev-parse FETCH_HEAD^", argvs)
        self.assertIn(
            f"git -C {tmp} push origin HEAD:refs/heads/{BRANCH}-2",
            argvs,
        )
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(f"--head {BRANCH}-2", create)
        self.assertIn("REVERT PR OPENED", out)

    def test_matching_ancestry_tip_is_reused_with_the_probe_run(self):
        # Given: the same matching-content different-sha shape, but
        # the fetched tip's PARENT is the SAME base this attempt's
        # revert was built on — the legitimate earlier-retry branch
        # the round-1 arm exists to reuse.
        surveys = iter([[thread("11", "resolved")]])

        # When: both probes match — patch-id over the fetched diff,
        # ancestry over FETCH_HEAD^ == the local HEAD^ base.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_heads={BRANCH: OLD_REVERT},
            git_answers=ancestry_answers(
                {BRANCH: (LOCAL_DIFF, BASE_TIP)}
            ),
        )

        # Then: REUSED — the ancestry proof is cited beside the
        # patch-id, no push argv exists, the PR opens against the
        # existing branch.
        self.assertEqual(code, 1)
        self.assertIn(f"REVERT BRANCH REUSED: refs/heads/{BRANCH}", out)
        self.assertIn("patch-id", out)
        self.assertIn("3835714798", out)
        self.assertIn(f"git -C {RUNNER.revert_tmp} rev-parse FETCH_HEAD^", argvs)
        self.assertNotIn("git push", " ".join(argvs))
        self.assertNotIn("REVERT BRANCH SUFFIXED", out)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(f"--head {BRANCH}", create)
        self.assertIn("REVERT PR OPENED", out)

    def test_unreadable_parent_probe_fails_closed_to_the_suffix(self):
        # Given: the matching-content tip again, but the FETCH_HEAD^
        # ancestry probe itself is UNREADABLE — an unknown parent can
        # never prove the candidate's history, so reuse must fail
        # closed exactly like a mismatch.
        surveys = iter([[thread("11", "resolved")]])

        # When: the parent probe answers nonzero.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_heads={BRANCH: OLD_REVERT},
            git_answers=ancestry_answers(
                {BRANCH: (LOCAL_DIFF, BASE_TIP)}, parent_rc=1
            ),
        )

        # Then: the suffix push — never a reuse over unproven
        # ancestry.
        self.assertEqual(code, 1)
        self.assertNotIn("REVERT BRANCH REUSED", out)
        self.assertIn("REVERT BRANCH SUFFIXED", out)
        self.assertIn(
            f"git -C {RUNNER.revert_tmp} push origin "
            f"HEAD:refs/heads/{BRANCH}-2",
            argvs,
        )
        self.assertIn("REVERT PR OPENED", out)


class ExhaustionMergedTests(unittest.TestCase):
    def test_merged_at_the_paced_exhaustion_probe_reverts(self):
        # Given: the completion poll timed out still-OPEN, the cancel
        # converged, and the settling watch burned both bounded
        # re-disables on a persistent re-enable — thread 3835714804's
        # exact shape (the PR lands during the FINAL pace, so the
        # fresh exhaustion re-read observes MERGED where the round-31
        # code fell into the broad != "AUTO" propagation arm).
        surveys = iter([[thread("11", "resolved")]])

        # When: the paced exhaustion probe's FRESH read reports
        # MERGED and the landed-sha read serves the merge commit
        # (the completion poll's 30 reads PLUS the post-window final
        # check and the three settling-probe state reads stay
        # pending — the MERGED observation belongs to the exhaustion
        # probe alone).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 34 + [merged()],
            cancel_reads=[
                {"autoMergeRequest": None, "state": "OPEN"},
                {"autoMergeRequest": None, "state": "OPEN"},
                {"autoMergeRequest": None, "state": "OPEN"},
                {"autoMergeRequest": {"id": 1}, "state": "OPEN"},
                {"autoMergeRequest": {"id": 1}, "state": "OPEN"},
                {"autoMergeRequest": {"id": 1}, "state": "OPEN"},
                {"autoMergeRequest": None, "state": "MERGED"},
            ],
        )

        # Then: the MERGED observation is named and the
        # pre-existing-gated revert path runs IMMEDIATELY on it —
        # landed-during-cancel revert PR opened — never the
        # propagation claim, never the exhaustion/cancellation
        # banners over a merge this guard watched land.
        self.assertEqual(code, 1)
        self.assertIn(
            "MERGED AT THE PACED EXHAUSTION PROBE of settling probe 3",
            out,
        )
        self.assertIn("thread 3835714804", out)
        self.assertIn("THE MERGE LANDED DURING CANCELLATION", out)
        self.assertIn("REVERT PR OPENED", out)
        self.assertNotIn("AUTO-MERGE PROPAGATED", out)
        self.assertNotIn("AUTO-MERGE STILL RE-ENABLED", out)
        self.assertNotIn("CANCEL UNCONFIRMED", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(argvs.count(
            "gh pr merge 39 --disable-auto -R RachaelsDen/UR-lorebook"
        ), 3)


if __name__ == "__main__":
    unittest.main()
