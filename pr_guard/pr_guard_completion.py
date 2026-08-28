"""The completion/reconciliation half of the guarded merge act.

Split from pr_guard_merge.py AND pr_guard_revert.py at the 250
pure-LOC ceiling (PR #41 round 6, thread 3833251667): the merge act
had grown to ~260 pure LOC, and the cancel-side queue settlement that
round 6 also had to extend (thread 3833251675) sat in a pr_guard_revert
already at 249. The natural seam on both sides was the SAME one — the
machinery that decides whether a dispatched merge request has truly
SETTLED.

PR #41 round 8 (thread 3833540913): this module had itself reached 252
pure LOC, so the queue-settlement machinery moved to pr_guard_settle —
settle_queue_contingency, the absent-entry settling watch (now
deadline-based, thread 3833540916), read_queue_contingency, the
converged/terminal banners, and the shared landed-state read — leaving
here the bounded completion poll (wait_for_merge_completion, threads
3832321683/3832660859), its verdict (completion_verdict), and the
pending-request cancel (cancel_pending_merge, threads
3832418151/3832522306) that hands a non-settling request to the
settlement module. Imports flow ONE way — completion -> settle ->
revert -> common — so no module in the chain imports back up it.

Thread 3832522306 (PR #40 round 3, carried): `gh pr merge
--disable-auto` disables AUTO-MERGE only — a QUEUED PR observably
shows OPEN + autoMergeRequest=null, so the cancel path verifies BOTH
contingencies it can see before claiming convergence.

Thread 3833073940 (PR #41, carried): even that converged verdict
proves nothing about a QUEUED entry, so convergence additionally runs
the queue-entry settlement now living in pr_guard_settle.
`attempts` is the caller's completion-poll budget (the reconcile path
after a failed merge command runs a SHORTER one, and the banners must
not claim the longer window).

Thread 3834590317 (PR #41 round 17): a QUEUED PR has NO auto-merge
request, so `gh pr merge --disable-auto` legitimately exits nonzero —
the cancel loop now probes the queue when the disable fails and
settles anyway on a LIVE entry (the rc is only meaningful for the
non-queued case); thread 3834988957 (round 23) threads the observed
rc into the settlement so the converged banner reports it instead
of implying the disable exited 0. Thread 3834590326 (round 17):
state=MERGED with an
EMPTY mergeCommit is a bounded PENDING state (GitHub can report
MERGED before the nullable field is readable) — the verdict keeps
polling and only the FINAL check fails closed; see completion_verdict.
"""

import subprocess
import time

from .pr_guard_common import CANCEL_ATTEMPTS, CANCEL_RECHECK_SECS
from .pr_guard_common import MERGE_POLL_ATTEMPTS, MERGE_POLL_INTERVAL
from .pr_guard_common import REPO_FLAG
from .pr_guard_common import gh_env, read_landed_state
from .pr_guard_common import read_pending_state
from .pr_guard_dequeue import read_queue_contingency
from .pr_guard_revert import revert_landed_during_cancel
from .pr_guard_settle import settle_queue_contingency
from .pr_guard_settle_banners import both_contingency_banner


# Thread 3832418151 (PR #40 round 2): the poll timing out does NOT
# undo `gh pr merge` — the request may persist as an enabled
# auto-merge or a merge-queue entry that lands AFTER this process
# exits, bypassing the destination/head assertions and the
# quiet-period watch entirely. Cancel the pending request and VERIFY
# both contingencies are gone before failing closed. Thread
# 3832522306 (PR #40 round 3): `--disable-auto` disables auto-merge
# only and gh 2.97.0 exposes no queue field, so "autoMergeRequest
# null + not MERGED" is NOT sufficient — the converged verdict
# additionally requires state=OPEN and a re-read after
# CANCEL_RECHECK_SECS that is STILL OPEN (a queue entry dequeuing and
# merging shows up as MERGED there); a MERGED verdict at any point
# means the merge landed during cancellation and goes straight to the
# revert path. Thread 3833073940 (PR #41): even that converged verdict
# proves nothing about a QUEUED entry (it observably shows OPEN +
# autoMergeRequest=null), so convergence additionally runs the
# queue-entry settlement in pr_guard_settle. Thread 3835501549
# (PR #41 round 30): the round-29 pre-dispatch merge identity rides
# down from merge_guarded so every MERGED verdict on THIS path (the
# timeout cancel and the interrupt reconciliation alike) is gated
# through the pre-existing check inside revert_landed_during_cancel
# BEFORE any revert — a stale invocation on an already-merged PR
# never auto-reverts the historical merge. Thread 3835877364
# (PR #45 round 4): the evidence widened to the FULL failed-dispatch
# identity (open_merge_sha/dispatch_ts/dispatch_failed) — a stale
# OPEN record that only becomes a visible landing during the
# cancellation is gated through the SAME shared ladder there.
# Thread 3836600782 (PR #45 round 17, P1): the transition-evidence
# holder this loop once threaded (rounds 8-16, pr_guard_transition)
# is RETIRED with the failed path's attribution arms — the
# reviewer's chain proved every between-reads signal reproducible
# by ordered cache snapshots of one historical timeline — so a
# MERGED verdict after a FAILED dispatch is uniformly AMBIGUOUS at
# the gate, and the SUCCESSFUL path needs no observation (rc 0
# bounds it). The reads below are plain verdicts again.
# Returns str (a fail-closed
# banner for the caller to print, exit 1) or int (a terminal exit
# code — the revert already ran and printed inside).
def cancel_pending_merge(
    pr: int,
    base: str,
    attempts: int = MERGE_POLL_ATTEMPTS,
    commits: list[str] | None = None,
    frozen_base_tip: str = "",
    pre_merged: bool = False, pre_merge_sha: str = "",
    open_merge_sha: str = "", dispatch_ts: float = 0.0,
    dispatch_failed: bool = False,
) -> str | int:
    for attempt in range(1, CANCEL_ATTEMPTS + 1):
        disabled = subprocess.run(
            ["gh", "pr", "merge", str(pr), "--disable-auto"] + REPO_FLAG,
            env=gh_env(),
        ).returncode
        verdict = read_pending_state(pr)
        if verdict == "MERGED":
            return revert_landed_during_cancel(
                pr, base, commits, frozen_base_tip,
                pre_merged, pre_merge_sha,
                open_merge_sha, dispatch_ts, dispatch_failed,
            )
        # Thread 3834590317 (PR #41 round 17): a QUEUED PR has NO
        # auto-merge request, so `gh pr merge --disable-auto` legitimately
        # exits nonzero ("nothing to disable") — the rc is only meaningful
        # for the non-queued case. When the queue probe shows a LIVE entry,
        # settlement now proceeds REGARDLESS of the disable's rc: the
        # round-16 gate gated the GraphQL dequeue on a SUCCESSFUL disable
        # from a DIFFERENT cancellation mechanism, so a timed-out QUEUED PR
        # exhausted the three attempts and exited with its live entry
        # never dequeued, never watched to convergence. Thread 3834988957
        # (round 23): the observed rc rides into the settlement so the
        # converged banner reports the ACTUAL disable outcome on the
        # queued path (the old banner's "exited 0" claim was false
        # cancellation evidence); 0 keeps the historical claim.
        queued = False
        if verdict == "OPEN":
            if disabled != 0:
                queued = read_queue_contingency(pr) == "QUEUED"
            if disabled == 0 or queued:
                time.sleep(CANCEL_RECHECK_SECS)
                verdict = read_pending_state(pr)
                if verdict == "MERGED":
                    return revert_landed_during_cancel(
                        pr, base, commits, frozen_base_tip,
                        pre_merged, pre_merge_sha,
                        open_merge_sha, dispatch_ts, dispatch_failed,
                    )
                if verdict == "OPEN":
                    # Thread 3833073940: the auto-merge contingency is
                    # verified gone — settle the merge-queue one before
                    # claiming anything (two OPEN reads never proved it).
                    return settle_queue_contingency(
                        pr, base, attempts,
                        disabled if queued else 0, commits,
                        frozen_base_tip, pre_merged, pre_merge_sha,
                        open_merge_sha, dispatch_ts, dispatch_failed,
                    )
        if attempt < CANCEL_ATTEMPTS:
            # Thread 3835450365 (PR #41 round 29): the attempts are
            # PACED at the cancellation re-check cadence before the
            # next disable — the round-28 form ran all three
            # back-to-back, so a --disable-auto whose effect had not
            # propagated yet (or a transient failure) exhausted the
            # whole budget inside ONE stale-read interval and exited
            # while the accepted auto-merge/queue request stayed live,
            # able to land with no post-merge assertions or survey.
            print(
                f"CANCEL PENDING attempt={attempt}/{CANCEL_ATTEMPTS} "
                f"disable_rc={disabled} verdict={verdict} — the pending "
                f"merge is not proven gone (auto-merge AND merge-queue "
                f"contingencies, thread 3832522306); PACING the retry: "
                f"sleeping {CANCEL_RECHECK_SECS:.0f}s before the next "
                f"disable (thread 3835450365) so each attempt meets a "
                f"FRESH read window, never the same stale one."
            )
            time.sleep(CANCEL_RECHECK_SECS)
        else:
            print(
                f"CANCEL PENDING attempt={attempt}/{CANCEL_ATTEMPTS} "
                f"disable_rc={disabled} verdict={verdict} — the PACED "
                f"budget is exhausted ({CANCEL_ATTEMPTS} disables at a "
                f"{CANCEL_RECHECK_SECS:.0f}s cadence, thread "
                f"3835450365); failing closed with both contingencies."
            )
    return both_contingency_banner(pr, base, attempts)


# Thread 3832321683: poll the PR until the merge has truly completed.
# Returns (merge_sha, landed_base, landed_head) once state == MERGED.
# Thread 3836600782 (PR #45 round 17, P1): the fourth
# transition_observed element rounds 8-16 appended (the retired
# pr_guard_transition holder's attributed() verdict) is GONE — the
# failed-dispatch path no longer observes for attribution AT ALL
# (the reviewer's chain proved every between-reads signal
# reproducible by ordered cache snapshots of one historical
# timeline), and the successful path never consulted it (rc 0
# bounds the landing). An error banner (fail-closed str) if the
# PR closed unmerged, reports MERGED without a merge commit, or the
# bounded poll times out, or an int exit code when the timeout path
# already handled itself. Thread 3832321698: baseRefName rides along
# every attempt so the destination is re-asserted against the
# verified base exactly when MERGED lands.
# Thread 3832522310: headRefOid rides along too — the FINAL head is
# re-asserted against the surveyed head once MERGED. Thread
# 3832660859 (PR #40 round 4): the loop's polls land at ~0-290s and
# the old code slept unconditionally after attempt 30 before
# cancelling, so a merge completing inside that FINAL interval was
# never observed as MERGED — cancel_pending_merge saw it instead and
# sent a clean landing straight through the revert path. ONE more
# completion check now runs after the loop (no sleep); only a final
# check that still shows no merge falls through to the cancellation.
def wait_for_merge_completion(
    pr: int,
    base: str,
    head: str,
    attempts: int = MERGE_POLL_ATTEMPTS,
    commits: list[str] | None = None,
    frozen_base_tip: str = "",
    pre_merged: bool = False, pre_merge_sha: str = "",
    open_merge_sha: str = "", dispatch_ts: float = 0.0,
    dispatch_failed: bool = False,
) -> tuple[str, str, str] | str | int:
    for attempt in range(1, attempts + 1):
        state, landed_base, merge_sha, landed_head = read_landed_state(
            pr
        )
        settled = completion_verdict(
            pr, base, head, state, landed_base, merge_sha, landed_head
        )
        if settled is not None:
            return settled
        print(
            f"MERGE PENDING attempt={attempt}/{attempts} "
            f"state={state or 'unknown'} base={landed_base or base} — the "
            f"merge queue / auto-merge is still draining (thread "
            f"3832321683); next poll in {MERGE_POLL_INTERVAL:.0f}s."
        )
        time.sleep(MERGE_POLL_INTERVAL)
    state, landed_base, merge_sha, landed_head = read_landed_state(pr)
    settled = completion_verdict(
        pr, base, head, state, landed_base, merge_sha, landed_head,
        final=True,
    )
    if settled is not None:
        return settled
    print(
        f"MERGE PENDING final check state={state or 'unknown'} "
        f"base={landed_base or base} — the bounded window expired, so "
        f"this last poll ran without a preceding sleep (thread "
        f"3832660859: a merge completing during the FINAL interval is "
        f"observed HERE, never bounced to the cancel path); cancelling."
    )
    # Thread 3835145981 (round 25): the frozen pre-dispatch commit
    # snapshot rides into the cancel path so a merge observed landing
    # during cancellation reverts with the pre-dispatch diagnostics,
    # never a post-merge re-read of the moved PR. Thread
    # 3835290443 (round 26): the frozen pre-dispatch BASE TIP rides
    # the same way — the single-parent revert's comparison target.
    # Thread 3835501549 (round 30): the round-29 pre-dispatch merge
    # IDENTITY rides the same way, so the timeout cancel's MERGED
    # verdict is pre-existing-gated before any revert. Thread
    # 3835877364 (PR #45 round 4): the FAILED-dispatch identity
    # evidence (open-record sha, dispatch wall clock, the failed
    # flag) rides the same way — the cancel gate below widens with
    # it. Thread 3836600782 (round 17): the transition holder once
    # threaded here is retired with the failed path's attribution.
    return cancel_pending_merge(
        pr, base, attempts, commits, frozen_base_tip,
        pre_merged, pre_merge_sha,
        open_merge_sha, dispatch_ts, dispatch_failed,
    )


# Thread 3832660859: the shared in-loop/final-check verdict — the
# settled outcome (tuple/banner str) or None while still pending.
# Thread 3834590326 (PR #41 round 17): state=MERGED with an EMPTY
# mergeCommit is a bounded PENDING state, not a terminal one — GitHub
# can report MERGED before the nullable mergeCommit is readable, and
# the round-16 code terminated instantly with the manual banner,
# skipping the destination/head assertions, the quiet watch, and the
# automatic revert even though the merge had definitely landed. The
# verdict keeps polling (it normally populates within seconds); only
# the FINAL check (final=True) fails closed with the unverified-merge
# banner.
def completion_verdict(
    pr: int,
    base: str,
    head: str,
    state: str,
    landed_base: str,
    merge_sha: str,
    landed_head: str,
    final: bool = False,
) -> tuple[str, str, str] | str | None:
    if state == "MERGED":
        if not merge_sha:
            if not final:
                print(
                    f"MERGE COMMIT UNREADABLE: PR #{pr} reports "
                    f"state=MERGED but mergeCommit is not yet readable "
                    f"(thread 3834590326) — treating this poll as "
                    f"still-pending and CONTINUING the bounded window "
                    f"(the sha normally populates); the final check "
                    f"fails closed if it never does."
                )
                return None
            return (
                f"MERGE UNVERIFIED: PR #{pr} reports MERGED but exposes "
                f"no mergeCommit even at the final poll of the bounded "
                f"window (thread 3834590326: the unreadable mergeCommit "
                f"was POLLED to the window's end, never an instant "
                f"terminal no-op) — if it landed, the merge MUST be "
                f"reverted manually on {landed_base or base} (direct "
                f"pushes are ruleset-blocked; revert via PR)."
            )
        return (merge_sha, landed_base, landed_head)
    if state == "CLOSED":
        return (
            f"MERGE DID NOT LAND: PR #{pr} reports state=CLOSED (closed "
            f"without merging) — nothing to revert; re-run the loop."
        )
    return None
