"""The reaction family's timing discipline and round-bounds probe.

PR #49 round 7 (thread 3868158304, P2) split this home out of
pr_guard_reaction.py at the 250 pure-LOC ceiling (split-first, the
PR #36 round-2 family rule): reaction.py stood at 236 pure LOC and
round 7 grows BOTH the round-bounds probe (the paginated
request-event walk below) and the wait loop (thread 3868158293's
observed-new +1 acceptance). Imports flow ONE way —
pr_guard_reaction imports FROM here; this module imports NOTHING
from the reaction family, only pr_guard_common.

THE TIMING LAYER: WAIT_INTERVAL_SECS / DEFAULT_WAIT_TIMEOUT_SECS
(the wait mode's cadence and window) and probe_timeout_budget
(threads 3867503708 + 3867572256: one subprocess's timeout is the
ACTUAL remaining window clamped to [1s, two poll intervals]) — one
home because the wait loop, the reactions walk
(pr_guard_reaction.gh_reactions), and the request-event walk below
must all speak the SAME clamps.

THE ROUND-BOUNDS PROBE (round_bounds, threads 3867653639 +
3867757439 + 3867757442): ONE GraphQL read carrying every
round-start fact — the head's pushedDate (committedDate fallback)
beside the latest round-engagement marker (the newest
CODEX-filtered ReviewRequestedEvent, the bot's latest SUBMITTED
review, and the bot's latest review-THREAD comment; this repo's
rounds engage without formal requests, live-verified). Thread
3868158304 (PR #49 round 7, P2): GitHub truncates the
request-events connection BEFORE the client-side codex filter
runs, so the old last:5 window let a CURRENT codex request vanish
behind five later unrelated requests — the marker's disappearance
reclassified the unchanged old +1 from STALE (transition latch
armed) to current and the wait exited 0 before the round posted
EYES, a review, or a thread comment. The window is now the LATEST
50 events with BACKWARDS pagination: pageInfo's
hasPreviousPage/startCursor drive before:$cursor pages, and the
FIRST codex event met walking back IS the latest (every event
newer than the cursor was already proven codex-free), so the walk
stops at the page that carries one. A FAILED, malformed, or
deadline-expired walk returns None and round_bounds reports
("", "") — unreadable bounds read THUMBS_UP_UNVERIFIED (never
done, never latch-arming; thread 3868047719), because a MISSING
marker must never bias a +1 toward done (the exact 3868158304
direction: the conservative failure keeps polling, it never
certifies the pass current).

PR #49 round 8 (thread 3868443452, P1): round_bounds PRESERVES the
headRefOid ROUND_QUERY always carried — the reading is now
(head_oid, head_push, round_marker). The oid lets the wait's
transition latch tell that a stale-classified probe and a
done-classified probe of the SAME +1 were certified against
DIFFERENT heads: a mid-wait head move to an already-pushed commit
whose pushedDate predates the +1 reclassifies it stale->done with
no bot activity, so the wait RESETS its latch/baseline when the oid
changes (see pr_guard_reaction.wait_reaction). An unreadable probe
returns ('', '', '') — an empty oid never certifies a change.

PR #49 round 10 (thread 3868782039, P1): the head-ONLY read below
(head_ref_oid) — the BEFORE side of the reactions read's STABILITY
BRACKET. bot_reaction_reading reads the head FIRST, then the
reactions, then round_bounds (whose ONE combined query carries the
AFTER oid beside the dates it certifies), and discards the whole
probe unless the two oids match: a single probe used to combine
snapshots from OPPOSITE sides of a head change (an EYES for head A
paired with head B's oid/dates), letting the wait treat the oid
change as handled, re-arm the latch from the pre-change EYES, and
exit on a completion that postdated B's push without B being
reviewed. A moved head raises ReactionHeadMoved — the probe is
UNREADABLE (retry next interval), never a mixed snapshot; an
unreadable side ('' — a failed head read) certifies nothing and
never discards, mirroring head_changed's refusal of empty oids.

User-taught refinements #2 (2026-08-27; vault note 'Unified
Realms/Notes/Codex Review Bot Reaction Signal.md', section 'User-
taught refinements #2'): the paginated reactions walk (gh_reactions)
moved home here — pr_guard_reaction.py stood at 237 pure LOC and the
wait loop gains the EYES->NONE findings exit and the cold-NONE
trigger hint, so the OTHER API-read concern splits first (the PR #36
round-2 family rule). The walk is this module's sibling pagination
concern (the same deadline discipline the request-event walk
speaks); reaction.py RE-EXPORTS gh_reactions and ReactionWalkExpired
so every existing test seam (mock.patch pr_guard_reaction.
gh_reactions) keeps ONE home — the round-7 re-export precedent.
[PR #49 round 15: the walk moved ONCE MORE — probe -> the NEW
sibling pr_guard_reaction_walk at the 250 pure-LOC ceiling (254),
separating the two API-read concerns the round-12 pressure had
colocated; the reaction-namespace re-export keeps the seam, and the
walk imports probe_timeout_budget FROM here (the timing home).]

PR #49 ROUND 15 (threads 3870293194 P1 / 3870293197 P1): the probe's
two round-15 holes. (1) The COLD-START head-transition bound: the
round-13 transition_floor only exists after a MID-WAIT head move,
so a retarget/force-push onto an already-pushed commit BEFORE the
first probe bound the old head's leftover EYES by the commit's OLD
pushedDate alone; ROUND_QUERY's new aliased headTransition connection
(the latest HeadRefForcePushedEvent — live-verified: the schema has
NO HeadRefPushedEvent timeline item, and a non-fast-forward retarget
IS a force push) MAXes its createdAt into the head bound, so the
leftover reads EYES_STALE while a normal fresh push (fresh-commit
pushedDate) is unchanged. (2) The
PARTIAL-ERROR unreadable probe: codex_request_marker treated a null/
omitted timelineItems as an empty history ('' — "provably no
request"), keeping the probe READABLE with the marker discarded; the
_nodes connection-shape check (shared by the request walk, the walk
page, and every ROUND_QUERY sibling connection) plus the top-level
errors rejection return the unreadable ('', '', '', '') instead —
per round 13's bracket rule the WHOLE probe retries, never a
readable no-request snapshot. The WAIT half of round 15 (the
request-advance latch reset of 3870293188 and the cold-NONE arming
gate of 3870293205) lives in pr_guard_reaction_wait.

PR #49 ROUND 18 (threads 3871485035 P1 / 3871485043 P2 /
3871485055 P1): the round-17 follow-ups. (1) THE FOLD: ROUND_QUERY's
new aliased `botReviews` connection — reviews(last:1,
author:"chatgpt-codex-connector[bot]") — carries the head-bound
review evidence INSIDE the one subprocess the bracket already
certifies (the separate post-bracket lookup of 3871485035 is gone;
the server-side author filter of 3871485043 means the fixed ten-
review window is gone too). (2) RoundBounds: round_bounds now
returns a 4-field tuple SUBCLASS — equality with every legacy plain
4-tuple seam fixture is preserved (the zero-repin seam rule, the
round-15/17 ABSENT-key tolerance applied to the return shape) —
carrying the three round-18 facts as ATTRIBUTES: .request and
.trigger (the per-kind boundary identities of 3871485055 — the wait
retains two INDEPENDENT high-waters; class-default None marks
"unset" so a legacy plain tuple falls back to its index-2 stream)
and .review_head (the folded evidence). The index-2 boundary stays
the MERGED identity (latest_boundary) — the EYES classification and
the composite marker compose across kinds; only the RETENTION split.

PR #49 ROUND 20 (threads 3872194007 P2 / 3872194017 P2 /
3872194023 P1): the RoundBounds attrs grow by three —
.request_ids/.trigger_ids (the walks' new `collect` sets: EVERY
same-second identity visible at the boundary's high-water second,
so the wait's seen-sets remember a sibling that later resurfaces
after the newest of its second is deleted) and .review_stamp (the
folded bot review's submittedAt — live-verified read-only
2026-08-27: `state` renders COMMENTED for findings AND pass rounds
alike on #49/#48, so the stamp is the evidence the wait's new
completion guards bind to; the ROUND_QUERY node carries it beside
commit.oid). The round-19 REQUEST-ADVANCE OBSERVATION FLOOR is
SUPERSEDED (thread 3872194017): the wait's wall-clock stamp demoted
a legitimately-requested round's EYES that posted BETWEEN polls;
the boundary is the REQUEST/TRIGGER's own createdAt — exactly the
reading's round-13 binding (see pr_guard_reaction_wait's round-20
section for the owned supersession).

PR #49 ROUND 22 (thread 3872980781, P1): the head bracket EXTENDS
PAST BOUNDARY PAGINATION. The request/trigger walks run additional
GraphQL subprocesses (backwards pages, same-second edge
continuations) AFTER ROUND_QUERY has already captured the bracket's
final headRefOid — a head moving during those walks left round_bounds
returning the OLD oid, so the wait accepted the old head's terminal
reaction before the next poll noticed the move (the round-10/18
bracket covered only the reactions read and the combined query
itself). The walks now report every dispatched cursor (the optional
paged list — a legacy 3/4-arg caller is byte-identical) and
round_bounds re-reads the head after all boundary pagination: a
re-read oid differing from the captured headRefOid (including '' —
a failed re-read certifies nothing, the round-13 ''-endpoint rule)
returns the unreadable all-empty bounds — the probe is DISCARDED
and retried next interval, never a certified stale-head snapshot.
The recheck rides the SAME probe deadline (an expired deadline
cannot certify the bracket either — unreadable), and a walk that
never paginated never rechecks (no window opened; no extra
subprocess for the common first-page-answers probe).

PR #49 ROUND 24 (thread 3873592857, P2): the post-pagination recheck
is WIDENED to the full bracket and the round-22 head-only re-read is
FOLDED into it — when either boundary walk paginated (paged
non-empty), round_bounds RE-RUNS the bracketed round query (ONE
extra ROUND_QUERY subprocess replacing round 22's separate
head-only read) and requires the whole newest-page picture
UNCHANGED: the head oid AND each kind's boundary facts as the
original query reported them. A new formal request or trigger
comment arriving AFTER ROUND_QUERY captured the newest page but
BEFORE the continuation reads finish is INVISIBLE to the
continuation cursors (they predate it) and to a head-only recheck
(an unchanged head certified the stale boundaries) — the probe
could return the PRECEDING round's bounds and the wait exit 0 on
its terminal +1 before the newly requested round began. The re-run's
own newest-50 window DOES see the arrival (a new boundary lands at
the top of the timeline): the latest VISIBLE request/trigger
identity must equal the original walk's reported identity, and a
walked-back (deeper-than-window) boundary is unchanged exactly while
the re-run window still shows none of its kind. ANY drift, a failed
or malformed re-run, or an expired deadline returns the unreadable
    all-empty bounds (retry next interval); TimeoutExpired propagates to
    the caller's UNREADABLE handling exactly like the opening query.

PR #49 ROUND 25 (thread 3873970927, P1): the recheck parse is
STRICT — the re-run is a live re-dispatch of OUR OWN assembled
ROUND_QUERY, where a success response always materializes every
requested alias, so an ABSENT triggerComments connection (timelineItems
was already strict through _nodes' None) is a partial/malformed
response, never a "provably no trigger" read: a successful-but-
partial re-run can no longer certify the preceding round's boundary
as "unchanged" while a newer trigger comment arrived during the
walk (the waiter keeping the old boundary could accept the old
round's terminal +1 before the requested review started). The
INITIAL query's legacy-absent-key tolerance stays (the minimal-
payload fixtures' no-trigger read; present-but-null is unreadable
there too) — see _bracket_unchanged for the documented asymmetry.

PR #49 ROUND 27 (thread 3874769245, P1): the BASE identity joins the
round facts. LIVE-VERIFIED read-only 2026-08-27 (the round-15/18/20
precedent): `baseRefOid` and `baseRef{target{... on Commit{pushedDate
committedDate}}}` exist on PullRequest (the base tip's push bound —
pushedDate reads NULL on PR #49's live base, so the committedDate
fallback is live-relevant, the head's exact round-3 shape), and
`BASE_REF_CHANGED_EVENT` is a valid PullRequestTimelineItemsItemType
carrying createdAt/id/databaseId/currentRefName/previousRefName
(shape positively verified on microsoft/vscode#101656 — PR #49
itself carries ZERO retarget events, the round-3
zero-ReviewRequestedEvent posture; the PR was never retargeted).
The P1's race: a retarget or a base-tip advance changes the
reviewed DIFF while `headRefOid` stays unchanged, so the head-keyed
bracket/reset never noticed the old-base job's review (whose
commit.oid still names the head) certifying a +1 over a diff the
new base derives. ROUND_QUERY therefore carries `baseRefOid` beside
the head oid (the identity — an OID, not the mutable ref NAME), the
aliased `baseChange` connection (the latest BaseRefChangedEvent —
retargets) beside headTransition, and the base target's own push
bound (tip advances, where NO PR timeline event exists: the base
branch's push is not a PR item, the round-17 FF posture's kin).
round_bounds threads both out as RoundBounds attrs (.base /
.base_bound, the round-26 head_bound pattern) and the wait keys its
base-change reset family and base_floor on them — the boundary's
OWN timestamp (the event's createdAt for retargets, the target's
own push bound for tip advances), NEVER an observation clock (the
round-20/22/26 floor doctrine). The review's commit.oid names the
HEAD, not the base — head_bound cannot separate bases; the
review_stamp > base_floor leg is the separation.
PR #49 ROUND 28 (thread 3875089268, P1): the base OID joins the
pagination bracket. When a request/trigger lookup paginates and the
PR base changes during those continuation reads, the final
ROUND_QUERY re-run contains the NEW baseRefOid — but the round-24
bracket validated only the head and the boundary connections, so
`_bracket_unchanged` accepted the drift and round_bounds returned
the ORIGINAL base: the waiter saw no base change and could accept
the old-base round's terminal +1 before the next poll's oid compare
caught it. The recheck now REQUIRES the re-run node to carry a
baseRefOid equal to the original query's (round-25 strict doctrine:
the re-run is our own assembled query, which always materializes
every requested alias — an ABSENT key is the partial/malformed
class exactly like an absent triggerComments, never "provably
unchanged"); the INITIAL query's legacy absent-key tolerance stays
(the re-run-node-only strictness, the documented asymmetry below).

PR #49 ROUND 29 (thread 3875352284, P1): the base tip's FORCE-UPDATE
bound — round 27's "NO PR timeline event exists for a base-branch
tip push" is CORRECTED by live introspection (read-only 2026-08-27,
the round-15/18/20/27 precedent): PullRequestTimelineItemsItemType
carries BASE_REF_FORCE_PUSHED_EVENT beside BASE_REF_CHANGED_EVENT,
BASE_REF_DELETED_EVENT, AUTOMATIC_BASE_CHANGE_SUCCEEDED_EVENT,
AUTOMATIC_BASE_CHANGE_FAILED_EVENT, and AUTO_REBASE_ENABLED_EVENT
(there is NO BaseRefRestoredEvent), its node carries createdAt/id/
ref/pullRequest/beforeCommit/afterCommit, and it POSITIVELY
materializes on real PRs whose base branch was force-pushed while
open (nodejs/node#60801: createdAt 2026-07-29T14:04:33Z, baseRefOid
== afterCommit.oid, pushedDate null on the target; a five-PR
electron mass-carrier set at 2022-11-12T01:49:2xZ; PR #49 itself
carries zero events — the base never moved). The race: a base
force-updated to an EXISTING OLDER commit changes baseRefOid with
NO BaseRefChangedEvent (the PR was not retargeted) while the
fallback bound read that commit's OLD committedDate (pushedDate
null on the live base) — an old-base review submitting after the
old stamp but before the force-update passed `review_stamp >
base_floor`, its delayed EYES re-armed the reset base, and WAIT
DONE accepted the +1 over a re-derived diff nobody reviewed. The
fix is the boundary's OWN timestamp (the round-20/22/26 doctrine —
the reviewer-sanctioned observation-floor fallback is NOT needed):
the aliased baseForce connection MAXes its createdAt into
base_bound, so base_floor postdates every pre-update review by
construction, while a post-update round's own review submits past
the event and completes (no false hold, no observation clock). The
    event-less residue — a FAST-FORWARD base advance (no force event,
    the round-15 head doctrine) whose fresh tip commit carries an OLD
    committedDate with pushedDate null — keeps the round-27 honest-
    documentation posture (quiet watch + rulesets backstop).

PR #49 ROUND 30 (thread 3875623447, P1): the round-29 FF residue's
    OBSERVATION bound — the finding's own sanctioned fallback ("or
    conservatively require post-observation review evidence when the
    base OID changes without a corresponding event timestamp"; round
    29 live-verified the FF move fires NO PR event, so no boundary-
    OWN timestamp exists for that class). round_bounds threads the
    event stamps out SEPARATELY as .base_event_bound (the max
    createdAt baseChange/baseForce contributed; '' when neither
    event exists) beside .base_bound, and the WAIT (unchanged here
    beyond consuming the attr — see pr_guard_reaction_wait's
    round-30 section) stamps base_floor with its observation
    wall-clock ONLY when a base change is NOT event-backed. This is
    the ONE sanctioned exception to the round-20/22/26 "no
    observation floor" doctrine: the event-backed retarget/force
    shapes keep their exact behavior (no observation stamp), the
    FF/null-dated class gains the conservative exit gate, and the
    documented prices (a same-interval post-FF round held for one
    round; a post-observation old-base review still indistinguishable
    — the standing documented-open class) are owned in the wait's
    round-30 section and the 3875623447 receipt.

PR #49 ROUND 32 (threads 3876000990 P1 / 3876001004 P1): the
pagination bracket's COMPOSITE-MARKER and HEAD-TRANSITION bounds.
(1) THE MARKER RECHECK (3876000990): a request-less follow-up can
submit a bot review or add a review-thread comment after the
original ROUND_QUERY but before the post-pagination re-run — those
fields advance the composite marker that makes the previously
fetched +1 stale, yet the round-24/25 bracket checked only the
request/trigger connections, so the waiter accepted the preceding
round's +1 and exited 0 after new findings had landed. The
engagement-marker parse (latestReviews submittedAt +
reviewThreads bot-comment stamps) is factored into
pr_guard_reaction_boundaries.bot_engagement_markers, moved ABOVE
the re-run (the original composite — the reading's `marker`
element — is the bar), and `_bracket_unchanged` rejects a re-run
whose own engagement ADVANCED past it or whose connections are
absent/null (the round-25 strict doctrine: our own assembled query
always materializes them). (2) THE TRANSITION BOUND (3876001004):
a head force-pushing A->B->A during the paginated walk leaves the
re-run's headRefOid UNCHANGED while its headTransition timestamp
ADVANCES — `_bracket_unchanged` compares the retained transition
stamp (threaded from the original parse beside the maxed head
bound) and rejects any drift under the same-OID picture (the
round-28 returning-OID fix's bracket twin). The ROUND_QUERY string
is UNCHANGED (validation only — the round-28 precedent).
    """

import json
import subprocess
import time

from .pr_guard_common import REPO_NAME, REPO_OWNER, gh_env
# PR #49 round 17 (threads 3870995905/11/19): the boundary walks,
# the bot vocabulary, the timing clamps, and the head-bound evidence
# read moved to the NEW sibling pr_guard_reaction_boundaries (the
# 250 pure-LOC ceiling again) — this module imports FROM it and
# RE-EXPORTS every moved name so each existing seam keeps ONE home:
# pr_guard_reaction_walk's probe_timeout_budget import, round-15's
# pr_guard_reaction_probe.codex_request_marker call, and every
# REACTION_BOT/GRAPHQL_BOT_LOGIN reference.
from .pr_guard_reaction_boundaries import (
    BOT_LOGINS,
    BOT_REVIEWS_FIELD,
    DEFAULT_WAIT_TIMEOUT_SECS,
    GRAPHQL_BOT_LOGIN,
    PROBE_TIMEOUT_CAP_SECS,
    PROBE_TIMEOUT_FLOOR_SECS,
    REACTION_BOT,
    REQUEST_WALK_QUERY,
    TRIGGER_WALK_QUERY,
    WAIT_INTERVAL_SECS,
    _codex_markers,
    _nodes,
    _trigger_markers,
    _walk_page,
    bot_engagement_markers,
    bot_review_stamp,
    codex_request_marker,
    latest_boundary,
    latest_review_commit,
    probe_timeout_budget,
    trigger_comment_marker,
)


# Thread 3871485055/3871485035 (round 18, P1): the round-facts
# carrier — a 4-field tuple SUBCLASS whose equality, indexing, and
# unpacking are byte-identical to the plain 4-tuple every legacy
# seam fixture patches with (zero repins), while the three round-18
# facts ride as attributes. The class defaults are None ("unset"):
# a legacy plain tuple has no attributes at all, so the reading's
# getattr(None) fallback rules feed the wait the fixture's own
# index-2 stream — the pre-round-18 behavior through the new
# plumbing.
class RoundBounds(tuple):
    """(head_oid, pushed, boundary, marker) + .request/.trigger/
    .review_head (round 18) + .request_ids/.trigger_ids/.review_stamp
    (round 20) + .base/.base_bound (round 27, thread 3874769245)
    + .base_event_bound (round 30, thread 3875623447)."""

    request = None
    trigger = None
    review_head = None
    # Thread 3872194007/23 (round 20): the full-identity same-second
    # sets (the wait's seen-sets union them) and the folded review's
    # submittedAt (the completion guards) — class-default None marks
    # "unset", the legacy plain-tuple/round-18 fallback.
    request_ids = None
    trigger_ids = None
    review_stamp = None
    # Thread 3874769245 (round 27, P1): the BASE identity (baseRefOid
    # — an OID, never the mutable ref name) and the base's OWN bound
    # (max(base target pushedDate/committedDate, the latest
    # BaseRefChangedEvent createdAt, the latest BaseRefForcePushedEvent
    # createdAt — round 29, thread 3875352284)) — the wait's base-change
    # reset and base_floor key on them (the round-26 head/head_bound twin).
    base = None
    base_bound = None
    # Thread 3875623447 (PR #49 round 30, P1): the EVENT portion of
    # base_bound — the max createdAt the baseChange/baseForce
    # connections contributed ('' when neither event exists, the
    # fast-forward-advance residue round 29 documented). The wait's
    # FF observation bound keys on it: only a move NO event stamp
    # covers falls back to the observation clock (the finding's own
    # sanctioned arm, consumed in pr_guard_reaction_wait).
    base_event_bound = None


# Threads 3867503712 + 3867653639 + 3867757439 + 3868158304: the
# round discriminator probe. The head half: the CURRENT head's oid
# (pinning that the date belongs to the head being merged) beside its
# pushedDate (committedDate fallback: a rebase can carry an old
# committer date while pushedDate is when the ref actually landed).
# The request half: the timeline's ReviewRequestedEvent createdAt
# values — a formal (re-)request, including one with NO head change,
# the exact shape the head date cannot see — read through the
# thread-3868158304 window: last:50 with pageInfo, because GitHub
# truncates the connection BEFORE the client-side filter to the
# codex bot (requestedReviewer is a union — live-introspected
# 2026-08-27: Bot/User/Team/...; the query selects the User/Bot
# login and only events whose reviewer IS the bot count, thread
# 3867757442 — a human or another bot requested after the +1
# extends nothing). Beside the bot's latest SUBMITTED review
# (latestReviews submittedAt) and the bot's latest review-THREAD
# comment (reviewThreads(last:10) with comments(last:3) per thread
# is the bounded single-field window; the full walk is the threads
# module's job — the wait mode stays a cheap poll). The +1 is the
# bot's POST-review verdict: it must postdate every marker.
# Threads 3870293194 (PR #49 round 15, P1): the head-TRANSITION
# connection — the latest HeadRefForcePushedEvent, aliased
# headTransition so it cannot clash with the request walk's
# unaliased timelineItems. Its createdAt is the moment the REF
# moved, and round_bounds MAXes it into the head bound so a
# cold-start probe cannot certify the old head's leftover EYES
# against a retargeted commit's old pushedDate alone. GOTCHA
# (live-verified 2026-08-27 against PR #49): the finding named
# HeadRefPushedEvent too, but the live schema REJECTS it —
# HEAD_REF_PUSHED_EVENT is not a PullRequestTimelineItemsItemType
# and no such fragment type exists — so the force-push event is the
# implementable boundary; sufficient, because a retarget onto
# already-pushed history is BY DEFINITION non-fast-forward (a
# force-push event) while a fast-forward push lands fresh commits
# whose pushedDate is itself current (event≈pushedDate either way,
# the pinned live shapes unchanged). Thread 3870995905 (round 17,
# P1): the ReviewRequestedEvent selection now carries the node ID
# (live-verified field; the events have NO databaseId) so the walk
# returns `createdAt|id` boundary identities — the same-second
# tie-breaker. Thread 3870995911 (round 17, P1): the aliased
# triggerComments connection — the PR's TOP-LEVEL comments (NOT the
# review-thread comments nested under reviewThreads), walked by
# pr_guard_reaction_boundaries.trigger_comment_marker for the
# documented '@codex review' manual trigger, ANY author.
ROUND_QUERY = (
    "query($owner:String!,$name:String!,$number:Int!){repository("
    "owner:$owner,name:$name){pullRequest(number:$number){headRefOid "
    "headRef{target{... on Commit{pushedDate committedDate}}} "
    # Thread 3874769245 (PR #49 round 27, P1): the BASE identity —
    # baseRefOid (the OID, never the mutable ref name) beside the
    # base target's own push bound (tip advances; pushedDate reads
    # null on the live base, the committedDate fallback is the
    # round-3 head shape) and the aliased baseChange connection (the
    # latest BaseRefChangedEvent — retargets; live-verified shape on
    # microsoft/vscode#101656, PR #49 itself carries zero events).
    # Thread 3875352284 (PR #49 round 29, P1): the aliased baseForce
    # connection — the latest BaseRefForcePushedEvent (the headTransition
    # twin), whose createdAt is a force-updated base tip's OWN move
    # timestamp (live-verified: see the module docstring's round-29
    # section).
    "baseRefOid baseRef{target{... on Commit{pushedDate committedDate}}} "
    "baseChange:timelineItems(itemTypes:[BASE_REF_CHANGED_EVENT],"
    "last:1){nodes{... on BaseRefChangedEvent{createdAt}}} "
    "baseForce:timelineItems(itemTypes:[BASE_REF_FORCE_PUSHED_EVENT],"
    "last:1){nodes{... on BaseRefForcePushedEvent{createdAt}}} "
    "timelineItems(itemTypes:REVIEW_REQUESTED_EVENT,last:50){pageInfo{"
    "hasPreviousPage startCursor} nodes{... on ReviewRequestedEvent{"
    "createdAt id requestedReviewer{... on User{login} ... on Bot{login}}}}} "
    "triggerComments:comments(last:50){pageInfo{hasPreviousPage "
    "startCursor} nodes{id createdAt body}} "
    "headTransition:timelineItems(itemTypes:[HEAD_REF_FORCE_PUSHED_EVENT],"
    "last:1){nodes{... on HeadRefForcePushedEvent{createdAt}}} "
    # Threads 3871485035/3871485043 (round 18, P1/P2): the aliased
    # botReviews connection — the head-bound review evidence FOLDED
    # into this one subprocess (the round-10 bracket certifies it
    # with the head oid for free). The author filter literal is the
    # [bot]-suffixed login: live-verified 2026-08-27, reviews(author:)
    # filters SERVER-SIDE but matches ONLY "chatgpt-codex-connector[bot]"
    # (the suffix-less form author{login} RENDERS returns an empty
    # connection — the inverse of the round-3 rendering GOTCHA); the
    # fixed latestReviews(last:10) window that evicted the connector
    # behind ten humans applies to the MARKER connection only.
    # Thread 3872194023 (round 20, P1): submittedAt rides the node
    # too (live-verified the same day) — the `state` field renders
    # COMMENTED for findings and pass rounds alike, so the verdict
    # stamp is the evidence the completion guards bind to.
    "botReviews:reviews(last:1,author:\"chatgpt-codex-connector[bot]\"){"
    "nodes{author{login} commit{oid} submittedAt}} "
    "latestReviews(last:10){nodes{author{login} submittedAt}} "
    "reviewThreads(last:10){nodes{comments(last:3){nodes{author{login} "
    "createdAt}}}}}}}"
)

# Thread 3868782039 (PR #49 round 10, P1): the head-ONLY read — the
# BEFORE side of the reactions read's stability bracket (the AFTER
# side is round_bounds' own headRefOid, read in ONE combined query
# beside the dates it certifies).
HEAD_ONLY_QUERY = (
    "query($owner:String!,$name:String!,$number:Int!)"
    "{repository(owner:$owner,name:$name){pullRequest(number:$number)"
    "{headRefOid}}}"
)


# Thread 3873592857 (PR #49 round 24, P2): the post-pagination
# re-run — ONE more ROUND_QUERY subprocess whose pullRequest node
# feeds the bracket recheck below. None on a failed read, malformed
# payload, or top-level GraphQL errors (the round-15 partial-error
# class: a re-run that cannot run validates nothing).
def _round_query_node(pr: int, timeout) -> dict | None:
    proc = subprocess.run(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={ROUND_QUERY}",
            "-F",
            f"owner={REPO_OWNER}",
            "-F",
            f"name={REPO_NAME}",
            "-F",
            f"number={pr}",
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
        if payload.get("errors"):
            return None
        return payload["data"]["repository"]["pullRequest"]
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


# Thread 3873592857 (PR #49 round 24, P2): the re-run's picture vs
# the original query's — the head oid PLUS each kind's newest-window
# boundary facts. A NEW request/trigger lands at the timeline's TOP
# (inside every newest-50 windows), so the latest VISIBLE identity of
# a kind must still be the identity the original walk returned; a
# walked-back boundary (deeper than the newest window) is unchanged
# exactly while the re-run window still carries none of its kind.
# The FOLD of round 22's head-only recheck: the re-run's headRefOid
# replaces the separate head read (one subprocess certifying MORE).
# Thread 3873970927 (PR #49 round 25, P1): the recheck parse is
# STRICT — BOTH connections (timelineItems AND triggerComments) must
# be PRESENT and well-formed. This is a re-run of OUR OWN assembled
# query, where a success response always materializes every
# requested alias: an ABSENT triggerComments (or timelineItems) key
# or a null connection means the re-run came back partial/malformed,
# not "provably no trigger" — accepting the omission as "unchanged"
# let a malformed-but-successful re-run certify the preceding
# round's boundary while a newer trigger had arrived, so the waiter
# kept the old boundary and accepted the old round's terminal +1
# before the requested review started. The ASYMMETRY with the
# INITIAL query's parse is deliberate and documented: the initial
# query tolerates an ABSENT triggerComments/timelineItems key (the
# legacy minimal-payload fixtures' no-trigger read, present-but-null
# stays unreadable there too), while the recheck — a live re-run of
# the assembled string, never a fixture — requires both.
# Thread 3875089268 (PR #49 round 28, P1): the BASE OID joins the
# strict recheck — the re-run node MUST carry a baseRefOid equal to
# the original query's parse: the base can move during the walks'
# continuation reads exactly as a request/trigger can arrive during
# them (the round-24 window class), and an unchanged-head/unchanged-
# boundary re-run over a MOVED base certified the ORIGINAL base's
# bounds — the waiter saw no base change until the next poll and
# could accept the old-base round's terminal +1 in between. An
# ABSENT key is the partial/malformed class (the round-25 doctrine:
# our own assembled query always materializes baseRefOid), never a
# "provably unchanged" base; the INITIAL query's legacy absent-key
# tolerance stays (the re-run node only).
# Thread 3876000990 (PR #49 round 32, P1): the COMPOSITE MARKER
# joins the strict recheck — a request-less follow-up can submit a
# bot review or add a review-thread comment after the original
# ROUND_QUERY but before the re-run; those fields advance the
# composite marker that makes the previously fetched +1 stale, so
# the re-run's engagement markers (bot_engagement_markers — the
# latestReviews submittedAt + reviewThreads bot-comment stamps,
# held to the round-25 present-and-readable rule) must NOT have
# advanced past the ORIGINAL query's composite marker (the reading's
# `marker` element, threaded in by round_bounds): a newer marker
# means the original +1's staleness classification is stale itself —
# the waiter must never accept the preceding round's +1 after new
# findings have landed.
# Thread 3876001004 (PR #49 round 32, P1): the HEAD-TRANSITION
# bound joins the strict recheck — a head force-pushing A->B->A
# during the paginated walk leaves the re-run's headRefOid UNCHANGED
# while its headTransition timestamp ADVANCES (the B->A force-push
# event — round-15/26 semantics: the event exists only when the ref
# moved, so the advance is never a false positive): the returning-
# OID cycle inside the pagination window, the round-28 cross-probe
# fix's bracket twin. The re-run's transition connection is held to
# the same strict present-and-readable rule (an absent key can never
# certify "no transition happened during the window") and its stamp
# must EQUAL the original query's — any drift reads unreadable
# bounds, so round_bounds can never return the pre-cycle bound the
# waiter could accept the old A round's terminal +1 off.
def _bracket_unchanged(node: dict, head_oid: str, request: str, trigger: str, base_oid: str, marker: str, head_transition: str) -> bool:
    if str(node.get("headRefOid") or "") != head_oid:
        return False
    if "baseRefOid" not in node or str(node.get("baseRefOid") or "") != base_oid:
        return False
    nodes = _nodes(node.get("timelineItems"))
    if nodes is None:
        return False
    visible = [m for m in _codex_markers(nodes) if m.partition("|")[0]]
    if visible and visible[-1] != request:
        return False
    tnodes = _nodes(node.get("triggerComments"))
    if tnodes is None:
        return False
    tvisible = [m for m in _trigger_markers(tnodes) if m.partition("|")[0]]
    if tvisible and tvisible[-1] != trigger:
        return False
    events = _nodes(node.get("headTransition"))
    if events is None or max([str(e.get("createdAt") or "") for e in events if e.get("createdAt")], default="") != head_transition:
        return False
    engagement = bot_engagement_markers(node)
    if engagement is None or max((m for m in engagement if m), default="") > marker:
        return False
    return True


# Thread 3868782039 (PR #49 round 10, P1): the exception a head-stability
# mismatch raises out of bot_reaction_reading — the probe paired reads from
# OPPOSITE sides of a head change (reactions for head A beside head B's
# oid/dates), so the WHOLE reading is UNREADABLE, never a mixed snapshot the
# wait could reset-and-re-arm from (the pre-change EYES re-arming under the
# new head's bounds let a completion for A satisfy B's timestamps and exit 0
# without B being reviewed). Both callers' conservative arms own the raise:
# the banner fails open (UNREADABLE, survey continues) and the wait keeps
# polling under its deadline (retry next interval).
class ReactionHeadMoved(Exception):
    """The head moved between the probe's reads (thread 3868782039)."""


# Thread 3869259808 (PR #49 round 13, P1): the exception an EMPTY
# bracket endpoint raises out of bot_reaction_reading — a failed
# head_ref_oid read ('', the BEFORE side) or a failed round probe
# ('' head oid, the AFTER side) left head_changed accepting the
# probe, so an EYES from a head that moved A->B inside the
# failed-before/reactions/bounds sequence armed the latch under B
# and A's later +1 satisfied B's bounds — exit 0 with B reviewed by
# nobody. Either empty endpoint makes the bracket UNCERTIFIED: the
# whole probe is UNREADABLE (retry next interval), never a
# certified mixed snapshot. This tightens the round-8 '' -rule on
# the WAIT side ('' never certifies NOR pollutes — it now also
# never PARTICIPATES); the round-6/7 empty-bounds UNVERIFIED reads
# are superseded too (a failed round probe retries; UNVERIFIED
# survives for the readable-oid/null-dates shape).
class ReactionBracketUnreadable(Exception):
    """A bracket endpoint read '' — the probe is uncertifiable (3869259808)."""


# Thread 3867572256 (PR #49 round 2, P2 — the function moved to
# pr_guard_reaction_boundaries round 17 and is RE-EXPORTED above):
# ONE subprocess's timeout — the ACTUAL remaining window clamped to
# [floor, two intervals]. Kept here as the seam home.


def head_ref_oid(pr: int, timeout_secs: float | None = None) -> str:
    """The PR head's CURRENT oid — '' when the read fails.

    Thread 3868782039 (PR #49 round 10, P1): the BEFORE side of the
    reactions read's STABILITY BRACKET. bot_reaction_reading reads
    the head FIRST, then the reactions, then round_bounds (ONE
    combined query carrying the AFTER oid beside its dates) and
    DISCARDS the whole probe unless the two oids match — a probe
    that combined snapshots from opposite sides of a head change is
    a mixed input, never a reading. A failure returns '' (never a
    die): an unreadable side certifies nothing, mirroring
    head_changed's refusal of empty oids; the caller's bracket
    treats '' as no-evidence and does not discard on it. The
    subprocess timeout rides the family clamp (probe_timeout_budget).
    """
    proc = subprocess.run(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={HEAD_ONLY_QUERY}",
            "-F",
            f"owner={REPO_OWNER}",
            "-F",
            f"name={REPO_NAME}",
            "-F",
            f"number={pr}",
        ],
        capture_output=True,
        text=True,
        env=gh_env(),
        timeout=None if timeout_secs is None else probe_timeout_budget(timeout_secs),
    )
    if proc.returncode != 0:
        return ""
    try:
        return str(
            json.loads(proc.stdout)["data"]["repository"]["pullRequest"]
            .get("headRefOid")
            or ""
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        return ""


# Threads 3867757442 + 3868158304 + 3870293197 (rounds 4/7/15 — the
# request walk, its markers, the connection-shape helper, and the
# shared walk page moved to pr_guard_reaction_boundaries round 17
# with the identity upgrade of 3870995905; RE-EXPORTED above for the
# round-15 seam).


def round_bounds(pr: int, timeout_secs: float | None = None) -> tuple[str, str, str, str]:
    """The round's START facts: (head_oid, head_push, request, marker).

    Thread 3868443452 (PR #49 round 8, P1): the head OID rides
    head-first — the identity of the head the date facts belong
    to. The pushedDate belongs to whichever commit the ref names, so
    a mid-wait head move (e.g. the ref retargeted onto an
    already-pushed commit) silently re-binds every date comparison;
    the wait compares the oid ACROSS probes and resets its
    transition latch/baseline when it moves (an unchanged +1 whose
    classification flipped stale->done on the new bounds is NOT a
    transition — it is the same pre-move reaction).

    Thread 3869259813 (PR #49 round 13, P1): the FORMAL codex
    request marker rides SEPARATELY (third) from the composite
    marker (fourth) — the EYES classification binds the request
    alone (a request PRECEDES its round's EYES by nature, while the
    round's own comments/submissions land after it — the round-11
    asymmetry), and the +1 completion keeps binding the composite
    max(request, submitted reviews, thread comments) exactly as
    rounds 3/4 always did.

    Thread 3867653639 (PR #49 round 3, P1): the head date alone cannot
    bind the round — a re-requested review WITHOUT a head change leaves
    the prior +1 postdating the head push, and the waiter exits 0
    while the new round is still pending. The second fact is the
    LATEST round-engagement marker: the newest of the CODEX request
    marker (thread 3868158304: read through the paginated 50-event
    window — codex_request_marker, None reads the whole bounds
    unreadable here), the bot's latest SUBMITTED review
    (latestReviews submittedAt), and the bot's latest review-THREAD
    comment (thread 3867757439: a request-less round that has begun
    posting marks itself the moment its first comment lands). GitHub
    timestamps share one ISO-Z format, so max() over the string
    list is chronological. A query failure returns ('', '', '', '')
    and the caller's bracket check reads the whole probe UNREADABLE
    (thread 3869259808, round 13) — never done, and never a
    latch-arming stale; never done-on-ambiguity; a markerless-but-
    readable history (no codex requests, no bot submissions, no bot
    comments) contributes nothing and leaves the head push carrying
    the binding, exactly the round-1 semantics.
    TimeoutExpired propagates to the caller's UNREADABLE handling;
    the request-walk's own expiry/failure returns ('', '', '', '')
    through the None arm instead (both conservative: an unreadable
    bound is never a fact a +1 could be proven newer than).

    Thread 3870293194 (round 15, P1): the head bound is
    max(pushedDate, committedDate-fallback, the latest head-ref
    FORCE-PUSH event's createdAt) — the event stamp is the moment
    the REF moved, so a retarget onto an already-pushed commit (old
    pushedDate) cannot certify the old head's leftover EYES current
    at cold start; a normal fresh push lands fresh-commit dates
    (the live shapes unchanged; live-verified: no HeadRefPushedEvent
    timeline item exists — a non-fast-forward retarget IS a force
    push). Thread 3870293197
    (round 15, P1): a top-level GraphQL errors array OR any null/
    malformed connection (timelineItems, headTransition,
    latestReviews, reviewThreads, comments) returns ('', '', '',
    '') — a partial response is UNREADABLE (the bracket rule makes
    the whole probe retry), never a readable history whose missing
    request marker could bias a +1 toward done.
    """
    # Live-fixed with round 4: the flags ride as SEPARATE argv tokens
    # ("-f", "query=...") — subprocess lists do not shell-split, so
    # the round-3 one-token shape ("-f query=...") reached gh as an
    # unknown argument and every LIVE probe failed into the
    # conservative ('', '') arm (the mocked tests never saw it).
    started = time.monotonic()
    deadline = None if timeout_secs is None else started + timeout_secs
    proc = subprocess.run(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={ROUND_QUERY}",
            "-F",
            f"owner={REPO_OWNER}",
            "-F",
            f"name={REPO_NAME}",
            "-F",
            f"number={pr}",
        ],
        capture_output=True,
        text=True,
        env=gh_env(),
        timeout=timeout_secs,
    )
    if proc.returncode != 0:
        return "", "", "", ""
    try:
        payload = json.loads(proc.stdout)
        # Thread 3870293197 (round 15, P1): ANY top-level GraphQL
        # error makes the whole probe unreadable — a partial response
        # (timelineItems null while head/reviews/threads survive) is
        # never a readable history whose missing request marker could
        # bias a +1 toward done.
        if payload.get("errors"):
            return "", "", "", ""
        pr_node = payload["data"]["repository"]["pullRequest"]
        commit = pr_node["headRef"]["target"]
        # Thread 3868443452 (round 8, P1): PRESERVE the head oid the
        # query already carried — pinning that the dates below belong
        # to the head being certified (the wait resets its latch when
        # this moves).
        head_oid = str(pr_node.get("headRefOid") or ""); pushed = str(commit.get("pushedDate") or commit.get("committedDate") or "")
        # Thread 3876001004 (PR #49 round 32, P1): the transition
        # event stamps are retained SEPARATELY beside the maxed head
        # bound — the post-pagination bracket compares the re-run's
        # headTransition stamp against THIS value (an advanced stamp
        # under an unchanged oid is the returning-OID A->B->A cycle
        # inside the pagination window; see _bracket_unchanged). ''
        # when no event contributed (the ABSENT-key legacy page and
        # the no-event shape alike — the pushedDate binding stands).
        head_transition = ""
        # Thread 3870293194 (round 15, P1): MAX the commit's own
        # stamps with the latest head-ref PUSH/FORCE-PUSH event — a
        # retarget onto an already-pushed commit carries an event
        # stamp NEWER than the commit's pushedDate, so the old head's
        # leftover EYES/+1 read STALE against the transition instead
        # of arming current on the old stamp alone. The event, never
        # the wait's own start clock: a legitimate mid-round EYES
        # predating wait start still arms (round 12's live shape).
        # Shape rule: a SUCCESS response always materializes the
        # requested alias, so a PRESENT-but-null/malformed connection
        # is the partial-error shape (unreadable, thread 3870293197)
        # while an ABSENT key is the no-event read (the pushedDate
        # binding stands — the legacy minimal-payload fixtures pin
        # exactly that).
        if "headTransition" in pr_node:
            events = _nodes(pr_node["headTransition"])
            if events is None:
                return "", "", "", ""
            stamps = [str(e.get("createdAt") or "") for e in events if e.get("createdAt")]; pushed = max([pushed] + stamps); head_transition = max(stamps, default="")
        # Thread 3874769245 (PR #49 round 27, P1): the BASE facts —
        # the oid beside the base's OWN bound, the headTransition
        # twin's exact pattern: max(base target pushedDate/
        # committedDate — tip advances — with the latest
        # BaseRefChangedEvent createdAt — retargets). [Round 27
        # documented "NO PR timeline event exists" for tip advances —
        # CORRECTED by round 29 / thread 3875352284: the FORCE-UPDATE
        # half HAS one (BaseRefForcePushedEvent, maxed below); only
        # the fast-forward advance stays event-less, where the fresh
        # tip's own dates are current — the round-15 head doctrine.]
        # Shape rules (the round-15/25 rule): an ABSENT key is the legacy
        # minimal-payload page (no base tracking, readable — the
        # wait's '' never certifies a change), a PRESENT-but-null/
        # malformed connection is the partial-error class (the WHOLE
        # probe retries, never a readable history whose missing base
        # fact could bias a completion toward done).
        base_oid = str(pr_node.get("baseRefOid") or ""); base_bound = base_event_bound = ""
        if "baseRef" in pr_node:
            btarget = pr_node["baseRef"]["target"]
            base_bound = str(btarget.get("pushedDate") or btarget.get("committedDate") or "")
        # Thread 3875352284 (PR #49 round 29, P1): BOTH base event
        # connections MAX their createdAt into the bound — the latest
        # BaseRefChangedEvent (retargets) AND the latest
        # BaseRefForcePushedEvent (force-updated tips: the event's own
        # createdAt is the ref's ACTUAL move time, so an old-commit
        # target's old committedDate can never certify a pre-update
        # review current; see the module docstring's round-29 section).
        # Shape rules (the round-15/25 rule): an ABSENT key is the
        # legacy minimal-payload page (readable — the other sources
        # carry the binding), a PRESENT-but-null/malformed connection
        # is the partial-error class (the WHOLE probe retries, never a
        # readable history whose missing base fact could bias a
        # completion toward done).
        # Thread 3875623447 (PR #49 round 30, P1): the SAME loop
        # threads the event stamps out SEPARATELY as base_event_bound
        # ('' when no event contributed — the fast-forward-advance
        # class round 29 documented as residue), so the wait's
        # observation fallback can key on event-backed-ness without
        # reparsing the page (the zero-repin attr seam).
        for bkey in ("baseChange", "baseForce"):
            if bkey not in pr_node:
                continue
            bevents = _nodes(pr_node[bkey])
            if bevents is None:
                return "", "", "", ""
            stamps = [str(e.get("createdAt") or "") for e in bevents if e.get("createdAt")]
            base_bound = max([base_bound] + stamps); base_event_bound = max([base_event_bound] + stamps)
        # Thread 3872194007 (round 20, P2): the walk also deposits
        # EVERY same-second identity at the boundary's high-water
        # second into the collect set (the attrs below carry it to
        # the wait's seen-sets — a same-second sibling visible beside
        # the latest boundary is remembered, so its later resurfacing
        # never counterfeit a new round).
        request_ids: set = set()
        # Thread 3872980781 (round 22, P1): the walks' pagination
        # REPORT — every backwards-page/edge-continuation cursor the
        # walks dispatch lands here, so the head recheck below runs
        # exactly when a post-ROUND_QUERY window opened.
        paged: list = []
        request = codex_request_marker(pr_node, pr, deadline, request_ids, paged)
        if request is None:
            return "", "", "", ""
        # Thread 3870995911 (round 17, P1): the TRIGGER boundary —
        # the documented '@codex review' top-level comment walks the
        # same machinery a formal re-request does. Shape rule
        # (round-15 precedent): an ABSENT triggerComments key is the
        # legacy minimal-payload fixture's no-trigger read, while a
        # PRESENT-but-null/malformed connection is the partial-error
        # shape — trigger_comment_marker returns None and the WHOLE
        # probe retries, never a readable history whose missing
        # boundary could bias the wait toward the preceding round's
        # certifications.
        trigger = ""; trigger_ids: set = set()
        if "triggerComments" in pr_node:
            trigger = trigger_comment_marker(pr_node, pr, deadline, trigger_ids, paged)
            if trigger is None:
                return "", "", "", ""
        # Threads 3870995905/11 (round 17): the boundary rides THIRD
        # as the merged IDENTITY `createdAt|node id` of the newest
        # request/trigger event (latest_boundary — newest createdAt
        # wins) — the same-second DISTINCT-node tie-breaker the
        # timestamp-only round-15 compare lacked; the EYES binding
        # and the composite marker consume its createdAt half below.
        # Thread 3871485055 (round 18, P1): the merge is
        # CLASSIFICATION-ONLY — the two kinds' identities ride the
        # attrs for the wait's SEPARATE per-kind high-waters.
        # [Round 32, thread 3876000990: computed HERE now — the
        # pagination recheck below consumes the composite the
        # reading will carry, so the engagement parse must precede
        # the re-run.]
        boundary = latest_boundary(request, trigger); boundary_at = boundary.partition("|")[0]
        # Thread 3870293197 (round 15, P1): the sibling-connection
        # audit — latestReviews/reviewThreads/comments nulls read
        # UNREADABLE through the same explicit _nodes shape check
        # the request connection requires (a null sibling is a
        # partial response, never a readable history). [Round 32,
        # thread 3876000990: the audit moved ABOVE the pagination
        # re-run, factored into bot_engagement_markers — the recheck
        # holds the re-run's node to the SAME marker facts; the
        # return value/order of the unreadable arms is unchanged.]
        engagement = bot_engagement_markers(pr_node)
        if engagement is None:
            return "", "", "", ""
        # Thread 3876000990 (PR #49 round 32, P1): the ORIGINAL
        # query's composite marker — max(boundary createdAt, the
        # engagement stamps) — the bar the re-run's own engagement
        # must not advance past (the reading's `marker` element).
        original_marker = max([m for m in ([boundary_at] if boundary_at else []) + engagement if m], default="")
        # Thread 3872980781 (round 22, P1) + thread 3873592857
        # (round 24, P2): the bracket's extension past boundary
        # pagination — after ALL continuation reads (backwards walks
        # + same-second edge continuations, the walks' paged
        # report), RE-RUN the bracketed round query (round 24 FOLDS
        # round 22's separate head-only read into this one
        # subprocess — the re-run's headRefOid certifies the head
        # while its newest window simultaneously certifies the
        # boundaries) and require the picture UNCHANGED: the head
        # oid, and each kind's boundary facts as the ORIGINAL query
        # reported them (a request/trigger arriving after the
        # newest page was captured is invisible to the continuation
        # cursors — only the re-run's own window sees it; see
        # _bracket_unchanged). ANY drift, a failed/malformed re-run
        # ('' certifies nothing, the round-13 ''-endpoint rule), or
        # an EXPIRED deadline returns the unreadable all-empty
        # bounds — the probe is discarded and retried next interval,
        # never a certified stale-boundary snapshot. A walk that
        # never paginated (the common first-page-answers probe)
        # rechecks nothing: no window opened. [Round 32, threads
        # 3876000990/3876001004: the UNCHANGED picture now includes
        # the re-run's engagement markers vs original_marker and its
        # headTransition stamp vs the retained head_transition —
        # see _bracket_unchanged's header.]
        if paged:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return "", "", "", ""
            node = _round_query_node(
                pr,
                None if remaining is None else probe_timeout_budget(remaining),
            )
            if node is None or not _bracket_unchanged(node, head_oid, request, trigger, base_oid, original_marker, head_transition):
                return "", "", "", ""
        # Threads 3871485035/3871485043 (round 18, P1/P2): the FOLDED
        # review evidence — latest_review_commit extracts it from THIS
        # query's author-filtered botReviews connection (one
        # subprocess, one stable-head bracket), so it can never be a
        # second unbracketed lookup racing a mid-sequence head move.
        # Shape rule (the trigger twin's): ABSENT key = the legacy
        # minimal-payload page (no evidence carried), PRESENT-but-null
        # = the partial-error class (None -> the WHOLE probe retries).
        # Thread 3872194023 (round 20, P1): the VERDICT STAMP rides
        # beside the oid (the state field separates nothing — both
        # findings and pass rounds render COMMENTED, live-verified
        # 2026-08-27 on #49/#48); the wait's completion guards bind
        # the accepting +1 to it.
        review_head = review_stamp = ""
        if BOT_REVIEWS_FIELD in pr_node:
            review_head = latest_review_commit(pr_node)
            review_stamp = bot_review_stamp(pr_node)
            if review_head is None or review_stamp is None:
                return "", "", "", ""
        # Thread 3869259813 (round 13, P1): the boundary rides BOTH as
        # its identity (third — the EYES's formal boundary, round 17's
        # merged request/trigger shape) and inside the composite max
        # (fourth — the +1's full both-facts binding, createdAt only).
        # Thread 3871485035/3871485055 (round 18): the three new facts
        # ride as ATTRIBUTES on the tuple subclass — every legacy
        # plain-4-tuple seam fixture stays equal (the zero-repin seam
        # rule; see RoundBounds above).
        markers = ([boundary_at] if boundary_at else []) + engagement
        bounds = RoundBounds(
            (head_oid, pushed, boundary, max((m for m in markers if m), default=""))
        )
        bounds.request = request
        bounds.trigger = trigger
        bounds.review_head = review_head
        # Thread 3872194007/23 (round 20): the same-second identity
        # sets and the verdict stamp join the round-18 attrs (the
        # reading's getattr fallbacks keep plain-tuple seams green).
        bounds.request_ids = request_ids
        bounds.trigger_ids = trigger_ids
        bounds.review_stamp = review_stamp
        # Thread 3874769245 (round 27, P1): the base identity + the
        # base's own bound join the attrs (the round-26 head_bound
        # twin — the wait's base-change reset and base_floor keys on
        # them through the reading's getattr fallbacks). Thread
        # 3875623447 (round 30, P1): the EVENT portion rides beside
        # them — the wait's FF observation fallback keys on it.
        bounds.base = base_oid; bounds.base_bound = base_bound; bounds.base_event_bound = base_event_bound
        return bounds
    except (ValueError, KeyError, TypeError, AttributeError):
        return "", "", "", ""

