"""pr_guard merge-act round-37 tests (PR #45 round 5).

Thread 3835944058 (P1) — capture OPEN-SHA provenance before
dispatch: the round-4 corroboration (canonical-remote fetch +
cat-file + second parent) ran only POST-LANDING, at which point the
object a fresh accepted-but-failed dispatch landed by REUSING is
already reachable through the base ref and merge-shaped — the probe
cannot discriminate this invocation's landing from a pre-existing
one, so it is REMOVED. The only provenance is the pre-dispatch
capture, and the ladder restructured around it: open-sha EQUAL +
committer date clearing the skew margin -> PRE-EXISTING;
open-sha EQUAL + anything else (including an UNREADABLE date) ->
AMBIGUOUS (manual banner, no auto-revert).

Thread 3835944061 (P1) — cross-clock committer-date comparisons:
the dispatch instant is the LOCAL runner's time.time() while %ct is
GitHub's commit clock; a runner clock ahead of GitHub's makes a
FRESH GitHub-authored merge read committed-before-dispatch. (Repinned
at PR #45 round 7, thread 3836043653: round 5 answered with a
300s margin — >=300s of precedence certified PRE-EXISTING — but NO
fixed margin bounds real-world divergence, so the by-date
pre-existing verdict is RETIRED: the failed path's two dispositions
are UNEQUAL-sha + clearly-after -> FRESH, everything else ->
AMBIGUOUS.)

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act; date_answers serves the %ct reads.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round37_test -v
"""

import unittest

from .pr_guard_merge_fixtures import HEAD, MERGE_SHA, WALL_NOW
from .pr_guard_merge_harness import MergeHarness, merged, thread

RUNNER = MergeHarness()


def open_record(merge_commit_sha: str = ""):
    return {
        "head": {"sha": HEAD},
        "base": {"ref": "dev"},
        "state": "open",
        "merged": False,
        "merge_commit_sha": merge_commit_sha,
    }


def date_answers(ct: int | None):
    def answers(argv, stdin):
        g = ["git", *argv[3:]] if argv[1:2] == ["-C"] else argv
        if g[:2] == ["git", "log"] and "--format=%ct" in g:
            if ct is None:
                return (1, "")
            return (0, f"{ct}\n")
        return None

    return answers


class OpenShaProvenanceTests(unittest.TestCase):
    def test_resolved_reuse_landing_is_ambiguous(self):
        # Given: the OPEN record's sha names an object that WOULD
        # corroborate post-landing (the gitfake default resolves
        # everything) — the exact shape the round-4 probe misread:
        # the failed dispatch was ACCEPTED and GitHub landed by
        # REUSING that object, so the landing is fresh yet equal,
        # reachable, and merge-shaped (thread 3835944058).
        surveys = iter([[thread("11", "resolved")]])

        # When: the reconcile observes the equal landing with its
        # committer date 60s before the dispatch (inside the margin
        # — the reused object was built during this invocation's
        # pre-flight).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record(MERGE_SHA)]),
            poll_states=[merged()],
            merge_rc=1,
            git_answers=date_answers(ct=int(WALL_NOW) - 60),
        )

        # Then: the uniform AMBIGUOUS banner (thread 3836600782,
        # round 17) — manual check, NO reachability corroboration
        # and NO date read run (both are deleted attribution arms),
        # NO automatic revert, exit 1, never CLEAN.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3835944058", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("--format=%ct", " ".join(argvs))
        self.assertNotIn("cat-file", " ".join(argvs))
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)

    def test_reuse_with_unreadable_date_is_ambiguous(self):
        # Given: the same equal-shape landing, but the %ct probe is
        # UNREADABLE — the equality cannot be upgraded and cannot be
        # discarded either; the disposition stays AMBIGUOUS.
        surveys = iter([[thread("11", "resolved")]])

        # When: the date read fails for the equal landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record(MERGE_SHA)]),
            poll_states=[merged()],
            merge_rc=1,
            git_answers=date_answers(ct=None),
        )

        # Then: the uniform AMBIGUOUS banner — an unreadable date is
        # now indistinguishable because NO date read runs at all
        # (thread 3836600782, round 17); manual check, never a
        # pre-existing claim, never an automatic revert.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3835944058", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)


if __name__ == "__main__":
    unittest.main()
