"""The terminal banners of the merge-queue settlement.

Split from pr_guard_settle.py at the PR #41 round-11 fixes: settle
stood at 247/250 pure LOC (HOT). The two banner builders are pure
string renders consumed by settle itself (the exhausted queue watch
and the re-disable budget exhaustion) and by pr_guard_completion and
pr_guard_merge (the cancel disposal's terminal fallback). The window
constants they render moved with them to pr_guard_common (settle
still reads them from there) so this stays a LEAF module beside
common — the one-way import rule holds (completion -> settle ->
revert -> range/remote -> common, with completion/settle/merge ->
settle_banners -> common).
"""

from .pr_guard_common import ABSENT_SETTLE_INTERVAL
from .pr_guard_common import ABSENT_SETTLE_WINDOW_SECS
from .pr_guard_common import CANCEL_RECHECK_SECS, MERGE_POLL_INTERVAL


# Threads 3832418151/3832522306/3833073940/3833251675/3833360201/
# 3833540916/3833762320: the converged-cancel evidence — both
# contingencies verified gone, with the deadline-measured settling
# window as the final proof (OPEN PERSISTED to the deadline with the
# entry ABSENT at every probe, the last one at/after it, and the
# autoMergeRequest re-read NULL at every probe — thread 3833762320:
# any non-null re-read would have re-dispatched --disable-auto
# instead of converging). Thread 3834093639 (round 13): the queue
# watch is DEADLINE-measured, so the banner names the outer probe's
# INDEX without a nominal attempt total — the watch's duration is the
# window constant, not probe-count math. Thread 3834375737 (round 15):
# a dequeue_note names how the entry left when the convergence
# followed a successful dequeuePullRequest mutation. Thread
# 3834988957 (round 23): the disable clause reports the OBSERVED rc —
# when cancellation handled a QUEUED PR the disable legitimately
# exits nonzero (no auto-merge request exists, thread 3834590317)
# and the rc was deliberately IGNORED, and the banner must say THAT
# instead of implying success ("exited 0" was false cancellation
# evidence in the operator's audit trail); disable_rc 0/None keeps
# the historical exited-0 claim (every real caller passes the rc).
# Thread 3835501550 (PR #41 round 30): the banner renders the window
# the watch ACTUALLY ran (window_secs — a re-settlement window is
# 30s, and claiming the ordinary 60s would be false evidence) and a
# non-empty resettle_note names the ONE bounded re-entry that
# preceded the convergence. Thread 3835587497 (round 31): the
# re-disable clause reports the PACING — the re-disables were
# dispatched at the cancellation cadence, never back-to-back.
def absent_settled_banner(
    pr: int,
    base: str,
    attempts: int,
    watch_attempt: int,
    redisables: int,
    dequeue_note: str = "",
    disable_rc: int | None = None,
    window_secs: float = ABSENT_SETTLE_WINDOW_SECS,
    resettle_note: str = "",
) -> str:
    disable_note = (
        f"{pr} --disable-auto was DISPATCHED and exited {disable_rc} — "
        f"the rc deliberately IGNORED because the queue probe read "
        f"QUEUED (a QUEUED PR has no auto-merge request to disable — "
        f"threads 3834590317/3834988957) —"
        if disable_rc
        else f"{pr} --disable-auto exited 0,"
    )
    redisable_note = (
        f" ({redisables} bounded auto-merge re-disable(s), each PACED "
        f"at a {CANCEL_RECHECK_SECS:.0f}s cadence before the dispatch "
        f"(thread 3835587497), ran inside the watch, thread "
        f"3833762320)"
        if redisables
        else ""
    )
    resettle_clause = (
        f" — {resettle_note}, entered after the reappearance->ABSENT "
        f"re-probe, and the OPEN then stayed OPEN through THIS "
        f"window's full span too"
        if resettle_note
        else ""
    )
    return (
        f"MERGE UNVERIFIED: PR #{pr} never reported state=MERGED "
        f"within {attempts * MERGE_POLL_INTERVAL:.0f}s (merge queue "
        f"stalled?) — the pending request was CANCELLED and "
        f"verified gone to the extent the CLI allows: gh pr merge "
        f"{disable_note} autoMergeRequest=null, "
        f"state=OPEN, still OPEN on a re-check "
        f"{CANCEL_RECHECK_SECS:.0f}s later, the merge-queue entry "
        f"itself {dequeue_note or ''}probed ABSENT (GraphQL "
        f"mergeQueueEntry, queue-watch probe {watch_attempt}), the PR "
        f"state was RE-READ STILL OPEN after the ABSENT probe, and "
        f"that OPEN then STAYED OPEN through the FULL "
        f"{window_secs:.0f}s post-ABSENT settling watch "
        f"with autoMergeRequest re-read NULL at every probe"
        f"{redisable_note}{resettle_clause} "
        f"(deadline-based: probes at a {ABSENT_SETTLE_INTERVAL:.0f}s "
        f"cadence with a FINAL probe at/after the deadline — thread "
        f"3833540916, PR #41 round 8: the round-7 probe COUNT "
        f"converged one sleep early on fast reads; threads "
        f"3833251675/3833360201: a merge in flight can hold the "
        f"cached state OPEN after the entry vanishes, so ONE recheck "
        f"proves nothing; a MERGED read at any settling probe REVERTS "
        f"instead; threads 3832418151/3832522306/3833073940). "
        f"Manually check whether the merge landed on {base} anyway and "
        f"revert it there if it did (direct pushes are "
        f"ruleset-blocked; revert via PR). DO NOT assume "
        f"MERGED CLEAN."
    )


# Threads 3832418151/3832522306/3833073940: the terminal fallback when
# neither the auto-merge nor the queue contingency could be
# cancelled-and-verified — both stay live, and the manual instructions
# must cover both (including the web-UI dequeue for an entry the
# mutation cannot remove). Thread 3834093639 (PR #41 round 13): when
# the QUEUE watch expired, watched_secs renders the MEASURED elapsed
# window instead of the probe-count product — the round-12 banner
# claimed a full 60s watch that a counted loop (six probes, five
# sleeps) never spanned on fast reads; None keeps the unmeasured form
# for the callers that did not run the deadline watch. Thread
# 3834375737 (round 15): the round-14 residual ("gh exposes no
# client-side dequeue") was FALSE — the dequeuePullRequest GraphQL
# mutation is the programmatic dequeue — so the residual now reports
# what the attempt actually did (dequeue_note, a full clause from the
# settlement) or states honestly that no attempt ran on the path.
# Thread 3835501550 (PR #41 round 30): a non-empty resettle_note
# reports that the ONE bounded re-settlement was entered and ALSO
# expired without a verdict — the honest residual when the budget is
# spent. Thread 3835587497 (round 31): a non-empty paced_note reports
# that the bounded auto-merge re-disables were PACED at the
# cancellation cadence and the exhaustion verdict rested on a FRESH
# paced re-read — the exhaustion caller's honest residual.
def both_contingency_banner(
    pr: int,
    base: str,
    attempts: int,
    watched_secs: float | None = None,
    dequeue_note: str | None = None,
    resettle_note: str = "",
    paced_note: str = "",
) -> str:
    watch_note = (
        f"the bounded {watched_secs:.0f}s watch expired "
        f"(deadline-measured with a FINAL probe at/after it — thread "
        f"3834093639)"
        if watched_secs is not None
        else "the bounded watch expired"
    )
    dequeue_residual = (
        f"the dequeuePullRequest mutation {dequeue_note}"
        if dequeue_note is not None
        else "the dequeuePullRequest mutation did NOT run on this path "
        "(no QUEUED observation preceded it)"
    )
    resettle_residual = (
        f"; {resettle_note} was entered after the reappearance->ABSENT "
        f"re-probe and ALSO expired without a verdict (the bounded "
        f"re-entry budget was spent)"
        if resettle_note
        else ""
    )
    paced_residual = f"; {paced_note}" if paced_note else ""
    return (
        f"MERGE UNVERIFIED + CANCEL UNCONFIRMED: PR #{pr} never reported "
        f"state=MERGED within {attempts * MERGE_POLL_INTERVAL:.0f}s "
        f"AND the pending merge could not be cancelled-and-verified — BOTH "
        f"contingencies are live (threads 3832418151/3832522306/"
        f"3833073940): (1) CANCEL the merge manually (gh pr merge {pr} "
        f"--disable-auto, or remove the PR from the merge queue), and "
        f"(2) if it landed on {base} anyway, revert it there (direct "
        f"pushes are ruleset-blocked; revert via PR). RESIDUAL TRUTH "
        f"(threads 3833073940/3834375737): gh has no dequeue CLI "
        f"command — {dequeue_residual} — so the live queue entry could "
        f"only be monitored ({watch_note}){resettle_residual}"
        f"{paced_residual}; remove it manually in the web UI. DO NOT "
        f"assume MERGED CLEAN."
    )


# Thread 3836323285 (PR #45 round 12, P2): the merge dispatch's
# captured stdout/stderr rendered for the operator on the failure
# summary paths. capture_output=True (kept for thread 3836217633's
# no-op-signature classification) removed gh's diagnostics from the
# terminal, so after the lengthy reconciliation the operator saw
# only the numeric return code and lost the actionable GitHub error
# — failed checks, permissions, merge policy, authentication —
# explaining WHY the merge failed. Labeled and truncated to a sane
# bound; "" when nothing was captured (a raised dispatch captures
# nothing — the caller prints nothing then).
MERGE_OUTPUT_PREVIEW = 2000


def merge_output_note(merge_output: str) -> str:
    text = merge_output.strip()
    if not text:
        return ""
    if len(text) > MERGE_OUTPUT_PREVIEW:
        text = (
            f"{text[:MERGE_OUTPUT_PREVIEW]}\n…[truncated at "
            f"{MERGE_OUTPUT_PREVIEW} chars]"
        )
    return (
        f"MERGE COMMAND OUTPUT (captured stdout/stderr, thread "
        f"3836323285) — the diagnostics gh pr merge printed before "
        f"its nonzero exit:\n{text}"
    )
