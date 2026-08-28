"""pr_guard merge-act round-45 tests (PR #45 round 13).

Thread 3836380780 (P1) — credit transitions from a PENDING
baseline: an early interrupt leaves the baseline empty and the
first live cancellation read can return PENDING (an OPEN PR with
an active auto-merge request), but round 12's arming stored the raw
"PENDING" while the credit arm still required baseline == "OPEN" —
so repeated live PENDING/OPEN reads followed by MERGED never earned
the credit and the fresh accepted landing was classified AMBIGUOUS.
A live PENDING arm now NORMALIZES to "OPEN" (PENDING is as live as
OPEN: both are UNMERGED states); UNKNOWN/MERGED arms keep their raw
verdicts and still never credit.

Thread 3836380790 (P1) — preserve transition evidence across the
settling watch: the nested watch armed/credited its OWN locals,
which died with its REAPPEARED/None returns (the pair was threaded
as immutable values), so the outer re-probe re-armed from empty and
the landing the window then read MERGED stayed unattributed. The
watch (and the dequeue flow that re-enters it) now update the
caller's SHARED pr_guard_transition.TransitionEvidence holder at
each probe through the same apply_transition_read helper, so a
REAPPEARED return still carries the armed-baseline evidence for the
outer decision.

Thread 3836380793 (P1) — contain failures in the diagnostic
timestamp probe: an interrupt or OSError from the committer-date
probe (the fetch, the log, or the canonical_remote resolution)
escaped the identity gate — which runs AFTER the completion-wait
exception envelope — leaving the guard dead with NO output after
the merge had landed. Every stage of the reporting-only probe is
contained as an UNREADABLE DATE (the AMBIGUOUS arm — exactly what
an unreadable date means); the exception never propagates.

PR #45 round 17 (thread 3836600782, P1 — the TERMINAL resolution):
the transition/corroboration machinery this suite's scenarios
exercised is RETIRED — the reviewer's rounds 7-17 chain proved
every between-reads attribution signal reproducible by ordered
cache snapshots of one historical timeline — so every
failed-dispatch landing below now pins the UNIFORM AMBIGUOUS
disposition (manual banner, NO revert), and the state-machine /
corroboration unit tests are deleted with the machinery.

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act; the round-45 fixtures raise from the diagnostic fetch.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round45_test -v
"""

import unittest

from .pr_guard_merge_fixtures import MERGE_SHA
from .pr_guard_merge_harness import MergeHarness, merged, pending, thread

RUNNER = MergeHarness()
OPEN_READ = {"autoMergeRequest": None, "state": "OPEN"}
# Thread 3836380780: the reviewer's first live read — an OPEN PR
# whose dispatch-time auto-merge request is still ACTIVE (the
# read_pending_state verdict for this shape is PENDING).
PENDING_READ = {"autoMergeRequest": {"mergeMethod": "MERGE"},
                 "state": "OPEN"}
MERGED_CANCEL_READ = {"autoMergeRequest": None,
                      "state": "MERGED"}


def open_record(merge_commit_sha: str = ""):
    return {
        "head": {"sha": "b979176095b9dd6b6f8e989ed460feab9ce0abc4"},
        "base": {"ref": "dev"},
        "state": "open",
        "merged": False,
        "merge_commit_sha": merge_commit_sha,
    }


# Thread 3836380793: a git_answers fixture whose landing-sha FETCH
# raises — the diagnostic probe's first stage. Every other argv
# falls through to the harness defaults (the canonical `git
# remote -v` still resolves origin, so the FETCH is what raises).
def raising_fetch(exc: BaseException):
    def answers(argv, stdin):
        g = ["git", *argv[3:]] if argv[1:2] == ["-C"] else argv
        if g[:2] == ["git", "fetch"] and MERGE_SHA in g:
            raise exc
        return None

    return answers


class PendingBaselineTests(unittest.TestCase):
    def test_pending_baseline_window_is_ambiguous(self):
        # Given: the failed dispatch was ACCEPTED (merge_rc=1), the
        # operator's interrupt lands ON the completion poll's first
        # read (wall 0s), and the reconciliation rides the cancel's
        # 0s/5s reads into the queue watch — the merge-queue entry
        # stays QUEUED (the dequeue mutation fails, the bounded
        # watch carries it), so the settle probes read at
        # 5s/15s/25s/35s and the FIRST LIVE read (probe 2 at 15s,
        # past the 10s interval) is the reviewer's PENDING one.
        surveys = iter([[thread("11", "resolved")]])

        # When: probe 2's live PENDING ARMS the baseline (normalized
        # to OPEN — round 12 stored the raw "PENDING"), probe 3's
        # live OPEN CREDITS the transition, and probe 4 reads the
        # landing MERGED.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[KeyboardInterrupt()],
            merge_rc=1,
            cancel_reads=[
                OPEN_READ, OPEN_READ, OPEN_READ,
                PENDING_READ, OPEN_READ, MERGED_CANCEL_READ,
            ],
            queue_entries=[{"state": "QUEUED"}],
        )

        # Then: repinned at round 17 (thread 3836600782) — the
        # live PENDING reads attribute NOTHING (the chain proved
        # every between-reads signal reproducible by ordered cache
        # snapshots of one historical timeline; the PENDING finding
        # 3836380780 is part of it), so the landing reports the
        # uniform AMBIGUOUS manual banner instead of reverting; the
        # original interrupt still propagates.
        self.assertIn("3836380780", out)
        self.assertIsNone(code)
        self.assertIsInstance(RUNNER.raised, KeyboardInterrupt)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("LANDED DURING CANCELLATION", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )


class NestedWatchEvidenceTests(unittest.TestCase):
    def test_reappeared_return_lands_ambiguous(self):
        # Given: the same interrupt window, but the queue entry
        # reads ABSENT at the settle probe and the settling watch's
        # FIRST probe (state at 5s, unspaced — arms nothing), while
        # the watch's SECOND probe at 10s is the window's FIRST LIVE
        # read (OPEN — it ARMS the baseline INSIDE the watch) and
        # the queue entry REAPPEARS on that same probe — the watch
        # returns the REAPPEARED sentinel, round 12's evidence loss.
        surveys = iter([[thread("11", "resolved")]])

        # When: the outer re-probe at 10s reads OPEN — post-round-14
        # it is ADJACENT to the arm (same instant), so it no longer
        # credits (thread 3836437095: one stale cache window arming
        # AND crediting proves nothing) — the fresh QUEUED dispatches
        # the failing dequeue, and the settle probe at 20s reads the
        # OPEN a full interval past the watch's arm (CREDITS through
        # the SHARED holder) before the probe at 30s reads the
        # landing MERGED.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[KeyboardInterrupt(), pending(), pending()],
            merge_rc=1,
            cancel_reads=[
                OPEN_READ, OPEN_READ, OPEN_READ, OPEN_READ,
                OPEN_READ, OPEN_READ, MERGED_CANCEL_READ,
            ],
            queue_entries=[None, None, {"state": "QUEUED"}],
        )

        # Then: repinned at round 17 (thread 3836600782) — the
        # watch's reads (whatever they accumulated before the
        # REAPPEARED return) attribute NOTHING, so the MERGED at 30s
        # reports the uniform AMBIGUOUS manual banner instead of
        # reverting; the QUEUE RE-PROBE still runs on the fresh
        # reads, and the original interrupt still propagates.
        self.assertIn("QUEUE ENTRY REAPPEARED at settling probe 2", out)
        self.assertIn("QUEUE RE-PROBE", out)
        self.assertIsNone(code)
        self.assertIsInstance(RUNNER.raised, KeyboardInterrupt)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("LANDED DURING CANCELLATION", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )


if __name__ == "__main__":
    unittest.main()
