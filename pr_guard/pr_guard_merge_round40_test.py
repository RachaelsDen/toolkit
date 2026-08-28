"""pr_guard merge-act round-40 tests (PR #45 round 8).

Thread 3836092104 (P1) — transition-observed freshness on the
failed path: round 7 left one unsound FRESH verdict — UNEQUAL sha +
a committer date clearly AFTER the dispatch presumed OUR dispatch
landed it, but a GitHub commit clock AHEAD of the runner's gives a
HISTORICAL merge (stale-OPEN record, synthetic sha != real merge
sha) exactly that future-dated shape, so the mismatch/head
assertions or the automatic revert could fire on a merge the
invocation never dispatched. The failed path's ONLY fresh
attribution is now the OBSERVED TRANSITION: the reconciliation
(completion poll -> cancel -> settlement, one window) watched the
state read OPEN/pending after the dispatch and MERGED later — the
landing provably occurred inside this invocation's watch, so FRESH
is sound regardless of dates and shas (%ct is never even
consulted). NO transition — the MERGED state already present on the
FIRST post-dispatch read — is AMBIGUOUS whatever the date says
(including clearly-after), the manual banner and NO automatic
revert. The successful-dispatch path is unchanged (rc 0 bounds it).

PR #45 round 17 (thread 3836600782, P1 — the TERMINAL resolution):
the transition/corroboration machinery this suite's scenarios
exercised is RETIRED — the reviewer's rounds 7-17 chain proved
every between-reads attribution signal reproducible by ordered
cache snapshots of one historical timeline — so every
failed-dispatch landing below now pins the UNIFORM AMBIGUOUS
disposition (manual banner, NO revert), and the state-machine /
corroboration unit tests are deleted with the machinery.

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act; date_answers serves the %ct reads (None = unreadable).

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round40_test -v
"""

import unittest

from .pr_guard_merge_fixtures import HEAD, MERGE_SHA, WALL_NOW
from .pr_guard_merge_harness import MergeHarness, merged, pending, thread

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


class TransitionObservedTests(unittest.TestCase):
    def test_transition_observed_landing_is_uniformly_ambiguous(self):
        # Given: the dispatch failed only because the connection
        # died AFTER GitHub accepted the request — repinned at
        # round 9 (thread 3836149500): the poll reads the PR
        # still-OPEN on the BASELINE (first post-dispatch poll) AND
        # on the SECOND poll (the live post-baseline observation
        # that credits); repinned again at round 10 (thread
        # 3836217630): the baseline must itself be LIVE — the first
        # read >= one real poll interval past the dispatch — so the
        # poll reads still-OPEN on the pre-interval (cache-suspect,
        # ignored), live-baseline, and crediting polls before the
        # fourth read observes the landing, and the committer date
        # sits 3600s BEFORE the dispatch clock (round 7 would have
        # banner'd this ambiguous; the date must not matter now).
        surveys = iter(
            [[thread("11", "resolved")], [thread("21", "DANGER")]]
        )

        # When: the quiet watch's first survey then finds a DANGER
        # thread on the transition-attributed landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("")]),
            poll_states=[pending(), pending(), pending(), merged()],
            merge_rc=1,
            git_answers=date_answers(ct=int(WALL_NOW) - 3600),
        )

        # Then: repinned at round 17 (thread 3836600782) — the
        # observed OPEN -> MERGED sequence attributes NOTHING (the
        # reviewer's chain proved every between-reads signal
        # reproducible by ordered cache snapshots of one historical
        # timeline), so even this genuinely-fresh landing reports
        # the uniform AMBIGUOUS manual banner: NO assertions, NO
        # quiet watch, NO DANGER revert — a human attributes it
        # against the server timeline; exit 1.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("--format=%ct", " ".join(argvs))
        self.assertNotIn("POST-MERGE DANGER", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )


class NoTransitionAmbiguousTests(unittest.TestCase):
    def test_already_merged_first_read_failed_dispatch_is_ambiguous(
        self,
    ):
        # Given: the reviewer's exact scenario — a stale-OPEN
        # pre-dispatch record whose SYNTHETIC sha differs from the
        # real merge sha (open_record carries "e"*40, the landing is
        # MERGE_SHA), the dispatch fails ("already merged"), and the
        # FIRST post-dispatch read is ALREADY MERGED — no transition
        # was ever observed. The landing's %ct sits 3600s clearly
        # AFTER the dispatch clock: the future-dated HISTORICAL
        # merge a GitHub clock ahead of the runner's manufactures,
        # the exact shape round 7 certified FRESH.
        surveys = iter([[thread("11", "resolved")]])

        # When: the reconcile reads that already-merged,
        # future-dated landing on its first poll.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[merged()],
            merge_rc=1,
            git_answers=date_answers(ct=int(WALL_NOW) + 3600),
        )

        # Then: the uniform AMBIGUOUS banner (thread 3836600782,
        # round 17 — closing rounds 7-8's date verdicts and rounds
        # 9-16's transition arms): NO mismatch assertions, NO
        # automatic revert, exit 1, never CLEAN, and NO %ct read
        # runs at all (the date probe is deleted).
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836043653", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("--format=%ct", " ".join(argvs))
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("QUIET PERIOD", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )


if __name__ == "__main__":
    unittest.main()
