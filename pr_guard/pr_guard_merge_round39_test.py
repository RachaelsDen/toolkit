"""pr_guard merge-act round-39 tests (PR #45 round 7).

Thread 3836043653 (P1) — a fixed skew margin is not merge
attribution: round 5 let a committer date >= 300s before the
dispatch certify PRE-EXISTING on the FAILED-dispatch path, but the
runner clock and GitHub's commit clock are UNSYNCHRONIZED and a
runner >= 300s AHEAD of GitHub's makes a FRESH GitHub-authored
merge read committed clearly BEFORE the local dispatch by more than
any fixed margin — so the tolerance never separated fresh from
pre-existing and the by-date PRE-EXISTING verdict is RETIRED. The
failed path now has EXACTLY TWO dispositions: UNEQUAL sha + a date
clearly AFTER the dispatch -> FRESH (the ordinary post-merge path,
normal revert coverage); everything else (equal sha, ANY
not-clearly-after date, unreadable evidence) -> the AMBIGUOUS
manual banner, NO automatic revert. The successful-dispatch path is
UNCHANGED: rc 0 itself bounds the landing to after-dispatch, so the
date arms never even run there.

Thread 3836043658 (P1) — distinct revert/identity-gate exits:
guarded_revert returned 1 for completed reverts AND the identity
gate's no-revert exits, and merge_guarded treated every int as "the
revert completed" — printing "the revert above already undid it"
over a gated exit (the stale-OPEN/equal-SHA cancel path emitted both
"NO automatic revert runs" and the opposite success claim) and over
FAILED reverts alike. The result contract is now DISTINCT — rc 0 =
revert COMPLETED, rc 3 = identity-gate no-revert (banner already
printed), rc 1 = revert FAILED — and merge_guarded's final handling
branches on the codes: each exit renders its own summary line, and
a gated exit reports the manual banner WITHOUT claiming a revert PR
exists.

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act; date_answers serves the %ct reads (None = unreadable).

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round39_test -v
"""

import unittest
from contextlib import redirect_stdout
from io import StringIO

from .pr_guard_common import reconciled_exit_summary
from .pr_guard_merge_fixtures import HEAD, MERGE_SHA, WALL_NOW
from .pr_guard_merge_harness import MergeHarness, merged, pending, thread

RUNNER = MergeHarness()
# Thread 3836501981 -> 3836565818 (PR #45 rounds 15-16): the
# landing cancel read carries a corroborating stamp (advanced
# past the pending() baseline's own — same-clock evidence).
from .pr_guard_merge_fixtures import iso_at
MERGED_CANCEL_READ = {"autoMergeRequest": None,
                      "state": "MERGED",
                      "updatedAt": iso_at(3600.0)}


# Thread 3836092104 (PR #45 round 8): a completion read that proves
# NOTHING — unreadable/unknown, so the poll never observed the PR
# unmerged and no transition attribution exists (an OPEN read
# anywhere would attribute the later MERGED fresh).
def unknown_read():
    return {
        "state": "UNKNOWN",
        "mergeCommit": None,
        "baseRefName": "dev",
        "headRefOid": HEAD,
    }


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


class AheadClockFreshMergeTests(unittest.TestCase):
    def test_ahead_clock_fresh_merge_beyond_margin_is_ambiguous(self):
        # Given: the reviewer's exact scenario — the runner clock
        # sits AHEAD of GitHub's, so a FRESH GitHub-authored merge
        # of the ACCEPTED-but-failed dispatch reads committed 3600s
        # BEFORE the local dispatch timestamp (far beyond round 5's
        # 300s margin), and the stale-OPEN record carried NO sha
        # (the landing mints a NEW object, so no equality either).
        surveys = iter([[thread("11", "resolved")]])

        # When: the failed dispatch's reconcile observes that
        # clearly-before-dated fresh landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("")]),
            poll_states=[merged()],
            merge_rc=1,
            git_answers=date_answers(ct=int(WALL_NOW) - 3600),
        )

        # Then: the uniform AMBIGUOUS banner (thread 3836600782,
        # round 17) — the ahead-clock date is irrelevant because NO
        # date read runs (the date arms are deleted; the banner
        # still cites the chain's 3836043653 clock-skew finding), NO
        # pre-existing verdict, NO automatic revert, exit 1, never
        # CLEAN.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836043653", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("--format=%ct", " ".join(argvs))
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )

    def test_successful_dispatch_path_is_unchanged(self):
        # Given: a SUCCESSFUL dispatch (rc 0 — the command's
        # acceptance itself bounds the landing to after-dispatch)
        # whose landing the fixture dates 3600s BEFORE the dispatch
        # clock: the successful path's pre-existing check is the
        # trusted arms alone, so the date arms must never run.
        surveys = iter(
            [[thread("11", "resolved")], [thread("11", "resolved")]]
        )

        # When: the guarded merge completes against that old-dated
        # landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("")]),
            poll_states=[merged()],
            git_answers=date_answers(ct=int(WALL_NOW) - 3600),
        )

        # Then: the ORDINARY path — the %ct probe never runs (no
        # date consulted), the quiet watch completes, MERGED CLEAN,
        # exit 0.
        self.assertEqual(code, 0)
        self.assertNotIn("%ct", " ".join(argvs))
        self.assertNotIn("AMBIGUOUS LANDING", out)
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertIn("MERGED CLEAN:", out)


class DistinctExitTests(unittest.TestCase):
    def test_identity_gate_exit_renders_banner_not_revert_claim(self):
        # Given: the reviewer's exact scenario — the FAILED dispatch
        # times out still-unreadable and the cancellation observes a
        # landing EQUAL to the stale-OPEN record's sha, which the
        # identity gate classifies AMBIGUOUS (round 6's contract):
        # round 6's rc-1 flowed into merge_guarded's every-int
        # completed-revert handling and printed "the revert above
        # already undid it" over the banner's "NO automatic revert
        # runs". Repinned at round 8 (thread 3836092104): the
        # completion reads must stay UNREADABLE — an OPEN read
        # anywhere would attribute the landing fresh through the
        # observed transition, and the gate would pass.
        surveys = iter([[thread("11", "resolved")]])

        # When: the timeout cancel's MERGED verdict gates ambiguous.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record(MERGE_SHA)]),
            poll_states=[unknown_read()] * 11 + [merged()],
            merge_rc=1,
            cancel_reads=[MERGED_CANCEL_READ],
            git_answers=date_answers(ct=int(WALL_NOW) - 1000),
        )

        # Then: the gate's OWN summary line renders — the manual
        # banner stands, NO revert PR is claimed to exist, and the
        # completed-revert line NEVER prints; exit 1, no revert
        # plumbing.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("NO automatic revert ran and NO revert PR exists", out)
        self.assertIn("3836043658", out)
        self.assertNotIn("revert above already undid it", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)

    def test_completed_revert_exit_renders_open_pr_action_required(self):
        # Given: thread 3836600782 (PR #45 round 17, P1) retired the
        # transition attribution, so a FAILED dispatch's landing can
        # no longer reach the revert (every such landing is the
        # uniform AMBIGUOUS disposition) and the completed-revert
        # epilogue is pinned here as a DIRECT call instead of the
        # end-to-end shape (rounds 7-10 drove it through the now-
        # impossible fresh-attributed landing). The copy contract
        # stands: thread 3836217635 (round 10) — the completed arm
        # must state the revert PR is OPEN and an OPERATOR must
        # merge it, never the retired "already undid it" claim.
        out = StringIO()

        # When: a completed-revert disposition renders under a
        # failed merge command.
        with redirect_stdout(out):
            reconciled_exit_summary(0, 1)

        # Then: the completed-revert summary renders its OWN
        # action-required line — the revert PR IS OPEN, an operator
        # must merge it, the landing is NOT yet undone.
        text = out.getvalue()
        self.assertIn("gh pr merge exited 1", text)
        self.assertIn("the REVERT PR IS OPEN", text)
        self.assertIn("ACTION REQUIRED", text)
        self.assertIn("OPERATOR must merge that revert PR", text)
        self.assertIn("3836217635", text)
        self.assertNotIn("already undid", text)
        self.assertNotIn("IDENTITY GATE above", text)
        self.assertNotIn("AUTOMATIC REVERT FAILED", text)

    def test_failed_revert_exit_renders_failure_summary(self):
        # Given: the failed-revert epilogue pinned DIRECTLY (round
        # 17, thread 3836600782, retired the end-to-end shape — a
        # failed dispatch's landing never reverts now); the contract
        # is round 6/7's: a FAILED revert disposition renders its
        # OWN line, never a completed-revert claim over it.
        out = StringIO()

        # When: a failed-revert disposition renders under a failed
        # merge command.
        with redirect_stdout(out):
            reconciled_exit_summary(1, 1)

        # Then: the FAILED-revert summary renders its OWN line —
        # NOTHING was undone — and the completed-revert claim NEVER
        # prints over it.
        text = out.getvalue()
        self.assertIn("gh pr merge exited 1", text)
        self.assertIn("AUTOMATIC REVERT FAILED", text)
        self.assertIn("NOTHING was undone", text)
        self.assertIn("3836043658", text)
        self.assertNotIn("revert above already undid it", text)
        self.assertNotIn("REVERT PR IS OPEN", text)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("MERGED CLEAN:", out)


if __name__ == "__main__":
    unittest.main()
