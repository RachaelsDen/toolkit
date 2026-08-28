"""The quiet-period watch half of the guarded merge act.

Split from pr_guard_merge.py at the 250 pure-LOC ceiling (PR #45
round 10, threads 3836217630/3836217633/3836217635): merge stood at
247/250 with round-10's no-op-dispatch classification inbound, so the
QUIET-PERIOD WATCH — the post-merge backstop loop — moved to this
sibling, the round-31 precedent (the settling watch's split to
pr_guard_settle_watch) applied once more. Imports flow ONE way
(merge -> quiet -> {revert, common, threads}); nothing here imports
merge, completion, or identity.

Thread 3829356723 (PR #39, carried): the backstop — re-survey AFTER
completion. A bot last word that landed in the survey->merge window
classifies DANGER here (resolved or not). Thread 3832321706 (PR #40,
carried): the survey dying must not bypass the backstop — merge_guarded
still wraps THIS watch in try/except BaseException and fails closed
through the same revert; the handler lives with the act.

Thread 3832418158 (PR #40 round 2, carried): ONE snapshot can print
MERGED CLEAN before the bot's final round lands (the documented
production failure — rounds arrived minutes after merge), so the
backstop is a QUIET-PERIOD WATCH, aborting to the revert path the
MOMENT any DANGER appears; MERGED CLEAN prints only after the FULL
window passes with zero DANGER. RESIDUAL TRUTH: a bot round arriving
AFTER the quiet period is out of any client-side gate's reach — the
mitigation is bounded monitoring plus the still-open server-side gap.

Thread 3832522300 (PR #40 round 3, carried): the watch is
DEADLINE-based, not cycle-counted — deadline = monotonic() +
quiet_secs; survey -> (DANGER reverts) -> sleep -> repeat while before
the deadline, with one FINAL survey always run at/after it; a short
remaining gap sleeps only the REMAINING time so the final survey lands
at the deadline (quiet_secs=0 stays the documented single snapshot).

Thread 3832660852 (PR #40 round 4, carried): the deadline can expire
between the check and the sleep subtraction, and time.sleep raises
ValueError on a negative duration — the clamped form (the shared
pr_guard_common.deadline_clamped_sleep since round 13, thread
39 3834093639) clamps to zero so the loop's next check breaks
immediately.

Thread 3867897759 (PR #49 round 5, P1): every watch survey — each
cycle's DANGER check AND the final MERGED CLEAN verdict — is a GATE
decision, so all of them run WITHOUT the reaction banner
(survey(pr, reaction=False)): the banner's bounded 15s informational
read between a cycle's snapshot and its revert/no-revert decision
let a bot follow-up land on an already-resolved thread (settled
stays clean, the deadline check exits) with the merged defect never
reverted. The banner's remaining home is the human-facing CLI survey
context, where it delays no decision.
"""

import time

from .pr_guard_common import deadline_clamped_sleep
from .pr_guard_revert import guarded_revert
from .pr_guard_threads import survey

QUIET_INTERVAL_SECS = 60
DEFAULT_QUIET_SECS = 15 * QUIET_INTERVAL_SECS


# Threads 3829356723/3832418158/3832522300 (carried from
# pr_guard_merge at the round-10 split): the deadline-based
# quiet-period watch over the landed merge — survey each
# QUIET_INTERVAL_SECS until quiet_secs have elapsed (one FINAL survey
# at/after the deadline), reverting through guarded_revert the MOMENT
# any DANGER thread appears, and printing MERGED CLEAN only after the
# FULL window passes empty. Returns the act's exit code: guarded_revert
# `or 1` (the completed revert's 0 normalizes nonzero — the open
# revert PR still needs a human merge, thread 3836043658) on DANGER,
# 0 on the clean window.
def quiet_period_watch(
    pr: int,
    base: str,
    merge_sha: str,
    quiet_secs: int,
    commits: list[str] | None = None,
    frozen_base_tip: str = "",
) -> int:
    start = time.monotonic()
    deadline = start + quiet_secs
    cycle = 0
    while True:
        cycle += 1
        # Thread 3867897759 (PR #49 round 5, P1): this snapshot FEEDS
        # a gate decision (the DANGER revert below, the MERGED CLEAN
        # verdict after the loop) — reaction=False keeps the banner's
        # 15s informational read out of the decision window.
        settled = survey(pr, reaction=False)
        late = [t for t in settled if t.classification == "DANGER"]
        elapsed = time.monotonic() - start
        if late:
            print(
                f"POST-MERGE DANGER: {len(late)} thread(s) hold a bot "
                f"last word ({', '.join(t.label for t in late)}) — "
                f"caught at quiet-period cycle {cycle}, {elapsed:.0f}s "
                f"into the {quiet_secs}s window (threads "
                f"3832418158/3832522300). REVERTING."
            )
            return guarded_revert(pr, base, merge_sha, "danger", commits, frozen_base_tip) or 1
        print(
            f"QUIET PERIOD cycle={cycle} elapsed={elapsed:.0f}s/"
            f"{quiet_secs}s — no bot last word on any thread (threads "
            f"3832418158/3832522300 deadline watch)."
        )
        if time.monotonic() >= deadline:
            break
        # Thread 3832660852: never a negative sleep past the deadline
        # (thread 3834093639: the shared clamped form) — the loop's
        # next check breaks immediately.
        time.sleep(
            deadline_clamped_sleep(deadline, QUIET_INTERVAL_SECS)
        )
    print(
        "MERGED CLEAN: the full quiet-period watch — first survey "
        "immediately, final survey at/after the deadline (thread "
        "3832522300) — found no bot last word on any thread; the residual "
        "survey->merge window closed empty and stayed empty for the whole "
        "bounded window. Residual truth (thread 3832418158): a bot round "
        "arriving AFTER the window is out of any client-side gate's reach "
        "— bounded monitoring mitigates it, the server-side gap remains "
        "open."
    )
    return 0
