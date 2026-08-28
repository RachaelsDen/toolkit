"""pr_guard merge-act round-5 tests (PR #41).

Thread 3833073940: the queue-aware cancel settlement — the converged
"cancelled and verified" verdict additionally probes the merge-queue
entry (GraphQL mergeQueueEntry, REST-corroborated) and watches a
bounded window when the entry is live or unverifiable, because a
QUEUED PR observably shows OPEN + autoMergeRequest=null. Thread
3833073949: a FAILED merge command is an unknown outcome — the
reconcile poll continues into the ordinary post-merge path if the
request had been accepted, and surfaces the original error only when
nothing landed. Thread 3833073952: every gh pr argv is pinned with
-R RachaelsDen/UR-lorebook and a foreign GH_REPO warns loudly. The
harness is the shared PLAIN non-TestCase class (thread 3832660856),
so importing it adds nothing to unittest discovery.

PR #41 round 6 (thread 3833251675) added a post-ABSENT state RE-READ
to the converged verdict — the mid-read-merge scenarios live in
pr_guard_merge_round6_test; round 7 (thread 3833360201) extended that
re-read into a settling window, and round 8 (thread 3833540916) made
that window DEADLINE-based with a final probe at/after it, so the
converged fixtures here feed 44 completion-family poll reads (31
poll-family + 13 settling probes) and 14 GraphQL probes.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round5_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    GRAPHQL_ARGV,
    HEAD,
    HEAD_ARGV,
    MERGE_ARGV,
    MERGE_SHA,
    POLL_ARGV,
    REPO_FLAG,
    REST_PR_ARGV,
    MergeHarness,
    merged,
    pending,
    queued_entry,
    revert_argv,
    thread,
)

RUNNER = MergeHarness()


def clean() -> dict:
    return {"autoMergeRequest": None, "state": "OPEN"}


def landed() -> dict:
    return {"autoMergeRequest": None, "state": "MERGED"}


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class QueueSettlementTests(unittest.TestCase):
    def test_converged_cancel_probes_the_queue_entry_absent(self):
        # Given: the completion poll timed out still-OPEN and the
        # disable + 5s re-check converged (thread 3832522306) — the
        # OLD code printed "cancelled and verified" here, but a QUEUED
        # PR shows exactly OPEN + autoMergeRequest=null (thread
        # 3833073940), so the verdict now additionally probes the
        # merge-queue entry before claiming anything. Thread
        # 3833251675 (round 6) added the post-ABSENT state RE-READ,
        # and thread 3833360201 (round 7) keeps watching: the OPEN
        # must STAY OPEN through the settling window — which thread
        # 3833540916 (round 8) measures by DEADLINE (the poll reads
        # below feed the 31 completion-family reads plus the window's
        # 13 probes, the last at/after the 60s deadline).
        surveys = iter([[thread("11", "resolved")]])

        # When: the GraphQL mergeQueueEntry probe reads ABSENT and the
        # settling window sees OPEN + ABSENT at every probe.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), poll_states=[pending()] * 44
        )

        # Then: the converged banner names the probed-ABSENT entry AND
        # the STILL-OPEN re-read AND the settling window it survived,
        # the outer probe ran once and the settling window re-probed
        # the entry at each of its 13 state reads (12 5s settling
        # sleeps past the 5s re-check — no 10s queue-watch sleeps; the
        # 13th probe lands at/after the deadline, thread 3833540916),
        # exit 1, no clean banner.
        self.assertEqual(code, 1)
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn("probed ABSENT (GraphQL mergeQueueEntry", out)
        self.assertIn("RE-READ STILL OPEN after the ABSENT probe", out)
        self.assertIn("STAYED OPEN through the FULL 60s", out)
        self.assertIn("queue-watch probe 1", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 14)
        self.assertEqual(argvs.count(POLL_ARGV), 44)
        self.assertNotIn(REST_PR_ARGV, argvs)
        self.assertEqual(RUNNER.clock.slept, [10.0] * 30 + [5.0] + [5.0] * 12)

    def test_queued_entry_landing_during_the_watch_reverts(self):
        # Given: the disable converged on OPEN reads, but the queue
        # probe reports a LIVE mergeQueueEntry (thread 3833073940) and
        # the entry LANDS on the watch's second attempt.
        surveys = iter([[thread("11", "resolved")]])

        # When: attempt 1 sees QUEUED, then the state read flips to
        # MERGED before attempt 2's probe.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 31,
            cancel_reads=[clean(), clean(), clean(), landed()],
            queue_entries=[queued_entry()],
        )

        # Then: the QUEUE WATCH progress printed, the landing went
        # straight through the landed-during-cancel REVERT path (never
        # a cancelled claim), the merge commit re-fetch and revert argv
        # fired on the landed base, exit 1.
        self.assertEqual(code, 1)
        self.assertIn(
            "QUEUE WATCH probe=1 elapsed=0s/60s "
            "queue=QUEUED state=OPEN", out
        )
        self.assertIn("LANDED DURING CANCELLATION", out)
        self.assertIn("REVERT PR OPENED", out)
        self.assertNotIn("CANCELLED and verified gone", out)
        self.assertNotIn("MERGED CLEAN:", out)
        tail = RUNNER.revert_tail(argvs)
        expected = revert_argv("dev", RUNNER.revert_tmp)
        self.assertEqual(tail[:6], expected[:6])
        self.assertTrue(tail[5].startswith(expected[5]))
        self.assertEqual(RUNNER.clock.slept, [10.0] * 30 + [5.0, 10.0])

    def test_queued_entry_draining_during_the_watch_converges(self):
        # Given: the queue probe first reports a LIVE entry, the
        # dequeue mutation cannot remove it (round 15's default
        # fallback, thread 3834375737), and the entry is then dequeued
        # server-side (a human removed it in the web UI).
        surveys = iter([[thread("11", "resolved")]])

        # When: attempt 1 sees QUEUED and attempt 2's probe reads
        # ABSENT with the state still OPEN — the settling window of
        # thread 3833360201 then watches OPEN + ABSENT through its
        # deadline-measured probes (the 32nd-44th POLL reads, thread
        # 3833540916).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 44,
            queue_entries=[queued_entry(), None],
        )

        # Then: one 10s watch sleep, the outer probes plus the
        # settling window's 13 deadline probes, and the converged
        # banner — the queue entry was observed GONE, not assumed.
        self.assertEqual(code, 1)
        self.assertIn(
            "QUEUE WATCH probe=1 elapsed=0s/60s "
            "queue=QUEUED state=OPEN", out
        )
        self.assertIn("probed ABSENT", out)
        self.assertIn("queue-watch probe 2", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 15)
        self.assertEqual(
            RUNNER.clock.slept,
            [10.0] * 30 + [5.0, 10.0] + [5.0] * 12,
        )

    def test_ambiguous_entry_expiring_the_watch_falls_back(self):
        # Given: the GraphQL probe is UNREADABLE every attempt (field/
        # schema/auth) — REST corroboration reads mergeable_state
        # 'blocked', which is consistent with a queued entry and
        # proves nothing (thread 3833073940's fail-closed AMBIGUOUS).
        surveys = iter([[thread("11", "resolved")]])

        # When: every queue-watch probe stays ambiguous through the
        # full deadline window (thread 3834093639: seven probes, six
        # 10s sleeps, the last probe AT the 60s deadline — the
        # round-12 counted loop ended one sleep early on fast reads).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 31,
            queue_entries=["FAIL"],
        )

        # Then: the bounded window expires — the final (7th) probe
        # runs AT the 60s deadline and falls straight to the
        # BOTH-CONTINGENCY manual instructions (a probe past the
        # deadline needs no progress line), including the honest
        # residual that the dequeuePullRequest mutation (the only
        # programmatic dequeue, thread 3834375737) did NOT run on an
        # AMBIGUOUS-probe path and the MEASURED 60s window (thread
        # 3834093639) — never a converged or clean claim.
        self.assertEqual(code, 1)
        self.assertIn("QUEUE WATCH probe=6 elapsed=50s/60s", out)
        self.assertNotIn("QUEUE WATCH probe=7", out)
        self.assertIn("mergeable_state=blocked", out)
        self.assertIn("CANCEL UNCONFIRMED", out)
        self.assertIn("BOTH contingencies are live", out)
        self.assertIn("remove the PR from the merge queue", out)
        self.assertIn("dequeuePullRequest mutation did NOT run", out)
        self.assertIn("the bounded 60s watch expired", out)
        self.assertIn("DO NOT assume MERGED CLEAN", out)
        self.assertNotIn("CANCELLED and verified gone", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 7)
        self.assertEqual(argvs.count(REST_PR_ARGV), 7)
        self.assertEqual(RUNNER.clock.slept, [10.0] * 30 + [5.0] + [10.0] * 6)


class AmbiguousMergeFailureTests(unittest.TestCase):
    def test_failed_command_that_had_landed_banners_ambiguous(self):
        # Given: `gh pr merge` exits 1 only because the connection died
        # AFTER GitHub accepted the request (thread 3833073949) —
        # repinned at round 9 (thread 3836149500): the reconcile
        # poll's still-OPEN reads span the BASELINE (first
        # post-dispatch poll) and a LATER poll (the post-baseline
        # credit that attributes the landing fresh); repinned again
        # at round 10 (thread 3836217630): the baseline must itself
        # be LIVE (the first read >= one real poll interval past the
        # dispatch), so the still-OPEN reads span THREE polls — the
        # pre-interval read (cache-suspect, ignored), the live
        # baseline, and the post-baseline credit — before the fourth
        # read observes state=MERGED.
        surveys = iter([[thread("11", "resolved")], [thread("11", "resolved")]])

        # When: the failed dispatch is reconciled and the request turns
        # out to have landed on the verified base and head.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending(), pending(), pending(), merged()],
            merge_rc=1,
        )

        # Then: the UNKNOWN-outcome banner printed first, the SHORTER
        # reconcile poll ran (attempt labels out of 10), and —
        # repinned at round 17 (thread 3836600782): the observed
        # OPEN -> MERGED sequence attributes NOTHING (the chain
        # proved every between-reads signal reproducible by ordered
        # cache snapshots of one historical timeline) — the landing
        # reports the uniform AMBIGUOUS manual banner: NO assertions,
        # NO quiet watch, NO automatic revert, exit 1, never CLEAN.
        self.assertEqual(code, 1)
        self.assertIn("MERGE COMMAND FAILED (gh exited 1)", out)
        self.assertIn("outcome is UNKNOWN", out)
        self.assertIn("MERGE PENDING attempt=1/10 state=OPEN", out)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("--disable-auto", " ".join(argvs))
        self.assertNotIn("ORIGINAL MERGE ERROR", out)
        self.assertNotIn("MERGED CLEAN", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )

    def test_failed_command_that_never_lands_surfaces_the_original_error(
        self,
    ):
        # Given: `gh pr merge` exits 1 and the request truly never
        # landed — every reconcile poll AND its final check read OPEN
        # (thread 3833073949's nothing-landed branch), so the cancel
        # machinery disposes of any lingering pending request first.
        surveys = iter([[thread("11", "resolved")]])

        # When: the shorter poll (10 attempts + the final check) never
        # observes MERGED, and the settling window of thread 3833360201
        # watches OPEN + ABSENT through its deadline-measured probes
        # (the 12th-24th POLL reads, the last at/after the 60s
        # deadline — thread 3833540916) before the cancel converges.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 24,
            merge_rc=1,
        )

        # Then: the cancel ran with the RECONCILE budget (the banner
        # names the 100s window, not the success path's 300s), the
        # ORIGINAL error is surfaced after the cancelled-and-verified
        # disposition, exit 1, never MERGED CLEAN.
        self.assertEqual(code, 1)
        self.assertIn("MERGE COMMAND FAILED (gh exited 1)", out)
        self.assertIn("MERGE PENDING attempt=10/10", out)
        self.assertIn("within 100s", out)
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn(
            "ORIGINAL MERGE ERROR: gh pr merge exited 1 — nothing landed",
            out,
        )
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [a for a in argvs if a == POLL_ARGV], [POLL_ARGV] * 24
        )

    def test_failed_command_reconciling_to_closed_reports_did_not_land(self):
        # Given: `gh pr merge` exits 1 and the reconcile poll reads
        # state=CLOSED — closed without merging, nothing to revert.
        surveys = iter([[thread("11", "resolved")]])

        # When: the first reconcile read observes CLOSED.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[
                {
                    "state": "CLOSED",
                    "mergeCommit": None,
                    "baseRefName": "dev",
                    "headRefOid": HEAD,
                }
            ],
            merge_rc=1,
        )

        # Then: the did-not-land banner AND the original error, exit 1,
        # no cancel or revert plumbing.
        self.assertEqual(code, 1)
        self.assertIn("MERGE DID NOT LAND", out)
        self.assertIn("ORIGINAL MERGE ERROR: gh pr merge exited 1", out)
        self.assertNotIn("--disable-auto", " ".join(argvs))
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)


class RepoPinningTests(unittest.TestCase):
    def test_every_gh_pr_argv_carries_the_repo_flag(self):
        # Given: a full run through the cancel settlement — head
        # capture, merge dispatch, polls, disable, verification reads,
        # queue probe (thread 3833073952: GH_REPO must not be able to
        # redirect any gh pr command at another repository).
        surveys = iter([[thread("11", "resolved")]])

        # When: the run converges through the cancelled path (the
        # settling window of thread 3833360201 consumes the 32nd-44th
        # POLL reads, the last at/after the deadline — thread
        # 3833540916).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), poll_states=[pending()] * 44
        )

        # Then: EVERY gh pr argv (view/merge/disable alike) carries
        # -R RachaelsDen/UR-lorebook, and the gh api probe argvs name
        # the repository in their paths/variables instead.
        gh_pr = [a for a in argvs if a.startswith("gh pr")]
        self.assertGreater(len(gh_pr), 4)
        for argv in gh_pr:
            self.assertIn(REPO_FLAG, argv)
        self.assertIn("owner=RachaelsDen", GRAPHQL_ARGV)
        self.assertIn("repos/RachaelsDen/UR-lorebook", REST_PR_ARGV)

    def test_foreign_gh_repo_env_warns_loudly_but_cannot_break_the_act(self):
        # Given: GH_REPO names an unrelated repository (thread
        # 3833073952) — the operator's environment disagrees with the
        # surveyed repository.
        surveys = iter([[thread("11", "resolved")], [thread("11", "resolved")]])

        # When: the guarded merge runs under the override.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), gh_repo="somebody/unrelated-repo"
        )

        # Then: a LOUD warning names the override and the thread — and
        # the act still completes against the pinned repository (every
        # gh pr argv carries the flag; the override redirected nothing).
        self.assertEqual(code, 0)
        self.assertIn(
            "WARNING: GH_REPO=somebody/unrelated-repo", out
        )
        self.assertIn("thread 3833073952", out)
        self.assertIn("MERGED CLEAN", out)
        for argv in [a for a in argvs if a.startswith("gh pr")]:
            self.assertIn(REPO_FLAG, argv)

    def test_matching_gh_repo_env_does_not_warn(self):
        # Given: GH_REPO names the surveyed repository itself.
        surveys = iter([[thread("11", "resolved")], [thread("11", "resolved")]])

        # When: the guarded merge runs under the matching override.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), gh_repo="RachaelsDen/UR-lorebook"
        )

        # Then: no warning — the environment agrees with the pin.
        self.assertEqual(code, 0)
        self.assertNotIn("WARNING", out)
        self.assertIn("MERGED CLEAN", out)


if __name__ == "__main__":
    unittest.main()
