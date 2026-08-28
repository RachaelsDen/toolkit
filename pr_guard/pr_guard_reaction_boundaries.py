"""The reaction family's timing layer, bot vocabulary, round-BOUNDARY
walks, and head-bound evidence.

PR #49 round 17 split this home out of pr_guard_reaction_probe at the
250 pure-LOC ceiling (split-first, the PR #36 round-2 family rule):
the probe stood at 207 pure LOC and round 17 grows its GraphQL read
surface by THREE concerns — the request walk's new identity shape
(thread 3870995905), the comment-trigger boundary walk (3870995911),
and the head-bound review-commit read (3870995919) — so the boundary
walks (the request-event walk that lived in the probe since round 7,
plus its new trigger twin), the evidence read, the connection-shape
helper, the bot-login vocabulary, and the subprocess TIMING clamps
they all speak moved down here together. Imports flow ONE WAY:
pr_guard_reaction_probe imports FROM here and RE-EXPORTS (the
reaction-namespace seam rule — pr_guard_reaction_walk's
`from pr_guard_reaction_probe import probe_timeout_budget`,
round-15's pr_guard_reaction_probe.codex_request_marker call, and
every REACTION_BOT/GRAPHQL_BOT_LOGIN seam keep ONE home); this
module imports NOTHING from the reaction family, only
pr_guard_common.

THE TIMING LAYER (moved probe -> here round 17, unchanged rules):
WAIT_INTERVAL_SECS / DEFAULT_WAIT_TIMEOUT_SECS (the wait mode's
cadence and window) and probe_timeout_budget (threads 3867503708 +
3867572256: one subprocess's timeout is the ACTUAL remaining window
clamped to [1s, two poll intervals]) — one home because the wait
loop, the reactions walk, and both boundary walks must all speak the
SAME clamps.

THREAD 3870995905 (P1) — the request IDENTITY: the walk returns
`createdAt|node id` per codex ReviewRequestedEvent. The timeline
node list is CHRONOLOGICAL (timelineItems semantics), so the LAST
codex event in a walked window is the latest request — including
same-second pairs, where list order (not the timestamp) carries the
sequence. The base64 node id is stable and globally unique but
carries NO chronology (ReviewRequestedEvents have NO databaseId —
the PullRequestReviewThread precedent), which is why the wait-side
advance rule (pr_guard_reaction_latch.request_advances) uses
DISTINCTNESS as the same-second tie-breaker.

THREAD 3870995911 (P1) — the comment-trigger boundary: the
documented manual trigger is a TOP-LEVEL PR comment (the
pullRequest.comments connection — NOT the review-thread comments the
round-4 marker walk reads; live-verified aliasable with
pageInfo/nodes{id createdAt body} and before: pagination). A trigger
comment is ANY comment whose body CONTAINS '@codex review'
(case-insensitive substring) by ANY author (the cold-start hint
teaches humans to post it); its identity `createdAt|comment node id`
feeds the SAME request-boundary machinery as a formal re-request —
the probe's round_bounds merges the two kinds through
latest_boundary (newest createdAt wins; a same-second cross-kind tie
is the round-10 ambiguity class and resolves deterministically to
the max identity string — the documented residual is backstopped by
the round-13 boundary binding, which stales any not-yet-armed EYES
against the shared second). The walk mirrors the request walk
exactly: bounded last:50 window, BACKWARDS before:$cursor pages
stopping at the FIRST page carrying a trigger, per-page budgets
recomputed against the probe deadline, and the None-means-unreadable
contract ('' means provably no trigger exists in the history).

THREAD 3870995919 (P1) — the head-bound evidence: latest_review_
commit reads latestReviews(last:10){author commit{oid}} (live-
verified 2026-08-27 on PR #49: the connector's submitted review
carries commit.oid 5c533c3... — the head the review ran against) and
returns the chronologically-LAST bot-authored review's oid ('' when
none exists or the read fails — never evidence; the wait's post-move
completion check withholds on '', never fails open). The bot's +1 is
its POST-review verdict (the PR #48 live shape: submission
22:52:48Z -> pass 23:01:38Z), so at an ACCEPTING +1 the latest bot
review names the head that round actually reviewed.

PR #49 ROUND 18 (threads 3871485035 P1 / 3871485043 P2 /
3871485055 P1): the evidence read is FOLDED into the round probe —
latest_review_commit became the EXTRACTION over the ROUND_QUERY
node's new author-filtered `botReviews` connection (no subprocess of
its own; see pr_guard_reaction_probe.ROUND_QUERY): thread 3871485035
condemned the separate post-bracket lookup whose unbracketed window
could still return the prior head's review against a stale
observed_head; thread 3871485043 condemned its latestReviews(last:10)
window — ten other reviewers' latest reviews evict the connector's
review and every otherwise-valid completion held to timeout.
LIVE-VERIFIED read-only on PR #49 (2026-08-27): the reviews(author:)
connection argument filters SERVER-SIDE, but matches ONLY the
`[bot]`-suffixed login "chatgpt-codex-connector[bot]" — the
SUFFIX-LESS render that GraphQL author{login} DISPLAYS returns an
EMPTY connection (the exact inverse of the round-3 rendering
GOTCHA; querying with the displayed login would read "no bot
review" forever) — and an author with zero reviews reads
{"nodes": []} (a LEGITIMATE empty, distinct from the null-
connection partial-error class), while `latestReviews` REJECTS the
author argument outright (argumentNotAccepted), so the marker
connection keeps its own shape. latest_boundary's merge survives
for CLASSIFICATION ONLY (round 18, 3871485055): the formal request
and the trigger comment retain their identities in SEPARATE
per-kind high-waters on the wait side; the merged index-2 boundary
feeds just the EYES binding and the composite marker.

PR #49 ROUND 20 (threads 3872194007 P2 / 3872194023 P1): (1) the
FULL-IDENTITY boundary streams — both walks accept an optional
`collect` set that receives EVERY marker identity sharing the
returned boundary's high-water second (the walk's latest-per-probe
stream alone records only markers[-1], so a same-second sibling
deleted-and-resurfaced later counterfeit an unseen identity through
the distinctness tie-break; the wait's per-kind seen-sets union the
collected identities and the resurfacing reads as the round's
CONTINUATION). Identities at OLDER seconds stay unrecorded — only
the high-water second is visible through the stream (a resurfacing
there is the mirror direction the round-17 compare already blocks).
(2) The VERDICT STAMP — bot_review_stamp is the submittedAt twin of
latest_review_commit over the SAME folded node (live-verified
2026-08-27 read-only on PR #49: the author-filtered connection
carries submittedAt beside commit.oid), because the reviews'
`state` field does NOT separate findings rounds from passes (both
render COMMENTED on #49's findings rounds AND #48's pass round —
live-verified the same day; see pr_guard_reaction_wait's round-20
section for the completion guards the stamp feeds).

PR #49 ROUND 21 (thread 3872631157, P2): the PAGE-EDGE continuation
of the same-second fill. Round 20's collect recorded every identity
sharing the returned boundary's high-water second ON THE ANSWERING
PAGE — but a same-second pair can STRADDLE the page boundary (the
answering page's OLDEST item carries the selected marker's second
while its older sibling sits on the PRECEDING page), so `collect`
only saw the in-page identities and the unrecorded sibling's
resurfacing (after the newer in-page comment's deletion) satisfied
boundary_advances' same-second distinctness rule, spuriously
resetting a valid round. The walk's STOP condition widens from
"first page carrying a marker" to that page PLUS the preceding
pages WHILE their newest item shares the marker's second (the
formal-request twin walks the same edge): deadline/pagination
hygiene unchanged, and a legacy 3-arg caller (collect None) never
continues — byte-identical reads, zero extra subprocesses.

PR #49 ROUND 22 (thread 3872980781, P1): the walks report whether
they PAGINATED — every backwards page and same-second edge
continuation appends its cursor to the caller's optional `paged`
list (a legacy caller passing nothing never reports and never
paginates differently — byte-identical reads, zero extra
subprocesses). round_bounds consumes the report to re-read the head
AFTER all boundary pagination and discard the probe on drift (see
pr_guard_reaction_probe): the walks run additional GraphQL
subprocesses AFTER ROUND_QUERY captured the bracket's final
headRefOid, so a head moving during a walk left the function
returning the OLD oid and the wait accepting the old head's
terminal reaction before the next poll noticed the move — the
round-10/18 bracket discipline extended past the pagination.

PR #49 ROUND 32 (thread 3876000990, P1): the bot ENGAGEMENT-marker
extraction — bot_engagement_markers factored out of the probe's
inline composite-marker build so the post-pagination bracket recheck
can hold the RE-RUN to the same marker facts it certifies for the
original query (the probe's _bracket_unchanged consumes it; see
pr_guard_reaction_probe's round-32 section).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round22_probe_test -v
"""

import json
import subprocess
import time

from .pr_guard_common import REPO_NAME, REPO_OWNER, gh_env

# Live-verified 2026-08-27: GraphQL renders the bot's author login
# WITHOUT the "[bot]" suffix (latestReviews author{login} reads
# "chatgpt-codex-connector") while REST reactions report it WITH the
# suffix — the round marker filters on both forms.
REACTION_BOT = "chatgpt-codex-connector[bot]"
GRAPHQL_BOT_LOGIN = REACTION_BOT.removesuffix("[bot]")
BOT_LOGINS = frozenset({REACTION_BOT, GRAPHQL_BOT_LOGIN})

# The wait mode's cadence (5s — be polite; the vault note's efficient
# loop polls the reaction seconds apart, not sub-second) and default
# window: a codex review round comfortably fits 600s, and
# --timeout-secs overrides for both quicker and longer waits.
WAIT_INTERVAL_SECS = 5.0
DEFAULT_WAIT_TIMEOUT_SECS = 600

# Threads 3867503708 + 3867572256: every subprocess this family
# dispatches is bounded by the ACTUAL remaining window — capped at
# two poll intervals (a subprocess stalled longer is dead:
# TimeoutExpired, read UNREADABLE, retried at the cadence) and
# floored at 1s so an at-deadline final probe can still read (round
# 1's last-instant THUMBS_UP promise). The floor is under one
# interval, so no probe can block a wait past deadline+interval.
PROBE_TIMEOUT_FLOOR_SECS = 1.0
PROBE_TIMEOUT_CAP_SECS = 2 * WAIT_INTERVAL_SECS


def probe_timeout_budget(remaining: float) -> float:
    return max(min(remaining, PROBE_TIMEOUT_CAP_SECS), PROBE_TIMEOUT_FLOOR_SECS)


# The per-page budget against the probe deadline (the round-7/15
# rule, factored for the three walk loops): None when unbounded,
# 0.0 when EXPIRED — probe_timeout_budget never returns 0.0 (the 1s
# floor), so the sentinel is unambiguous; a caller seeing it reads
# the whole walk unreadable (thread 3868158304: a stopped-early walk
# is never a readable no-marker history).
def _remaining_budget(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    remaining = deadline - time.monotonic()
    return probe_timeout_budget(remaining) if remaining > 0 else 0.0


# Thread 3870293197 (round 15, P1 — moved here round 17 with the
# walks): the connection-shape hygiene — a node list ONLY when the
# connection is present, an object, and carries a nodes list; None
# otherwise. A null/omitted connection inside an otherwise-
# successful response must read UNREADABLE, never "provably empty"
# (the missing-marker bias toward done).
def _nodes(conn) -> list | None:
    if isinstance(conn, dict) and isinstance(conn.get("nodes"), list):
        return conn["nodes"]
    return None


# Thread 3870995905 (round 17, P1): the boundary-node IDENTITY —
# `createdAt|node id`. An id-less node (a legacy minimal fixture, or
# a degraded-but-readable payload) degrades to the BARE createdAt:
# round-15 semantics, conservative — no id means no same-second
# tie-breaker, while strictly-newer createdAt still advances.
def _identity(node: dict) -> str:
    at = str(node.get("createdAt") or "")
    node_id = str(node.get("id") or "")
    return f"{at}|{node_id}" if node_id else at


# Thread 3870995905 (round 17, P1): the codex request walk's node
# selection — identity-shaped markers, reviewer-filtered per thread
# 3867757442 (either login render).
def _codex_markers(nodes: list) -> list[str]:
    return [
        _identity(node)
        for node in nodes
        if (node.get("requestedReviewer") or {}).get("login") in BOT_LOGINS
    ]


# Thread 3870995911 (round 17, P1): the trigger matcher — the
# documented manual-review phrase, a case-insensitive SUBSTRING of
# the top-level PR comment body, ANY author.
TRIGGER_BODY = "@codex review"


def _trigger_markers(nodes: list) -> list[str]:
    return [
        _identity(node)
        for node in nodes
        if TRIGGER_BODY in str(node.get("body") or "").lower()
    ]


# Thread 3868158304 (round 7): the request walk's backwards page —
# the same ReviewRequestedEvent node shape (plus the node id,
# 3870995905) under before:$cursor, so a codex request older than
# the newest 50 events is still read BEFORE the client-side filter
# runs. Walking BACKWARDS lets the walk stop at the FIRST page
# carrying a codex event: that page's LAST codex event is the
# LATEST codex request, because every event newer than the cursor
# was already proven codex-free.
REQUEST_WALK_QUERY = (
    "query($owner:String!,$name:String!,$number:Int!,$before:String!)"
    "{repository(owner:$owner,name:$name){pullRequest(number:$number)"
    "{timelineItems(itemTypes:REVIEW_REQUESTED_EVENT,last:50,"
    "before:$before){pageInfo{hasPreviousPage startCursor} nodes{... on "
    "ReviewRequestedEvent{createdAt id requestedReviewer{... on User{login} "
    "... on Bot{login}}}}}}}}"
)

# Thread 3870995911 (round 17, P1): the trigger walk's backwards
# page — the PR-level comments connection (aliased to match
# ROUND_QUERY's field) under before:$cursor.
TRIGGER_WALK_QUERY = (
    "query($owner:String!,$name:String!,$number:Int!,$before:String!)"
    "{repository(owner:$owner,name:$name){pullRequest(number:$number)"
    "{triggerComments:comments(last:50,before:$before){pageInfo{"
    "hasPreviousPage startCursor} nodes{id createdAt body}}}}}"
)

# Thread 3870995919 (round 17, P1) + round 18 (threads 3871485035/
# 3871485043): the head-bound evidence read is FOLDED into ROUND_QUERY
# as the author-filtered `botReviews` connection — no standalone query
# survives. The filter literal is the [bot]-suffixed login (the
# live-verified inverse-rendering rule: reviews(author:) matches
# "chatgpt-codex-connector[bot]" ONLY while author{login} RENDERS the
# suffix-less form — if REACTION_BOT ever changes, this literal
# changes with it).
BOT_REVIEWS_FIELD = "botReviews"


def _walk_page(pr: int, before: str, budget, query: str, conn_key: str, markers_of, paged=None):
    # One BACKWARDS page for either boundary walk: (markers, next
    # before-cursor or '', OLDEST item stamp, NEWEST item stamp) —
    # None when the page is unreadable (rc, JSON, shape, top-level
    # errors — thread 3870293197's contract). Thread 3872631157
    # (round 21, P2): the page's EDGE stamps ride along so the walks
    # can see a same-second pair STRADDLING the page boundary (the
    # node list is chronological: nodes[0] the oldest, nodes[-1] the
    # newest). Thread 3872980781 (round 22, P1): the dispatch REPORTS
    # itself to the caller's paged list — the cursor is recorded
    # BEFORE the subprocess leaves (any dispatch, succeeded or not,
    # opens the post-ROUND_QUERY window the probe's head recheck
    # must cover).
    if paged is not None:
        paged.append(before)
    proc = subprocess.run(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={REPO_OWNER}",
            "-F",
            f"name={REPO_NAME}",
            "-F",
            f"number={pr}",
            "-F",
            f"before={before}",
        ],
        capture_output=True,
        text=True,
        env=gh_env(),
        timeout=budget,
    )
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout)
        if payload.get("errors"):
            return None
        conn = payload["data"]["repository"]["pullRequest"][conn_key]
        nodes = _nodes(conn)
        if nodes is None:
            return None
        info = conn.get("pageInfo") or {}
        cursor = str(info.get("startCursor") or "") if info.get("hasPreviousPage") else ""
        stamps = [str(node.get("createdAt") or "") for node in nodes]
        return (
            markers_of(nodes),
            cursor,
            stamps[0] if stamps else "",
            stamps[-1] if stamps else "",
        )
    except (ValueError, KeyError, TypeError):
        return None


# Thread 3872194007 (round 20, P2): the same-second FILL — every
# marker identity sharing the returned boundary's high-water second,
# deposited into the caller's optional collect set. The wait's
# seen-sets consume it so a sibling that was VISIBLE beside the
# latest boundary of its second is remembered even after the latest
# is deleted/omitted and the sibling becomes the stream.
def _fill_same_second(markers: list[str], collect) -> None:
    if collect is not None and markers:
        at = markers[-1].partition("|")[0]
        collect.update(m for m in markers if m.partition("|")[0] == at)


# Thread 3872631157 (PR #49 round 21, P2): the PAGE-EDGE continuation
# of the same-second fill — when the ANSWERING page's OLDEST item
# carries the selected marker's second, the second may straddle into
# the PRECEDING page (the sibling the in-page fill never saw), so the
# walk continues backwards collecting that second's identities while
# each fetched page's NEWEST item still shares the second (a page
# whose newest predates it carries nothing of the second; one whose
# OLDEST also shares it may straddle yet another edge). Returns False
# when a continuation page is unreadable/deadline-expired — a walk
# that stopped before the second's identities are proven recorded is
# UNREADABLE itself (the thread 3868158304 bias rule: never a
# readable boundary whose collect set may be incomplete). collect
# None (a legacy 3-arg caller) never continues — byte-identical
# reads, zero extra subprocesses (the round-20 zero-repin rule).
def _collect_edge_siblings(pr, before, deadline, second, oldest, collect, query, conn_key, markers_of, paged=None) -> bool:
    if collect is None or not second or oldest != second:
        return True
    while before:
        budget = _remaining_budget(deadline)
        if budget == 0.0:
            return False
        page = _walk_page(pr, before, budget, query, conn_key, markers_of, paged)
        if page is None:
            return False
        markers, before, oldest, newest = page
        if newest != second:
            return True
        collect.update(m for m in markers if m.partition("|")[0] == second)
        if oldest != second:
            return True
    return True


def codex_request_marker(
    pr_node: dict, pr: int, deadline: float | None, collect=None, paged=None
) -> str | None:
    """The latest CODEX request's identity `createdAt|node id`: ''
    when provably none, None when the walk is UNREADABLE.

    The newest-50 window's own codex events answer immediately; only
    a codex-FREE full window with earlier pages pending walks back
    (before:$cursor), stopping at the first page carrying one — that
    page's LAST codex event IS the latest request overall (the node
    list is chronological, so same-second pairs keep their true
    order — thread 3870995905's requirement). The walk's per-page
    timeout is RECOMPUTED against the probe deadline and an expired
    deadline returns None (unreadable): a walk that stopped early
    must never read as "no codex request exists" (thread 3868158304).
    A null/omitted timelineItems connection returns None too (thread
    3870293197) — never a readable no-request history. Thread
    3872194007 (round 20): collect, when a set, receives every
    same-second identity at the answering page's high-water second.
    Thread 3872631157 (round 21, P2): when that second straddles the
    page edge (the answering page's OLDEST item shares it), the
    continuation collects the PRECEDING pages' identities of the same
    second — an unreadable/expired continuation page makes the WHOLE
    walk unreadable (never a readable boundary whose collect set may
    be incomplete). Thread 3872980781 (round 22, P1): paged, when a
    list, receives every backwards-page cursor the walk dispatches —
    the post-ROUND_QUERY window round_bounds' head recheck covers.
    """
    nodes = _nodes(pr_node.get("timelineItems"))
    if nodes is None:
        return None
    markers = [m for m in _codex_markers(nodes) if m.partition("|")[0]]
    info = (pr_node.get("timelineItems") or {}).get("pageInfo") or {}
    if markers or not info.get("hasPreviousPage"):
        _fill_same_second(markers, collect)
        # Thread 3872631157: the continuation cursor exists only when
        # hasPreviousPage does (a page may carry a startCursor with no
        # previous page — the round-7 fixture shape) — else '' stops
        # the helper before any subprocess.
        before = (
            str(info.get("startCursor") or "") if info.get("hasPreviousPage") else ""
        )
        if markers and not _collect_edge_siblings(
            pr, before, deadline, markers[-1].partition("|")[0],
            str(nodes[0].get("createdAt") or ""), collect,
            REQUEST_WALK_QUERY, "timelineItems", _codex_markers, paged,
        ):
            return None
        return markers[-1] if markers else ""
    before = str(info.get("startCursor") or "")
    while before:
        budget = _remaining_budget(deadline)
        if budget == 0.0:
            return None
        page = _walk_page(
            pr, before, budget, REQUEST_WALK_QUERY, "timelineItems", _codex_markers, paged
        )
        if page is None:
            return None
        markers, before, oldest, _newest = page
        if markers:
            _fill_same_second(markers, collect)
            if not _collect_edge_siblings(
                pr, before, deadline, markers[-1].partition("|")[0], oldest,
                collect, REQUEST_WALK_QUERY, "timelineItems", _codex_markers, paged,
            ):
                return None
            return markers[-1]
    return ""


def trigger_comment_marker(
    pr_node: dict, pr: int, deadline: float | None, collect=None, paged=None
) -> str | None:
    """The latest `@codex review` TRIGGER comment's identity: '' when
    provably none, None when the walk is UNREADABLE (3870995911).

    Same discipline as codex_request_marker: the newest-50 window
    answers when it carries a trigger (its LAST match is the latest
    overall), otherwise BACKWARDS pages run until one does or the
    history is exhausted; per-page budgets recompute against the
    probe deadline; a failed/malformed/expired page reads None —
    never "no trigger exists" (a missing boundary biases the wait
    toward the preceding round's certifications). Thread 3872194007
    (round 20): collect, when a set, receives every same-second
    identity at the answering page's high-water second. Thread
    3872631157 (round 21, P2): when that second straddles the page
    edge (the answering page's OLDEST item shares it), the
    continuation collects the PRECEDING pages' identities of the same
    second — an unreadable/expired continuation page makes the WHOLE
    walk unreadable (the formal-request twin's exact rule). Thread
    3872980781 (round 22, P1): paged, when a list, receives every
    backwards-page cursor the walk dispatches (the twin's rule).
    """
    nodes = _nodes(pr_node.get("triggerComments"))
    if nodes is None:
        return None
    markers = [m for m in _trigger_markers(nodes) if m.partition("|")[0]]
    info = (pr_node.get("triggerComments") or {}).get("pageInfo") or {}
    if markers or not info.get("hasPreviousPage"):
        _fill_same_second(markers, collect)
        before = (
            str(info.get("startCursor") or "") if info.get("hasPreviousPage") else ""
        )
        if markers and not _collect_edge_siblings(
            pr, before, deadline, markers[-1].partition("|")[0],
            str(nodes[0].get("createdAt") or ""), collect,
            TRIGGER_WALK_QUERY, "triggerComments", _trigger_markers, paged,
        ):
            return None
        return markers[-1] if markers else ""
    before = str(info.get("startCursor") or "")
    while before:
        budget = _remaining_budget(deadline)
        if budget == 0.0:
            return None
        page = _walk_page(
            pr, before, budget, TRIGGER_WALK_QUERY, "triggerComments", _trigger_markers, paged
        )
        if page is None:
            return None
        markers, before, oldest, _newest = page
        if markers:
            _fill_same_second(markers, collect)
            if not _collect_edge_siblings(
                pr, before, deadline, markers[-1].partition("|")[0], oldest,
                collect, TRIGGER_WALK_QUERY, "triggerComments", _trigger_markers, paged,
            ):
                return None
            return markers[-1]
    return ""


def latest_boundary(request: str, trigger: str) -> str:
    """The newest of the two request-boundary identities (3870995911).

    CLASSIFICATION-ONLY since round 18 (thread 3871485055): this merge
    feeds the EYES binding and the composite marker (both consume the
    boundary's createdAt half — the later boundary is the binding
    one), NEVER the wait's retention — the formal request and the
    trigger comment advance SEPARATE per-kind high-waters there, so a
    same-second pair of different kinds both register. A same-second
    CROSS-KIND tie carries the round-10 ambiguity (no shared
    chronology across connections), so it resolves DETERMINISTICALLY
    to the max identity string — harmless here (both halves share the
    second, which is all classification consumes; the pre-round-18
    RETENTION use of this value was the finding's collapse).
    """
    if not request or not trigger:
        return request or trigger
    req_at = request.partition("|")[0]
    trg_at = trigger.partition("|")[0]
    if req_at != trg_at:
        return request if req_at > trg_at else trigger
    return max(request, trigger)


def latest_review_commit(pr_node: dict) -> str | None:
    """The latest BOT review's commit oid from the FOLDED round-query
    node — '' when none, None when the connection is unreadable.

    Thread 3870995919 (round 17, P1) named the evidence; round 18
    (threads 3871485035/3871485043) folded its READ into the round
    probe: the author-filtered `botReviews` connection rides the ONE
    subprocess whose stable-head bracket already certifies the head
    oid — the evidence can never be a second, unbracketed lookup that
    races a mid-sequence head move, and the server-side author filter
    (live-verified, the [bot]-suffixed login form) means no fixed
    window of other reviewers' reviews can evict the connector's
    review the way the old latestReviews(last:10) window did. The
    client-side BOT_LOGINS filter backstops the server's. '' is never
    evidence (no bot review exists — the live-verified empty-nodes
    shape — or every node is non-bot/an oid is missing): the caller
    withholds, never fails open. None (the connection present but
    null/malformed) is the round-15 partial-error class: the WHOLE
    probe retries. An ABSENT key is the legacy minimal-payload page —
    no evidence carried, readable.
    """
    if BOT_REVIEWS_FIELD not in pr_node:
        return ""
    nodes = _nodes(pr_node[BOT_REVIEWS_FIELD])
    if nodes is None:
        return None
    oids = [
        str((node.get("commit") or {}).get("oid") or "")
        for node in nodes
        if (node.get("author") or {}).get("login") in BOT_LOGINS
    ]
    return oids[-1] if oids else ""


# Thread 3872194023 (round 20, P1): the VERDICT STAMP — the
# submittedAt twin of latest_review_commit over the SAME folded
# node. LIVE-VERIFIED read-only 2026-08-27 (PR #49 + PR #48): the
# reviews' `state` field does NOT separate findings rounds from
# passes (every review on both PRs renders COMMENTED — #49's
# findings rounds AND #48's pass round alike), so the completion
# guard binds to what DOES distinguish evidence: WHEN the latest
# head-bound review submitted (the bot's +1 is its POST-review
# verdict — the PR #48 live shape submission 22:52:48Z -> pass
# 23:01:38Z). Same shape contract as its twin: '' when none/absent
# (never evidence — the caller withholds, never fails open), None
# when the connection is present-but-null (the round-15 partial-
# error class: the WHOLE probe retries).
def bot_review_stamp(pr_node: dict) -> str | None:
    """The latest BOT review's submittedAt from the FOLDED round-query
    node — '' when none, None when the connection is unreadable."""
    if BOT_REVIEWS_FIELD not in pr_node:
        return ""
    nodes = _nodes(pr_node[BOT_REVIEWS_FIELD])
    if nodes is None:
        return None
    stamps = [
        str(node.get("submittedAt") or "")
        for node in nodes
        if (node.get("author") or {}).get("login") in BOT_LOGINS
    ]
    return stamps[-1] if stamps else ""


# Thread 3876000990 (PR #49 round 32, P1): the bot ENGAGEMENT markers
# of a round-query node — the latestReviews submittedAt stamps and
# the reviewThreads bot-comment createdAt stamps (the composite
# marker's review-side sources; the request/trigger boundary
# createdAt composes in the probe beside them). None when ANY
# connection is unreadable (the round-15 shape rule: a null/omitted
# latestReviews/reviewThreads — or thread-comments connection — is
# the partial-error class, never a readable no-marker history).
# BOTH the probe's initial parse and the post-pagination bracket
# recheck consume it: the recheck requires the re-run's engagement
# NOT to have advanced past the ORIGINAL query's composite marker —
# a bot review or thread comment landing during the continuation
# reads makes the previously fetched +1's staleness classification
# stale itself (unreadable bounds, retry next interval), never a
# certified picture the waiter could accept the preceding round's
# terminal +1 off.
def bot_engagement_markers(pr_node: dict) -> list | None:
    """The bot's latestReviews submittedAt + reviewThreads comment
    markers — None when any connection is unreadable (3876000990)."""
    reviews = _nodes(pr_node.get("latestReviews")); threads = _nodes(pr_node.get("reviewThreads"))
    if reviews is None or threads is None: return None
    markers = [
        str(node.get("submittedAt") or "")
        for node in reviews
        if (node.get("author") or {}).get("login") in BOT_LOGINS
    ]
    for node in threads:
        comments = _nodes(node.get("comments"))
        if comments is None: return None
        markers += [
            str(comment.get("createdAt") or "")
            for comment in comments
            if (comment.get("author") or {}).get("login") in BOT_LOGINS
        ]
    return markers
