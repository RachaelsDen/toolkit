"""pr_guard merge-act round-44 tests (PR #45 round 12).

Thread 3836323283 (P1) — the paced OPEN probe of the settling
watch's re-disable EXHAUSTION path feeds transition tracking: round
11 wired eight read sites through the shared
pr_guard_common.apply_transition_read but not this ninth — with the
transition baseline still EMPTY (every earlier read inside the
first poll interval) the paced exhaustion probe can be the window's
FIRST LIVE read and return OPEN, and its untracked OPEN armed
nothing while the next loop read's OPEN merely ARMED the baseline
itself, so the landing the watch then read MERGED earned no
post-baseline credit and the identity gate denied the fresh
attribution. The probe now runs the helper: its OPEN arms the LIVE
baseline (a later loop OPEN credits, the MERGED after is FRESH);
unspaced it arms nothing and the landing stays AMBIGUOUS (round
10's cache rule).

Thread 3836323285 (P2) — the captured merge diagnostics are
EMITTED on the failure summary paths: capture_output=True (kept
for the round-10 no-op-signature classification) removed gh's
stdout/stderr from the terminal, so after the reconciliation the
operator saw only the numeric rc and lost the actionable GitHub
error. The nothing-landed summary and the reconciliation epilogue
both print the labeled, truncated capture.

The exhaustion-probe scenarios widen MERGE_POLL_INTERVAL (a
pr_guard_common module constant the helper reads at call time) so
the reviewer's first-live-read shape is reachable at exact fake
seconds: at the default 10s the watch's 5s-paced re-disable cycle
lands probe 2's state read exactly ON the interval boundary, and
the exhaustion probe is never the first live read.

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

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round44_test -v
"""

import unittest
from unittest import mock

from . import pr_guard_common
from .pr_guard_merge_fixtures import HEAD, WALL_NOW
from .pr_guard_merge_harness import MergeHarness, merged, pending, thread
from .pr_guard_settle_banners import MERGE_OUTPUT_PREVIEW, merge_output_note

RUNNER = MergeHarness()
OPEN_READ = {"autoMergeRequest": None, "state": "OPEN"}
AUTO_READ = {"autoMergeRequest": {"mergeMethod": "MERGE"},
             "state": "OPEN"}


def open_record(merge_commit_sha: str = ""):
    return {
        "head": {"sha": HEAD},
        "base": {"ref": "dev"},
        "state": "open",
        "merged": False,
        "merge_commit_sha": merge_commit_sha,
    }


def closed_read():
    return {
        "state": "CLOSED",
        "mergeCommit": None,
        "baseRefName": "dev",
        "headRefOid": HEAD,
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


def exhaustion_reads():
    # The cancel/settle opening reads (OPEN, OPEN, OPEN), the watch
    # probes 1-3 observing the RE-ENABLED autoMergeRequest (AUTO x3,
    # burning the two paced re-disables and arming the exhaustion
    # branch), then the exhaustion probe's FRESH OPEN (the last item
    # repeats forever — the post-continue probe 4's auto read is the
    # clean OPEN that keeps the watch probing to the landing).
    return [OPEN_READ, OPEN_READ, OPEN_READ, AUTO_READ, AUTO_READ,
            AUTO_READ, OPEN_READ]


class ExhaustionProbeTransitionTests(unittest.TestCase):
    def test_paced_exhaustion_probe_open_is_ambiguous(self):
        # Given: the failed dispatch was ACCEPTED (merge_rc=1), the
        # operator's interrupt lands ON the completion poll's first
        # read (wall 0s), and the reconciliation rides the cancel's
        # 0s/5s reads into the settling watch — where a competing
        # automation keeps RE-ENABLING auto-merge (probes 1-3 at
        # 5s/10s/15s, all inside the widened 17s first interval —
        # round 10's cache rule arms nothing), burning the two
        # paced re-disables. The exhaustion probe at wall 20s is
        # then the window's FIRST LIVE read (thread 3836323283:
        # round 11 never wired it through the helper).
        surveys = iter([[thread("11", "resolved")]])

        # When: the paced exhaustion probe reads the FRESH OPEN (the
        # last re-disable took — ARMS the LIVE baseline under the
        # round-12 fix) at 20s, and the post-continue loop read at
        # 20s reads OPEN again (ADJACENT to the arm: post-round-14
        # it no longer credits — thread 3836437095), so the credit
        # waits for the probes at 25s/30s/35s (still inside the
        # widened interval past the arm) and lands on the probe at
        # 40s (a full interval past the 20s arm) before the probe
        # at 45s reads the landing MERGED.
        with mock.patch.object(
            pr_guard_common, "MERGE_POLL_INTERVAL", 17.0
        ):
            code, out, argvs, events = RUNNER.run_guarded(
                surveys,
                iter([open_record("e" * 40)]),
                poll_states=[
                    KeyboardInterrupt(),
                    pending(), pending(), pending(), pending(),
                    pending(), pending(), pending(), pending(),
                    merged(),
                ],
                merge_rc=1,
                cancel_reads=exhaustion_reads(),
            )

        # Then: repinned at round 17 (thread 3836600782) — the
        # exhaustion probe and the spaced loop reads attribute
        # NOTHING (the chain proved every between-reads signal
        # reproducible by ordered cache snapshots of one historical
        # timeline), so the landing reports the uniform AMBIGUOUS
        # manual banner instead of reverting; the PROPAGATED
        # progress line still prints and the original interrupt
        # still propagates.
        self.assertIn(
            "AUTO-MERGE PROPAGATED at the paced exhaustion probe", out
        )
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

    def test_unspaced_exhaustion_probe_still_arms_nothing(self):
        # Given: the same interrupt/re-enable window with the first
        # interval widened past the whole exhaustion sequence (25s —
        # the cancel 0s/5s reads, the watch probes at 5s/10s/15s,
        # AND the paced exhaustion probe at 20s all sit INSIDE it),
        # so the round-10 cache rule keeps every one of them — the
        # exhaustion probe included — from arming or crediting.
        surveys = iter([[thread("11", "resolved")]])

        # When: the unspaced exhaustion probe reads OPEN (arms
        # nothing), the post-continue loop read at 20s reads OPEN
        # (unspaced too), and the probe at 25s reads the landing
        # MERGED with a future-dated committer timestamp.
        with mock.patch.object(
            pr_guard_common, "MERGE_POLL_INTERVAL", 25.0
        ):
            code, out, argvs, events = RUNNER.run_guarded(
                surveys,
                iter([open_record("e" * 40)]),
                poll_states=[
                    KeyboardInterrupt(),
                    pending(), pending(), pending(), pending(),
                    merged(),
                ],
                merge_rc=1,
                cancel_reads=exhaustion_reads(),
                git_answers=date_answers(ct=int(WALL_NOW) + 3600),
            )

        # Then: the uniform AMBIGUOUS banner (thread 3836600782,
        # round 17) — unspaced or paced alike, no read attributes
        # anything, so no fresh shortcut and NO automatic revert of
        # the possibly-historical merge; the original interrupt
        # still propagates.
        self.assertIsNone(code)
        self.assertIsInstance(RUNNER.raised, KeyboardInterrupt)
        self.assertIn(
            "AUTO-MERGE PROPAGATED at the paced exhaustion probe", out
        )
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


class MergeDiagnosticsTests(unittest.TestCase):
    def test_nothing_landed_summary_emits_the_captured_output(self):
        # Given: the merge command FAILED with a diagnostic on its
        # stderr (the fake dispatch's "boom") and the reconcile poll
        # then observes the PR CLOSED unmerged — the nothing-landed
        # failure summary path (thread 3836323285: the capture kept
        # for the round-10 no-op classification was never shown).
        surveys = iter([[thread("11", "resolved")]])

        # When: the act renders its failure summary.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[pending(), closed_read()],
            merge_rc=1,
        )

        # Then: the ORIGINAL MERGE ERROR summary is followed by the
        # clearly-labeled captured output — the operator sees WHY gh
        # pr merge failed, not just the numeric rc.
        self.assertEqual(code, 1)
        self.assertIn("MERGE DID NOT LAND", out)
        self.assertIn(
            "ORIGINAL MERGE ERROR: gh pr merge exited 1", out
        )
        self.assertIn(
            "MERGE COMMAND OUTPUT (captured stdout/stderr, thread "
            "3836323285)",
            out,
        )
        self.assertIn("boom", out)
        self.assertLess(
            out.index("ORIGINAL MERGE ERROR"),
            out.index("MERGE COMMAND OUTPUT"),
        )

    def test_reconciled_exit_summary_emits_the_captured_output(self):
        # Given: the same failed dispatch whose reconcile observes a
        # landing — repinned at round 17 (thread 3836600782): the
        # landing is the uniform AMBIGUOUS disposition (no revert
        # runs), so the epilogue the diagnostics ride is the
        # identity-gate summary.
        surveys = iter([[thread("11", "resolved")]])

        # When: the act renders the reconciliation epilogue for the
        # identity-gate disposition.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[pending()] * 11 + [merged()],
            merge_rc=1,
            cancel_reads=[OPEN_READ, OPEN_READ, OPEN_READ],
        )

        # Then: the identity-gate summary (NO revert PR exists, the
        # manual banner stands) is followed by the labeled captured
        # output naming the original dispatch failure.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertIn(
            "ORIGINAL MERGE ERROR: gh pr merge exited 1", out
        )
        self.assertIn("IDENTITY GATE above", out)
        self.assertIn("MERGE COMMAND OUTPUT", out)
        self.assertIn("boom", out)
        self.assertLess(
            out.index("IDENTITY GATE above"),
            out.index("MERGE COMMAND OUTPUT"),
        )

    def test_merge_output_note_truncates_and_skips_empty(self):
        # Given: the note builder's contract (thread 3836323285):
        # nothing captured prints nothing (a raised dispatch
        # captures no output), and an oversized capture is truncated
        # to a sane, labeled bound.

        # When/Then: empty and blank-only captures render no note.
        self.assertEqual(merge_output_note(""), "")
        self.assertEqual(merge_output_note("  \n "), "")
        # And: a short capture renders fully under its label.
        self.assertIn(
            "MERGE COMMAND OUTPUT", merge_output_note("gh: auth failed")
        )
        self.assertIn("gh: auth failed", merge_output_note("gh: auth failed"))
        # And: an oversized capture is truncated at the bound.
        note = merge_output_note("x" * (MERGE_OUTPUT_PREVIEW + 100))
        self.assertIn(
            f"[truncated at {MERGE_OUTPUT_PREVIEW} chars]", note
        )
        self.assertLess(len(note), MERGE_OUTPUT_PREVIEW + 200)


if __name__ == "__main__":
    unittest.main()
