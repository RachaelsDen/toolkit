"""The post-ABSENT settling watch, split from pr_guard_settle.py at
the PR #41 round-31 fixes (thread 3835587497).

Settle stood at 247/250 pure LOC with the round-31 PACING fix for the
bounded auto-merge re-disables inbound, so the watch — the machinery
the fix lands in — moved to this sibling. Imports flow ONE way
(settle -> settle_watch -> dequeue/revert/settle_banners -> common):
settle passes this watch INTO pr_guard_dequeue's attempt_queue_dequeue
as the injected settle_watch callable (the round-15 injection pattern),
so dequeue never imports this module and no cycle forms.

Threads 3833360201/3833540916 (PR #41 rounds 7-8, carried): a queued
merge removes its mergeQueueEntry BEFORE the separately cached PR
state flips to MERGED, so the ABSENT probe's accompanying OPEN read —
and even ONE immediate re-read — can both be stale OPEN from a merge
still in flight; this watch keeps probing OPEN + ABSENT for a bounded
DEADLINE-measured window (a monotonic deadline plus one FINAL probe
at/after it, the preceding sleep clamped to the REMAINING window) —
a probe COUNT under-watches by one sleep — before any converged
cancellation claim. Thread 3833251675's fail-closed rule carries:
never a cancellation claim on weaker evidence.

Thread 3833762320 (PR #41 round 10, carried): every probe ALSO reads
autoMergeRequest — another operator or automation can re-enable
auto-merge after the initial successful --disable-auto, and OPEN +
ABSENT alone would converge while a RE-ENABLED request sits live and
lands later with no assertions. A non-null re-read re-dispatches
--disable-auto (bounded to SETTLE_REDISABLES_MAX re-disables, the
window extended one ABSENT_SETTLE_WINDOW_SECS per re-disable); still
non-null with the budget exhausted returns the both-contingency
banner instead of the converged-cancel one.

Thread 3835501550 (PR #41 round 30, carried): the watch returns the
REAPPEARED sentinel (pr_guard_common) when the entry was seen live
again, plain None on weaker evidence, so the caller can distinguish
a reappearance (which can earn ONE bounded re-settlement window at a
spent outer deadline) from ambiguity (which never does).

Thread 3835587497 (PR #41 round 31 — THIS round's P1): the re-disable
attempts and the exhaustion probe are PACED at the cancellation
re-check cadence (CANCEL_RECHECK_SECS, the round-29 cancel-pacing
precedent of thread 3835450365). The round-30 form's `continue`
re-probed immediately after each re-disable, so both bounded
re-disables and the exhaustion probe ran back-to-back: ordinary
--disable-auto propagation delay kept the re-read non-null through
the whole budget inside ONE stale-read interval, and the guard
returned the contingency banner while the accepted request remained
live and able to land after exit, with no destination/head assertions
and no post-merge survey. The paced form sleeps BEFORE consuming
another re-disable attempt (each dispatch meets a FRESH read window)
and AGAIN before the exhaustion verdict — which then rests on a FRESH
paced re-read, never the stale read that watched the re-enable; a
fresh read that no longer says AUTO continues the watch instead of
declaring the budget exhausted.

Thread 3835714804 (PR #43 round 2): the exhaustion probe's FRESH
read seeing MERGED is a DEFINITIVE landing observation, never
disable-propagation evidence — the broad != "AUTO" branch used to
swallow it into the propagated arm, and a later stale/unreadable
state read could end the flow in a cancellation banner with no
revert. MERGED at the exhaustion probe goes straight through the
pre-existing-gated revert path (revert_landed_during_cancel), the
same arm the watch's own per-probe MERGED observations take.
"""

import subprocess
import time

from .pr_guard_common import ABSENT_SETTLE_INTERVAL
from .pr_guard_common import ABSENT_SETTLE_WINDOW_SECS
from .pr_guard_common import CANCEL_RECHECK_SECS
from .pr_guard_common import REAPPEARED
from .pr_guard_common import REPO_FLAG
from .pr_guard_common import deadline_clamped_sleep
from .pr_guard_common import gh_env, read_auto_merge, read_landed_state
from .pr_guard_dequeue import read_queue_contingency
from .pr_guard_revert import revert_landed_during_cancel
from .pr_guard_settle_banners import absent_settled_banner
from .pr_guard_settle_banners import both_contingency_banner

# Thread 3833762320 (PR #41 round 10, moved with the watch at round
# 31): the bounded re-disable budget for an autoMergeRequest that
# REAPPEARS during the settling watch — another operator or
# automation can re-enable auto-merge after the initial
# --disable-auto, and an unbounded re-disable loop would ping-pong
# with a competing automation forever.
SETTLE_REDISABLES_MAX = 2


# The post-ABSENT settling watch (threads 3833360201/3833540916,
# carried from pr_guard_settle — see the module docstring). Thread
# 3835501550 (round 30): window_secs is a PARAMETER (the ordinary
# 60s window, or the 30s re-settlement window from
# settle_queue_contingency's bounded re-entry) and the converged
# banner renders the window ACTUALLY run plus the caller's
# resettle_note. Thread 3834375737 (round 15) threads a dequeue_note
# through from the post-dequeue convergence; thread 3834988957
# (round 23) the observed disable rc; thread 3835501549 (round 30)
# the pre-dispatch merge identity so a MERGED verdict inside the
# window is gated through the pre-existing check before any revert.
# Returns None to mean "keep watching", a str banner, or an int exit
# code from the revert. Thread 3835587497 (round 31): the AUTO branch
# is PACED — see the module docstring. Thread 3835877364 (PR #45
# round 4): the FAILED-dispatch identity evidence rides the same way
# so every MERGED verdict inside the window is gated through the
# SHARED ladder in revert_landed_during_cancel. Thread 3836600782
# (PR #45 round 17, P1): the transition-evidence holder rounds 8-16
# threaded through the probes is RETIRED (no client-side observation
# can attribute a failed dispatch's landing — the reviewer's rounds
# 7-17 chain), so the probes below read plain verdicts and every
# failed-dispatch MERGED verdict is uniformly AMBIGUOUS at the gate;
# a successful dispatch's landing still reverts (rc 0 bounds it).
def watch_absent_entry_settlement(
    pr: int,
    base: str,
    attempts: int,
    watch_attempt: int,
    dequeue_note: str = "",
    disable_rc: int | None = None,
    commits: list[str] | None = None,
    frozen_base_tip: str = "",
    window_secs: float = ABSENT_SETTLE_WINDOW_SECS,
    resettle_note: str = "",
    pre_merged: bool = False,
    pre_merge_sha: str = "",
    open_merge_sha: str = "",
    dispatch_ts: float = 0.0,
    dispatch_failed: bool = False,
) -> str | int | None:
    start = time.monotonic()
    deadline = start + window_secs
    probe = 0
    redisables = 0
    while True:
        probe += 1
        state, _, _, _ = read_landed_state(pr)
        if state == "MERGED":
            return revert_landed_during_cancel(
                pr, base, commits, frozen_base_tip,
                pre_merged, pre_merge_sha,
                open_merge_sha, dispatch_ts, dispatch_failed,
            )
        if state != "OPEN":
            # Thread 3833251675's fail-closed branch, carried into the
            # window: never a cancellation claim on weaker evidence.
            return None
        if read_queue_contingency(pr) != "ABSENT":
            print(
                f"QUEUE ENTRY REAPPEARED at settling probe {probe} "
                f"(elapsed {time.monotonic() - start:.0f}s) — the "
                f"ABSENT observation was not durable (thread "
                f"3833360201); resuming the queue watch with its "
                f"QUEUED semantics."
            )
            return REAPPEARED
        auto = read_auto_merge(pr)
        if auto == "MERGED":
            return revert_landed_during_cancel(
                pr, base, commits, frozen_base_tip,
                pre_merged, pre_merge_sha,
                open_merge_sha, dispatch_ts, dispatch_failed,
            )
        if auto == "AUTO":
            # Thread 3835587497 (PR #41 round 31): PACING at the
            # cancellation cadence — the round-30 form ran the bounded
            # re-disables and the exhaustion probe back-to-back (the
            # `continue` re-probed immediately), so --disable-auto
            # propagation delay exhausted the budget inside ONE
            # stale-read interval and the banner fired while the
            # accepted request stayed live. The round-29 precedent
            # (thread 3835450365): sleep before consuming another
            # re-disable attempt, and pace again before the exhaustion
            # verdict below.
            if redisables >= SETTLE_REDISABLES_MAX:
                time.sleep(CANCEL_RECHECK_SECS)
                # Thread 3835587497: the exhaustion probe is a FRESH
                # read taken AFTER the pace — the triggering read can
                # be stale propagation from the LAST re-disable, and
                # only a fresh paced re-read may declare the budget
                # exhausted. A read that no longer says AUTO means the
                # last re-disable TOOK: the watch continues on fresh
                # probes instead of banner-ing over a disable that
                # merely had not landed yet.
                # Thread 3835714804 (PR #43 round 2): but MERGED on
                # that fresh read is a DEFINITIVE landing observation,
                # not disable-propagation evidence — the old broad
                # != "AUTO" branch discarded it into the propagated
                # arm, and a stale/unreadable later read_landed_state
                # could end the flow in a cancellation banner without
                # the revert despite having SEEN the merge. MERGED is
                # handled BEFORE the propagation branch, through the
                # same pre-existing-gated revert path the watch's own
                # auto == "MERGED" arm takes.
                fresh = read_auto_merge(pr)
                if fresh == "MERGED":
                    print(
                        f"MERGED AT THE PACED EXHAUSTION PROBE of "
                        f"settling probe {probe} (thread 3835714804) "
                        f"— the fresh paced re-read observed the "
                        f"landing directly, so the revert runs on "
                        f"this observation and never on a later "
                        f"stale state read."
                    )
                    return revert_landed_during_cancel(
                        pr, base, commits, frozen_base_tip,
                        pre_merged, pre_merge_sha,
                        open_merge_sha, dispatch_ts, dispatch_failed,
                    )
                if fresh != "AUTO":
                    print(
                        f"AUTO-MERGE PROPAGATED at the paced exhaustion "
                        f"probe of settling probe {probe} (thread "
                        f"3835587497) — "
                        f"the last re-disable took effect "
                        f"within the {CANCEL_RECHECK_SECS:.0f}s pace, so "
                        f"the budget is NOT declared exhausted on the "
                        f"stale re-enabled read; the watch continues on "
                        f"fresh probes."
                    )
                    continue
                print(
                    f"AUTO-MERGE STILL RE-ENABLED at settling probe "
                    f"{probe} after {redisables} bounded re-disables "
                    f"each PACED at a {CANCEL_RECHECK_SECS:.0f}s cadence "
                    f"and a FRESH paced re-read here (threads "
                    f"3833762320/3835587497) — a competing operator or "
                    f"automation keeps re-enabling it; the manual "
                    f"instructions cover both contingencies."
                )
                return both_contingency_banner(
                    pr, base, attempts, None, dequeue_note or None,
                    paced_note=(
                        f"the {redisables} bounded auto-merge "
                        f"re-disable(s) were PACED at a "
                        f"{CANCEL_RECHECK_SECS:.0f}s cadence and the "
                        f"exhaustion verdict rests on a FRESH paced "
                        f"re-read (thread 3835587497)"
                    ),
                )
            redisables += 1
            deadline += ABSENT_SETTLE_WINDOW_SECS
            print(
                f"AUTO-MERGE RE-ENABLED at settling probe {probe} "
                f"(thread 3833762320) — PACING the re-disable at the "
                f"cancellation cadence (thread 3835587497: sleeping "
                f"{CANCEL_RECHECK_SECS:.0f}s before the dispatch so it "
                f"meets a FRESH read window, never the stale one that "
                f"watched the re-enable) and re-dispatching --disable-"
                f"auto ({redisables}/{SETTLE_REDISABLES_MAX}) and "
                f"extending the settling window by "
                f"{ABSENT_SETTLE_WINDOW_SECS:.0f}s: persistent OPEN + "
                f"ABSENT no longer converges while a live "
                f"autoMergeRequest can land unbackstopped."
            )
            time.sleep(CANCEL_RECHECK_SECS)
            subprocess.run(
                ["gh", "pr", "merge", str(pr), "--disable-auto"] + REPO_FLAG,
                env=gh_env(),
            )
            continue
        if auto != "OPEN":
            return None
        if time.monotonic() >= deadline:
            # Thread 3833540916: the FINAL probe ran at/after the
            # deadline — the FULL window elapsed, never probes-minus-
            # one sleeps.
            return absent_settled_banner(
                pr, base, attempts, watch_attempt, redisables,
                dequeue_note, disable_rc, window_secs, resettle_note,
            )
        print(
            f"ABSENT SETTLE probe={probe} elapsed="
            f"{time.monotonic() - start:.0f}s/"
            f"{window_secs:.0f}s state=OPEN queue=ABSENT "
            f"auto-merge=null — the entry is gone but the cached PR "
            f"state can still read OPEN from a merge in flight (thread "
            f"3833360201), and the autoMergeRequest is re-checked at "
            f"every probe (thread 3833762320); watching the full "
            f"{window_secs:.0f}s settling window by "
            f"DEADLINE with a final probe at/after it (thread "
            f"3833540916: a probe COUNT under-watches by one sleep) "
            f"for MERGED (reverts) or persistent OPEN (converges)."
        )
        # Thread 3834093639 (PR #41 round 13): the clamped deadline
        # sleep is the shared pr_guard_common.deadline_clamped_
        # sleep — the same discipline the queue watch and the quiet
        # watch use.
        time.sleep(
            deadline_clamped_sleep(deadline, ABSENT_SETTLE_INTERVAL)
        )
