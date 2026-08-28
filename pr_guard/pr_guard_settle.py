"""The merge-queue settlement half of the guarded merge act.

Split from pr_guard_completion.py at the 250 pure-LOC ceiling (PR #41
round 8, thread 3833540913): the completion module had reached 252
pure lines with round 7's absent-entry settling watch. This module now
owns the machinery that settles a pending merge request GitHub may
still be holding after the completion poll timed out — the merge-queue
settlement (settle_queue_contingency, thread 3833073940; the GraphQL
queue-entry probe and the round-15 dequeue it triggers live in
pr_guard_dequeue, thread 3834375737), the post-ABSENT settling watch
(watch_absent_entry_settlement,
threads 3833360201/3833540916), and the shared landed-state read
(read_landed_state) that BOTH the settling watch and the completion
poll consume — its home moved with this split because imports must
flow ONE way (completion -> settle -> revert -> common), never a
cycle. pr_guard_completion keeps the bounded completion poll, its
verdict, and the pending-request cancel that hands a non-settling
request here. The converged/terminal banners moved on to
pr_guard_settle_banners at the PR #41 round-11 fixes (settle stood at
247/250 pure LOC, HOT), with the window constants they render moved
to pr_guard_common so the banners module stays a leaf. The
post-ABSENT settling WATCH itself (watch_absent_entry_settlement and
its SETTLE_REDISABLES_MAX budget) moved on to pr_guard_settle_watch
at the round-31 fixes (thread 3835587497) — the round-31 re-disable
PACING fix lands in the watch, and settle was back at the 247/250
ceiling — leaving here the merge-queue watch that orchestrates it
(settle_queue_contingency) and the dequeue-report clause builder.

Thread 3833073940 (PR #41, carried from pr_guard_completion): the
settlement originally assumed gh exposes NO client-side dequeue
operation, so a live queue entry could only be monitored. That premise
was WRONG (thread 3834375737) and is corrected below — the watch
remains the FALLBACK, not the whole story.

Thread 3834375737 (PR #41 round 15): a QUEUED probe result is now met
with an actual DEQUEUE first — the dequeuePullRequest GraphQL mutation
(live-schema-verified; the plumbing lives in pr_guard_dequeue, split
at the same round for the 250 pure-LOC ceiling) runs once with the
PR's node id, and only when the mutation cannot remove the entry (or
the removed entry REAPPEARS) does the bounded watch carry the
contingency, with the terminal banner documenting exactly what the
dequeue attempt did.

Thread 3834590319 (PR #41 round 17): the dequeue is RETRIED, not
one-shot — the round-15 guard suppressed every later attempt once
any report existed, so a transient mutation failure or an entry
automation RE-ENQUEUED during the settlement watch rode out the
window to the manual banner while still live. Each QUEUED probe
re-attempts the removal (bounded by DEQUEUE_ATTEMPTS_MAX), and the
terminal banner reports the attempt count.

Thread 3833251675 (PR #41 round 6, carried): an ABSENT queue-entry
probe still proves NOTHING by itself — a QUEUED PR can dequeue-and-
MERGE in the gap between the cancel's OPEN read and the GraphQL probe
(the entry is gone BECAUSE it merged), so the convergence verdict
RE-READS the PR state after observing the queue removal: MERGED goes
straight through the revert path; only still-OPEN settles.

Thread 3833360201 (PR #41 round 7, carried): that ONE re-read is still
not a durable cancellation signal either — the queue entry can vanish
while the separately cached PR state keeps reading OPEN for a while
(merge in flight) — so the ABSENT branch watches a short bounded
SETTLING window before any converged claim.

Thread 3833540916 (PR #41 round 8): the settling watch is measured by
ELAPSED TIME, not probe count — the round-7 form's 12 probes spanned
only 11 sleeps, so with fast API reads it converged at ~55s while its
banner claimed a FULL 60s watch, and a MERGED flip inside the missing
final interval exited unobserved and unreverted. The watch now uses
the quiet watch's deadline discipline (thread 3832522300): a monotonic
deadline plus one FINAL probe at/after it (the preceding sleep clamped
to the REMAINING window), so even instantaneous reads span the full
window. The quiet watch itself is inline in pr_guard_merge around
survey-specific handling — the shared form of the clamped sleep lives
in pr_guard_common.deadline_clamped_sleep since round 13, used by the
quiet watch, the settling watch, and the queue watch alike.

Thread 3834093639 (PR #41 round 13): the QUEUE watch itself is
deadline-measured now too — its round-12 form counted six probes,
which span only five sleeps, so fast API reads ended the watch at
~50s while its progress and terminal banners computed the full 60s
window, and a queued merge landing inside the missing final interval
exited unobserved into the manual-contingency banner instead of the
revert path. The watch now runs against a monotonic deadline
(QUEUE_WATCH_WINDOW_SECS) with a FINAL probe at/after it, and the
terminal banner renders the MEASURED elapsed window.

Thread 3833762320 (PR #41 round 10): each settling probe ALSO reads
autoMergeRequest — another operator or automation can re-enable
auto-merge after the initial successful --disable-auto, and the
round-9 watch polled only state + queue, so persistent OPEN + ABSENT
converged with a NEW autoMergeRequest live that could land later with
no post-merge assertions or watch. A non-null re-read re-dispatches
--disable-auto (bounded to SETTLE_REDISABLES_MAX re-disables) and
EXTENDS the settling window; still non-null after the budget is
exhausted returns the both-contingency banner instead of the
converged-cancel one.

Thread 3835587497 (PR #41 round 31): the re-disable attempts and the
exhaustion probe inside that watch are PACED at the cancellation
re-check cadence — the round-30 form ran them back-to-back, so
ordinary --disable-auto propagation delay exhausted the budget inside
ONE stale-read interval and the contingency banner fired while the
accepted request remained live. The pacing (and the watch it lives
in) is implemented in pr_guard_settle_watch; the exhaustion banner it
returns reports the pacing (settle_banners renders the paced_note).
"""

import time

from .pr_guard_common import ABSENT_RESETTLE_WINDOW_SECS
from .pr_guard_common import ABSENT_SETTLE_WINDOW_SECS
from .pr_guard_common import DEQUEUE_ATTEMPTS_MAX
from .pr_guard_common import QUEUE_WATCH_INTERVAL
from .pr_guard_common import QUEUE_WATCH_WINDOW_SECS
from .pr_guard_common import REAPPEARED
from .pr_guard_common import deadline_clamped_sleep
from .pr_guard_dequeue import attempt_queue_dequeue, read_queue_contingency
from .pr_guard_common import read_pending_state
from .pr_guard_revert import revert_landed_during_cancel
from .pr_guard_settle_banners import both_contingency_banner
from .pr_guard_settle_watch import watch_absent_entry_settlement

# Thread 3833073940: the bounded queue watch (~60s past the ordinary
# cancel re-check) and the post-ABSENT settling window constants live
# in pr_guard_common since round 11 — the banner renders in
# pr_guard_settle_banners share them. Round 13 (thread 3834093639)
# added QUEUE_WATCH_WINDOW_SECS and the shared deadline_clamped_sleep
# there for the same reason. Round 15 (thread 3834375737): the GraphQL
# queue-entry surface itself (the QUEUE_ENTRY_QUERY probe and the
# dequeue machinery) lives in pr_guard_dequeue — settle imports it,
# never the inverse.

# Thread 3835501550 (PR #41 round 30): the bounded RE-SETTLEMENT
# budget — an expired settling watch whose reappearance is followed by
# an ABSENT re-probe re-enters settlement exactly ONCE (the shorter
# ABSENT_RESETTLE_WINDOW_SECS window), because an unbounded
# reappear/re-settle loop would ping-pong with a re-enqueueing
# automation forever; the budget spent, the spent outer deadline is
# enforced with the manual banner (which reports the used re-entry).
RESETTLES_MAX = 1


# Thread 3833073940 (PR #41): the merge-queue settlement. Thread
# 3833073940's own premise — "gh exposes NO dequeue operation, so this
# watch is the honest best" — was corrected by thread 3834375737
# (round 15): the dequeuePullRequest GraphQL mutation DOES exist (the
# plumbing lives in pr_guard_dequeue), so a QUEUED probe now triggers
# one dequeue ATTEMPT with the PR's node id first; success is
# re-verified by the probe itself (entry gone + PR OPEN goes through
# the same settling window as any other ABSENT observation — the
# removal is never trusted from the mutation's response alone), and
# only a dequeue that cannot remove the entry (or an entry that
# REAPPEARS after a successful one) falls back to this bounded watch
# for it to LAND (revert) or DRAIN (converge); the terminal banner
# documents the attempt either way. The watch stays DEADLINE-based
# (thread 3834093639): the monotonic deadline plus one FINAL probe
# at/after it guarantees the full window elapses, and the banner
# renders the MEASURED elapsed window.
# Thread 3834590319 (PR #41 round 17): compose the terminal banner's
# dequeue clause — the LAST attempt's report (a full clause from
# pr_guard_dequeue naming the probe and outcome) plus the bounded
# attempt count, so the residual truth states HOW MANY removals were
# tried before the watch gave up. None (no attempt ran — e.g. every
# probe was AMBIGUOUS) keeps the banner's honest "did NOT run" form.
def dequeue_banner_note(report: str, attempts: int) -> str | None:
    if not attempts:
        return None
    return (
        f"{report} — {attempts} bounded attempt(s) in total across the "
        f"watch (thread 3834590319: a transient mutation failure or an "
        f"entry re-enqueued during settlement is RETRIED while the "
        f"probe stays QUEUED)"
    )


# Thread 3834988957 (PR #41 round 23): disable_rc is the OBSERVED
# exit code of the cancel loop's `gh pr merge --disable-auto` —
# threaded through to the converged banner so the evidence clause
# reports the ACTUAL rc (a QUEUED cancellation legitimately fails
# the disable; the banner must not imply it exited 0). None keeps
# the historical exited-0 clause for callers that never observed an
# rc. Thread 3836600782 (PR #45 round 17, P1): the
# transition-evidence holder rounds 8-16 threaded through this
# watch is RETIRED (no client-side observation can attribute a
# failed dispatch's landing — the reviewer's rounds 7-17 chain), so
# every MERGED verdict below is gated uniformly AMBIGUOUS on the
# failed path; the successful path's landing still reverts.
def settle_queue_contingency(
    pr: int,
    base: str,
    attempts: int,
    disable_rc: int | None = None,
    commits: list[str] | None = None,
    frozen_base_tip: str = "",
    pre_merged: bool = False, pre_merge_sha: str = "",
    open_merge_sha: str = "", dispatch_ts: float = 0.0,
    dispatch_failed: bool = False,
) -> str | int:
    start = time.monotonic()
    deadline = start + QUEUE_WATCH_WINDOW_SECS
    probe = 0
    # Thread 3834375737: the dequeue attempts' report — a clause the
    # progress line and terminal banner both render verbatim, empty
    # until an attempt ran (an AMBIGUOUS probe never triggers one, and
    # the banner says so instead of claiming an attempt).
    dequeue_report = ""
    # Thread 3834590319 (PR #41 round 17): the round-15 one-shot guard
    # (`not dequeue_report`) permanently suppressed every later dequeue
    # attempt once ANY report existed — a TRANSIENT mutation failure, or
    # a successful dequeue whose entry automation RE-ENQUEUED during the
    # settlement watch, then rode out the whole window to the manual
    # banner while subsequent probes still read QUEUED and the entry
    # stayed able to land after the guard exited. Each QUEUED probe now
    # re-attempts the removal until DEQUEUE_ATTEMPTS_MAX is spent.
    dequeue_attempts = 0
    resettles = 0
    resettle_clause = (
        f"1 bounded {ABSENT_RESETTLE_WINDOW_SECS:.0f}s "
        f"re-settlement window (thread 3835501550)"
    )
    while True:
        probe += 1
        state = read_pending_state(pr)
        if state == "MERGED":
            return revert_landed_during_cancel(
                pr, base, commits, frozen_base_tip,
                pre_merged, pre_merge_sha,
                open_merge_sha, dispatch_ts, dispatch_failed,
            )
        queue = read_queue_contingency(pr)
        if queue == "ABSENT" and state == "OPEN":
            # Thread 3833251675 (PR #41 round 6): the ABSENT probe and
            # the OPEN read are NOT one observation — the queued PR can
            # dequeue-and-MERGE between them (read_pending_state still
            # saw OPEN; the entry is gone BECAUSE it merged). Thread
            # 3833360201 (PR #41 round 7): ONE immediate re-read is not
            # a durable cancellation signal EITHER — the merge in
            # flight can hold the cached state OPEN past that recheck —
            # so the ABSENT branch watches the bounded settling window
            # below instead of returning on the first still-OPEN read.
            # Thread 3835501550 (PR #41 round 30): the watch/re-probe/
            # re-settle cycle is a LOOP — the first entry runs the
            # ordinary ABSENT_SETTLE_WINDOW_SECS window; a watch that
            # returns without a verdict is followed by the round-29
            # RE-PROBE, and (only) a REAPPEARANCE whose re-probe reads
            # ABSENT with the outer deadline already spent re-enters
            # ONE shorter re-settlement window before any banner.
            window = ABSENT_SETTLE_WINDOW_SECS
            resettle_note = ""
            while True:
                settled = watch_absent_entry_settlement(
                    pr, base, attempts, probe,
                    disable_rc=disable_rc, commits=commits,
                    frozen_base_tip=frozen_base_tip,
                    window_secs=window, resettle_note=resettle_note,
                    pre_merged=pre_merged,
                    pre_merge_sha=pre_merge_sha,
                    open_merge_sha=open_merge_sha,
                    dispatch_ts=dispatch_ts,
                    dispatch_failed=dispatch_failed,
                )
                reappeared = settled is REAPPEARED
                if settled is not None and not reappeared:
                    return settled
                # Thread 3835450362 (PR #41 round 29): the settling
                # watch returning without a verdict consumed up to its
                # FULL window — an entry that REAPPEARED on the watch's
                # FINAL probe (or weaker evidence) leaves the pre-watch
                # queue == "ABSENT" STALE, and the round-28 code fell
                # straight to the deadline check below: with the outer
                # window spent, the timeout banner returned while a
                # LIVE entry remained, able to land after the guard
                # exited with no assertions and no survey. RE-PROBE
                # both reads before choosing the branch — a fresh
                # MERGED reverts, a fresh QUEUED dispatches the
                # dequeue, and only a durable ABSENT may reach the
                # banner; the progress/terminal output below reports
                # the RE-PROBED values, never the stale pre-watch pair.
                state = read_pending_state(pr)
                if state == "MERGED":
                    return revert_landed_during_cancel(
                        pr, base, commits, frozen_base_tip,
                        pre_merged, pre_merge_sha,
                        open_merge_sha, dispatch_ts, dispatch_failed,
                    )
                queue = read_queue_contingency(pr)
                print(
                    f"QUEUE RE-PROBE after the settling watch returned "
                    f"without a verdict (thread 3835450362): state={state} "
                    f"queue={queue} — the pre-watch ABSENT/OPEN pair is "
                    f"stale after the consumed window, so the FRESH probe "
                    f"decides the next branch (QUEUED dispatches the "
                    f"dequeue; MERGED reverts; a durable ABSENT continues "
                    f"the watch or banners)."
                )
                if not (
                    reappeared and queue == "ABSENT" and state == "OPEN"
                    and resettles < RESETTLES_MAX
                    and time.monotonic() >= deadline
                ):
                    break
                # Thread 3835501550 (PR #41 round 30): the expired
                # settling watch saw the entry REAPPEAR, and the fresh
                # re-probe reads it ABSENT again with the PR still OPEN
                # — the entry may be mid-consumption (removed to merge
                # right now), and the round-29 code enforced the SPENT
                # outer deadline over that possibly-stale OPEN, so the
                # merge could finish after the read with no revert. ONE
                # fresh bounded re-settlement window (shorter, and
                # bounded in TOTAL by RESETTLES_MAX to avoid a
                # reappear/re-settle loop) watches for the MERGED flip
                # instead; a MERGED read anywhere inside it still goes
                # straight through the (pre-existing-gated) revert path.
                resettles += 1
                print(
                    f"RE-SETTLING after the reappearance->ABSENT "
                    f"re-probe (thread 3835501550): the expired watch "
                    f"saw the entry REAPPEAR and the fresh re-probe "
                    f"reads it ABSENT again with the PR still OPEN — "
                    f"the entry may be mid-consumption, so ONE fresh "
                    f"bounded {ABSENT_RESETTLE_WINDOW_SECS:.0f}s "
                    f"settlement window re-enters (total re-entries "
                    f"bounded: {RESETTLES_MAX}) instead of enforcing "
                    f"the spent outer deadline over the possibly-stale "
                    f"OPEN."
                )
                window = ABSENT_RESETTLE_WINDOW_SECS
                resettle_note = resettle_clause
                continue
        if queue == "QUEUED" and dequeue_attempts < DEQUEUE_ATTEMPTS_MAX:
            # Thread 3834375737 (PR #41 round 15): the entry is LIVE —
            # do not merely watch what can be REMOVED; the flow lives in
            # pr_guard_dequeue's attempt_queue_dequeue, and every
            # non-converging outcome becomes the report the watch and
            # banner document. Thread 3834590319 (round 17): the
            # attempt repeats (bounded) on every later probe that still
            # reads QUEUED.
            dequeue_attempts += 1
            settled, dequeue_report = attempt_queue_dequeue(
                pr,
                base,
                attempts,
                probe,
                watch_absent_entry_settlement,
                disable_rc,
                commits,
                frozen_base_tip,
                pre_merged,
                pre_merge_sha,
                open_merge_sha,
                dispatch_ts,
                dispatch_failed,
            )
            if settled is not None and settled is not REAPPEARED:
                return settled
        elapsed = time.monotonic() - start
        if time.monotonic() >= deadline:
            # Thread 3834093639: this probe ran AT/AFTER the deadline —
            # the FULL window elapsed, never probes-minus-one sleeps,
            # and the banner renders the measured window. Threads
            # 3834375737/3834590319: the dequeue attempts (or their
            # absence) are part of the honest residual the banner
            # reports, WITH the bounded attempt count. Thread
            # 3835501550 (round 30): a used re-settlement is part of
            # the same honest residual.
            return both_contingency_banner(
                pr,
                base,
                attempts,
                time.monotonic() - start,
                dequeue_banner_note(dequeue_report, dequeue_attempts),
                resettle_clause if resettles else "",
            )
        dequeue_status = (
            f" — the dequeuePullRequest mutation {dequeue_report} "
            f"({dequeue_attempts}/{DEQUEUE_ATTEMPTS_MAX} bounded "
            f"attempt(s) used, thread 3834590319)"
            if dequeue_report
            else ""
        )
        print(
            f"QUEUE WATCH probe={probe} elapsed={elapsed:.0f}s/"
            f"{QUEUE_WATCH_WINDOW_SECS:.0f}s queue={queue} "
            f"state={state} — the merge-queue entry is live "
            f"or unverifiable{dequeue_status}; watching the bounded "
            f"{QUEUE_WATCH_WINDOW_SECS:.0f}s window by DEADLINE with a "
            f"FINAL probe at/after it (thread 3834093639: a probe "
            f"COUNT under-watches by one sleep) for it to land "
            f"(revert) or drain (converge)."
        )
        time.sleep(deadline_clamped_sleep(deadline, QUEUE_WATCH_INTERVAL))


# Threads 3832418151/3832522306/3833073940/3833251675/3833360201/
# 3833540916/3833762320: the converged-cancel banner moved to
# pr_guard_settle_banners at the round-11 split (settle at the
# 247/250 pure-LOC ceiling); the watch calls it by import from the
# sibling that owns the watch now. Thread 3833073940's queue-entry
# PROBE (read_queue_contingency) moved on to pr_guard_dequeue at the
# round-15 split (thread 3834375737) to sit beside the dequeue it
# now serves. Thread 3835501549 (PR #41 round 30): the shared
# landed-state read (read_landed_state) and the settling probe's
# autoMergeRequest read (read_auto_merge) moved HOME to
# pr_guard_common with the family's other reads. Thread 3835587497
# (PR #41 round 31): the settling watch ITSELF moved to
# pr_guard_settle_watch (the pacing fix's landing zone, split FIRST
# at the pure-LOC ceiling) — settle passes it into the dequeue flow
# by the import above, never the inverse.
