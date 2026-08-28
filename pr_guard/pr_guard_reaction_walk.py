"""The reaction family's REST reactions walk (gh_reactions).

PR #49 round 15 split this home out of pr_guard_reaction_probe.py at
the 250 pure-LOC ceiling (split-first, the PR #36 round-2 family
rule): the probe module stood at 254 pure LOC and round 15 grows the
GraphQL round-bounds side (the aliased headTransition connection of
thread 3870293194 plus the 3870293197 connection-shape hygiene), so
the OTHER API-read concern — the REST-side paginated issue-reactions
walk — splits first. The walk moved homes once before (reaction.py
-> probe at user-taught refinements #2, the same ceiling); this
split separates the two API-read concerns the round-12 pressure had
colocated: the GraphQL round probe and the REST reactions walk.

SEAM RULES (unchanged by the move): pr_guard_reaction RE-EXPORTS
gh_reactions and ReactionWalkExpired, so every existing test seam
keeps ONE home (mock.patch pr_guard_reaction.gh_reactions — the
round-7 re-export precedent; the walk-module indirection is
invisible at the seams). The walk's subprocess.run resolves through
the global subprocess module like every family read, so the
subprocess-shaped fixtures (the followup pagination pair) are
unaffected. Imports flow ONE way: walk FROM probe (the shared
probe_timeout_budget timing home) and pr_guard_common; nothing
imports back.

Thread 3867503705 (PR #49, P2) is this walk's founding rule: the
endpoint paginates at per_page=100, and a single first-page read
let an OLDER page-1 bot reaction masquerade as the latest while a
newer page-2 signal sat unread — the walk follows the ?page=N
cursor until a SHORT page and flattens every page before any
latest-wins selection. See gh_reactions' docstring (brought over
verbatim) for the full rounds-1-13 discipline.

PR #49 ROUND 19 (thread 3871844580, P2): the MUTATION guard — the
walk is OFFSET-paginated (page numbers, no cursors), so a reaction
added, removed, or moved on an earlier page between two page-number
requests shifts the next page's offset and the flattened walk is an
internally inconsistent snapshot latest-wins must never see. The
locally PROVABLE signatures reject the walk (ReactionWalkExpired,
the round-5 unreadable arm: probe UNREADABLE, retry next interval,
banner fails open): any reaction id REPEATING across consecutive
pages (an addition shifted the offset into overlap), a page boundary
whose first item's created_at strictly PREDATES the previous page's
last item (a reorder), or a same-second boundary whose ids REGRESS
(REST ids increase monotonically). The pure-deletion residue that
round 19 DOCUMENTED (a mid-walk deletion omitting exactly the
boundary item leaves no local signature) is CLOSED by round 24
below for page 1 and GENERALIZED to every full page by round 25
(thread 3873970919) — the re-reads prove each full page's snapshot
changed even when no page PAIR can.

PR #49 ROUND 32 (thread 3876001013, P2): the LENGTH leg of the
per-page revalidation — when the reaction count is an EXACT
MULTIPLE of 100 the walk's terminal page is FULL, so deleting a
NON-FINAL item from its range after the initial fetch leaves the
re-read's newest identity UNCHANGED (the page merely shrinks
100 -> 99; no later item exists to refill the window) and the
identity-only compare accepted the stale flattened page — if the
deleted item is the bot's +1, an armed waiter could still exit 0
from a reaction no longer present. The re-read of a full page must
ALSO stay FULL: the shrunk terminal page (100 -> 99, the
exact-multiple deletion with no refill) raises ReactionWalkExpired.

PR #49 ROUND 33 (thread 3876172349, P2): the TERMINAL short page's
revalidation — the per-page loop re-read only the pages recorded in
full_newest, so the walk's LAST page (the short one that ended it,
possibly the 0-item page of an exact-multiple count) was never
re-read: with more than 100 reactions, a reaction on that short
page deleted AFTER the page was fetched (while the full-page
rechecks run) left every full-page recheck succeeding and the stale
flattened list still containing the deleted item — if it is the
bot's latest +1, an already-armed waiter reported WAIT DONE from a
reaction no longer present (the current state NONE, or a new round
starting). After the full-page rechecks the walk re-reads the
terminal page and requires BOTH its LENGTH and its NEWEST identity
unchanged: the terminal page has NO later page to refill it, so a
deletion shrinks the length without moving the identity (the length
leg is the only witness), and deleting the NEWEST changes the
identity outright; the 0-item terminal page treats length 0 the
same way (a refill — an earlier-page addition shifting items
forward — reads a non-zero page and rejects). Any change, a failed
re-read, or an expired deadline (the recheck rides the walk's
EXISTING deadline, never a fresh grant) raises ReactionWalkExpired
— walk unreadable, retry next interval. Single-page walks still
never recheck (no offset window shifted; the standing round-24
rule). SUPERSEDES round 25's "the SHORT final page shifts nothing
past it" scope: the short page shifts nothing PAST it, but its own
membership can change UNDER it.
"""

import json
import subprocess
import time

from .pr_guard_common import REPO_NAME, REPO_OWNER, die, gh_env
from .pr_guard_reaction_probe import probe_timeout_budget


# Thread 3867897764 (PR #49 round 5, P2): the exception an exhausted
# deadline raises out of gh_reactions mid-walk — the partial page
# list is UNREADABLE, never a latest-wins input. Both callers
# already carry the conservative arm: the banner fails open
# (UNREADABLE, survey continues) and the wait keeps polling under
# its deadline (an unreadable read is never a done signal).
# User-taught refinements #2: moved home from pr_guard_reaction.py
# (the 250 pure-LOC ceiling; the re-export keeps this module's name
# the ONE patch seam). PR #49 round 15: moved again, probe ->
# walk (the ceiling, same rule). PR #49 round 19 (thread
# 3871844580): the class widens from the deadline alone to EVERY
# unusable walk — a MUTATED pagination snapshot (a duplicate id or
# an inverted boundary across consecutive pages) is the same
# never-a-latest-wins-input shape an exhausted deadline produces.
class ReactionWalkExpired(Exception):
    """The reactions walk could not read a CONSISTENT full history.

    The list read so far is INCOMPLETE or INTERNALLY INCONSISTENT —
    latest-wins selection on it could crown an older page-1 bot +1
    while a newer eyes or unknown reaction sits on an unread or
    shifted page (thread 3867897764), or run on pages whose overlap
    proves the reaction set mutated between the page requests
    (thread 3871844580) — so the read must fail as UNREADABLE
    rather than return a partial or mixed input.
    """


# Thread 3871844580 (PR #49 round 19, P2): the mid-walk mutation
# signature — '' when the consecutive page pair is CONSISTENT, a
# reason string when the snapshot provably shifted between the two
# page-number requests (offset pagination re-reads the list from
# the top each page, so any earlier-page mutation moves the next
# page's window). An addition shifts the window into OVERLAP (an id
# repeats across the boundary), a reorder breaks the ascending
# created_at order at the boundary, and a same-second reorder breaks
# the monotonically-increasing REST id order — each is locally
# provable; a pure deletion's omission is not (the module docstring
# residual).
def _page_shift_reason(prior: list, current: list) -> str:
    if not prior or not current:
        return ""
    prior_ids = {str(node.get("id") or "") for node in prior}
    prior_ids.discard("")
    for node in current:
        nid = str(node.get("id") or "")
        if nid and nid in prior_ids:
            return f"reaction id {nid} repeats across the page boundary"
    last, first = prior[-1], current[0]
    last_at = str(last.get("created_at") or "")
    first_at = str(first.get("created_at") or "")
    if last_at and first_at and first_at < last_at:
        return f"page boundary order inverted ({first_at} follows {last_at})"
    last_id = str(last.get("id") or "")
    first_id = str(first.get("id") or "")
    if last_id and first_id:
        regressed = (
            int(first_id) < int(last_id)
            if last_id.isdigit() and first_id.isdigit()
            else first_id < last_id
        )
        if regressed:
            return f"page boundary id regressed ({first_id} follows {last_id})"
    return ""


# Thread 3873592851 (PR #49 round 24, P2): a page item's snapshot
# IDENTITY — `created_at|id`, the same pairing the boundary streams
# use. The stability recheck compares each FULL page's NEWEST item by
# this identity: every page is a POSITIONAL window (page p is items
# (p-1)*100..p*100-1 of the current list), so ANY membership change
# in that range — the pure deletion round 19 could not see, an
# addition, a reorder — moves a different item into the window's last
# position; identical newest identities therefore prove the whole
# window unchanged (unique ids make a changed set landing on the same
# last item impossible).
def _newest_identity(payload: list) -> str:
    node = payload[-1] if payload else {}
    return f"{node.get('created_at') or ''}|{node.get('id') or ''}"


# Thread 3873592851 (round 24) + thread 3873970919 (PR #49 round 25,
# P2): the per-page RE-READ — one lightweight REST call per full page
# after a multi-page walk completes. None on a failed or malformed
# read (NOT the house die: a re-read that cannot run validates
# nothing, and the unreadable-raise arm below owns the conservative
# outcome — a transient re-read failure must retry the probe, not
# kill the wait).
def _reread_page(pr: int, page: int, timeout) -> list | None:
    proc = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{REPO_OWNER}/{REPO_NAME}/issues/{pr}/reactions?per_page=100&page={page}",
        ],
        capture_output=True,
        text=True,
        env=gh_env(),
        timeout=timeout,
    )
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        return None
    return payload if isinstance(payload, list) else None


def gh_reactions(pr: int, timeout_secs: float | None = None) -> list:
    """The PR's issue-reactions list — EVERY page, flattened.

    Thread 3867503705 (PR #49, P2): the endpoint paginates at
    per_page=100; a single first-page read let an OLDER page-1 bot
    reaction masquerade as the latest while a newer page-2 signal sat
    unread — follow the ?page=N cursor until a SHORT page (the
    round-18 rulesets precedent, thread 3834666213) and combine every
    page before any latest-wins selection.

    Thread 3867503708 (PR #49, P2) + 3867572256 (round 2, P2):
    timeout_secs (the wait probe's budget) bounds the WHOLE walk —
    each page's subprocess timeout is RECOMPUTED against the probe
    deadline (elapsed page time subtracted, probe_timeout_budget
    clamps), never reused, so pagination cannot sequentially spend
    the budget once per page; a stalled gh api raises
    subprocess.TimeoutExpired instead of blocking the wait past its
    deadline; None leaves the walk unbounded (no live caller — the
    banner's informational read is bounded by BANNER_TIMEOUT_SECS
    since thread 3867653642, and the wait probes always pass a
    budget).

    Dies (exit 2, the house die) on a failed or malformed read — the
    two callers deliberately disagree on what to do with that: the
    survey banner fails OPEN (thread state is the merge authority),
    the wait loop keeps polling under its deadline (a failed read is
    never a done signal).

    Thread 3867757445 (PR #49 round 4, P2): an exhausted deadline
    STOPS the walk — never a fresh per-page grant through the 1s
    floor. Thread 3867897764 (round 5, P2): the stopped walk RAISES
    ReactionWalkExpired instead of returning the partial list — the
    pages already read can hold an OLDER bot +1 while a newer eyes
    sits unread, so latest-wins selection must never see the
    incomplete walk; both callers' UNREADABLE arms own the raise
    (the banner fails open, the wait keeps polling under its
    deadline). Thread 3871844580 (round 19, P2): a page pair whose
    boundary carries a mutation SIGNATURE (a repeated id, an
    inverted created_at order, or a regressed same-second id) raises
    the SAME exception for the same reason — the offset window
    provably shifted between the page requests, so the flattened
    list is a mixed snapshot, never a latest-wins input; the probe
    reads UNREADABLE and retries next interval. Thread 3873592851
    (round 24, P2): after a MULTI-PAGE walk completes, the page-1
    STABILITY RECHECK re-reads the first page and requires its
    newest item's identity unchanged — the SUPERSESSION of round
    19's documented pure-deletion residue (a mid-walk deletion on
    page 1 shifts every later page's offset — page 2 SKIPS its
    former first item, the bot's current eyes included — with no
    page-PAIR signature to see; the positional re-read proves the
    window changed and raises the same unreadable exception).
    Thread 3873970919 (round 25, P2): the recheck generalizes to
    EVERY FULL PAGE the walk fetched (1..last-full) — round 24's
    page-1 re-read only detected mutations in the FIRST offset
    window: with more than 200 reactions, deleting an item from page
    2's range after page 2 is fetched but before page 3 shifts page
    3 and silently skips its former first reaction while page 1
    stays identical (and `_page_shift_reason` still cannot detect a
    pure deletion), so EACH full page that can shift a later offset
    is revalidated the same way. The short final page needs no
    OFFSET recheck (nothing shifts past it). Thread 3876001013 (PR
    #49 round 32, P2): the re-read of a FULL page must ALSO stay
    FULL — at an EXACT MULTIPLE of 100 the terminal full page's
    non-final deletion shrinks the re-read 100 -> 99 with the newest
    identity unchanged (no later item refills the window), so the
    length is the only local witness the list mutated.
    Thread 3876172349 (PR #49 round 33, P2): the terminal SHORT
    page is revalidated TOO — the full-page loop excluded it, so a
    reaction on it (the bot's latest +1, say) deleted after the
    page was fetched while the full-page rechecks ran left the
    stale flattened list crowning a reaction no longer present; the
    re-read after the full-page checks requires BOTH its length and
    its newest identity unchanged (the 0-item terminal page of an
    exact-multiple count included — a refill reads non-zero), any
    change raising the same unreadable exception.
    """
    combined: list = []
    prior_page: list | None = None
    full_newest: list = []
    short_page, short_len, short_newest = 0, 0, ""
    page = 1
    deadline = None if timeout_secs is None else time.monotonic() + timeout_secs
    while True:
        if deadline is None:
            timeout = None
        else:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ReactionWalkExpired(
                    f"the probe deadline expired at page {page} with "
                    f"{len(combined)} reaction(s) read — the partial "
                    f"walk is UNREADABLE, never a latest-wins input "
                    f"(thread 3867897764)"
                )
            timeout = probe_timeout_budget(remaining)
        proc = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{REPO_OWNER}/{REPO_NAME}/issues/{pr}/reactions?per_page=100&page={page}",
            ],
            capture_output=True,
            text=True,
            env=gh_env(),
            timeout=timeout,
        )
        if proc.returncode != 0:
            die(
                f"gh api reactions page {page} exited "
                f"{proc.returncode}: {proc.stderr.strip()}"
            )
        try:
            payload = json.loads(proc.stdout)
        except ValueError:
            payload = None
        if not isinstance(payload, list):
            die(
                f"reactions page {page} for PR #{pr} is malformed: "
                f"{proc.stdout[:120]!r}"
            )
        if len(payload) == 100:
            full_newest.append(_newest_identity(payload))
        # Thread 3871844580 (round 19, P2): reject the mutated walk
        # BEFORE it contributes — the boundary signature proves the
        # snapshot shifted between this page request and the last.
        if prior_page is not None:
            reason = _page_shift_reason(prior_page, payload)
            if reason:
                raise ReactionWalkExpired(
                    f"the reaction set mutated across pages {page - 1}->"
                    f"{page} ({reason}) — the walk is UNREADABLE, never a "
                    f"latest-wins input (thread 3871844580)"
                )
        prior_page = payload
        combined.extend(payload)
        if len(payload) < 100:
            short_page, short_len, short_newest = page, len(payload), _newest_identity(payload)
            break
        page += 1
    # Thread 3873592851 (PR #49 round 24, P2) + thread 3873970919
    # (round 25, P2): the per-page stability recheck — ONLY after a
    # multi-page walk (a single-page read has no offset window to
    # shift), riding the SAME deadline (expired = the snapshot
    # cannot be validated = unreadable, never a fresh grant). Every
    # FULL page p (1..last-full) is re-read and its NEWEST item's
    # identity required unchanged: a full page's window can shift
    # every LATER page's offset (round 25's page-2 deletion race —
    # page 1 alone provably unchanged certifies nothing about the
    # window page 3 was offset against), while the SHORT final page
    # shifts nothing past it. A failed/malformed re-read or ANY
    # newest-identity drift raises the walk-unreadable exception:
    # the pre-deletion snapshot the walk flattened no longer
    # describes the list, so later pages were offset against a
    # window that moved — the exact pure-deletion shift round 19
    # documented as residue and round 24 closed for page 1.
    # Thread 3876001013 (PR #49 round 32, P2): the LENGTH leg — when
    # the reaction count is an EXACT MULTIPLE of 100 the walk's
    # TERMINAL page is FULL, so deleting a NON-FINAL item from its
    # range after the initial fetch leaves the re-read's newest
    # identity UNCHANGED (the page merely shrinks 100 -> 99 — no
    # later item exists to refill the window) and the identity-only
    # compare accepted the stale flattened page; if the deleted item
    # is the bot's +1, an armed waiter could still exit 0 from a
    # reaction no longer present. The re-read of a full page must
    # ALSO stay FULL (100 items) — a shrunk terminal full page
    # proves the list mutated across the walk and raises the same
    # unreadable exception.
    for p in range(1, len(full_newest) + 1):
        timeout = None
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ReactionWalkExpired(
                    f"the probe deadline expired before the page-{p} stability "
                    f"recheck could run with {len(combined)} reaction(s) read "
                    f"— the unvalidated walk is UNREADABLE, never a "
                    f"latest-wins input (thread 3873970919)"
                )
            timeout = probe_timeout_budget(remaining)
        reread = _reread_page(pr, p, timeout)
        reread_newest = _newest_identity(reread) if reread is not None else ""
        if reread is None or len(reread) != 100 or reread_newest != full_newest[p - 1]:
            raise ReactionWalkExpired(
                f"page {p}'s snapshot changed across the walk (its newest "
                f"item read {full_newest[p - 1]!r} at page {p}, "
                f"{reread_newest!r} over {len(reread or [])} item(s) at the "
                f"recheck — a full page must stay full) — the reaction list "
                f"mutated across the walk, so it is UNREADABLE, never a "
                f"latest-wins input (threads 3873970919 + 3876001013)"
            )
    # Thread 3876172349 (PR #49 round 33, P2): the TERMINAL short
    # page's revalidation — after the full-page rechecks (a walk
    # always ends on a short page: the 0-item page of an exact
    # multiple included, so the recorded facts always exist; a
    # single-page walk never reaches here — full_newest empty, the
    # standing round-24 rule). The terminal page has NO later page
    # whose offset it shifts, but its OWN membership can change
    # under it while the rechecks run: a deletion shrinks the LENGTH
    # without moving the identity (no refill exists — the length is
    # the only witness), deleting the NEWEST moves the identity
    # outright, and an earlier-page ADDITION shifts items forward
    # into a formerly-0-item terminal page (a refill reads
    # non-zero). ANY change — or a failed re-read, or an expired
    # deadline (the recheck rides the walk's EXISTING deadline,
    # never a fresh grant) — raises the walk-unreadable exception:
    # the flattened list no longer describes the terminal window,
    # so latest-wins could crown a deleted reaction (the bot's +1,
    # an armed waiter's WAIT DONE from a reaction no longer
    # present).
    if full_newest:
        timeout = None
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ReactionWalkExpired(
                    f"the probe deadline expired before the terminal page-"
                    f"{short_page} stability recheck could run with "
                    f"{len(combined)} reaction(s) read — the unvalidated "
                    f"walk is UNREADABLE, never a latest-wins input "
                    f"(thread 3876172349)"
                )
            timeout = probe_timeout_budget(remaining)
        reread = _reread_page(pr, short_page, timeout)
        reread_newest = _newest_identity(reread) if reread is not None else ""
        if reread is None or len(reread) != short_len or reread_newest != short_newest:
            raise ReactionWalkExpired(
                f"the terminal page {short_page}'s snapshot changed across "
                f"the walk (its newest item read {short_newest!r} over "
                f"{short_len} item(s) at page {short_page}, "
                f"{reread_newest!r} over {len(reread or [])} item(s) at the "
                f"recheck — the terminal page has no refill, so its length "
                f"and newest identity must BOTH hold) — the reaction list "
                f"mutated across the walk, so it is UNREADABLE, never a "
                f"latest-wins input (thread 3876172349)"
            )
    return combined
