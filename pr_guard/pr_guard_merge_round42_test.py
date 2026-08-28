"""pr_guard merge-act round-42 tests (PR #45 round 10).

Thread 3836217630 (P1) — repeated cached OPEN reads stay ambiguous:
round 9 armed the transition baseline on the FIRST post-dispatch
poll, but a stale pre-dispatch OPEN record for an already-merged PR
can serve that read AND the next one (two reads inside one cache
window), so the baseline+credit pair still certified the cache's
eventual-consistency OPEN -> MERGED flip as a live observation and
the mismatch/DANGER auto-revert could fire on a historical merge.
The baseline is now the FIRST LIVE read — one occurring at least
ONE REAL POLL INTERVAL (wall clock) after the dispatch moment — and
reads inside the first interval arm and credit NOTHING: the
reviewer's two-immediate-reads-then-MERGED shape stays AMBIGUOUS,
while properly spaced reads (pre-interval, live baseline, credit,
then MERGED) attribute the landing FRESH.

Thread 3836217633 (P1) — an idempotent merge success is ambiguous:
with the same stale-OPEN record, `gh pr merge` on the already-merged
PR can exit 0 reporting "was already merged" (the idempotent no-op
success), and the successful-dispatch path treated rc 0 as OUR
landing bound — running the post-merge machinery on the historical
merge. An rc-0 dispatch whose output carries the no-op signature is
now classified into the FAILED-dispatch class for attribution (the
identity ladder applies; the ambiguous banner, no revert); only a
GENUINE rc 0 — no signature — keeps the rc-0 bounding.

Thread 3836217635 (P1) — truthful revert copy: the reconciliation
epilogue's completed-revert summary claimed the revert "already
undid" the landing while the revert PR is only OPEN; an operator
following that summary could leave the unsafe merge live. All copy
now states the revert PR is OPEN and must be merged by the operator
(the round-39 suite pins the epilogue line; the fixtures' fake
clock advances wall time with sleep so the live-read rule asserts
in exact fake seconds).

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

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round42_test -v
"""

import unittest

from .pr_guard_merge_fixtures import HEAD, WALL_NOW
from .pr_guard_merge_harness import MergeHarness, merged, pending, thread

RUNNER = MergeHarness()
OPEN_READ = {"autoMergeRequest": None, "state": "OPEN"}


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


class CachedBaselineTests(unittest.TestCase):
    def test_two_immediate_reads_then_merged_stay_ambiguous(self):
        # Given: the reviewer's exact scenario — the pre-dispatch
        # REST record is a STALE OPEN for an already-merged PR
        # (synthetic sha "e"*40 != the real MERGE_SHA) and the
        # dispatch fails; the operator interrupts the completion
        # wait IMMEDIATELY (the first poll read raises), so the
        # reconciliation cancel's own reads run inside the FIRST
        # poll interval: the cancel's verdict read at ~0s elapsed
        # and its CANCEL_RECHECK_SECS (5s) re-check — BOTH under
        # the 10s MERGE_POLL_INTERVAL. Under round 9 the first
        # read armed the baseline and the second CREDITED, so the
        # historical MERGED the settlement then observed was
        # certified fresh and auto-reverted (thread 3836217630's
        # finding: another cached read still provides no
        # merge-event provenance).
        surveys = iter([[thread("11", "resolved")]])

        # When: the cancel reads OPEN twice inside the first
        # interval and the settling watch's state read then reports
        # the historical MERGED.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[KeyboardInterrupt(), merged()],
            merge_rc=1,
            cancel_reads=[OPEN_READ, OPEN_READ],
            git_answers=date_answers(ct=int(WALL_NOW) + 3600),
        )

        # Then: the uniform AMBIGUOUS banner (thread 3836600782,
        # round 17) — the two immediate reads are one more shape the
        # chain proved unattributable, so NO fresh shortcut and NO
        # automatic revert of the possibly-historical merge; the
        # banner cites the chain's first-interval finding
        # (3836217630) and the original interrupt still propagates
        # (nonzero exit through the re-raise).
        self.assertIsNone(code)
        self.assertIsInstance(RUNNER.raised, KeyboardInterrupt)
        self.assertIn("INTERRUPTED DURING THE COMPLETION WAIT", out)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836217630", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("LANDED DURING CANCELLATION", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)

    def test_properly_spaced_reads_then_merged_is_ambiguous(self):
        # Given: the dispatch failed only because the connection
        # died AFTER GitHub accepted the request, and the reconcile
        # poll's reads are PROPERLY SPACED — the pre-interval read
        # (~0s, cache-suspect, ignored), the LIVE baseline at 10s,
        # the crediting still-OPEN read at 20s, and the landing on
        # the fourth read at 30s (thread 3836217630's live-read
        # rule in its fresh shape).
        surveys = iter(
            [[thread("11", "resolved")], [thread("11", "resolved")]]
        )

        # When: the reconcile observes that spaced sequence and the
        # quiet watch then completes clean.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[pending(), pending(), pending(), merged()],
            merge_rc=1,
        )

        # Then: repinned at round 17 (thread 3836600782) — the
        # properly-spaced live OPEN pair attributes NOTHING (the
        # chain proved every between-reads signal reproducible by
        # ordered cache snapshots of one historical timeline), so
        # the landing reports the uniform AMBIGUOUS manual banner:
        # NO assertions, NO quiet watch, NO revert; the banner still
        # cites the chain's 3836217630/3836149500 findings; exit 1.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836217630", out)
        self.assertIn("3836149500", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("--format=%ct", " ".join(argvs))
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )


class NoopDispatchTests(unittest.TestCase):
    def test_noop_success_with_historical_merged_is_ambiguous(self):
        # Given: the reviewer's exact scenario — the stale-OPEN
        # pre-dispatch record on an already-merged PR, but this
        # time `gh pr merge` takes GitHub's IDEMPOTENT path: it
        # exits 0 reporting "was already merged" (thread
        # 3836217633's no-op success; rc 0 alone used to bound the
        # landing as OURS), and the reconcile's first read exposes
        # the historical MERGED — the landing's %ct sits 3600s
        # clearly AFTER the dispatch clock.
        surveys = iter([[thread("11", "resolved")]])

        # When: the no-op-signature rc-0 dispatch is classified and
        # the reconcile observes the historical landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[merged()],
            merge_noop=True,
            git_answers=date_answers(ct=int(WALL_NOW) + 3600),
        )

        # Then: the classification banner names the no-op demotion
        # (rc 0 proves nothing — GitHub accepted no request from
        # THIS invocation), the landing is AMBIGUOUS through the
        # identity ladder — manual banner, NO automatic revert, NO
        # quiet watch, exit 1 — and MERGED CLEAN never prints over
        # a merge the invocation never dispatched.
        self.assertEqual(code, 1)
        self.assertIn(
            "MERGE COMMAND EXITED 0 WITHOUT DISPATCHING", out
        )
        self.assertIn("IDEMPOTENT NO-OP SUCCESS", out)
        self.assertIn("FAILED-dispatch class", out)
        self.assertIn("3836217633", out)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("--format=%ct", " ".join(argvs))
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("QUIET PERIOD", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )

    def test_genuine_rc0_dispatch_keeps_the_successful_path(self):
        # Given: a GENUINE rc-0 dispatch — no no-op signature in
        # the output — whose landing the poll observes (thread
        # 3836217633 keeps the rc-0 bounding for exactly this
        # shape: GitHub accepted THIS invocation's request).
        surveys = iter(
            [[thread("11", "resolved")], [thread("11", "resolved")]]
        )

        # When: the guarded merge completes through the ordinary
        # successful path.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[merged()],
        )

        # Then: no demotion banner, the full ordinary path runs
        # (quiet watch, MERGED CLEAN, exit 0) with no identity
        # ladder, no ambiguity, and no revert.
        self.assertEqual(code, 0)
        self.assertNotIn("WITHOUT DISPATCHING", out)
        self.assertNotIn("AMBIGUOUS LANDING", out)
        self.assertIn("MERGED CLEAN:", out)


class TruthfulRevertCopyTests(unittest.TestCase):
    def test_revert_pr_body_demands_the_operator_merge(self):
        # Given: a SUCCESSFUL dispatch whose quiet watch finds
        # DANGER, so the automatic revert opens its PR (thread
        # 3836217635: every piece of revert copy must state the PR
        # is OPEN and the operator must merge it). Repinned at round
        # 17 (thread 3836600782): the failed-dispatch shape this
        # test used to drive (a transition-attributed fresh landing)
        # is retired — the uniform ambiguous disposition never
        # reverts, so the copy rides the successful path's ordinary
        # DANGER coverage.
        surveys = iter(
            [[thread("11", "resolved")], [thread("21", "DANGER")]]
        )

        # When: the POST-MERGE DANGER revert opens the revert PR.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("")]),
            poll_states=[merged()],
        )

        # Then: the act exits nonzero with the PR open (never 0 —
        # an open revert PR is not a completed undo), and the PR
        # body's standing instruction to merge the revert PR
        # survives as the operative operator step.
        self.assertEqual(code, 1)
        self.assertNotIn("AMBIGUOUS LANDING", out)
        self.assertIn("POST-MERGE DANGER", out)
        self.assertIn("REVERT PR OPENED", out)
        self.assertIn("MERGE IT NOW to undo", out)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn("MERGE THIS REVERT IMMEDIATELY", create)
        self.assertNotIn("already undid", out)
        self.assertNotIn("MERGED CLEAN:", out)


if __name__ == "__main__":
    unittest.main()
