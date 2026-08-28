"""The codex review-bot PR-reaction signal for pr_guard.

SIGNAL SOURCE (user-taught 2026-08-26, verified live via the API on
PR #48 — vault note 'Unified Realms/Notes/Codex Review Bot Reaction
Signal.md'): the review bot chatgpt-codex-connector[bot] reacts ON
THE PR ITSELF to signal review state — THUMBS_UP = review COMPLETE,
nothing further found (the PR passed); EYES = review ACTIVELY in
progress (do not poll threads yet); no reaction = not started, or a
stale/previous round. The reaction is the DONE/ACTIVE signal: it
replaces the orchestrator's blind `sleep N` + survey cycles with a
cheap single-endpoint poll (REST issues/{n}/reactions filtered to
the bot login).

PROTOCOL BOUNDARY: the reaction NEVER authorizes a merge by itself —
thread state (survey/pre-merge) remains the merge authority, and the
post-merge quiet-period watch still guards the landed tree (the
reaction says the bot is done, not that the merged tree is safe).

Split-first at birth (the PR #36 round-2 family rule, 250 pure-LOC
ceiling): the reaction read, the survey banner, and the wait-mode
poll loop live here rather than growing pr_guard_threads.py or the
CLI. Imports flow ONE way (threads/pr_guard -> reaction -> common);
nothing here imports threads, merge, or the CLI.

PR #49 follow-ups: gh_reactions paginates (thread 3867503705), every
wait probe is deadline-bounded (thread 3867503708), and a THUMBS_UP
that predates the current head's push reads THUMBS_UP_STALE — never
done (thread 3867503712, P1). Round 2 (thread 3867572256, P2): every
probe's subprocess timeout is the ACTUAL remaining window —
recomputed for EACH subprocess (every reactions page, the head-date
read), capped at two poll intervals, floored at 1s so the
at-deadline final probe still reads — never a fixed 10s grant past
the deadline, so the wait never blocks past deadline+interval.
Round 3 (threads 3867653639 P1/3867653642 P2): completion is bound
to the ACTUAL requested round — a THUMBS_UP must postdate the head
push AND the latest round-engagement marker (the timeline
ReviewRequestedEvent's createdAt — a re-request with NO head change —
beside the bot's latest SUBMITTED review; this repo's rounds engage
without formal requests, live-verified) — and the survey banner's
informational read is bounded by BANNER_TIMEOUT_SECS, so a stalled
banner read fails open instead of hanging the gate.
Round 4 (threads 3867757439 P1/3867757442 P2): the marker set gains
the bot's latest review-THREAD comment (live-verified 2026-08-27 on
PR #49: the round's findings land as bot-authored thread comments,
rendered with the suffix-less GraphQL login) — a request-less round
that has begun posting marks itself the moment its first comment
lands, so the prior round's +1 reads STALE mid-round — and only
ReviewRequestedEvents whose requestedReviewer IS the codex bot bind
(a human/other-bot request after the +1 no longer extends the round
into a stale-forever wait). Thread 3867757445 (P2): gh_reactions
STOPS walking once the shared deadline expires — the exhausted
remainder never feeds through the 1s floor for a fresh per-page
grant. Round 5 (threads 3867897764 P2/3867897766 P1): the stopped
walk now RAISES ReactionWalkExpired — the partial page list is
UNREADABLE (the banner fails open, the wait keeps polling), never a
latest-wins input that could crown an older page-1 +1 while a newer
eyes sits on an unread page; and a THUMBS_UP already present at
WAIT START is no longer accepted on sight — the asynchronous round
may not have posted anything yet (no marker exists to stale the old
pass), so exit 0 waits for the wait itself to OBSERVE one confirmed
non-DONE reading (a fresh EYES, a marker-driven stale, a none)
between start and the accepted +1, else times out with that
explanation. Round 6 (threads 3868047715 P2/3868047719 P1): the
reaction-state vocabulary, the stale/unverified classification, and
the transition latch moved to the sibling pr_guard_reaction_latch
(the 250 pure-LOC ceiling; imports one way — reaction FROM latch),
and unreadable round bounds no longer read THUMBS_UP_STALE — a
bounds-failure +1 is THUMBS_UP_UNVERIFIED, a distinct state that
never arms the transition latch (only VERIFIED non-DONE states arm;
an error-armed latch let the recovered-bounds prior +1 exit 0).
Round 7 (threads 3868158293 P2/3868158297 P1/3868158304 P2): the
timing discipline and the round-bounds probe (its request-event
timeline now a PAGINATED latest-50 window with backwards
before:$cursor pages read BEFORE the codex filter — the old last:5
let GitHub's server-side truncation evict a current codex request
behind five later unrelated ones) moved to the sibling
pr_guard_reaction_probe (the ceiling again; imports one way —
reaction FROM probe), and the wait's initial-+1 hold gains the
OBSERVED-NEW acceptance: the +1's identity (created_at|id) is
compared across probes, so a fast round that goes EYES->+1
ENTIRELY between two probes still completes the wait when a
DIFFERENT (newer) +1 object postdating the round bounds replaces
the initial-held one — the transient EYES never has to be sampled
(thread 3868158293).
Round 8 (thread 3868443452, P1): the wait tracks the observed
headRefOid — round_bounds now PRESERVES it head-first beside the
dates it always returned, and every probe reads it (not only +1
probes): when the head MOVES mid-wait (e.g. the ref retargets onto
an already-pushed commit whose pushedDate predates the standing
+1), an earlier probe may have classified that same reaction STALE
against the OLD head's bounds — arming the transition latch — while
the next probe reclassifies the UNCHANGED reaction DONE against the
NEW head's older bounds. The wait RESETS the latch and the
+1-identity baseline the moment the oid changes, so completion
requires a fresh POST-head-change transition (a new EYES arming, or
a demonstrably replaced +1); an unreadable oid never certifies a
change. Round 9 (threads 3868625463 P1/3868625469 P1): the wait
retains a MONOTONE marker high-water — a request-less round's only
marker (a bot comment) is evicted from the bounded
comments(last:3)/reviewThreads(last:10) windows by later comments,
so the probe that SAW it armed the latch on the prior +1's
staleness while a later probe (marker evicted) would reclassify
the same unchanged +1 current and exit 0; the effective marker
never goes backwards (bot_reaction_reading classifies against
marker_floor, and the reading returns the effective marker fourth).
And completion follows the OBSERVED EYES: the reading's identity
now rides EVERY state (not only DONE), each latch-arming probe
refreshes the observed-activity watermark to its latest reaction's
identity, and BOTH DONE exits (the transition latch and the
observed-replacement) require the accepted +1's identity to
POSTDATE that watermark — the prior round's +1 re-surfaced when a
non-atomic reaction switch removed the newer EYES is not this
round's completion.
Round 10 (threads 3868782039 P1/3868782042 P1): the head STABILITY
bracket — bot_reaction_reading reads the head oid FIRST (the new
head_ref_oid in the probe module), then the reactions, then the
round bounds, and a head that MOVED between the reads discards the
WHOLE probe (ReactionHeadMoved → UNREADABLE, retry next interval):
a single probe used to pair an EYES for head A with head B's OID,
so the wait treated the change as handled, reset the latch, and
immediately re-armed it from the pre-change EYES — a completion
for A that arrived after B was pushed then satisfied B's timestamp
bounds and exited 0 without B being reviewed; an unreadable side
('') certifies nothing and never discards. And equal-second round
facts are AMBIGUOUS: thumbs_up_round_state's comparisons became
`<=` (only STRICTLY-greater created_at is DONE; equality reads
THUMBS_UP_STALE), so a prior-round +1 landing in the same second
as a head push or re-request can no longer ride an armed latch to
exit 0 — order is unknowable, so it reads stale (conservative).
Round 11 (threads 3868979509 P1/3868979515 P2): the EYES binds to
the CURRENT head's push — an EYES predating the head bound is a
PRIOR round's leftover (head B pushed before the wait began while
head A's review still showed EYES) and classifies EYES_STALE /
EYES_UNVERIFIED, latch-arming NEVER (so A's late completion +1 —
genuinely postdating B's timestamps, passing every round-bound
check — cannot ride a stale-EYES-armed latch out of the wait); the
classification lives in the latch module (eyes_round_state) and
binds the head push ONLY (not the marker: a request-less round's
comments land AFTER its own EYES, so a newer marker is the round's
OWN engagement, not a supersession). And every probe reads under
ONE SHARED budget — the head-only read, the reactions walk, and
the round probe all consume the START-of-probe deadline (the walk
receives the raw remaining and its own ≤0 guard stops the probe
UNREADABLE, thread 3868979515), never a fresh grant per stage. The
banner moved to the sibling pr_guard_reaction_banner at this round
(the ceiling again; imports one way — banner FROM reaction).

USER-TAUGHT REFINEMENTS #2 (2026-08-27; vault note 'Unified
Realms/Notes/Codex Review Bot Reaction Signal.md', SECTION 'User-
taught refinements #2'): the bot REMOVES its EYES when a round
finishes — it posts +1 (THUMBS_UP) when the round passed and leaves
NO reaction (NONE) when it found feedback. wait_reaction therefore
gains TWO None-discriminating behaviors. (1) EYES -> NONE = the
review completed WITH FINDINGS: a transition from a LATCH-ARMING
(current-head-verified, round 11) EYES to NONE exits the NEW code 3
with the WAIT FINDINGS line (survey the threads now — fix + receipt
+ re-wait); only a VERIFIED-current EYES arms it (EYES_STALE/
EYES_UNVERIFIED are an old round's eyes disappearing, never a
findings signal) and the findings transition resets with the latch
on a head move (a certification, round 8). The NONE must PERSIST
across one confirming probe — the bot's remove-EYES-then-post-+1 is
a NON-ATOMIC switch (the round-9 thread-3868625469 precedent: the
EYES removal lands before the replacement +1 is visible), so a lone
NONE that flips back to EYES or +1 keeps polling (the round-5
initial-+1 discipline's conservative direction). (2) A COLD NONE —
no EYES variant EVER observed and >= COLD_NONE_GRACE_SECS of
continuous NONE — prints the '@codex review' trigger HINT exactly
once (the bot may have failed to start; a HINT only, the
orchestrator decides whether to post) and keeps polling to timeout
as before. Exit codes now: 0 passed, 1 timeout, 2 usage, 3
findings. At the ceiling again (237 pure LOC + the new wait logic):
the paginated reactions walk (gh_reactions + ReactionWalkExpired)
moved to the sibling pr_guard_reaction_probe (the API-read layer's
pagination home; re-exported below so every patch seam keeps ONE
home — the round-7 re-export precedent).

PR #49 ROUND 13 (threads 3869259808/3869259813/3869453944/
3869453955 P1 + 3869453959 P2): four wait-safety tightenings and
a hint reset. (1) The head STABILITY bracket (round 10) rejects
EITHER EMPTY endpoint — a failed head_ref_oid read or a failed
round probe raises ReactionBracketUnreadable out of the reading:
the whole probe is UNREADABLE (retry next interval), never a
certified mixed snapshot an EYES from a moved head could arm under
the new head's bounds; the round-6/7 empty-bounds UNVERIFIED
reads are superseded (THUMBS_UP_UNVERIFIED survives for the
readable-oid/null-dates shape). (2) The accepted EYES binds the
FORMAL codex request (round_bounds grew a separate request element
beside the composite marker — 4-tuple): a re-request on an
UNCHANGED head stales the preceding round's EYES, so the preceding
job's delayed +1 (postdating the request) cannot ride it; post-EYES
thread-comment markers NEVER bind the EYES (round 11's asymmetry —
a request-less round's only marker lands after its own EYES). (3)
Post-transition the EYES binds the transition OBSERVATION — the
wait's own wall clock stamped at the head-move detection (passed
into later readings as transition_floor, and applied to the
transition probe's own reading by an explicit demotion to
EYES_STALE since that reading classified one step before the floor
existed): a retarget onto an already-pushed commit carries a
pushedDate predating the old head's EYES, so the commit's own
timestamp certifies nothing; the demoted probe also seeds NO held
baseline, so the old round's delayed +1 replaces nothing.
Cold-start keeps the pushedDate binding. (4) replaced_plus_one
orders the identities (reaction_follows): only a strictly NEWER
+1 satisfies the replacement path — removing the newer bot +1
must not let an OLDER one masquerade as a replacement. (5) The
head-move reset clears the cold-NONE detector (saw_any_eyes and
the hint state) with the latch: head A's EYES must not suppress
head B's '@codex review' hint when codex never starts for B.
The round-13 additions pushed reaction.py past the 250 pure-LOC
ceiling: the WAIT LOOP (wait_reaction + wall_iso_z +
COLD_NONE_GRACE_SECS) split to the sibling pr_guard_reaction_wait,
which calls time/the reading THROUGH this namespace (the round-11
banner rule) so every patch seam keeps ONE home; wait_reaction is
re-exported below for pr_guard.py.
PR #49 ROUND 14 (threads 3869941505 P1 / 3869941509 P2 /
3869941521 P1): the REST_CONTENT conservative pin is REPINNED — an
unrecognized latest content (rocket, heart, ...) reads the DISTINCT
REACTION_UNKNOWN (never NONE: refinements #2 made persistent NONE
the terminal findings exit, and an unexpected reaction must not
claim findings while the bot may still be running), the raw content
rides the reading's new DETAIL half (fifth element) so the wait's
state lines render WHAT was unrecognized, and the two wait-side
tightenings (the transition-NONE arming gate of 3869941505 and the
resurfaced-prior-+1 findings confirmation of 3869941521) live in
pr_guard_reaction_wait — see its docstring.

PR #49 ROUND 15 (threads 3870293188 P1 / 3870293194 P1 /
3870293197 P1 / 3870293205 P1): the reading threads round-13's
FORMAL REQUEST element through as its SIXTH return element (raw,
never floored — the request walk paginates the full history) so the
wait can retain a request-marker high-water beside the composite
one (3870293188); the probe's head bound MAXes the commit stamps
with the latest head-ref FORCE-PUSH event (the cold-start
transition bound, 3870293194); and the probe rejects top-level
GraphQL errors and null/malformed connections as UNREADABLE
(3870293197). The two wait-side tightenings (the request-advance
latch reset and the cold-NONE arming gate initializing True at wait
start, 3870293205) live in pr_guard_reaction_wait — see its
docstring's round-15 section. The REST reactions walk (gh_reactions
+ ReactionWalkExpired) moved probe -> pr_guard_reaction_walk at the
same ceiling (254 pure) — re-exported below unchanged.

PR #49 ROUND 17 (threads 3870995905 P1 / 3870995911 P1 /
3870995919 P1): the reading's SIXTH element is now the merged
request/trigger boundary IDENTITY `createdAt|node id` (round_bounds
merges the formal codex request with the documented '@codex review'
top-level-comment trigger, 3870995911 — one boundary stream feeding
the wait's high-water), the EYES request binding partitions the
createdAt half out of it before classifying, and latest_review_commit
(the head-bound evidence read, 3870995919) is re-exported for the
wait's post-move completion check — the boundary walks and the
timing/bot-vocabulary homes moved to the NEW sibling
pr_guard_reaction_boundaries (re-exported through the probe module;
every patch seam keeps ONE home). request_advances (the identity
advance predicate, 3870995905) joined the latch re-exports. The
wait-side rules live in pr_guard_reaction_wait's round-17 section.
"""

# Round 13: subprocess stays imported for the SEAM alone — tests
# patch pr_guard_reaction.subprocess.run for the gh_reactions walk
# that lives in the probe module (the one-home rule).
import subprocess
import time

from .pr_guard_common import deadline_clamped_sleep
# Round 6 (thread 3868047719, P1): the state vocabulary, renders,
# the stale/unverified classification, and the latch arming set live
# in the sibling latch module — one-way imports (reaction FROM
# latch; the latch imports nothing back).
from .pr_guard_reaction_latch import (
    EYES_VARIANTS,
    REACTION_ACTIVE,
    REACTION_DONE,
    REACTION_EYES_STALE,
    REACTION_NONE,
    REACTION_STALE,
    REACTION_UNKNOWN,
    arms_transition_latch,
    boundary_advances,
    effective_round_marker,
    eyes_round_state,
    head_changed,
    plus_one_identity,
    reaction_follows,
    render_state,
    replaced_plus_one,
    request_advances,
    thumbs_up_round_state,
)
# Round 7 (thread 3868158304, P2): the timing discipline and the
# round-bounds probe (with its paginated request-event walk) live in
# the sibling probe module — one-way imports (reaction FROM probe;
# the probe imports nothing back). The names re-exported here keep
# every existing seam (tests patch pr_guard_reaction.round_bounds;
# pr_guard.py imports the wait constants) pointed at one home.
# User-taught refinements #2: the reactions walk (gh_reactions +
# ReactionWalkExpired) joined the probe module at the 250 pure-LOC
# ceiling — same one-way rule, same single seam home. PR #49 round
# 15: the walk moved AGAIN, probe -> the sibling
# pr_guard_reaction_walk (the probe hit the ceiling at 254 growing
# round 15's GraphQL hygiene); the re-export below is unchanged, so
# the seams still keep ONE home.
from .pr_guard_reaction_probe import (
    DEFAULT_WAIT_TIMEOUT_SECS,
    REACTION_BOT,
    WAIT_INTERVAL_SECS,
    ReactionBracketUnreadable, ReactionHeadMoved,
    head_ref_oid,
    latest_review_commit,
    probe_timeout_budget,
    round_bounds,
)
from .pr_guard_reaction_walk import ReactionWalkExpired, gh_reactions

REST_CONTENT = {"+1": REACTION_DONE, "eyes": REACTION_ACTIVE}

VAULT_NOTE = "the design-history note in the source repository"

# User-taught refinements #2: ReactionWalkExpired + gh_reactions
# MOVED to pr_guard_reaction_probe (the 250 pure-LOC ceiling; the
# re-export above keeps this module's name the ONE patch seam).


# Threads 3872194007/23 (PR #49 round 20): the reading's return
# shape — the round-18 eight AS A TUPLE SUBCLASS (the RoundBounds
# zero-repin seam rule applied to the reading's own return):
# equality/indexing/unpacking stay byte-identical for every legacy
# plain-tuple mock, while the round-20 evidence (the per-kind
# same-second identity sets + the folded review's verdict stamp)
# rides as attributes the wait reads through getattr (class-default
# None = the legacy fallback).
# Thread 3874405295 (round 26): the head's OWN bound joins
# the attrs — the max(pushedDate, committedDate, headTransition
# event createdAt) the classification consumes (plain bounds[1]), so
# the wait's transition floor stamps the HEAD's bound, never the
# wait's observation wall clock.
# Thread 3874769245 (round 27, P1): the BASE identity twin —
# .base (baseRefOid) + .base_bound (the base's own boundary
# timestamp: max(base target stamps, BaseRefChangedEvent createdAt)),
# the wait's base-change reset family and base_floor key on them.
# Thread 3875623447 (round 30, P1): the EVENT portion of the base
# bound rides beside them — .base_event_bound ('' when no
# baseChange/baseForce stamp contributed, the FF-advance class) keys
# the wait's observation fallback in pr_guard_reaction_wait.
class Reading(tuple):
    """(state, identity, head_oid, marker, detail, request, trigger,
    review_head) + .request_ids/.trigger_ids/.review_stamp (round 20)
    + .head_bound (round 26) + .base/.base_bound (round 27)
    + .base_event_bound (round 30, thread 3875623447)."""

    request_ids = None
    trigger_ids = None
    review_stamp = None
    head_bound = None
    base = None
    base_bound = None
    base_event_bound = None


def bot_reaction_reading(
    pr: int,
    timeout_secs: float | None = None,
    marker_floor: str = "",
    transition_floor: str = "",
) -> tuple[str, str, str, str, str, str]:
    """The bot's latest reaction AS (state, identity, head oid, marker,
    detail, request, trigger, review_head) — the round-18 eight (the
    trigger identity and the folded review evidence ride seventh and
    eighth; a legacy plain-tuple bounds seam degrades them to '' —
    see the getattr block below).

    The state half: THUMBS_UP | THUMBS_UP_STALE |
    THUMBS_UP_UNVERIFIED | EYES | NONE | UNKNOWN (see the latch
    module; thread 3869941509, round 14: the unrecognized-content
    shape renders through the detail half below).

    transition_floor (thread 3869453944, round 13, P1): the wait's
    transition OBSERVATION wall clock after a mid-wait head move —
    an EYES must postdate it to read EYES ('' on a cold start binds
    nothing; see eyes_round_state).

    Vault note (2026-08-26, PR #48): the bot may hold MORE than one
    reaction on the PR (a stale THUMBS_UP from a prior round beside a
    fresh EYES), so the LATEST is the authoritative one — max over
    (created_at, index); REST lists ascending, so the higher index
    breaks a same-second tie. An UNKNOWN latest content (heart,
    rocket, ...) reads REACTION_UNKNOWN (thread 3869941509, round 14,
    P2 — the rounds-1-13 conservative-to-NONE pin is REPINNED): never
    a done signal, and never NONE either — refinements #2 made two
    persistent NONEs after a verified EYES the terminal findings
    exit, so an unrecognized reaction must not counterfeit that
    transition (see the latch module's round-14 section).

    Thread 3867503712 (PR #49, P1): after a new commit (or a newly
    requested round), the prior round's THUMBS_UP stays the bot's
    latest reaction until the new EYES lands — so a THUMBS_UP only
    counts as DONE when its created_at POSTDATES the current head's
    push. Thread 3867653639 (round 3, P1) + 3867757439 (round 4, P1):
    the head date alone still cannot bind the round — a re-requested
    review with NO head change leaves the prior +1 postdating the
    push — so DONE requires the +1 to postdate BOTH round-start facts
    (round_bounds): the head push AND the latest round-engagement
    marker (the newest CODEX-requested ReviewRequestedEvent — the
    formal re-request, reviewer-filtered per thread 3867757442 and,
    since round 7, read through the paginated window of thread
    3868158304 — the bot's latest submitted review, or the bot's
    latest review-thread comment, the marker a request-less round
    leaves the moment it begins posting). One that predates a
    READABLE fact reads THUMBS_UP_STALE: not done, keep polling for
    the new round's EYES->THUMBS_UP; never done-on-ambiguity. Thread
    3868047719 (round 6, P1): a +1 whose bounds are UNREADABLE
    (round_bounds failing) reads THUMBS_UP_UNVERIFIED via the
    null-dates shape — not done EITHER, but not a verified stale: a
    read failure is not round evidence, so the wait's transition
    latch never arms on it (see thumbs_up_round_state in the latch
    module).

    The identity half (thread 3868158293, round 7, P2):
    plus_one_identity of the +1 OBJECT the state classifies —
    created_at|id, '' when the latest reaction is no +1 — so the
    wait can compare it ACROSS probes: a fast round that goes
    EYES->+1 entirely between two probes leaves both observed
    states THUMBS_UP, and only the CHANGED identity proves the
    second +1 is a different (newer) object, a fresh completion the
    wait watched happen. The marker-staleness rules still apply to
    it (the state half already bound it to the round bounds).

    The head half (thread 3868443452, round 8, P1): the headRefOid
    the round probe read BESIDE its dates — '' when the probe
    failed — so the wait can tell that two probes classified the
    SAME +1 against DIFFERENT heads. The round probe rides EVERY
    reading (EYES and NONE included, not only +1 probes): the wait
    must observe the head each probe to catch a mid-wait move the
    instant it lands, and an EYES probe under the NEW head is the
    fresh post-change arming a head-flip wait needs.

    Round 9 (thread 3868625463, P1): marker_floor is the wait's
    RETAINED marker high-water — the classification runs against
    max(marker_floor, the probe's own marker) and the reading
    returns that EFFECTIVE marker fourth, so a bounded-window
    eviction (the marker reading '' on a later probe) can never let
    the effective marker go backwards. Round 9 (thread 3868625469,
    P1): the identity half rides EVERY state — the EYES object's
    identity included ('' only when no bot reaction exists) — so
    the wait's observed-activity watermark can order an accepted
    +1 against the activity it actually SAW.

    Thread 3867572256 (PR #49 round 2, P2): the round probe's budget
    is the REMAINING window AFTER pagination — recomputed against the
    probe deadline, never the same fresh grant the pages already
    spent.

    Dies (exit 2) on a failed/malformed reactions read, and
    propagates ReactionWalkExpired when the walk's deadline expires
    mid-pagination (thread 3867897764) — see gh_reactions: the
    caller's UNREADABLE arm owns both.

    Thread 3868782039 (round 10, P1): the head STABILITY bracket —
    the head is read BEFORE the reactions and verified against the
    round probe's own oid AFTER them; a head that moved between the
    reads makes the WHOLE probe UNREADABLE (ReactionHeadMoved: an
    EYES for head A must never pair with head B's oid/dates), so
    the wait retries next interval instead of resetting its latch
    and re-arming from a pre-change EYES.

    Thread 3869259808 (round 13, P1): EITHER EMPTY bracket endpoint
    raises ReactionBracketUnreadable the same way — a failed
    head_ref_oid ('' before) or a failed round probe ('' after)
    left the bracket UNCERTIFIED while head_changed refused the
    empty pair, so an EYES from a head that moved inside the
    failed-before/reactions/bounds sequence could arm the latch
    under the NEW head; the uncertifiable probe is UNREADABLE
    (retry next interval), never a certified mixed snapshot.

    Thread 3868979515 (round 11, P2): ONE SHARED budget — every
    subprocess this probe dispatches (the head-only read, every
    reactions page, the round probe) consumes the START-of-probe
    deadline: the head read and the walk receive the RAW remaining
    (probe_timeout_budget clamps the head read; the walk's own <=0
    guard raises ReactionWalkExpired — stop, probe UNREADABLE —
    before granting any page), and the round probe keeps the
    clamped remaining (the round-2 discipline). The pre-fix probe
    handed the walk the ORIGINAL timeout_secs AFTER the head read
    had already spent part of it, so a stalled probe could overrun
    the documented deadline-plus-interval bound.

    Thread 3868979509 (round 11, P1): an EYES whose created_at
    predates (or EQUALS — the round-10 ambiguity rule) the current
    head's push classifies EYES_STALE, and an unreadable push reads
    EYES_UNVERIFIED: neither ARMS the transition latch or refreshes
    the observed-activity watermark (see eyes_round_state in the
    latch module). Thread 3869259813 (round 13, P1): the EYES also
    binds the FORMAL codex request (round_bounds' separate third
    element) — a re-request on an unchanged head stales the
    preceding round's EYES — but NEVER the composite marker's
    post-EYES comment half (a request-less round's only marker
    lands after its own EYES); the +1 completion still carries the
    full both-facts binding.
    """
    deadline = None if timeout_secs is None else time.monotonic() + timeout_secs
    # Thread 3868979515 (round 11, P2): the shared deadline — each
    # stage receives the REMAINING window against the SAME
    # start-of-probe timestamp, never a fresh grant of the original.
    head_before = head_ref_oid(
        pr, None if deadline is None else deadline - time.monotonic()
    )
    reactions = gh_reactions(
        pr, None if deadline is None else deadline - time.monotonic()
    )
    # Thread 3868443452 (round 8, P1): the round probe rides EVERY
    # reading — EYES and NONE included — so the wait always knows
    # which head a probe was certified against; the DATES still feed
    # only the +1 classification below. Thread 3869259813 (round 13):
    # the FORMAL request rides third (the EYES's boundary), the
    # composite marker fourth (the +1's).
    bounds = round_bounds(
        pr,
        None
        if deadline is None
        else probe_timeout_budget(deadline - time.monotonic()),
    )
    head_oid, pushed, requested, observed = bounds[0], bounds[1], bounds[2], bounds[3]
    # Threads 3871485035/3871485055 (round 18): the per-kind boundary
    # identities and the FOLDED review evidence ride the bounds as
    # attributes (RoundBounds); a LEGACY plain-tuple seam fixture
    # (every pre-round-18 wait suite) carries none, so its single
    # index-2 stream feeds the request kind unchanged and the trigger
    # kind reads '' — the pre-round-18 behavior through the new
    # plumbing, zero fixture repins.
    request = getattr(bounds, "request", None)
    if request is None:
        request, trigger = requested, ""
    else:
        trigger = getattr(bounds, "trigger", "") or ""
    review_head = getattr(bounds, "review_head", "") or ""
    # Threads 3872194007/23 (round 20): the same-second identity
    # sets and the verdict stamp ride the SAME attr pattern (a
    # legacy plain tuple reads the '' / empty-set fallbacks).
    request_ids = getattr(bounds, "request_ids", None) or set()
    trigger_ids = getattr(bounds, "trigger_ids", None) or set()
    review_stamp = getattr(bounds, "review_stamp", "") or ""
    # Thread 3874769245 (round 27, P1): the base identity twin (a
    # legacy plain tuple reads the '' fallbacks — zero repins).
    # Thread 3875623447 (round 30, P1): the event portion rides the
    # same attr pattern (a legacy plain tuple/missing attr reads '').
    base_oid = getattr(bounds, "base", "") or ""
    base_bound = getattr(bounds, "base_bound", "") or ""; base_event_bound = getattr(bounds, "base_event_bound", "") or ""

    def _reading(state, identity, marker, detail=""):
        out = Reading(
            (state, identity, head_oid, marker, detail, request, trigger, review_head)
        )
        out.request_ids = request_ids
        out.trigger_ids = trigger_ids
        out.review_stamp = review_stamp
        # Thread 3874405295 (round 26): the head's own bound (the
        # classification's `pushed` — max of the commit stamps and
        # the headTransition event), so the wait's transition floor
        # stamps the HEAD's bound, never its observation wall clock.
        out.head_bound = pushed
        # Thread 3874769245 (round 27): the base's own bound rides
        # the same attr pattern — the wait's base_floor stamps the
        # BOUNDARY's own timestamp, never its observation clock.
        # Thread 3875623447 (round 30): the event portion rides too
        # (the wait's FF observation fallback keys on it).
        out.base = base_oid; out.base_bound = base_bound; out.base_event_bound = base_event_bound
        return out
    if head_changed(head_before, head_oid):
        raise ReactionHeadMoved(f"head {head_before[:7]}->{head_oid[:7]} mid-probe (3868782039)")
    if not head_before or not head_oid:
        raise ReactionBracketUnreadable(
            f"head bracket endpoint unreadable "
            f"({head_before[:7]!r}/{head_oid[:7]!r}) — probe discarded (3869259808)"
        )
    # Thread 3868625463 (round 9, P1): the EFFECTIVE marker never
    # goes backwards — the wait's retained high-water survives the
    # bounded-window eviction of a request-less round's only marker
    # ('' sorts lowest, so max() is eviction-proof).
    marker = effective_round_marker(marker_floor, observed)
    mine = [
        (index, node)
        for index, node in enumerate(reactions)
        if (node.get("user") or {}).get("login") == REACTION_BOT
    ]
    if not mine:
        return _reading(REACTION_NONE, "", marker)
    _, latest = max(
        mine, key=lambda pair: (str(pair[1].get("created_at") or ""), pair[0])
    )
    content = str(latest.get("content") or "")
    # Thread 3869941509 (round 14, P2): the unrecognized-content
    # repin — the REST_CONTENT miss reads UNKNOWN (distinct, never
    # NONE: refinements #2 made persistent NONE the findings signal),
    # and the raw content rides the detail half so the wait/banner
    # renders can show WHAT was unrecognized.
    state = REST_CONTENT.get(content, REACTION_UNKNOWN)
    detail = content if state == REACTION_UNKNOWN else ""
    # Thread 3868625469 (round 9, P1): the identity rides EVERY
    # state, not only DONE — the wait's observed-activity watermark
    # needs the EYES object's identity to order an accepted +1
    # against it.
    identity = plus_one_identity(latest)
    created = str(latest.get("created_at") or "")
    # Thread 3868979509 (round 11, P1): the EYES binds the CURRENT
    # head's push — a pre-head EYES is a PRIOR round's leftover
    # (head B pushed before the wait began while head A's review
    # still showed EYES) and classifies EYES_STALE/EYES_UNVERIFIED,
    # NEVER latch-arming, so A's late completion +1 — genuinely
    # postdating B's timestamps, passing every round-bound check —
    # cannot ride it out of the wait. Thread 3869259813 (round 13):
    # the formal REQUEST binds too (a re-request precedes its
    # round's EYES); the post-EYES comment markers NEVER do (round
    # 11's asymmetry). Thread 3869453944 (round 13): so does the
    # wait's transition OBSERVATION after a mid-wait head move.
    if state == REACTION_ACTIVE:
        # Thread 3870995905/11 (round 17): `requested` is the merged
        # request/trigger boundary IDENTITY `createdAt|node id` — the
        # EYES binding consumes its createdAt half (a trigger feeds
        # the SAME machinery a formal re-request does, 3870995911;
        # the identity suffix would otherwise make an equal-second
        # EYES compare against an ALWAYS-greater string).
        state = eyes_round_state(
            created, pushed, requested.partition("|")[0], transition_floor
        )
    if state != REACTION_DONE:
        return _reading(state, identity, marker, detail)
    # Round 6 (thread 3868047719, P1): the stale/unverified split —
    # the latch module classifies (null dates -> UNVERIFIED, never an
    # error-armed stale). Round 7 (thread 3868158293, P2): the +1's
    # identity rides beside the state for the wait's cross-probe
    # comparison. Round 8 (thread 3868443452, P1): the head oid rides
    # third, for the wait's head-change reset. Round 9 (thread
    # 3868625463, P1): the effective marker rides fourth, for the
    # wait's monotone high-water. Round 14 (3869941509): the detail
    # fifth — '' for every known-content state. Round 15 (3870293188):
    # the FORMAL REQUEST sixth — round-13's separate boundary element,
    # threaded through raw (never floored: the request walk paginates
    # the full history, so no bounded-window eviction applies) for the
    # wait's request-marker high-water. Round 18 (threads
    # 3871485035/3871485055): the reading grew to EIGHT — the TRIGGER
    # comment's boundary identity seventh and the FOLDED review
    # evidence eighth (both from the bounds' attributes; the EYES
    # classification still consumes the MERGED boundary's createdAt
    # — max(formal, trigger) — through `requested` above). Round 20
    # (threads 3872194007/23): the three round-20 facts ride the
    # Reading attrs (the subclass keeps every legacy plain-tuple
    # mock byte-identical).
    return _reading(thumbs_up_round_state(created, pushed, marker), identity, marker)


def bot_review_reaction(pr: int, timeout_secs: float | None = None) -> str:
    """The STATE half of bot_reaction_reading — every pre-round-7
    caller's contract unchanged (the banner; the classification
    tests). The wait loop consumes the full (state, identity, head
    oid) reading."""
    return bot_reaction_reading(pr, timeout_secs)[0]

# PR #49 round 13 (the 250 pure-LOC ceiling again): the wait loop +
# wall_iso_z + COLD_NONE_GRACE_SECS moved to the sibling
# pr_guard_reaction_wait — re-exported here (the round-7 re-export
# precedent) so pr_guard.py's `from pr_guard_reaction import ...
# wait_reaction` and every test seam keep ONE home. The wait calls
# time/the reading THROUGH this namespace (the round-11 banner rule)
# — see the wait module's docstring.
from .pr_guard_reaction_wait import COLD_NONE_GRACE_SECS, wait_reaction
