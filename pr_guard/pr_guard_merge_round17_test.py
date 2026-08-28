"""pr_guard merge-act round-17 tests (PR #41 round 17).

Thread 3834590317: a QUEUED PR has NO auto-merge request, so `gh pr
merge --disable-auto` legitimately exits nonzero — the cancel loop's
round-16 gate skipped the queue settlement entirely on that rc, and
the live entry was never dequeued or watched to convergence. The
settlement now runs whenever the state reads OPEN and the queue probe
shows a LIVE entry, regardless of the disable's rc.

Thread 3834590319: the dequeue RETRIES — the round-15 one-shot guard
permanently suppressed every later attempt once any report existed,
so a transient mutation failure or a re-enqueued entry rode out the
window to the manual banner. Each QUEUED probe re-attempts the
removal (bounded to three); persistent failure banners the attempt
count.

Thread 3834590322's contiguity arm — one more reproducible
provenance signal — was RETIRED at round 25 (threads 3835145976/
3835145981/3835175506/3835175508) with the classifier it served;
its two ContiguityChain suites were DELETED as redundant with the
refit round-11 fail-closed suite (the suite count drops by design).

Thread 3834590326: GitHub can report state=MERGED before the nullable
mergeCommit is readable — the round-16 verdict terminated instantly
with the manual banner, skipping the assertions, the quiet watch, and
the automatic revert. MERGED-with-empty-mergeCommit is now a bounded
PENDING state; only the final check fails closed.

Thread 3834590328: the suffix scan skips branch names that exist
LOCALLY too — a prior attempt's failed push left the renamed branch
behind, and `git branch -m` refuses an existing target, so the retry
could never rename again.

No network: the shared fake-gh/fake-git/fake-clock harness drives the
act; dequeue_rc lists serve per-attempt mutation outcomes and a
git_answers wrapper serves the local `branch --list` probe.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round17_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    DEQUEUE_ARGV,
    GRAPHQL_ARGV,
    HEAD,
    MERGE_SHA,
    NODE_ID_ARGV,
    POLL_ARGV,
    MergeHarness,
    merged,
    pending,
    queued_entry,
    thread,
)

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"
COMMIT_X = "bbbb0000000000000000000000000000000000aa"
COMMIT_Y = "cccc0000000000000000000000000000000000bb"
FOREIGN_DUP = "eeee0000000000000000000000000000000000d1"
EXCLUDED_MERGE = "9999000000000000000000000000000000000mm"
REBASED_FIRST = "eeee000000000000000000000000000000000b01"
BRANCH = f"revert/pr39-{MERGE_SHA[:7]}"
DEAD_HEAD = "dead0000000000000000000000000000000000ff"


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


def clean_surveys(count: int = 1):
    return iter([[thread("11", "resolved")] for _ in range(count)])


def merged_no_sha(base: str = "dev", head: str = HEAD) -> dict:
    return {"state": "MERGED", "mergeCommit": None,
            "baseRefName": base, "headRefOid": head}


class QueueSettleOnDisableFailTests(unittest.TestCase):
    def test_queued_disable_failure_still_dequeues(self):
        # Given: the completion poll timed out still-OPEN and the PR
        # is QUEUED — it has NO auto-merge request, so
        # `gh pr merge --disable-auto` exits 1 (thread 3834590317's
        # exact finding: the round-16 gate required a SUCCESSFUL
        # disable before any settlement, so the live entry was never
        # dequeued and the guard exhausted its three attempts into the
        # both-contingency banner instead).
        surveys = iter([[thread("11", "resolved")]])

        def rc_for(argv):
            return 1 if "--disable-auto" in argv else 0

        # When: attempt 1's disable fails, the queue probe reads
        # QUEUED, the re-check stays OPEN, and the settlement's first
        # dequeue mutation then SUCCEEDS (the entry reads ABSENT with
        # the PR still OPEN, and the settling window holds).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 44,
            rc_for=rc_for,
            queue_entries=[queued_entry(), queued_entry(), None],
            dequeue_rc=0,
        )

        # Then: the settlement RAN despite disable_rc=1 — no retry
        # progress line, the dequeue dispatched through the pinned
        # node-id view, the removal re-verified by the probe and the
        # settling window, and the CONVERGED banner reports how the
        # entry left; never the both-contingency manual banner.
        self.assertEqual(code, 1)
        self.assertNotIn("CANCEL PENDING attempt=1/3", out)
        self.assertNotIn("CANCEL UNCONFIRMED", out)
        self.assertIn(DEQUEUE_ARGV, argvs)
        self.assertIn("QUEUE ENTRY DEQUEUED", out)
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn(
            "REMOVED by the dequeuePullRequest mutation at queue-watch "
            "probe 1",
            out,
        )
        self.assertIn("STAYED OPEN through the FULL 60s", out)
        self.assertNotIn("MERGED CLEAN:", out)


class DequeueRetryTests(unittest.TestCase):
    def test_transient_failure_then_successes_converge(self):
        # Given: the first dequeue attempt FAILS transiently, the
        # second SUCCEEDS but the entry is RE-ENQUEUED inside the
        # settling window (thread 3834590319's exact finding: the
        # round-15 one-shot guard suppressed every later attempt, so
        # the re-enqueued entry rode the watch to the manual banner).
        surveys = iter([[thread("11", "resolved")]])

        # When: probe 1 reads QUEUED (attempt 1 fails), probe 2 reads
        # QUEUED (attempt 2 succeeds; the settling window then sees
        # the entry REAPPEAR at its second probe), and probe 3 reads
        # QUEUED (attempt 3 succeeds; the settling window now holds
        # OPEN + ABSENT through its deadline).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[pending()] * 46,
            queue_entries=[
                queued_entry(),
                queued_entry(),
                None,
                None,
                queued_entry(),
                queued_entry(),
                None,
            ],
            dequeue_rc=[1, 0],
        )

        # Then: all THREE bounded attempts ran (fail, succeed,
        # succeed), the reappearance was re-met with a fresh dequeue,
        # and the run CONVERGED — the banner reports the removal at
        # queue-watch probe 3, never the manual both-contingency form.
        self.assertEqual(code, 1)
        self.assertEqual(argvs.count(NODE_ID_ARGV), 3)
        self.assertEqual(argvs.count(DEQUEUE_ARGV), 3)
        self.assertIn(
            "DEQUEUE FAILED: the dequeuePullRequest mutation for PR "
            "#39 exited 1",
            out,
        )
        self.assertIn("QUEUE ENTRY DEQUEUED", out)
        self.assertIn("QUEUE ENTRY REAPPEARED at settling probe 2", out)
        self.assertIn("2/3 bounded attempt(s) used", out)
        self.assertIn("3834590319", out)
        self.assertIn("CANCELLED and verified gone", out)
        self.assertIn(
            "REMOVED by the dequeuePullRequest mutation at queue-watch "
            "probe 3",
            out,
        )
        self.assertNotIn("CANCEL UNCONFIRMED", out)
        self.assertNotIn("MERGED CLEAN:", out)


class MergeCommitPollTests(unittest.TestCase):
    def test_unreadable_merge_commit_polls_then_proceeds(self):
        # Given: GitHub reports state=MERGED while mergeCommit is not
        # yet readable (thread 3834590326's exact finding: the
        # round-16 verdict terminated INSTANTLY with the manual banner
        # — no destination/head assertions, no quiet watch, no
        # automatic revert), and the sha populates on the next poll.
        surveys = clean_surveys(2)

        # When: poll 1 reads MERGED-with-empty-mergeCommit and poll 2
        # reads the populated landing on the verified base and head.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged_no_sha(), merged()],
        )

        # Then: the empty read was treated as still-pending (the
        # dedicated progress line, then the ordinary pending cadence),
        # the poll CONTINUED, and the populated sha went through the
        # ORDINARY post-merge path — assertions, quiet watch, MERGED
        # CLEAN — never the manual unverified-merge banner.
        self.assertEqual(code, 0)
        self.assertIn("MERGE COMMIT UNREADABLE", out)
        self.assertIn("3834590326", out)
        self.assertIn("MERGE PENDING attempt=1/30", out)
        self.assertIn("QUIET PERIOD cycle=1", out)
        self.assertIn("MERGED CLEAN", out)
        self.assertNotIn("exposes no mergeCommit", out)
        self.assertEqual(argvs.count(POLL_ARGV), 2)
        self.assertEqual(RUNNER.clock.slept, [10.0])

    def test_persistently_unreadable_merge_commit_fails_closed(self):
        # Given: the mergeCommit stays unreadable through the ENTIRE
        # bounded window — the final check must fail closed (the
        # unverified-merge manual banner), never a clean or cancelled
        # claim, and never an instant terminal on the FIRST read.
        surveys = iter([[thread("11", "resolved")]])

        # When: all 30 in-loop polls AND the final no-sleep check read
        # MERGED with an empty mergeCommit.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged_no_sha()] * 31,
        )

        # Then: the FULL window was polled (30 sleeps + the final
        # check), the final-check banner names the unreadable
        # mergeCommit, no cancel plumbing ran (the state never read
        # OPEN), and no clean claim printed.
        self.assertEqual(code, 1)
        self.assertIn("MERGE COMMIT UNREADABLE", out)
        self.assertIn("MERGE PENDING attempt=30/30", out)
        self.assertIn("reports MERGED but exposes no mergeCommit", out)
        self.assertIn("even at the final poll of the bounded window", out)
        self.assertIn("3834590326", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertNotIn("--disable-auto", " ".join(argvs))
        self.assertEqual(argvs.count(POLL_ARGV), 31)
        self.assertEqual(RUNNER.clock.slept, [10.0] * 30)


class DetachedSuffixTests(unittest.TestCase):
    def test_locally_existing_suffix_never_blocks_the_detached_push(self):
        # Given: a prior attempt left refs/heads/<branch>-2 behind
        # LOCALLY (thread 3834590328's residue — its push failed
        # after the old `git branch -m` rename), the remote still
        # holds the BASE branch name at a different commit, and -2
        # is free REMOTELY. Round 20 (thread 3834819191) removed the
        # rename entirely — the revert builds on a DETACHED HEAD and
        # the push refspec never touches local refs — so the local
        # namespace is not even CONSULTED and the local residue
        # cannot block the suffix the way it aborted `branch -m`.
        surveys = iter([[thread("11", "resolved")]])

        def answers(argv, stdin):
            if argv[1:2] == ["-C"] and argv[3:5] == ["branch", "--list"]:
                return (0, f"  {argv[5]}\n")
            return None

        # When: the suffix scan finds -2 free on the remote and the
        # detached-HEAD push lands the commit straight on it.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_heads={BRANCH: DEAD_HEAD},
            git_answers=answers,
        )

        # Then: NO local-namespace probe ran (no `branch --list`, no
        # `branch -m`), the push refspec created refs/heads/<branch>-2
        # from the worktree's detached HEAD, and the PR carries the
        # -2 name.
        self.assertEqual(code, 1)
        tmp = RUNNER.revert_tmp
        joined = " ".join(argvs)
        self.assertNotIn("branch --list", joined)
        self.assertNotIn("git branch -m", joined)
        self.assertIn("REVERT BRANCH SUFFIXED", out)
        self.assertIn("3834819191", out)
        self.assertIn(
            f"git -C {tmp} push origin HEAD:refs/heads/{BRANCH}-2",
            argvs,
        )
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(f"--head {BRANCH}-2", create)
        self.assertIn("REVERT PR OPENED", out)


if __name__ == "__main__":
    unittest.main()
