"""pr_guard merge-act round-36 tests (PR #45 round 4).

Thread 3835877361 (P1) — do not trust the OPEN sha after an
ambiguous dispatch: a fresh landing of an ACCEPTED-but-failed
dispatch can land REUSING the synthetic test-merge object the
stale OPEN record carried, so bare open-sha equality certified a
pre-existing merge and skipped the assertions/watch/revert for THIS
invocation's landing. The open-sha arm now applies only when the
sha PROVES a real merge commit through the canonical remote
(fetch + `git cat-file -t` = commit + a resolvable second parent);
a synthetic/unresolvable sha falls to the committer-date arm.

Thread 3835877364 (P1) — apply the identity evidence on the
cancellation paths: a stale OPEN record that persists through the
short failed-dispatch poll (the historical merge becoming visible
only during the timeout cancellation or interrupt settlement) used
to reach revert_landed_during_cancel with ONLY the round-29 trusted
arms. Every cancel/interrupt MERGED verdict now runs the SAME
shared pr_guard_identity ladder (open-sha/committer-date/ambiguous)
as the reconciliation path.

Thread 3835877366 (P1) — compare committer times at matching
precision: %ct is an INTEGER second while the dispatch clock is
fractional, so `committed < dispatch_ts` misread a merge at 100.9
against a dispatch at 100.8 as pre-existing. The comparison floors
the dispatch timestamp to seconds and treats the SAME second as
AMBIGUOUS (manual banner, no auto-revert); strictly-before is the
only pre-existing verdict. The FractionalClock fixture pins the
dispatch wall clock at WALL_NOW + 0.8 so a %ct of int(WALL_NOW) is
exactly the finding's same-second shape.

Thread 3835877368 (P2) — locale-independent single-parent probe:
the stderr-signature match broke under a non-English LC_MESSAGES,
reading every candidate unreadable. The probe is
`git rev-parse --verify --quiet FETCH_HEAD^2` classified by EXIT
CODE alone (rc 1 = proven single-parent — verified on git 2.55,
which prints NO stderr in the quiet form); a LOCALIZED-stderr
fixture at rc 1 must still classify as single-parent and reuse.

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act; the git_answers fixtures serve the synthetic-sha failure,
the committer-date reads, and the localized probe stderr.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round36_test -v
"""

import unittest

from .pr_guard_merge_fixtures import WALL_NOW, FakeClock
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
MERGED_CANCEL_READ = {"autoMergeRequest": None, "state": "MERGED"}


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


def open_record(merge_commit_sha: str = ""):
    return {
        "head": {"sha": HEAD},
        "base": {"ref": "dev"},
        "state": "open",
        "merged": False,
        "merge_commit_sha": merge_commit_sha,
    }


# Thread 3836092104 (PR #45 round 8): a completion read that proves
# NOTHING — an unreadable/unknown state, so the poll never observed
# the PR unmerged (the shape the ambiguous pins need).
def unknown_read():
    return {
        "state": "UNKNOWN",
        "mergeCommit": None,
        "baseRefName": "dev",
        "headRefOid": HEAD,
    }


# Thread 3835846318/3835877366: the identity gate's retired date
# evidence — kept as an inert fixture (the round-17 gate runs no
# date probe; ct serves the historical scenarios' git answers).
def date_answers(ct: int | None):
    def answers(argv, stdin):
        g = ["git", *argv[3:]] if argv[1:2] == ["-C"] else argv
        if g[:2] == ["git", "log"] and "--format=%ct" in g:
            if ct is None:
                return (1, "")
            return (0, f"{ct}\n")
        return None

    return answers


# Thread 3835877368: the patch-id reuse stages with a CONTROLLABLE
# QUIET --verify FETCH_HEAD^2 answer — (rc, stdout, stderr). The
# localized fixture serves rc 1 WITH a non-English fatal: under the
# rc-only rule the stderr is ignored, so rc 1 still proves a
# single-parent tip and the branch is REUSED.
def localized_probe_answers(parent2: tuple):
    fetched: list[bool] = []

    def answers(argv, stdin):
        g = ["git", *argv[3:]] if argv[1:2] == ["-C"] else argv
        if g[:2] == ["git", "fetch"]:
            fetched.append(True)
            return (0, "")
        if g[:2] == ["git", "diff"]:
            return (0, LOCAL_DIFF)
        if g[:2] == ["git", "patch-id"]:
            pid = PIDS.get((stdin or "").strip())
            if pid is None:
                return None
            return (0, f"{pid} 0000000000000000000000000000000000000000\n")
        if (
            g[:2] == ["git", "rev-parse"]
            and g[2:] == ["--verify", "--quiet", "FETCH_HEAD^2"]
        ):
            return parent2 if fetched else None
        return None

    return answers


class SyntheticOpenShaTests(unittest.TestCase):
    def test_open_sha_reuse_landing_is_ambiguous_manual_banner(self):
        # Given: the stale-OPEN record carries the SYNTHETIC
        # test-merge sha and the failed dispatch's reconcile observes
        # a landing EQUAL to it — thread 3835944058's reuse shape
        # (the commit OBJECT predates the dispatch, and an
        # ACCEPTED-but-failed request may have landed REUSING it, so
        # post-landing reachability proves nothing). Repinned at
        # round 17 (thread 3836600782): every failed-dispatch landing
        # is the ONE uniform AMBIGUOUS disposition.
        surveys = iter([[thread("11", "resolved")]])

        # When: the merge command fails ("already merged"), the
        # reconcile poll observes the equal landing, and its
        # committer date predates the dispatch-time wall clock by
        # 30s (within round 5's retired 300s margin).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record(MERGE_SHA)]),
            poll_states=[merged()],
            merge_rc=1,
            git_answers=date_answers(ct=int(WALL_NOW) - 30),
        )

        # Then: the uniform AMBIGUOUS banner — the manual-check
        # disposition with the chain citation, NO reachability probe
        # and NO date read (both are deleted attribution arms), NO
        # automatic revert (the landing may be this invocation's own
        # fresh reuse), exit 1, NO pre-existing verdict, never CLEAN.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3835944058", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("--format=%ct", " ".join(argvs))
        self.assertNotIn("cat-file", " ".join(argvs))
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)


class CancelPathIdentityTests(unittest.TestCase):
    def test_stale_open_timeout_cancel_banners_ambiguous_reuse(self):
        # Given: the stale-OPEN pre-dispatch record persists through
        # the SHORT failed-dispatch poll and the historical merge
        # becomes visible only during the timeout cancellation
        # (thread 3835877364's bypass: the int return preceded
        # merge_guarded's gate) — the landing EQUALS the kept
        # open-record sha. Repinned at round 17 (thread 3836600782):
        # every failed-dispatch landing is the ONE uniform AMBIGUOUS
        # disposition, whatever the observation path.
        surveys = iter([[thread("11", "resolved")]])

        # When: the cancel verification observes MERGED and the
        # landed-sha read resolves a merge EQUAL to the kept
        # open-record sha, with a committer date 1000s before the
        # dispatch (the aged-equality shape the retired date arms
        # once evaluated).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record(MERGE_SHA)]),
            poll_states=[unknown_read()] * 11 + [merged()],
            merge_rc=1,
            cancel_reads=[MERGED_CANCEL_READ],
            git_answers=date_answers(ct=int(WALL_NOW) - 1000),
        )

        # Then: the SHARED gate fires on the cancel path with the
        # uniform AMBIGUOUS banner (no date read runs), NO revert,
        # and the quiet watch never runs (exactly the closing
        # survey).
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836003345", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("--format=%ct", " ".join(argvs))
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("LANDED DURING CANCELLATION", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )

    def test_stale_open_interrupt_cancel_banners_ambiguous_reuse(self):
        # Given: the same stale-OPEN failed dispatch, but the
        # operator interrupts the completion wait — the
        # reconciliation cancel runs before the exception re-raises,
        # and ITS MERGED verdict is the equal-sha landing. Repinned
        # at round 17 (thread 3836600782): uniformly AMBIGUOUS on
        # the interrupt path too.
        surveys = iter([[thread("11", "resolved")]])

        # When: KeyboardInterrupt raises at the third completion poll
        # and the reconciliation cancel then observes MERGED, with
        # the landing EQUAL to the open-record sha and an aged
        # committer date the retired arms once evaluated.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record(MERGE_SHA)]),
            poll_states=[
                unknown_read(), unknown_read(), KeyboardInterrupt(),
                merged(),
            ],
            merge_rc=1,
            cancel_reads=[MERGED_CANCEL_READ],
            git_answers=date_answers(ct=int(WALL_NOW) - 1000),
        )

        # Then: the uniform AMBIGUOUS disposition on the interrupt
        # path — manual banner, NO revert, and the ORIGINAL
        # interrupt still propagates (nonzero exit through the
        # re-raise).
        self.assertIsNone(code)
        self.assertIsInstance(RUNNER.raised, KeyboardInterrupt)
        self.assertIn("INTERRUPTED DURING THE COMPLETION WAIT", out)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836003345", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("LANDED DURING CANCELLATION", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))


class LocaleFreeProbeTests(unittest.TestCase):
    def test_localized_stderr_rc1_still_proves_single_parent(self):
        # Given: the occupied candidate signatures exactly like the
        # legitimate earlier-retry branch (sha differs, patch-id
        # matches, first parent IS the base), but the operator runs
        # under a non-English LC_MESSAGES and the probe's stderr
        # carries a LOCALIZED fatal (thread 3835877368's shape — the
        # old stderr-signature match read this as unreadable).
        surveys = iter([[thread("11", "resolved")]])

        # When: the QUIET --verify probe answers rc 1 WITH the
        # localized stderr (real git's quiet form prints nothing;
        # the rc alone must decide).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_heads={BRANCH: OLD_REVERT},
            git_answers=localized_probe_answers(
                (
                    1,
                    "",
                    "Schwerer Fehler: unbekannte Referenz "
                    "»FETCH_HEAD^2«",
                )
            ),
        )

        # Then: rc 1 PROVES the single-parent tip regardless of the
        # stderr language — the branch is REUSED, no suffix push.
        self.assertEqual(code, 1)
        self.assertIn(f"REVERT BRANCH REUSED: refs/heads/{BRANCH}", out)
        self.assertIn("SINGLE-PARENT", out)
        self.assertIn("3835877368", out)
        self.assertIn(
            f"git -C {RUNNER.revert_tmp} rev-parse --verify --quiet "
            f"FETCH_HEAD^2",
            argvs,
        )
        self.assertNotIn("REVERT BRANCH SUFFIXED", out)
        self.assertNotIn("git push", " ".join(argvs))
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(f"--head {BRANCH}", create)
        self.assertIn("REVERT PR OPENED", out)


if __name__ == "__main__":
    unittest.main()
