"""The reaction-state vocabulary and the wait's transition latch.

PR #49 round 6 (thread 3868047719, P1) split this state machine out
of pr_guard_reaction.py — the 250 pure-LOC ceiling (split-first, the
PR #36 round-2 family rule). Imports flow ONE way: pr_guard_reaction
imports FROM here; this module imports NOTHING from the reaction
family — it owns the vocabulary the family speaks.

THE VOCABULARY: the five states the bot's latest reaction reads as —
THUMBS_UP (done), THUMBS_UP_STALE (a VERIFIED prior-round pass),
THUMBS_UP_UNVERIFIED (round 6: a +1 whose round bounds were
UNREADABLE — a read failure, not round evidence), EYES (active),
NONE.

THE CLASSIFICATION (thumbs_up_round_state): a +1 against the round's
start facts. DONE only when it postdates BOTH readable facts. STALE
when a READABLE fact (the head push, or a round-engagement marker)
certifies it predates the round — the state rounds 1-4 called stale.
UNVERIFIED when the bounds themselves are unreadable ('' pushed —
round_bounds' conservative ("", "") return on a failed or malformed
probe): the round-5 conflation ("not pushed -> STALE") armed the
transition latch on an ERROR (thread 3868047719) — a transient
round_bounds failure at wait start labeled the prior +1 stale, and
when bounds recovered the unchanged old +1 read DONE on an
error-armed latch. Never done either way: unverified keeps polling
to its timeout (conservative).

THE LATCH (arms_transition_latch): only GENUINELY-VERIFIED non-DONE
readings arm the transition latch — EYES, NONE, or marker-verified
STALE (thread 3867897766's observed active->done requirement).
THUMBS_UP_UNVERIFIED, like the wait loop's UNREADABLE, never arms:
a read failure is not round evidence and must not counterfeit the
transition an initial-+1 wait exits 0 on.

ROUND 9 (threads 3868625463/3868625469, P1): two more wait-safety
predicates — effective_round_marker (the marker HIGH-WATER: max of
the retained and the freshly observed marker, so a bounded-window
eviction can never let the effective marker go backwards) and
reaction_follows (the OBSERVED-ACTIVITY watermark: whether one
reaction identity POSTDATES another — created_at first, the numeric
id on a same-second tie — so an accepted +1 must follow the EYES
the wait actually observed).

ROUND 10 (thread 3868782042, P1): EQUAL-SECOND round facts are
AMBIGUOUS — GitHub's ISO-Z timestamps carry no sub-second order, so
a +1 created in the SAME second as the head push (or a re-request/
marker) can never be PROVEN to postdate it; thumbs_up_round_state
classifies only STRICTLY-greater created_at as DONE (the `<`
comparisons became `<=`: equality reads THUMBS_UP_STALE, the
conservative never-done class — the pre-fix equality fell through
to DONE and an armed latch exited 0 on a pass that may have
preceded the new round). reaction_follows KEEPS its same-second id
tie-break: it orders two REST REACTION objects (ids increase
monotonically), where order IS establishable — the ambiguity is
cross-entity (+1 vs push/request), where no shared tie-break
exists.

ROUND 11 (thread 3868979509, P1): the EYES binds the CURRENT
HEAD'S PUSH — eyes_round_state classifies an EYES postdating the
push (strictly; equality is the same round-10 ambiguity) EYES, one
predating-or-equal to it EYES_STALE, and an unreadable push ('')
EYES_UNVERIFIED. NEITHER variant arms the transition latch or
refreshes the observed-activity watermark: the reviewer's race had
head B pushed BEFORE the wait began while head A's review still
showed EYES — the stale EYES armed the latch, and A's completion
+1 (genuinely postdating B's push, passing every round-bound and
watermark check) exited 0 with B reviewed by nobody. A pre-head
EYES is NOT round evidence for the current head, so it must not
counterfeit the transition — unlike THUMBS_UP_STALE, whose +1
(observed stale, later observed done) PROVES a moved round, a
stale EYES proves only that an OLD round was active. The binding
is the HEAD PUSH ONLY, never the marker: a request-less round's
only marker (its bot comments) lands AFTER its own EYES, so a
newer marker is the round's OWN engagement, not a supersession —
the +1 completion keeps the full both-facts binding.

ROUND 13 (threads 3869259813 P1 / 3869453944 P1 / 3869453955 P1):
the EYES's bound set widens by two REQUEST-class facts the push
comparison missed, and the replacement predicate gains ordering.
(1) The FORMAL codex request marker (a ReviewRequestedEvent —
round_bounds returns it SEPARATELY from the composite marker
since round 13): a re-request on an UNCHANGED head leaves the
preceding round's EYES standing, and the preceding job's delayed
+1 postdates the new request — an accepted EYES must now postdate
the request too (strictly; equality carries the round-10
ambiguity). A request PRECEDES its round's EYES by nature, so
request-less rounds keep a '' request that binds nothing — the
round-11 asymmetry stands (post-EYES thread-comment markers NEVER
bind the EYES; they stay composite-only, binding the +1). (2) The
TRANSITION floor (3869453944): a retarget/force-push onto an
already-pushed commit carries a pushedDate PREDATING the old
head's EYES, so the push comparison alone re-classifies the old
EYES current under the new head — after a mid-wait head move the
wait passes its transition OBSERVATION (its own wall clock at the
detection) as transition_floor, and an EYES predating-or-equal to
it reads EYES_STALE (cold-start keeps the pushedDate binding
alone). (3) replaced_plus_one orders the two identities
chronologically (reaction_follows — created_at first, the numeric
REST id on a same-second tie): removing the newer bot +1 must not
let an OLDER +1 masquerade as its replacement (any-different
accepted pre-round-13); only a strictly NEWER +1 satisfies the
replacement path.

ROUND 14 (threads 3869941505 P1 / 3869941509 P2 / 3869941521 P1):
the vocabulary gains REACTION_UNKNOWN (3869941509) — the bot's
latest reaction carrying content REST_CONTENT does not map (rocket,
heart, ...). Rounds 1-13 pinned that shape conservatively to NONE
("never a done signal"); refinements #2 made two persistent NONEs
after a verified EYES the TERMINAL findings exit, so the
conservative pin turned poisonous: an unexpected reaction exited 3
and claimed findings while the bot never removed its EYES and may
still be running. UNKNOWN is DISTINCT: never DONE, never
latch-arming, never the findings transition's NONE, never the
cold-NONE hint's "no reaction" (an unknown reaction proves the bot
REACTED — the cold streak resets on it like on any real reading),
and it breaks NONE persistence exactly as any non-NONE reading does
(a real observation, not a transient). The two wait-side tightenings
(3869941505/3869941521) live in pr_guard_reaction_wait — this
module's vocabulary serves them.

ROUND 17 (threads 3870995905 P1 / 3870995919 P1): the request
high-water consumes boundary IDENTITIES (`createdAt|node id` — the
base64 GraphQL node id; ReviewRequestedEvents carry NO databaseId,
the PullRequestReviewThread precedent), so request_advances joins
the predicate set: an advance fires on a strictly-newer createdAt OR
a same-second DISTINCT node id — distinctness, NOT ordering, because
the base64 id carries no chronology (a same-second re-request whose
id sorts BELOW the standing one is still a new round boundary the
timestamp-only round-15 compare could not see).

ROUND 19 (threads 3871844565 P1 / 3871844576 P2): the identity
compare gains a SET-guarded twin. boundary_advances (3871844576)
overlays the round-17 compare with the wait's per-kind SEEN-SET:
an identity observed by ANY earlier probe never advances again —
a same-second boundary that is deleted and later RESURFACES reads
as the round's CONTINUATION, never a new round boundary (each kind
retains only its latest identity otherwise, and the resurfaced id
is distinct from it), so visibility oscillation can never
counterfeit a re-request. 3871844565's request-advance observation
floor was a WAIT-side stamp (not a latch predicate) and is
SUPERSEDED by round 20 (thread 3872194017): the boundary is the
request/trigger's own createdAt — the reading's round-13
eyes_round_state binding, which this module already owned.

ROUND 20 (thread 3872194007 P2): the seen-sets gained their
FULL-IDENTITY feed — the boundary walks' collect sets deposit every
visible same-second identity at the high-water second (see
pr_guard_reaction_boundaries), so the set remembers siblings the
latest-only stream never returned. boundary_advances itself is
unchanged: an advance still needs an identity NOT in the set
passing the round-17 compare.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round6_test -v
"""

REACTION_DONE = "THUMBS_UP"
REACTION_STALE = "THUMBS_UP_STALE"
# Thread 3868047719 (PR #49 round 6, P1): the +1 whose round bounds
# read failed — a distinct state, never a done signal AND never a
# latch-arming stale (a read failure certifies nothing).
REACTION_UNVERIFIED = "THUMBS_UP_UNVERIFIED"
REACTION_ACTIVE = "EYES"
# Thread 3868979509 (PR #49 round 11, P1): the EYES that predates
# the current head's push (a prior round's leftover activity) and
# the EYES whose head-bound read failed — both distinct from EYES,
# never latch-arming (see eyes_round_state below for why the stale
# EYES, unlike the stale THUMBS_UP, certifies nothing).
REACTION_EYES_STALE = "EYES_STALE"
REACTION_EYES_UNVERIFIED = "EYES_UNVERIFIED"
REACTION_NONE = "NONE"
# Thread 3869941509 (PR #49 round 14, P2): the UNRECOGNIZED-content
# state — the bot's latest reaction exists but REST_CONTENT does not
# map it (rocket, heart, ...). Distinct from NONE (which since
# refinements #2 feeds the terminal findings exit and the cold-NONE
# hint): UNKNOWN is never DONE, never latch-arming, never satisfies
# the findings transition, and never counts as "no reaction" for the
# hint — the bot demonstrably reacted with SOMETHING the tool cannot
# interpret, so the reading renders its content and keeps polling.
REACTION_UNKNOWN = "UNKNOWN"

# User-taught refinements #2 (vault note section of that name,
# 2026-08-27): every EYES-shaped state — the verified EYES and its
# stale/unverified variants — in one set, so the wait's cold-NONE
# hint can ask "was ANY EYES ever observed" (any variant proves the
# bot started, so a later NONE is never a failed-start symptom).
EYES_VARIANTS = frozenset(
    {REACTION_ACTIVE, REACTION_EYES_STALE, REACTION_EYES_UNVERIFIED}
)

REACTION_MEANINGS = {
    REACTION_DONE: "review complete, nothing further",
    REACTION_ACTIVE: "review actively in progress — poll the reaction, not the threads",
    # User-taught refinements #2 (vault note section): the bot
    # REMOVES its EYES at round end — +1 when it passed, NOTHING when
    # it found feedback — so NONE after a seen EYES means findings,
    # while a cold NONE may mean the bot never started ('@codex
    # review' triggers it) or the signal is stale. One line.
    REACTION_NONE: (
        "review not active — either done WITH findings (if EYES "
        "was seen before: survey the threads), not started (bot "
        "may have failed — '@codex review' can trigger it), or "
        "stale"
    ),
}

# Threads 3867503712 + 3867653639 (PR #49, P1): how a VERIFIED
# stale-round pass renders — surfaced as THUMBS_UP with the
# explanation, never a done state the waiter could exit 0 on. Round 3
# widened the stale facts: the pass predates the round's HEAD PUSH or
# its REVIEW REQUEST/marker.
STALE_RENDER = (
    "THUMBS_UP (stale — predates the current round's start (head "
    "push or review request); waiting for the new round's signal)"
)

# Thread 3868047719 (PR #49 round 6, P1): how a bounds-failure +1
# renders — its own explanation, never the stale render (the two
# states carry different evidence: a verified fact vs a read
# failure).
UNVERIFIED_RENDER = (
    "THUMBS_UP (unverified — the round-start read failed, so the "
    "+1's round could not be checked; not round evidence, the poll "
    "continues)"
)

# Thread 3868979509 (PR #49 round 11, P1): how the pre-head EYES
# renders — its own explanation beside the +1's stale render,
# because its evidence is a round-boundary fact (a prior round's
# leftover activity under a newer round boundary) and it arms
# nothing. Round 13 (threads 3869259813/3869453944): the boundary
# widened past the head push to the codex re-request and the
# observed mid-wait head transition — the render names the boundary
# CLASS, not just the push. Round 19 (thread 3871844565) briefly
# listed the request-advance observation transition; round 20
# (thread 3872194017) SUPERSEDED that floor with the boundary
# event's own createdAt (the reading's round-13 binding), so the
# list names the surviving boundaries.
EYES_STALE_RENDER = (
    "EYES (stale — predates the current round's boundary (head "
    "push, codex re-request, or an observed head-move transition); "
    "a prior round's leftover activity, so it arms nothing — the "
    "poll waits for the new round's signal)"
)

# Thread 3868979509 (round 11, P1): how the unprovable EYES
# renders — the head-bound read failed, so the EYES's round cannot
# be checked; not round evidence, the poll continues.
EYES_UNVERIFIED_RENDER = (
    "EYES (unverified — the head-bound read failed, so the EYES's "
    "round could not be checked; not round evidence, the poll "
    "continues)"
)

# Thread 3868047719: the latch's arming set — the VERIFIED non-DONE
# states only. THUMBS_UP_UNVERIFIED and the wait loop's UNREADABLE
# stay out: an error must not arm the transition an initial-+1 wait
# exits 0 on. Thread 3868979509 (round 11, P1): the EYES variants
# stay out TOO — a pre-head EYES is a PRIOR round's leftover (it
# proves an old round was active, not that the current round moved),
# and an unprovable EYES is a read failure; neither may counterfeit
# the transition (see the module docstring's round-11 section).
# Thread 3869941509 (round 14, P2): UNKNOWN stays out as well — an
# uninterpretable reaction is not round evidence in ANY direction
# (not done, not a moved round, not an absence), so it arms nothing.
LATCH_ARMING_STATES = frozenset(
    {REACTION_ACTIVE, REACTION_NONE, REACTION_STALE}
)


def render_state(state: str, content: str = "") -> str:
    """One render home for the banner and wait-loop state lines."""
    if state == REACTION_STALE:
        return STALE_RENDER
    if state == REACTION_UNVERIFIED:
        return UNVERIFIED_RENDER
    if state == REACTION_EYES_STALE:
        return EYES_STALE_RENDER
    if state == REACTION_EYES_UNVERIFIED:
        return EYES_UNVERIFIED_RENDER
    if state == REACTION_UNKNOWN:
        # Thread 3869941509 (round 14, P2): its OWN line — the
        # unrecognized content and the report-if-persist warning,
        # never NONE's findings/not-started/stale meanings.
        shown = f" '{content}'" if content else ""
        return (
            f"UNKNOWN (unrecognized reaction content{shown} — "
            f"report if this persists)"
        )
    if state in REACTION_MEANINGS:
        return f"{state} ({REACTION_MEANINGS[state]})"
    return f"{state} (reaction unreadable — the poll continues)"


def thumbs_up_round_state(created: str, pushed: str, requested: str) -> str:
    """Classify a +1 against the round's start facts (round_bounds).

    DONE only when created STRICTLY postdates BOTH facts (thread
    3868782042, round 10, P1: a created_at EQUAL to a round fact's
    timestamp is AMBIGUOUS — same-second API writes carry no
    provable order, so equality reads STALE, never done).
    STALE when a READABLE fact certifies it predates the round —
    or fails to order it AFTER the round (equality included).
    UNVERIFIED when the bounds are unreadable ('' pushed — a failed
    round_bounds probe): never done, never stale, never
    latch-arming (thread 3868047719).
    """
    if not pushed:
        return REACTION_UNVERIFIED
    # Thread 3868782042 (round 10, P1): `<=`, not `<` — the strictly-
    # greater requirement. A +1 created in the same second as the
    # push or the marker cannot be proven to postdate it, so the
    # ambiguous second reads STALE (conservative, never done); only
    # a strictly-greater created_at classifies DONE.
    if created <= pushed or (requested and created <= requested):
        return REACTION_STALE
    return REACTION_DONE


def arms_transition_latch(state: str) -> bool:
    """True only for VERIFIED non-DONE readings (thread 3868047719)."""
    return state in LATCH_ARMING_STATES


# Thread 3868979509 (PR #49 round 11, P1): classify an EYES against
# the CURRENT HEAD'S PUSH — the arming watermark only counts when
# the observed EYES postdates the head the probe certified (the
# same strict-comparison rules as the +1's round facts: equality is
# the round-10 ambiguity, so only a STRICTLY-greater created_at is
# ACTIVE). The marker deliberately does NOT bind here: a
# request-less round's only marker (its bot comments) lands AFTER
# its own EYES, so a newer marker is the round's OWN engagement —
# the +1, the round's END, keeps the full both-facts binding in
# thumbs_up_round_state above.
# Thread 3869259813 (round 13, P1): the FORMAL codex request
# (round_bounds' separate third element) DOES bind — a request
# PRECEDES its round's EYES by nature (unlike the round's own
# comments/submissions), so requiring the EYES to postdate it
# closes the re-request-on-unchanged-head hole while request-less
# rounds ('' request) keep binding nothing. Thread 3869453944
# (round 13, P1): transition_floor is the wait's transition
# OBSERVATION wall clock after a mid-wait head move — a retarget
# onto an already-pushed commit carries a pushedDate predating the
# old head's EYES, so post-transition the OBSERVATION (never the
# commit's own timestamp) is the safe bound; '' (cold start) binds
# nothing and keeps the pushedDate binding.
def eyes_round_state(
    created: str, pushed: str, requested: str = "", transition_floor: str = ""
) -> str:
    """EYES | EYES_STALE | EYES_UNVERIFIED against the round bounds.

    EYES_STALE: the EYES predates (or shares a second with) the
    head push, the formal codex request, or the observed head
    transition — a prior round's leftover under a newer round
    boundary; it never arms the transition latch (a stale
    THUMBS_UP PROVES a moved round — stale then done is the
    transition the wait exits 0 on — but a stale EYES proves only
    that an old round was active, and the old round's late
    completion +1 genuinely postdates the new boundary's
    timestamps).
    EYES_UNVERIFIED: the head-bound read failed ('' push) — a read
    failure is not round evidence (round 6's rule), so the EYES
    cannot be proven post-head and arms nothing.
    """
    if not pushed:
        return REACTION_EYES_UNVERIFIED
    if created <= pushed:
        return REACTION_EYES_STALE
    if requested and created <= requested:
        return REACTION_EYES_STALE
    if transition_floor and created <= transition_floor:
        return REACTION_EYES_STALE
    return REACTION_ACTIVE


# Thread 3868158293 (PR #49 round 7, P2): the +1 OBJECT's identity —
# created_at|id. The REST reaction object carries both; the pair
# distinguishes a genuinely NEW +1 from the initial-held one even
# when a same-second flip leaves created_at equal (the id still
# moved), which created_at alone cannot.
def plus_one_identity(node: dict) -> str:
    return f"{node.get('created_at') or ''}|{node.get('id') or ''}"


# Thread 3868158293: the OBSERVED-NEW predicate — True only when a
# captured baseline identity exists AND the current reading carries
# a DIFFERENT one: the wait watched the +1 be REPLACED. No baseline
# ('' — the first unarmable DONE reading captures it) or an empty
# current identity never accepts; an UNCHANGED identity keeps
# holding (the round-5 conservative core). Thread 3869453955
# (round 13, P1): different is no longer enough — the candidate
# must be strictly NEWER (reaction_follows' chronological
# ordering: created_at first, the numeric REST id on a same-second
# tie), so removing the newer bot +1 cannot let an OLDER +1
# masquerade as a replacement and exit the wait with no new review
# activity.
def replaced_plus_one(held: str, current: str) -> bool:
    return bool(held) and bool(current) and reaction_follows(current, held)


# Thread 3868443452 (PR #49 round 8, P1): the head-change predicate
# — True only when BOTH oids are readable AND differ. A mid-wait
# head move re-binds every round-bounds date comparison, so the
# wait resets its transition latch/baseline on a change; an
# UNREADABLE oid ('' — a failed or malformed round probe) certifies
# nothing in either direction (a read failure must not counterfeit
# the reset), mirroring replaced_plus_one's refusal to act on an
# empty identity.
def head_changed(observed: str, current: str) -> bool:
    return bool(observed) and bool(current) and current != observed


# Thread 3870995905 (PR #49 round 17, P1): the request-boundary
# ADVANCE predicate — True when a candidate boundary identity
# (`createdAt|node id`, the boundary walk's return shape) is a NEW
# round boundary relative to the retained high-water. Strictly-newer
# createdAt always advances; an EQUAL createdAt advances only on a
# DISTINCT node id (two Codex requests inside one timestamp second
# are different events even though their stamps compare equal) —
# distinctness, not ordering: the base64 GraphQL node id is stable
# and globally unique but carries NO chronology, so the
# lexicographically-smaller same-second id must still fire. '' never
# advances (an unreadable probe's boundary contribution is not bot
# activity), and any first boundary against '' does (the
# baseline-on-first-observation rule lives in the wait's
# readable_probe_seen instead).
def request_advances(candidate: str, high_water: str) -> bool:
    if not candidate:
        return False
    if not high_water:
        return True
    cand_at, _, cand_id = candidate.partition("|")
    mark_at, _, mark_id = high_water.partition("|")
    if cand_at != mark_at:
        return cand_at > mark_at
    return cand_id != mark_id


# Thread 3871844576 (PR #49 round 19, P2): the SET-guarded advance
# — True only when the candidate is an identity NO earlier probe of
# this kind observed AND the round-17 identity compare itself
# advances. The wait's per-kind retention held only the LATEST
# identity, so a same-second boundary deleted and later RESURFACED
# (a different node id than the retained one) counterfeit a new
# forward boundary through the distinctness tie-break and
# spuriously reset a running round; the seen-set remembers EVERY
# identity the walk ever returned, and a resurfacing is the round's
# CONTINUATION, never a new boundary. An empty seen-set keeps the
# baseline rule where it lives (the wait's readable_probe_seen).
def boundary_advances(candidate: str, high_water: str, seen) -> bool:
    if not candidate or candidate in seen:
        return False
    return request_advances(candidate, high_water)


# Thread 3868625463 (PR #49 round 9, P1): the marker HIGH-WATER —
# the maximum round marker RETAINED across probes. A request-less
# round's only marker (a bot thread comment) is EVICTED from the
# bounded comments(last:3)/reviewThreads(last:10) windows by three
# later comments, and the probe faithfully reports the emptied ('')
# window — but the wait never lets the EFFECTIVE marker go
# backwards: once a marker is observed it binds for the rest of the
# wait ('' sorts lowest, so max() is chronological AND
# eviction-proof).
def effective_round_marker(retained: str, observed: str) -> str:
    return max(retained, observed)


# Thread 3868625469 (PR #49 round 9, P1): the OBSERVED-ACTIVITY
# watermark — True only when the candidate identity POSTDATES the
# watermark identity (created_at first; the numeric id breaks a
# same-second tie — REST ids increase). The prior round's +1 beside
# a newer EYES arms the latch, but when the EYES is removed before a
# replacement +1 is visible the OLD +1 becomes latest again — an
# accepted +1 that does not FOLLOW that observed activity is not
# this round's completion. An empty watermark binds nothing (nothing
# observed armed); an empty or IDENTICAL candidate never follows
# (unprovable, or the very object the watermark names).
def reaction_follows(candidate: str, watermark: str) -> bool:
    if not watermark:
        return True
    if not candidate or candidate == watermark:
        return False
    cand_at, _, cand_id = candidate.partition("|")
    mark_at, _, mark_id = watermark.partition("|")
    if cand_at != mark_at:
        return cand_at > mark_at
    return _numeric_id(cand_id) > _numeric_id(mark_id)


def _numeric_id(raw: str) -> int:
    return int(raw) if raw.isdigit() else -1
