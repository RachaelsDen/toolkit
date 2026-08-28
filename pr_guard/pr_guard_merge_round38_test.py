"""pr_guard merge-act round-38 tests (PR #45 round 6).

Thread 3836003345 (P1) — aged OPEN test-merge SHAs stay ambiguous:
round 5 let an equal-sha landing upgrade to PRE-EXISTING when its
committer date cleared the 300s skew margin,
but the reused synthetic object CARRIES ITS OLD test-merge creation
date — %ct dates the commit OBJECT, not the landing EVENT — so a
FRESH landing of an aged synthetic (any age beyond the margin) read
clearly-before and was certified pre-existing, skipping the
base/head assertions and the post-merge safety survey for exactly
the reuse this module anticipates. The equal-sha arm is now
ambiguous REGARDLESS of the date; the manual-check banner replaces
the upgrade on the reconcile AND cancel/settlement paths.

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act; date_answers serves the %ct reads.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round38_test -v
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


class AgedSyntheticEqualityTests(unittest.TestCase):
    def test_aged_synthetic_reuse_landing_is_ambiguous(self):
        # Given: the reviewer's exact scenario — the OPEN record
        # carries the SYNTHETIC test-merge sha and the object is
        # AGED far beyond the skew margin (its test-merge creation
        # sits 3600s before the dispatch), and the failed dispatch's
        # reconcile observes a landing EQUAL to it: round 5's
        # clearly-before test read this shape as pre-existing even
        # though the landing EVENT is fresh (an ACCEPTED-but-failed
        # dispatch landing by REUSING the aged object).
        surveys = iter([[thread("11", "resolved")]])

        # When: the failed dispatch reconciles into that equal,
        # aged-dated landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record(MERGE_SHA)]),
            poll_states=[merged()],
            merge_rc=1,
            git_answers=date_answers(ct=int(WALL_NOW) - 3600),
        )

        # Then: the uniform AMBIGUOUS banner (thread 3836600782,
        # round 17) — the aged-synthetic date is irrelevant because
        # NO date read runs (the date arms are deleted); manual
        # check, NO pre-existing verdict, NO automatic revert, exit
        # 1, never CLEAN.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836003345", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("--format=%ct", " ".join(argvs))
        self.assertNotIn("cat-file", " ".join(argvs))
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)

    def test_exactly_margin_aged_equality_stays_ambiguous(self):
        # Given: the boundary itself under equality — the object's
        # date sits EXACTLY the 300s margin before the dispatch (the
        # first age round 5 ever certified), and the landing equals
        # the OPEN record's sha: the boundary must not resurrect the
        # upgrade, because the aged-reuse shape is just as
        # unexcludable at 300s as at 3600s.
        surveys = iter([[thread("11", "resolved")]])

        # When: the failed dispatch reconciles into that equal,
        # boundary-aged landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record(MERGE_SHA)]),
            poll_states=[merged()],
            merge_rc=1,
            git_answers=date_answers(ct=int(WALL_NOW) - 300),
        )

        # Then: AMBIGUOUS — same uniform manual-check disposition
        # (thread 3836600782), no pre-existing verdict, no revert.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836003345", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)


if __name__ == "__main__":
    unittest.main()
