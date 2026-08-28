"""pr_guard merge-act round-43 tests (PR #45 round 11).

Thread 3836277960 (P1) — arm the transition baseline on later
cancellation reads: round 10 armed the LIVE baseline (the first
post-dispatch read >= one real poll interval past the dispatch) only
at the window's OPENING reads — the completion poll's own read and
the cancel loop's first read. When the completion wait is interrupted
before MERGE_POLL_INTERVAL elapses, those reads are all unspaced and
leave transition_baseline EMPTY; the disable-recheck and the queue
settlement reads then only CREDITED against a baseline that never
armed — so even a settlement that watched the PR read OPEN well past
the interval and merge right after passed transition_observed=False,
and the identity gate classified the fresh accepted landing AMBIGUOUS
(skipping the destination/head checks, the quiet survey, and the
automatic revert). Every post-dispatch read path — the cancel
recheck, the settle probes and re-probes, the settling watch, the
post-dequeue verification — now runs the SAME baseline-arming helper
(pr_guard_common.apply_transition_read): the first LIVE read arms the
baseline WHEREVER it happens to occur, and later reads credit/deny
consistently. Immediate-unspaced reads still arm nothing (the round-10
cache rule), so the reviewer's two-immediate-reads shape stays
AMBIGUOUS.

PR #45 round 17 (thread 3836600782, P1 — the TERMINAL resolution):
the transition/corroboration machinery this suite's scenarios
exercised is RETIRED — the reviewer's rounds 7-17 chain proved
every between-reads attribution signal reproducible by ordered
cache snapshots of one historical timeline — so every
failed-dispatch landing below now pins the UNIFORM AMBIGUOUS
disposition (manual banner, NO revert), and the state-machine /
corroboration unit tests are deleted with the machinery.

No network: the shared fake-gh/fake-git/fake-clock harness drives the
act; date_answers serves the %ct reads (None = unreadable). The fake
clock's WALL time advances with sleep, so the live-read rule asserts
in exact fake seconds (interrupt at ~0s wall, spacing from the
cancel/settle/watch cadences).

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round43_test -v
"""

import unittest

from .pr_guard_merge_fixtures import HEAD, WALL_NOW
from .pr_guard_merge_harness import MergeHarness, merged, pending, thread
from .pr_guard_merge_fixtures import queued_entry

RUNNER = MergeHarness()
OPEN_READ = {"autoMergeRequest": None, "state": "OPEN"}
MERGED_READ = {"autoMergeRequest": None, "state": "MERGED"}


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


class CancelReadArmingTests(unittest.TestCase):
    def test_interrupted_wait_first_cancel_read_spaced_is_ambiguous(
        self,
    ):
        # Given: the failed dispatch was ACCEPTED (merge_rc=1), and
        # the operator's interrupt lands ON the completion poll's
        # would-be FIRST LIVE read (wall 10s — the pre-interval read
        # at 0s observed OPEN but armed nothing, thread 3836217630),
        # so the reconciliation cancel inherits an EMPTY baseline
        # (round 9's "the interrupt beat the first poll read" shape)
        # — and its own FIRST read, also at wall 10s, is the window's
        # first LIVE one (thread 3836277960: it arms wherever it
        # occurs).
        surveys = iter([[thread("11", "resolved")]])

        # When: the cancel's first read (10s, LIVE) observes OPEN —
        # it ARMS the baseline — and the 5s-paced recheck (15s)
        # observes OPEN again (ADJACENT to the arm: post-round-14 it
        # no longer credits — thread 3836437095, one stale cache
        # window arming and crediting proves nothing), so the credit
        # waits for the settle probe's OPEN at 25s (a full interval
        # past the 10s arm) before the probe at 35s reads the
        # landing MERGED.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[pending(), KeyboardInterrupt()],
            merge_rc=1,
            cancel_reads=[OPEN_READ] * 4 + [MERGED_READ],
            queue_entries=[queued_entry()],
        )

        # Then: repinned at round 17 (thread 3836600782) — the
        # live first cancel read and the spaced settle-probe OPEN
        # attribute NOTHING (the chain proved every between-reads
        # signal reproducible by ordered cache snapshots of one
        # historical timeline), so the landing reports the uniform
        # AMBIGUOUS manual banner (citing the chain's 3836277960
        # every-read finding): NO revert, and the original
        # interrupt still propagates (nonzero exit through the
        # re-raise).
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
        self.assertIn("3836277960", out)

    def test_settle_probe_live_reads_are_ambiguous(self):
        # Given: the reviewer's exact scenario — the interrupt beats
        # the FIRST poll read (wall 0s, nothing armed), the cancel's
        # opening reads sit inside the first interval (0s and the 5s
        # recheck), and the queue settlement inherits the EMPTY
        # baseline; the merge-queue entry stays QUEUED with every
        # bounded dequeue failing, so the queue watch keeps probing.
        # Round 10 never armed on those probes — the landing they
        # watched go OPEN -> MERGED past the interval reached the
        # gate unattributed.
        surveys = iter([[thread("11", "resolved")]])

        # When: the settle probes observe OPEN at 5s (unspaced, arms
        # nothing), 15s (the window's FIRST LIVE read — ARMS the
        # baseline, thread 3836277960), and 25s (CREDITS the
        # transition), and the probe at 35s reads the landing MERGED.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[KeyboardInterrupt()],
            merge_rc=1,
            cancel_reads=[OPEN_READ] * 5 + [MERGED_READ],
            queue_entries=[queued_entry()],
        )

        # Then: repinned at round 17 (thread 3836600782) — the
        # settle probes' live OPEN pair attributes NOTHING, so the
        # accepted-but-failed dispatch's landing reports the uniform
        # AMBIGUOUS manual banner instead of reverting; the dequeue
        # attempt still ran (DEQUEUE FAILED) and the interrupt
        # still propagates.
        self.assertIn("DEQUEUE FAILED", out)
        self.assertIn("3836277960", out)
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

    def test_dequeue_and_settle_watch_probes_are_ambiguous(self):
        # Given: the same interrupt-inside-the-first-interval window
        # (nothing armed at 0s/5s), but the queue entry is REMOVED —
        # the dequeuePullRequest mutation succeeds and the re-probe
        # reads ABSENT with the PR still OPEN — so the POST-DEQUEUE
        # verification read and the settling watch's per-probe reads
        # carry the window from here.
        surveys = iter([[thread("11", "resolved")]])

        # When: the post-dequeue read (5s, unspaced, arms nothing)
        # reads OPEN, and the settling watch's probes then read
        # OPEN at 5s (unspaced), 10s (the FIRST LIVE read — ARMS,
        # thread 3836277960), 15s (ADJACENT to the arm — no longer
        # credits, thread 3836437095), 20s (a full interval past
        # the arm — CREDITS), and MERGED at 25s.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[
                KeyboardInterrupt(),
                pending(),
                pending(),
                pending(),
                pending(),
                merged(),
            ],
            merge_rc=1,
            cancel_reads=[OPEN_READ] * 3,
            queue_entries=[queued_entry(), None],
            dequeue_rc=0,
        )

        # Then: repinned at round 17 (thread 3836600782) — the
        # watch's live, spaced probes attribute NOTHING, so the
        # landing inside the settling window reports the uniform
        # AMBIGUOUS manual banner instead of reverting; the dequeue
        # still ran (QUEUE ENTRY DEQUEUED) and the interrupt still
        # propagates.
        self.assertIn("QUEUE ENTRY DEQUEUED", out)
        self.assertIn("3836277960", out)
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


class UnspacedStaysAmbiguousTests(unittest.TestCase):
    def test_immediate_unspaced_settle_read_still_arms_nothing(self):
        # Given: the interrupt beats the first poll read and every
        # read of the window sits INSIDE the first poll interval
        # (the cancel read at 0s, its 5s recheck, and the settle
        # probe at 5s) — the round-10 cache rule (thread 3836217630):
        # a stale-OPEN record can serve all of them, so NONE of them
        # is live evidence. The round-11 arming must stay LIVE-ONLY:
        # arming the new sites unconditionally would let this cached
        # sequence certify the historical MERGED the settle probe
        # then reads.
        surveys = iter([[thread("11", "resolved")]])

        # When: the settle probe's state read (5s, unspaced) reports
        # the landing MERGED with a future-dated committer timestamp.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[KeyboardInterrupt()],
            merge_rc=1,
            cancel_reads=[OPEN_READ, OPEN_READ, MERGED_READ],
            git_answers=date_answers(ct=int(WALL_NOW) + 3600),
        )

        # Then: the uniform AMBIGUOUS banner (thread 3836600782,
        # round 17) — no read anywhere in the window attributes
        # anything (the every-read finding, thread 3836277960, is
        # part of the chain the banner cites), so NO fresh shortcut
        # and NO automatic revert of the possibly-historical merge;
        # the original interrupt still propagates.
        self.assertIsNone(code)
        self.assertIsInstance(RUNNER.raised, KeyboardInterrupt)
        self.assertIn("INTERRUPTED DURING THE COMPLETION WAIT", out)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836600782", out)
        self.assertIn("3836277960", out)
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
