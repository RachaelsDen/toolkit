"""The survey banner — the reaction signal's human-facing read.

PR #49 round 11 (thread 3868979509, P1) split this home out of
pr_guard_reaction.py at the 250 pure-LOC ceiling (split-first, the
PR #36 round-2 family rule): reaction.py stood AT 250 and round 11
grows the reading itself (the EYES head-binding classification and
the shared probe budget), so the banner — a self-contained
presentation concern — moves here. Imports flow ONE way: banner
FROM reaction (bot_review_reaction, VAULT_NOTE) and FROM latch
(render_state); nothing imports back.

THE BANNER: survey's first-class BOT REACTION line — FAIL-OPEN by
design. The reaction is the cheap WAIT signal, never the merge
authority, so an unreadable reaction must not block or kill a
survey (a pre-merge running through survey()): a failed read prints
UNREADABLE and survey continues on thread state alone.

Thread 3867653642 (PR #49 round 3, P2): the read is bounded by
BANNER_TIMEOUT_SECS — a stalled gh api raises TimeoutExpired into
the EXISTING fail-open path (UNREADABLE, survey continues) instead
of hanging survey — and with it pre-merge and the post-merge quiet
watch — indefinitely. Not deadline-driven like the wait probes:
15s is generous for healthy reads yet short enough that the banner
never becomes the gate's long pole.

THE BANNER'S HOMES (threads 3867757449/3867897759/3868158297, and
round 11's 3868979526): ONLY human-facing informational surveys —
the plain survey CLI, harden, pre-merge's OPENING survey, and
resolve's OPENING survey. EVERY survey whose snapshot feeds a gate
decision passes reaction=False at ITS call site (pr_guard_threads.
survey's reaction flag): the guarded merge's closing survey, the
post-merge quiet watch's cycles and final verdict, pre-merge's
CLOSING late-findings check, and — since thread 3868979526 —
resolve's FINAL AUDIT, because the banner's bounded 15s
informational read between that snapshot and the RESOLVE DONE
go/no-go could let a bot follow-up land on an already-resolved
thread while the audit consumed the stale clean list.

PR #49 ROUND 23 lives here too (thread 3873317572, P2): a
state-only THUMBS_UP renders as an UNQUALIFIED snapshot. The
banner calls bot_review_reaction — the state-only wrapper with NO
freshness machinery — so when a same-head, request-less follow-up
round is queued but has not yet posted EYES, the preceding round's
still-present +1 classifies THUMBS_UP and the banner's plain
render ("review complete, nothing further") claimed the PENDING
round passed. The wait path deliberately holds exactly this
initial-+1 shape (rounds 5/13's freshness checks), but the banner
never ran them, so its DONE render now carries the explicit
unverified qualification; every other state keeps render_state's
one-line reading, and the WAIT's own renders/exit logic are
untouched (they already carry the freshness machinery).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round23_test -v
"""

from . import pr_guard_reaction
from .pr_guard_reaction_latch import render_state

BANNER_TIMEOUT_SECS = 15.0


def reaction_banner(pr: int, thread_labels: list[str] | None = None) -> str:
    """Survey's BOT REACTION line — FAIL-OPEN by design (see module)."""
    # Round 7's seam rule (thread 3868158304): the reading is called
    # THROUGH the reaction module's namespace — tests patch
    # pr_guard_reaction.bot_review_reaction / subprocess / head_ref_oid
    # and every patch must keep pointing at ONE home after this
    # round-11 split.
    if thread_labels:
        shown = ", ".join(thread_labels[:3]) + ("…" if len(thread_labels) > 3 else "")
        authority = f"threads {shown} are the authority"
    else:
        authority = "thread state is the authority"
    try:
        state = pr_guard_reaction.bot_review_reaction(
            pr, timeout_secs=BANNER_TIMEOUT_SECS
        )
    except (SystemExit, Exception):
        print(
            f"BOT REACTION: UNREADABLE (the reaction read failed — "
            f"{authority}; see vault note "
            f"'{pr_guard_reaction.VAULT_NOTE}')"
        )
        return "UNREADABLE"
    # Thread 3873317572 (PR #49 round 23, P2): a state-only DONE is
    # an UNQUALIFIED snapshot — bot_review_reaction cannot run the
    # wait's freshness checks (rounds 5/13: the initial +1 may be
    # the PRECEDING round's pass while a queued follow-up round has
    # not yet posted EYES), so the banner must never present the
    # bare +1 as the current round's completion. Banner path ONLY —
    # the wait's own renders keep their verdict lines.
    rendered = render_state(state)
    if state == pr_guard_reaction.REACTION_DONE:
        rendered = (
            "THUMBS_UP (unqualified snapshot — the wait's freshness "
            "checks are not applied here; threads remain the "
            "authority)"
        )
    print(
        f"BOT REACTION: {rendered} — {authority}; this is the "
        f"cheap wait signal (vault note '{pr_guard_reaction.VAULT_NOTE}')"
    )
    return state
