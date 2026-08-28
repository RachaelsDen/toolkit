"""pr_guard merge-act round-46 tests (PR #45 round 14).

Threads 3836437093/3836437095/3836437098/3836437100 — ONE coherent
revision of the transition baseline/credit state machine (moved HOME
to pr_guard_transition beside the shared holder; common was back at
the 250 pure-LOC ceiling):

- 3836437093 (P1): an UNKNOWN first live read is a TRANSIENT, never
  a frozen baseline — round 13 stored the raw "UNKNOWN" permanently,
  so later valid OPEN/PENDING reads could neither replace it nor
  earn the credit and the fresh accepted landing rendered AMBIGUOUS.
- 3836437100 (P1): a transient MERGED-from-cache first live read
  (nonempty, not OPEN/PENDING) must not PIN the baseline either —
  later live OPEN/PENDING reads RE-ARM (an armed baseline is
  sticky; rearm replaces only unknown/transient states), so a real
  OPEN -> MERGED after a cache blip still earns the fresh
  attribution.
- 3836437095 (P1): the arming read and the crediting read must each
  be live AND separated from EACH OTHER by a real interval — the
  baseline timestamp is recorded (baseline_ts) and the credit
  requires elapsed >= interval since the BASELINE too. A single
  read at the interval boundary arming plus a same-instant read
  crediting proves nothing (the reviewer's cancel-recheck ->
  adjacent settle-read shape over a stale cached OPEN).
- 3836437098 (P2): every interval is measured on time.monotonic()
  — a wall-clock jump (VM clock correction / resume) cannot fake
  the spacing; the wall-clock dispatch_ts survives only for the
  identity gate's committer-date REPORTING comparisons.

PR #45 round 17 (thread 3836600782, P1 — the TERMINAL resolution):
the transition/corroboration machinery this suite's scenarios
exercised is RETIRED — the reviewer's rounds 7-17 chain proved
every between-reads attribution signal reproducible by ordered
cache snapshots of one historical timeline — so every
failed-dispatch landing below now pins the UNIFORM AMBIGUOUS
disposition (manual banner, NO revert), and the state-machine /
corroboration unit tests are deleted with the machinery.

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act; date_answers serves the %ct reads. The rearm scenarios
ride the completion poll (the MERGED-with-empty-mergeCommit read is
the thread-3834590326 bounded pending state the poll TOLERATES
while it keeps polling — the one read site an inconclusive verdict
does not abort).

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round46_test -v
"""

import unittest

from .pr_guard_merge_fixtures import HEAD, WALL_NOW
from .pr_guard_merge_harness import FakeClock, MergeHarness, merged
from .pr_guard_merge_harness import pending, thread

RUNNER = MergeHarness()
OPEN_READ = {"autoMergeRequest": None, "state": "OPEN"}
PENDING_READ = {"autoMergeRequest": {"mergeMethod": "MERGE"}, "state": "OPEN"}
MERGED_CANCEL_READ = {"autoMergeRequest": None, "state": "MERGED"}
# The completion poll's raw landed-state reads: an UNREADABLE one
# (state empty — read_landed_state's fail-closed shape) and the
# MERGED-with-empty-mergeCommit blip (thread 3834590326's bounded
# pending state the poll keeps polling through).
UNKNOWN_LANDED = {"state": "", "mergeCommit": None,
                  "baseRefName": "dev", "headRefOid": HEAD}
MERGED_NO_SHA = {"state": "MERGED", "mergeCommit": None,
                 "baseRefName": "dev", "headRefOid": HEAD}


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


# Thread 3836437098: the runner's WALL clock jumps forward a full
# poll interval (VM clock correction / resume) between the dispatch
# and the first reads, while the MONOTONIC clock advances only by
# real sleep — round 13's wall-clock interval math armed and
# credited off the jump; round 14 must not.
class WallJumpClock(FakeClock):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def time(self):
        self.calls += 1
        # Call 1 is the dispatch timestamp itself (no sleep precedes
        # the dispatch); call 2 is the first post-dispatch wall read.
        if self.calls == 2:
            self.wall += 100.0
        return super().time()


class RearmWindowTests(unittest.TestCase):
    def test_unknown_first_live_read_then_live_opens_are_ambiguous(
        self,
    ):
        # Given: the failed dispatch was ACCEPTED (merge_rc=1) and
        # its completion poll reads an UNREADABLE state at 0s
        # (unspaced — nothing armed) and at 10s — the window's FIRST
        # LIVE read is the transiently-unreadable one (thread
        # 3836437093's scenario; round 13 froze "UNKNOWN" here and
        # every later OPEN was ignored). Two resolved surveys: the
        # pre-merge one and the fresh landing's quiet watch.
        surveys = iter(
            [[thread("11", "resolved")], [thread("11", "resolved")]]
        )

        # When: the live UNKNOWN records only a TRANSIENT, the OPEN
        # at 20s RE-ARMS over it, the OPEN at 30s credits (a full
        # interval past the arm, thread 3836437095), and the poll at
        # 40s observes the landing MERGED.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[
                UNKNOWN_LANDED, UNKNOWN_LANDED,
                pending(), pending(), merged(),
            ],
            merge_rc=1,
        )

        # Then: repinned at round 17 (thread 3836600782) — the
        # re-arm and the live OPEN pair attribute NOTHING (the
        # chain proved every between-reads signal reproducible by
        # ordered cache snapshots of one historical timeline), so
        # the landing reports the uniform AMBIGUOUS manual banner
        # the round-13 code once rendered only over its frozen
        # UNKNOWN baseline — now over EVERY failed-dispatch landing:
        # NO assertions, NO survey, NO revert; exit 1.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )

    def test_merged_cache_blip_first_live_read_is_ambiguous(self):
        # Given: the reviewer's cache blip (thread 3836437100) — the
        # poll reads MERGED with an EMPTY mergeCommit at 0s and at
        # 10s (the thread-3834590326 bounded pending state the poll
        # tolerates while it keeps polling), so the window's FIRST
        # LIVE read is a MERGED-from-cache one for a PR that is
        # actually still OPEN; round 13 pinned "MERGED" here. Two
        # resolved surveys: the pre-merge one and the fresh
        # landing's quiet watch.
        surveys = iter(
            [[thread("11", "resolved")], [thread("11", "resolved")]]
        )

        # When: the live MERGED blip records only a TRANSIENT, the
        # OPEN at 20s RE-ARMS over it, the OPEN at 30s credits, and
        # the poll at 40s observes the real landing MERGED — the
        # OPEN -> MERGED after the blip still earns fresh.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[
                MERGED_NO_SHA, MERGED_NO_SHA,
                pending(), pending(), merged(),
            ],
            merge_rc=1,
        )

        # Then: repinned at round 17 (thread 3836600782) — the
        # OPEN -> MERGED sequence after the blip attributes NOTHING
        # (the chain proved every between-reads signal reproducible
        # by ordered cache snapshots of one historical timeline), so
        # the landing reports the uniform AMBIGUOUS manual banner:
        # NO assertions, NO survey, NO revert; exit 1.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )


class SeparatePacingWindowTests(unittest.TestCase):
    def test_adjacent_recheck_arm_and_settle_read_no_longer_credits(self):
        # Given: the reviewer's exact scenario (thread 3836437095)
        # — the failed dispatch was ACCEPTED, the interrupt lands on
        # the completion poll's first read (0s), the cancel's
        # opening reads sit inside the first interval (PENDING at
        # 0s, OPEN at 5s), and the DELAYED RECHECK at 10s is the
        # first read at/after the interval — it ARMS OPEN — after
        # which the flow IMMEDIATELY enters the queue settlement,
        # whose first ADJACENT read observes the same stale cached
        # OPEN for a historically merged PR. Round 13 set
        # observed=True on that adjacent read; the later cache
        # refresh to MERGED was misclassified as this invocation's
        # fresh landing, enabling an automatic revert of the
        # historical merge.
        surveys = iter([[thread("11", "resolved")]])

        # When: the recheck at 10s arms, the settle probe's adjacent
        # OPEN at 10s does NOT credit, and the settle probe at 20s
        # reads the landing MERGED with a future-dated committer
        # timestamp (the cache refresh).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[KeyboardInterrupt()],
            merge_rc=1,
            cancel_reads=[
                PENDING_READ, OPEN_READ, OPEN_READ, OPEN_READ,
                MERGED_CANCEL_READ,
            ],
            queue_entries=[{"state": "QUEUED"}],
            git_answers=date_answers(ct=int(WALL_NOW) + 3600),
        )

        # Then: the uniform AMBIGUOUS banner (thread 3836600782,
        # round 17 — the pacing this test pinned is part of the
        # retired machinery; the disposition is uniform now), so the
        # historical merge keeps the manual-check disposition with
        # NO automatic revert; the original interrupt still
        # propagates.
        self.assertIsNone(code)
        self.assertIsInstance(RUNNER.raised, KeyboardInterrupt)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("LANDED DURING CANCELLATION", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )


class MonotonicWindowTests(unittest.TestCase):
    def test_wall_clock_jump_does_not_fake_the_interval(self):
        # Given: thread 3836437098's scenario — the runner's wall
        # clock jumps 100s forward right after the dispatch (VM
        # clock correction / resume) while the monotonic clock
        # advances only by the poll sleeps; the failed dispatch's
        # reconcile then reads OPEN at monotonic 0s and 10s and the
        # landing MERGED at 20s, with a future-dated committer
        # timestamp. Round 13 armed the baseline off the jumped wall
        # clock at the FIRST poll and credited at the second,
        # running the ordinary post-merge path (survey + MERGED
        # CLEAN) over a possibly-historical landing.
        surveys = iter([[thread("11", "resolved")]])

        # When: the reconciliation runs under the jumping clock.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[pending(), pending(), merged()],
            merge_rc=1,
            clock_cls=WallJumpClock,
            git_answers=date_answers(ct=int(WALL_NOW) + 3600),
        )

        # Then: the uniform AMBIGUOUS banner (thread 3836600782,
        # round 17 — the monotonic pacing this test pinned is part
        # of the retired machinery; the disposition is uniform now):
        # the manual-check banner stands with NO survey cycle and NO
        # automatic revert; exit 1.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )


if __name__ == "__main__":
    unittest.main()
