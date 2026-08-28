"""pr_guard merge-act round-29 tests (PR #41 round 29).

Three P1s in one remediation round:

Thread 3835450362 — RE-PROBE after an absent-settlement reappearance:
when the queue entry reappears on the FINAL probe of the settling
watch, that watch returns None after consuming the outer queue-watch
deadline, and the round-28 code retained the stale pre-watch
queue == "ABSENT", skipped the dequeue branch, and returned the
timeout banner while a LIVE entry remained (it could land after the
guard exited with no destination/head assertions and no post-merge
survey). settle_queue_contingency now re-probes the state/queue pair
after every watch-None: a fresh QUEUED dispatches the dequeue, a
fresh MERGED reverts, and only a durable ABSENT reaches the banner.

Thread 3835450365 — PACED cancellation retries: the three
--disable-auto attempts ran back-to-back, so a disable whose effect
had not propagated yet (or a transient failure) exhausted the whole
budget inside ONE stale-read interval while the accepted request
stayed live. The attempts are now separated by the CANCEL_RECHECK_SECS
cadence sleep (asserted on the fake clock); the final attempt's
progress line reports the exhausted PACED budget instead of promising
another retry.

Thread 3835450367 — PRE-EXISTING merge detection: re-invoking the
merge act for an ALREADY-MERGED PR (a stale retry) passed the head/
base validation, the dispatch exited nonzero, and the reconcile poll
observed the HISTORICAL MERGED state as though the dispatch had just
landed it — running the post-merge mismatch/DANGER cycle and the
AUTOMATIC REVERT against a legitimate earlier merge. The act now
snapshots the pre-dispatch merge identity (the merged flags from the
same REST read that validates head/base); a PR already merged
pre-dispatch is a PRE-EXISTING merge: a distinct banner, a nonzero
exit, and NO revert path. A NEW mergeCommit is the ordinary
post-merge path.

PR #43 round 2 (thread 3835714800) refit: the round-29 identity arm
additionally keyed on the REST merge_commit_sha of an OPEN record —
but for an open PR that field is GitHub's synthetic TEST merge
commit, and a dispatched merge can land REUSING that very commit
object, so the equal-sha arm classified this invocation's fresh
landing as historical and skipped the assertions/quiet watch. The
identity snapshot now trusts ONLY the merged flags; the equal-sha
test below pins the new ordinary-path behavior (the identity arm
survives solely through the merged-record shape).

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round29_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    DEQUEUE_ARGV,
    GRAPHQL_ARGV,
    HEAD,
    MERGE_SHA,
    NODE_ID_ARGV,
    MergeHarness,
    merged,
    pending,
    queued_entry,
    thread,
)

RUNNER = MergeHarness()


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


def pre_merged_record():
    # Thread 3835450367: the REST shape of an ALREADY-MERGED PR —
    # state "closed" with merged=true and the historical merge sha
    # (head/base never move post-merge, so the act's validation
    # passes on a stale retry).
    return {
        "head": {"sha": HEAD},
        "base": {"ref": "dev"},
        "state": "closed",
        "merged": True,
        "merge_commit_sha": MERGE_SHA,
    }


def open_record(merge_commit_sha: str = ""):
    return {
        "head": {"sha": HEAD},
        "base": {"ref": "dev"},
        "state": "open",
        "merged": False,
        "merge_commit_sha": merge_commit_sha,
    }


class SettleReprobeTests(unittest.TestCase):
    def test_reappearance_on_final_settle_probe_dispatches_the_dequeue(
        self,
    ):
        # Given: the completion poll timed out still-OPEN, the cancel
        # converged into the settlement, the outer probe read ABSENT,
        # and the settling window held OPEN + ABSENT through probes
        # 1-12 — but the entry REAPPEARS on the window's FINAL probe
        # (the one at/after the 60s deadline), exactly when the outer
        # queue-watch window is spent (thread 3835450362: the round-28
        # code skipped the dequeue on the stale pre-watch ABSENT and
        # returned the timeout banner over the live entry).
        surveys = iter([[thread("11", "resolved")]])

        # When: the final settle probe reads QUEUED and the round-29
        # RE-PROBE's fresh queue read is QUEUED too (the dequeue
        # mutation itself keeps failing — the default rc 1 — so the
        # honest residual is the bounded attempt report).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 46,
            queue_entries=[None] * 13 + [queued_entry(), queued_entry()],
        )

        # Then: the reappearance announced, the RE-PROBE reported, the
        # dequeue DISPATCHED through the pinned node-id view despite
        # the consumed outer deadline (a live entry never rides out
        # the guard un-attempted), and the terminal banner carries the
        # bounded attempt count — never a converged or clean claim.
        self.assertEqual(code, 1)
        self.assertIn(
            "QUEUE ENTRY REAPPEARED at settling probe 13", out
        )
        self.assertIn("QUEUE RE-PROBE", out)
        self.assertIn("thread 3835450362", out)
        self.assertEqual(argvs.count(NODE_ID_ARGV), 1)
        self.assertEqual(argvs.count(DEQUEUE_ARGV), 1)
        self.assertIn(
            "was attempted at queue-watch probe 1 and FAILED", out
        )
        self.assertIn("1 bounded attempt(s) in total", out)
        self.assertIn("CANCEL UNCONFIRMED", out)
        self.assertNotIn("CANCELLED and verified gone", out)
        self.assertNotIn("MERGED CLEAN:", out)


class CancelPacingTests(unittest.TestCase):
    def test_pending_verdicts_are_paced_not_back_to_back(self):
        # Given: the merge command FAILED (the reconcile path) and
        # every --disable-auto leaves the verification read PENDING —
        # the exact stale-read/transient-failure interval of thread
        # 3835450365 where the round-28 budget was exhausted
        # back-to-back while the accepted request stayed live.
        surveys = iter([[thread("11", "resolved")]])

        # When: all three attempts meet a PENDING verdict (the last
        # cancel read repeats forever).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 24,
            cancel_reads=[
                {"autoMergeRequest": {"id": 1}, "state": "OPEN"}
            ],
            merge_rc=1,
        )

        # Then: the attempts are SEPARATED by the re-check cadence
        # sleep — exactly two pacing sleeps between three attempts on
        # the fake clock, never a third after the exhausted budget —
        # the progress lines report the PACING, no queue probe ran (a
        # PENDING verdict never reaches the OPEN-only queue branch),
        # and the disposition fails closed with the both-contingency
        # banner plus the original merge error.
        self.assertEqual(code, 1)
        self.assertEqual(
            RUNNER.clock.slept, [10.0] * 10 + [5.0, 5.0]
        )
        self.assertEqual(RUNNER.clock.slept.count(5.0), 2)
        self.assertIn("CANCEL PENDING attempt=1/3", out)
        self.assertIn("CANCEL PENDING attempt=2/3", out)
        self.assertIn("CANCEL PENDING attempt=3/3", out)
        self.assertIn("PACING the retry", out)
        self.assertIn("thread 3835450365", out)
        self.assertIn("PACED budget is exhausted", out)
        self.assertIn("CANCEL UNCONFIRMED", out)
        self.assertIn("ORIGINAL MERGE ERROR: gh pr merge exited 1", out)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 0)
        self.assertEqual(argvs.count(DEQUEUE_ARGV), 0)
        self.assertNotIn("MERGED CLEAN:", out)


class PreExistingMergeTests(unittest.TestCase):
    def test_pre_merged_invocation_banners_without_reverting(self):
        # Given: the operator retries a stale `pre-merge`/merge
        # invocation for a PR that is ALREADY MERGED (thread
        # 3835450367) — the REST validation passes (head/base never
        # moved), the snapshot records merged=true with the
        # historical merge sha, and the dispatch exits nonzero.
        surveys = iter([[thread("11", "resolved")]])

        # When: the reconcile poll observes the historical MERGED
        # state (same mergeCommit as the pre-dispatch snapshot).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([pre_merged_record()]),
            poll_states=[merged()],
            merge_rc=1,
        )

        # Then: the PRE-EXISTING MERGE banner — nothing was dispatched
        # by us, the operator surveys it as a post-merge check — and
        # NO revert: no mismatch assertions, no quiet watch (exactly
        # the one closing survey), no revert argv, no PR create,
        # nonzero exit, never MERGED CLEAN.
        self.assertEqual(code, 1)
        self.assertIn("PRE-EXISTING MERGE", out)
        self.assertIn("already merged before this invocation", out)
        self.assertIn("nothing was dispatched by us", out)
        self.assertIn("thread 3835450367", out)
        self.assertNotIn("QUIET PERIOD", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )

    def test_open_pr_test_merge_sha_is_not_pre_existing(self):
        # Given: the pre-dispatch REST record is a genuinely OPEN PR
        # whose merge_commit_sha names GitHub's synthetic TEST merge
        # commit — thread 3835714800 (PR #43 round 2) refit of the
        # round-29 identity arm: the old test treated an equal sha as
        # pre-existing evidence, but a dispatched merge can land
        # REUSING that very commit object, so an open record's sha
        # proves nothing about who landed it.
        surveys = iter(
            [[thread("11", "resolved")], [thread("11", "resolved")]]
        )

        # When: the dispatch itself succeeds (rc 0) and the completion
        # poll's MERGED observation carries the SAME sha the open
        # pre-dispatch record exposed.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record(MERGE_SHA)]),
            poll_states=[merged()],
        )

        # Then: NOT pre-existing — the identity snapshot trusts only
        # the merged flags, so this invocation's fresh landing runs
        # the FULL post-merge path (assertions + quiet watch, MERGED
        # CLEAN, exit 0) instead of returning before them.
        self.assertEqual(code, 0)
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertIn("MERGED CLEAN", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)],
            [("survey",)] * 2,
        )

    def test_new_merge_commit_after_failed_dispatch_banners_ambiguous(
        self,
    ):
        # Given: the pre-dispatch snapshot is a genuinely OPEN PR
        # (no merge identity), the dispatch exits nonzero only because
        # the connection died AFTER GitHub accepted the request, and
        # the reconcile poll observes a landing with a NEW mergeCommit
        # (thread 3835450367's ordinary arm — the dispatch DID land).
        # Repinned at round 9 (thread 3836149500): the still-OPEN
        # reads span the baseline AND a later poll (the post-baseline
        # credit), so the observed transition still attributes the
        # landing fresh. Repinned at round 10 (thread 3836217630):
        # the baseline must itself be LIVE (the first read >= one
        # real poll interval past the dispatch), so the still-OPEN
        # reads span THREE polls — pre-interval cache-suspect, live
        # baseline, post-baseline credit — before the landing.
        surveys = iter(
            [[thread("11", "resolved")], [thread("11", "resolved")]]
        )

        # When: reconcile polls 1-3 read OPEN and attempt 4 reads
        # MERGED with the fresh sha.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record()]),
            poll_states=[pending(), pending(), pending(), merged()],
            merge_rc=1,
        )

        # Then: repinned at round 17 (thread 3836600782) — the
        # failed path no longer attributes landings AT ALL (the
        # chain proved every between-reads signal reproducible by
        # ordered cache snapshots of one historical timeline), so
        # even the fresh landing reports the uniform AMBIGUOUS
        # manual banner: NO assertions, NO quiet watch, NO revert,
        # exit 1; the pre-existing gate never fired either.
        self.assertEqual(code, 1)
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("MERGED CLEAN", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)],
            [("survey",)],
        )


if __name__ == "__main__":
    unittest.main()
