"""pr_guard merge-act round-31 tests (PR #41 round 31).

Three findings, one remediation round:

Thread 3835587497 (P1) — the settling watch's bounded auto-merge
re-disables and the exhaustion probe are PACED at the cancellation
re-check cadence: the round-30 form's `continue` re-probed
immediately after each re-disable, so ordinary --disable-auto
propagation delay exhausted the whole budget inside ONE stale-read
interval and the both-contingency banner fired while the accepted
request remained live. The paced form sleeps before consuming
another re-disable attempt, and the exhaustion verdict rests on a
FRESH paced re-read — a fresh read that no longer says AUTO
continues the watch (the disable merely had not propagated) instead
of banner-ing; the exhaustion and converged banners report the
pacing.

Thread 3835587498 (P2) — the suffix scan REUSES a remote suffix
branch whose head IS this attempt's revert commit (the same match
rule as the deterministic name): an earlier retry that pushed the
exact revert to `-2` and then failed creating the PR is no longer
treated as an ordinary collision that mints further suffixes toward
the 50-name budget.

Thread 3835587500 (P2) — a successful dequeue whose injected
settlement watch returns plain None keeps its own AMBIGUOUS report
clause: only the REAPPEARED sentinel proves a re-enqueue, and the
old form fed the reappearance clause (false evidence of a competing
re-enqueue) into the progress and terminal banners whenever a later
state/queue/auto-merge probe was weaker or unreadable.

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act (the fake GH lives in pr_guard_merge_ghfake since this
round's LOC splits).

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round31_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    DEQUEUE_ARGV,
    GRAPHQL_ARGV,
    HEAD,
    MERGE_SHA,
    NODE_ID_ARGV,
    REVERT_HEAD,
    MergeHarness,
    merged,
    pending,
    queued_entry,
    thread,
)

RUNNER = MergeHarness()
BRANCH = f"revert/pr39-{MERGE_SHA[:7]}"
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


def clean():
    return {"autoMergeRequest": None, "state": "OPEN"}


def auto_enabled():
    return {"autoMergeRequest": {"mergeMethod": "MERGE"}, "state": "OPEN"}


def closed_pending():
    # Thread 3835587500's weaker-evidence blip: a settling-probe
    # state read that is neither OPEN nor MERGED makes the watch
    # return plain None (the AMBIGUOUS arm), never a verdict.
    return {
        "state": "CLOSED",
        "mergeCommit": None,
        "baseRefName": "dev",
        "headRefOid": HEAD,
    }


class RedisablePacingTests(unittest.TestCase):
    def test_persistent_reenable_is_paced_into_both_banner(self):
        # Given: the cancel converged into the settlement and the
        # settling watch's probes keep reading a RE-ENABLED
        # autoMergeRequest (thread 3835587497's exact shape: the
        # round-30 code re-probed immediately after each re-disable,
        # so propagation delay burned the budget back-to-back).
        surveys = iter([[thread("11", "resolved")]])

        # When: every settling-probe auto read is non-null and the
        # FRESH paced exhaustion re-read is still non-null.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 35,
            cancel_reads=[clean(), clean(), clean(), auto_enabled()],
        )

        # Then: the two bounded re-disables and the exhaustion probe
        # each ran at a 5s PACING cadence (never back-to-back), the
        # exhaustion verdict rested on the FRESH paced re-read, and
        # the BOTH-CONTINGENCY banner REPORTS the pacing — never a
        # converged claim over the live request.
        self.assertEqual(code, 1)
        self.assertEqual(argvs.count(
            "gh pr merge 39 --disable-auto -R RachaelsDen/UR-lorebook"
        ), 3)
        self.assertIn("AUTO-MERGE RE-ENABLED at settling probe 1", out)
        self.assertIn("AUTO-MERGE RE-ENABLED at settling probe 2", out)
        self.assertIn(
            "AUTO-MERGE STILL RE-ENABLED at settling probe 3", out
        )
        self.assertIn("PACING the re-disable", out)
        self.assertIn(
            "PACED at a 5s cadence and the exhaustion verdict rests "
            "on a FRESH paced re-read (thread 3835587497)",
            out,
        )
        self.assertIn("CANCEL UNCONFIRMED", out)
        self.assertNotIn("CANCELLED and verified gone", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 4)
        self.assertEqual(
            RUNNER.clock.slept, [10.0] * 30 + [5.0] + [5.0] * 3
        )

    def test_propagated_disable_at_paced_exhaustion_probe_converges(
        self,
    ):
        # Given: the same re-enable storm, but the LAST re-disable
        # actually took — the re-enabled reads through settling probe
        # 3 are ordinary propagation delay, and the budget is spent.
        surveys = iter([[thread("11", "resolved")]])

        # When: the paced exhaustion probe's FRESH re-read no longer
        # says AUTO (the disable propagated inside the 5s pace) and
        # every later read stays clean through the extended window.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 70,
            cancel_reads=[
                clean(),
                clean(),
                clean(),
                auto_enabled(),
                auto_enabled(),
                auto_enabled(),
                clean(),
            ],
        )

        # Then: the budget is NOT declared exhausted on the stale
        # re-enabled read — the watch CONTINUES on fresh probes and
        # converges through the extended window, with the converged
        # banner reporting the two PACED re-disables.
        self.assertEqual(code, 1)
        self.assertIn(
            "AUTO-MERGE PROPAGATED at the paced exhaustion probe of "
            "settling probe 3",
            out,
        )
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn(
            "2 bounded auto-merge re-disable(s), each PACED at a 5s "
            "cadence before the dispatch (thread 3835587497)",
            out,
        )
        self.assertNotIn("CANCEL UNCONFIRMED", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 38)
        self.assertEqual(
            RUNNER.clock.slept,
            [10.0] * 30 + [5.0] + [5.0] * 3 + [5.0] * 33,
        )


class AmbiguousDequeueTests(unittest.TestCase):
    def test_dequeue_success_with_ambiguous_settlement_banners_it(self):
        # Given: the queue watch dispatched a dequeue that SUCCEEDED
        # and the entry read ABSENT — but the injected settling
        # watch's first state probe returns weaker evidence
        # (neither OPEN nor MERGED), so the watch returns plain None
        # (thread 3835587500's exact shape: the old form reported
        # this as an explicit REAPPEARED to the operator).
        surveys = iter([[thread("11", "resolved")]])

        # When: the settle watch ends AMBIGUOUS and the queue watch
        # then carries the full bounded window without a verdict.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 31 + [closed_pending()] * 10,
            queue_entries=[queued_entry(), None],
            dequeue_rc=0,
        )

        # Then: the terminal banner carries the AMBIGUOUS clause —
        # neither convergence nor reappearance proven — with the
        # bounded attempt count, and the REAPPEARED clause NEVER
        # renders: the sentinel never fired, so no false re-enqueue
        # evidence reaches the operator.
        self.assertEqual(code, 1)
        self.assertEqual(argvs.count(NODE_ID_ARGV), 1)
        self.assertEqual(argvs.count(DEQUEUE_ARGV), 1)
        self.assertIn("QUEUE ENTRY DEQUEUED", out)
        self.assertIn(
            "SUCCEEDED at queue-watch probe 1 and the entry read "
            "ABSENT, but the settlement watch ended AMBIGUOUS",
            out,
        )
        self.assertIn(
            "neither convergence nor reappearance is proven", out
        )
        self.assertIn("3834375737/3835587500", out)
        self.assertIn("1 bounded attempt(s) in total", out)
        self.assertNotIn(
            "but it REAPPEARED inside the settling window", out
        )
        self.assertIn("CANCEL UNCONFIRMED", out)
        self.assertNotIn("CANCELLED and verified gone", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(argvs.count(GRAPHQL_ARGV), 14)

    def test_reappeared_dequeue_renders_the_reappearance_clause(self):
        # Given: the same successful dequeue, but the settling
        # watch's queue probe reads the entry LIVE again — the
        # REAPPEARED sentinel fires (the distinct fact thread
        # 3835587500 keeps separate from ambiguity).
        surveys = iter([[thread("11", "resolved")]])

        # When: the settle watch returns the sentinel and the fresh
        # re-probe then reads the entry durably ABSENT through the
        # full settling window.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 50,
            queue_entries=[
                queued_entry(), None, queued_entry(), None,
            ],
            dequeue_rc=0,
        )

        # Then: the REAPPEARED clause renders (progress line and
        # converged banner) with its own thread citation — and the
        # AMBIGUOUS clause NEVER renders: each outcome keeps its
        # distinct evidence.
        self.assertEqual(code, 1)
        self.assertIn("QUEUE ENTRY REAPPEARED at settling probe 1", out)
        self.assertIn(
            "SUCCEEDED at queue-watch probe 1 and the entry read "
            "ABSENT, but it REAPPEARED inside the settling window "
            "(thread 3834375737)",
            out,
        )
        self.assertIn("CANCELLED and verified gone", out)
        self.assertNotIn("ended AMBIGUOUS", out)
        self.assertNotIn("3835587500", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(argvs.count(DEQUEUE_ARGV), 1)


class SuffixReuseTests(unittest.TestCase):
    def test_matching_suffixed_branch_is_reused_without_push(self):
        # Given: a PRIOR retry pushed this exact revert to the `-2`
        # suffix and then failed while creating the PR, and the
        # deterministic branch is occupied by an OLDER commit —
        # thread 3835587498's exact scenario (the round-30 suffix
        # scan treated the matching suffix as a collision and
        # minted -3, -4, ... toward the 50-name budget).
        surveys = iter([[thread("11", "resolved")]])

        # When: the rerun rebuilds the same revert commit, the
        # deterministic ls-remote reports a different head, and the
        # -2 candidate's head IS this attempt's revert commit.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_heads={
                BRANCH: "dead0000000000000000000000000000000000ff",
                f"{BRANCH}-2": REVERT_HEAD,
            },
        )

        # Then: the suffix is REUSED — no push argv at all, the PR
        # opens straight against the existing `-2` branch, and the
        # reuse print names the suffix and the thread.
        self.assertEqual(code, 1)
        self.assertIn(
            f"REVERT BRANCH REUSED: refs/heads/{BRANCH}-2", out
        )
        self.assertIn("thread 3835587498", out)
        self.assertIn(f"git ls-remote origin refs/heads/{BRANCH}", argvs)
        self.assertIn(
            f"git ls-remote origin refs/heads/{BRANCH}-2", argvs
        )
        self.assertNotIn("git push", " ".join(argvs))
        self.assertNotIn("REVERT BRANCH SUFFIXED", out)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(f"--head {BRANCH}-2", create)
        self.assertIn("REVERT PR OPENED", out)


if __name__ == "__main__":
    unittest.main()
