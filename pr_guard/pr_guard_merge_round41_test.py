"""pr_guard merge-act round-41 tests (PR #45 round 9).

Thread 3836149500 (P1) — the post-dispatch-only transition
baseline: round 8's observed-transition shortcut credited ANY
post-dispatch OPEN read before the MERGED verdict, but a stale
pre-dispatch OPEN record (an already-merged PR) can persist ONE
post-dispatch poll before the cache flips to the historical MERGED
— that first poll's OPEN is the PRE-DISPATCH-CACHED value, not a
live observation, and the OPEN -> MERGED "flip" is eventual
consistency, not a merge event inside the watch (round 8 certified
it FRESH and ran the mismatch/DANGER auto-revert on a historical
merge this invocation never dispatched). The transition BASELINE is
now the FIRST post-dispatch poll's own read: the baseline never
credits, the credit requires the baseline itself to have read
OPEN/pending, and only an OPEN/pending read AFTER the baseline — a
live observation one full poll interval past the dispatch —
attributes a later MERGED fresh. The reviewer's stale shape
(stale-OPEN persisting one poll, then the historical MERGED) earns
no credit and stays AMBIGUOUS (the manual banner, NO automatic
revert); the live shape (baseline OPEN, a LATER poll still OPEN,
then MERGED) is FRESH (the ordinary post-merge path with its
revert coverage).

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

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round41_test -v
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


class StaleBaselineTests(unittest.TestCase):
    def test_stale_open_persisting_one_poll_then_merged_is_ambiguous(
        self,
    ):
        # Given: the reviewer's exact scenario — the pre-dispatch
        # REST record is a STALE OPEN for an already-merged PR
        # (synthetic sha "e"*40 != the real MERGE_SHA), the dispatch
        # fails ("already merged"), and the stale OPEN persists ONE
        # post-dispatch poll before the cache flips to the
        # historical MERGED; the landing's %ct sits 3600s clearly
        # AFTER the dispatch clock (the future-dated historical
        # shape a GitHub clock ahead of the runner's manufactures).
        surveys = iter([[thread("11", "resolved")]])

        # When: the reconcile's FIRST post-dispatch read serves the
        # stale OPEN (the transition baseline) and the second read
        # exposes the historical MERGED.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[pending(), merged()],
            merge_rc=1,
            git_answers=date_answers(ct=int(WALL_NOW) + 3600),
        )

        # Then: the uniform AMBIGUOUS banner (thread 3836600782,
        # round 17) — the stale-persisting baseline is one more shape
        # the chain proved unattributable, so NO fresh shortcut, NO
        # mismatch assertions or automatic revert; the banner cites
        # the chain (3836149500 among them) and NO %ct read runs.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836149500", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("--format=%ct", " ".join(argvs))
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("QUIET PERIOD", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )


class LiveTransitionTests(unittest.TestCase):
    def test_live_open_after_baseline_then_merged_is_ambiguous(self):
        # Given: the dispatch failed only because the connection
        # died AFTER GitHub accepted the request — the reconcile's
        # polls read the PR genuinely OPEN past the dispatch;
        # repinned at round 10 (thread 3836217630): the BASELINE is
        # the first LIVE read (>= one real poll interval past the
        # dispatch — reads inside the interval may be the
        # pre-dispatch cache and never arm or credit), so the poll
        # reads still-OPEN on the pre-interval read (ignored), the
        # live BASELINE (poll 2), and the crediting post-baseline
        # read (poll 3) before the landing, and the committer date
        # sits 3600s BEFORE the dispatch clock (dates must not
        # matter).
        surveys = iter(
            [[thread("11", "resolved")], [thread("21", "DANGER")]]
        )

        # When: the quiet watch's first survey finds a DANGER thread
        # on the transition-attributed landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("")]),
            poll_states=[pending(), pending(), pending(), merged()],
            merge_rc=1,
            git_answers=date_answers(ct=int(WALL_NOW) - 3600),
        )

        # Then: repinned at round 17 (thread 3836600782) — the
        # live OPEN pair attributes NOTHING (the chain proved every
        # between-reads signal reproducible by ordered cache
        # snapshots of one historical timeline), so the landing
        # reports the uniform AMBIGUOUS manual banner: NO
        # assertions, NO DANGER revert — a human attributes it; the
        # banner still cites the chain's 3836217630/3836149500
        # cache-baseline findings; exit 1.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836217630", out)
        self.assertIn("3836149500", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("POST-MERGE DANGER", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("--format=%ct", " ".join(argvs))
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )


if __name__ == "__main__":
    unittest.main()
