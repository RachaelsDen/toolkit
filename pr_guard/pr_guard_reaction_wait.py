"""The reaction family's wait loop — the `wait` mode's poll home.

PR #49 round 13 split this home out of pr_guard_reaction.py at the
250 pure-LOC ceiling (split-first, the PR #36 round-2 family rule):
reaction.py stood at 230 and round 13 grows BOTH the reading (the
bracket rejection, the request/transition-bound EYES) and the wait
(the transition floor, the demotion, the cold-NONE reset), so the
WAIT LOOP — a self-contained consumer of the reading — moves here.

SEAM RULE (the round-11 banner precedent, thread 3868979509): the
wait calls time, bot_reaction_reading, and every latch/probe name
THROUGH the pr_guard_reaction namespace — `import pr_guard_reaction`
only (a call-time attribute read; the module-object import is safe
against the re-export cycle because every attribute is touched at
CALL time, after both modules finished loading) — so the ONE patch
home survives this split: tests keep patching pr_guard_reaction.time
(the FakeClock), pr_guard_reaction.gh_reactions/round_bounds/
head_ref_oid, and pr_guard.py keeps importing wait_reaction FROM
pr_guard_reaction (re-exported there). Do NOT import these names
directly here — an early-bound import falls through to a LIVE gh
call (the round-11 lesson that motivated the rule).

The wait's semantics live in wait_reaction's docstring (brought
over verbatim from reaction.py — rounds 1-13's accumulated
discipline) and in the vault note 'Unified Realms/Notes/Codex
Review Bot Reaction Signal.md'.

PR #49 ROUND 14 lives here too: the transition-NONE arming gate
(thread 3869941505 — the head-move reset's companion: post-move
NONEs stay uncertified until a post-floor EYES or a
post-observation marker opens the gate) and the resurfaced-prior-+1
findings confirmation (3869941521 — the completion-absent signal is
two-shaped: NONE, or a THUMBS_UP proven older than the observed
arming EYES); the UNKNOWN vocabulary half of 3869941509 lives in
pr_guard_reaction/pr_guard_reaction_latch (this loop renders its
detail and never lets it satisfy the findings transition or the
cold-NONE hint).

PR #49 ROUND 15 lives here too: the request-advance latch reset
(thread 3870293188 — the REQUEST-marker high-water over the reading's
sixth element: baseline on first observation, round-latch reset on
strict mid-wait advancement) and the cold-NONE arming gate at WAIT
START (3870293205 — none_arming_gated initializes True).

PR #49 ROUND 16 lives here too (threads 3870734078 P1 / 3870734085
P1): the EYES-only NONE-gate openers. Both findings kill
marker/request-based openers of none_arming_gated — a marker or a
request carries NO head/round identity (a still-running review of
the OLD head posts markers after a transition floor; a re-request
says nothing about which job's reactions follow it), so neither can
certify the round a NONE would arm against. The ONLY opener is a
verified EYES (state == REACTION_ACTIVE — the one classification
that binds the head push, the formal request, and the transition
floor, rounds 11/13/15). Retired: round-14's post-floor marker
opener (3870734085) and round-15's request/marker ADVANCE openers
(3870734078); KEPT: the request-advance latch RESET itself
(3870293188 — protective), which now RE-CLOSES the gate (mirroring
the head-move block: a re-request supersedes the old round's
certifications, a gate its EYES opened included), the mid-wait
head-move gate set, and the cold-start True initialization.
3870734078's alternative "a later bot marker" opener has exactly
the same no-identity problem, hence EYES-only. The conservative
price is accepted (round-15 precedent): a legitimate round going
NONE→+1 with NO EYES ever observed holds to timeout (the
replacement path still exits 0 when a baseline exists); the survey
is the authority.

PR #49 ROUND 17 lives here too (threads 3870995905 P1 /
3870995911 P1 / 3870995919 P1): the request-advance detection
consumes the boundary IDENTITY (request_advances — strictly-newer
createdAt OR a same-second DISTINCT node id, so a re-request
landing inside the standing request's timestamp second still
resets), the boundary stream merges the documented '@codex review'
TOP-LEVEL comment trigger with the formal request (a posted trigger
while the wait observes a preceding round advances the high-water
and re-closes the gate exactly like a re-request; a pre-wait
trigger is the cold-start baseline), and the accepting +1 gains
the HEAD-BOUND completion check post-move — the latest BOT review's
commit oid must equal the observed head (the EYES-gate corollary:
the EYES still OPENS the gate, the +1's completion carries the
evidence; a request-less cold start keeps today's behavior and
never calls the review seam, an unreadable review read withholds).

PR #49 ROUND 18 lives here too (threads 3871485035 P1 /
3871485043 P2 / 3871485055 P1). (1) THE FOLD (3871485035 + the P2's
window): the head-bound completion check consumes the review
evidence from the READING's eighth element — the round probe's own
author-filtered botReviews connection (one subprocess, one
stable-head bracket: a mid-sequence head move discards the evidence
WITH the probe as an UNREADABLE bracket, and an oid mismatch
withholds) — never a separate post-bracket lookup whose unbracketed
window could return the prior head's review against a stale
observed_head; the server-side author filter (live-verified on
PR #49) also retires the old latestReviews(last:10) window whose
ten-other-reviewers eviction held every otherwise-valid completion
to timeout. (2) PER-KIND boundary retention (3871485055): the
formal request and the trigger comment retain INDEPENDENT
high-waters (each with the round-17 createdAt + node-id
distinctness) — a same-second pair of different kinds both register,
and the reset + gate re-close fire when EITHER kind advances on its
own; the merged boundary survives for CLASSIFICATION only (the EYES
binding and the composite marker keep consuming max(formal
createdAt, trigger createdAt) inside the reading).

PR #49 ROUND 19 lives here too (threads 3871844565 P1 /
3871844567 P2 / 3871844576 P2). (1) THE REQUEST-ADVANCE
OBSERVATION FLOOR (3871844565) — SUPERSEDED BY ROUND 20 (thread
3872194017; see below): the closed race was the immediate-reopen
shape — a same-head re-request landing after the old job launched
but before it posted EYES leaves the old EYES postdating the
REQUEST (the round-13 binding cannot stale it), so the advance
probe's reset + gate re-close were undone in the same iteration.
Round 19 answered with the wait's own wall clock stamped at every
advance observation; round 20 removes that stamp (the owned
supersession). (2) THE COLD-NONE reset on advance (3871844567):
the reset clears saw_any_eyes/cold_none_since/cold_hinted with the
latch — the round-13 head-move symmetry (a re-requested round that
never starts hints at the 10s mark instead of holding the prior
round's EYES suppression to timeout). (3) THE BOUNDARY SEEN-SETS
(3871844576): each kind's retention records EVERY identity any
probe observed (boundary_advances in the latch module) — a
deleted-then-resurfaced same-second boundary never readvances,
visibility oscillation is inert, and the high-water only moves on
unseen identities.

PR #49 ROUND 20 lives here too (threads 3872194007 P2 /
3872194017 P2 / 3872194023 P1). (1) THE REQUEST-BOUNDARY FLOOR
(3872194017 — the OWNED SUPERSESSION of 3871844565): the round-19
observation stamp demoted ANY post-advance EYES whose created_at
predates-or-equals the poll's wall clock — including the newly
requested round's OWN EYES posted between two five-second probes
(normal asynchronous startup), permanently staling it so its
passing +1 only seeded a held baseline and an otherwise-completed
review timed out. THE SAME OBSERVABLE SEQUENCE is the round-19
P1's race (an old job's EYES postdating the request, landing
before the advance-observing probe) and this P2's legitimate
shape — no job identity exists at the reaction API, so the two
floors choose between false-hold and false-exit-acceptance; the
reviewer's P2-vs-residue grading selects the REQUEST/TRIGGER's own
createdAt as the boundary — exactly the reading's standing round-13
binding (eyes_round_state), so the wait-side stamp machinery is
DELETED outright: an EYES certifies iff it postdates the boundary
event's createdAt (pre-boundary EYES still stale AT THE READING),
a between-polls EYES certifies, and the false-exit class it
re-opens is backstopped by the post-merge quiet watch + the server
rulesets (the documented residue posture). The cold-NONE reset and
the rest of the round-19 advance machinery are unchanged.
(2) THE FULL-IDENTITY SEEN-SETS (3872194007): the walks' new
collect sets record EVERY visible same-second identity at the
boundary's high-water second (not just markers[-1]) and the wait's
seen-sets union them — a sibling that was VISIBLE beside the
second's newest is remembered, so the newest's deletion/omission
can never leave an unrecorded resurfacer to counterfeit an advance
(a genuinely-new same-second boundary still advances, round 17's
core race preserved). (3) THE REVIEW-STATE COMPLETION BIND
(3872194023): live-verified 2026-08-27 read-only — the reviews'
`state` field renders COMMENTED for findings rounds (#49) and the
pass round (#48) alike, so the state-based bind is UNAVAILABLE
(documented, the round-15/17 posture); the built guard binds the
completing +1 to the folded VERDICT STAMP (see the head_bound
block): post-move the latest head-bound bot review must submit
after the transition floor AND be followed by the +1 — closing the
stale-review retarget coincidence and the verdict-predates-review
eviction shape, while the exact out-of-order same-era race (the
new head's findings review submitting before the old head's
delayed +1) is DOCUMENTED-OPEN with the quiet watch + rulesets as
the standing backstop.

PR #49 ROUND 21 lives here too (thread 3872631145, P2): the
FINDINGS exit's evidence bind. The EYES -> NONE completion path
bypassed head_bound entirely — after an observed head A->B move, A's
still-running job can post its EYES AFTER the transition floor (a
verified ACTIVE reading: it opens the gate and arms
saw_verified_eyes), finish WITH feedback, and remove the EYES; the
confirming NONE pair then carried A's round's findings signal while
the folded review evidence named head A and B's round may not have
started. The exit-3 gate now carries the SAME post-transition
evidence legs the THUMBS_UP exits have (rounds 17/18/20):
review_head == observed_head AND review_stamp > transition_floor —
the +1-follows-stamp leg is MOOT here (no +1 is accepted on a
findings exit). An unbound findings signal does NOT exit: the wait
keeps polling (the new head's round produces its own signal); ''
stamps/oids withhold like everywhere (never evidence). The
confirming NONE pair + saw_verified_eyes machinery is UNCHANGED —
only the EXIT gate gained the check.

PR #49 ROUND 22 lives here too (threads 3872740865 P2 /
3872980765 P1 / 3872980771 P2) — the ARM-RELAXED/EXIT-GUARDED
resolution of the round-19/20 floor trade, plus the monotone
high-waters. (1) THE HEAD-MOVE EYES DEMOTION IS DELETED (3872740865,
the owned supersession of the round-13 wait-side demotion of
3869453944): the probe that first notices BOTH a head move and the
new head's EYES stamps transition_floor at the LATER observation
time, so a between-polls legitimate EYES (posted after the move,
before the poll) was demoted to EYES_STALE — and because the floor
persisted, every later probe staled it AT THE READING too, leaving
no held baseline and no arming, so the completed round timed out.
The demotion is REDUNDANT since rounds 17/21: post-move completions
(the +1 exits AND the findings exit) already require
review_head == observed_head and review_stamp > transition_floor, so
the OLD head's job cannot exit regardless of arming (A's +1 submits
review(A) != B -> holds; B's own round completes) — the ARM relaxes,
the EXIT guards. The transition_floor itself STAYS (it feeds the
exit gates — never the reading: the wait no longer passes it into
bot_reaction_reading, whose EYES classification the round-15
headTransition event bound already covers — a mid-wait retarget's
force-push event stales the old head's leftover EYES by pushedDate
alone, the 3869453944 shape re-owned by 3870293194). (2) THE
BOUNDARY-FLOOR COMPLETION BIND (3872980765): a same-head re-request
landing before the preceding job posts EYES leaves that old EYES
classified ACTIVE (it postdates the request), re-opening the freshly
reset gate; the same exit-evidence discipline now extends to
request/trigger advances — the advancing boundary's createdAt is
retained as boundary_floor and post-advance completions additionally
require review_stamp > floor (and review_head == observed_head):
the old job whose review SUBMITTED before the re-request cannot
certify the +1 (its stamp predates the boundary). THE DOCUMENTED-OPEN
RACE (the round-19/20 posture, unchanged): the old job whose review
also submits AFTER the request passes every leg — its observable
sequence is IDENTICAL to the newly requested round's own pass at the
reaction API (no job identity, COMMENTED-only states, no
reaction-to-review association) — the quiet watch + the server
rulesets remain the standing backstop. (3) THE MONOTONE HIGH-WATERS
(3872980771): the per-kind retention records an unseen identity in
the seen-set but advances the high-water ONLY when boundary_advances
accepted it (or the first readable probe initializes the baseline) —
a deleted newest boundary whose older previously-unseen sibling
becomes the stream records WITHOUT regressing the high-water, so a
later resurfacing mid-history boundary can never counterfeit a
forward advance and spuriously reset a valid round.

PR #49 ROUND 23 lives here too (threads 3873317562 P2 /
3873317572 P2 — the banner half lives in pr_guard_reaction_banner).
(1) THE FINDINGS GRACE PROBES (3873317562): the round-12 exit-3
confirming design assumed the remove-EYES-then-post-+1 switch
completes within ONE five-second poll interval — the code treats
the switch as non-atomic (a lone NONE keeps polling) yet bounded
its patience at exactly one interval beyond the arming probe, so a
PASSING round whose replacement +1 took longer to publish through
GitHub/connector latency was reported as findings at the second
consecutive completion-absent probe. The confirmation now requires
FINDINGS_GRACE_PROBES (3) consecutive completion-absent probes —
covering ~2 poll intervals of switch latency beyond the arming
probe — for BOTH absence shapes (literal NONE and the
proven-older +1), resetting on any non-absent reading exactly like
today's findings_pending (a transient is a transient; UNREADABLE
resets too, as before). The round-12 arming discipline and the
round-21/22 exit-evidence legs (head/stamp floors) are UNCHANGED —
this fix only widens the confirmation window; the exit's TIMING
moves (the third probe, not the second), the races it guards do
not.

PR #49 ROUND 25 lives here too (thread 3873970933, P1): the
COLD-START head-bound completions. The round-17/22 head leg was
FLOORED-ONLY (`floor and ...`), so a wait starting AFTER a head
change — `floor` empty: no transition observed during THIS process,
no boundary advance — skipped `review_head` validation entirely,
and the OLD head's still-running job posting its EYES and +1 after
the new head was pushed armed the latch and exited 0 even though
the folded review named the OLD commit. BOTH +1 exits (primary and
replacement) and the findings exit now require the folded review to
NAME the observed head, floored or not: '' review_head withholds
(no review -> no verdict — the +1 is a POST-review verdict per the
PR #48 live evidence), a legit cold-start pass carries
review(B) == observed B, and the old-head race review(A) != B holds.
The stamp/floor legs stay floored-only (a cold start has no floor —
none is invented). The round-5 initial-+1 replacement shape still
exits 0: the replacing +1's round submitted a review for the
CURRENT head (pinned green).

PR #49 ROUND 26 lives here too (threads 3874405295 P2 / 3874405318
P2): the PUSH-BOUND stamp floor, the retained baselines. (1) THE
PUSH-BOUND FLOOR (3874405295): the transition floor was the wait's
OBSERVATION wall clock at the move-detecting probe — a LATER time
than a between-polls review — so a new-head round completing
entirely inside one poll interval failed `review_stamp > floor`,
its +1 was re-captured as the held baseline, and the completed
review timed out (round 22 deleted the EYES-demotion half; this
owns the stamp half). The floor is now the HEAD'S OWN BOUND — the
max(pushedDate, headTransition event) the reading's classification
already consumes, threaded through the reading's new `head_bound`
attr and stamped MONOTONE across moves: a review submitted after
the head's push/transition bound is current-head work regardless of
when the WAIT noticed the move, while the pre-move leftover (the
retarget coincidence) is owned by the force-push EVENT bound — the
wall_iso_z stamp machinery is DELETED outright (the round-20
boundary-floor discipline applied to the head stream: the boundary
event's own timestamp, never the wait's clock). The move block's
baseline RE-CAPTURE is deleted with it (the finding's harm half):
the pre-move baseline is RETAINED so the between-polls replacement
fires naturally — the arm relaxes, the exit guards (round 22): the
round-17/18/20/25 evidence legs withhold the old head's job at the
EXIT, so the re-capture stranded legitimate completions while
guarding nothing the legs do not; an UNCHANGED pre-move +1 still
never exits by replacement (identical identity — the round-8
rule's substance). (2) THE FAST-ROUND ADVANCE COMPLETION
(3874405318): the advance reset no longer clears held_plus_one — a
re-request and the entire resulting EYES->+1 round can land between
two probes, and the cleared baseline discarded the preceding +1 the
replacement path needs (the new +1 installed as the baseline and
held unchanged to timeout). The retained baseline lets the
replacement fire THIS iteration, and the round-22 boundary-floor
stamp leg still withholds the preceding job's pre-request review —
the round-7 fast-round discipline advertised, with the false-exit
class closed at the exit, not the reset.

PR #49 ROUND 27 lives here too (threads 3874769241 P2 /
3874769245 P1 / 3874769253 P2): the same-second verdict, the
base-change reset, the deadline-crossing final probe. (1) THE
SAME-SECOND VERDICT (3874769241): the +1-follows-stamp leg became
EQUALITY-SAFE (`plus_one_created >= review_stamp`, the round-27
SUPERSESSION of the round-10 strictness FOR THIS LEG ONLY — the
classification legs of thumbs_up_round_state/eyes_round_state keep
strict `>`): a valid bot review submission and its subsequent +1 can
share one API timestamp second, and the strict compare made
`head_bound` false — the reaction object is IMMUTABLE, so a
same-second reject stranded the passed round FOREVER (both
completion branches re-encounter the same object on every later
probe). The false-accept surface the strict leg guarded is already
owned by the OTHER legs: review_head == observed_head names the
round's own commit, and review_stamp > floor binds the submission
past the transition/boundary/base boundary; the +1 IS the
post-review verdict by the bot's lifecycle (the PR #48 live shape),
so on equality the ONLY orderings are verdict-after-review (accept)
or a same-second stranding (the pre-fix bug). A stable-id
tie-breaker is UNAVAILABLE here: the review stamp carries no REST id
on the folded read (unlike reaction_follows' two REST objects).
(2) THE BASE-CHANGE RESET + FLOOR (3874769245, the P1 — see
pr_guard_reaction_probe's round-27 section for the live-verified
schema facts): a retarget or a base-tip advance changes the reviewed
diff while headRefOid stays unchanged, so the wait now tracks
`observed_base` (the reading's new .base attr — baseRefOid, an OID,
never the mutable ref name) exactly as it tracks observed_head, and
a change fires the SAME reset family as a head move (latches,
watermark, findings streak, cold-NONE state, gate re-close — the
held baseline retained per the round-26 rule) while stamping
`base_floor` = the boundary's OWN timestamp (BaseRefChangedEvent
createdAt for retargets; the base target's own push bound for
fast-forward tip advances MAX the BaseRefForcePushedEvent createdAt
for force-updated tips — round 29, thread 3875352284, the probe's
new baseForce connection — NEVER an observation clock, the
round-20/22/26 doctrine)
into `floor = max(transition_floor, boundary_floor, base_floor)`:
the old-base job's review (commit.oid names the unchanged HEAD, so
head_bound cannot separate bases) fails `review_stamp > base_floor`
— the stamp leg IS the separation; a post-base-change round submits
past it and completes. Where nothing verifiable exists for a
base-tip advance (null-dated target on a FAST-FORWARD move — the
round-29 force event covers the force-updated half), the reset
alone + the honest-documentation posture (the round-15/17 FF
precedent). (3)
THE DEADLINE-CROSSING FINAL PROBE (3874769253): the timeout fires
only when a probe BEGAN at-or-after the deadline (`probe_started >=
deadline`) — a probe that started before but whose later reads ran
long gets ONE more fresh reading (the promised final probe, riding
the 1s probe_timeout_budget floor), THEN the timeout; the old
post-probe `monotonic() >= deadline` check burned the final probe on
any overlong earlier one while its reaction read had happened long
before, leaving a +1 that landed between the reaction fetch and the
deadline unobserved.

PR #49 ROUND 28 lives here too (threads 3875089260 P1 /
3875089273 P1 — the base twin lives in pr_guard_reaction_probe's
round-28 section, thread 3875089268): the cold-start base floor,
the returning-OID head transitions. (1) THE COLD-START BASE FLOOR
(3875089260): when the wait starts AFTER the base already changed,
the first readable probe only initialized observed_base — base_floor
stayed '', so the completion stamp checks were skipped and a review
of the unchanged head against the OLD base (EYES persisting across
the base move, the +1 landing later) exited 0 with review_head ==
observed_head trivially true — the current base-derived diff was
never reviewed. The first readable probe now initializes base_floor
= max(base_floor, base_bound) ALONGSIDE observed_base —
INITIALIZATION, never a change: NO reset family fires (the boundary
baseline rule — a pre-wait base is the round's FLOOR, not a
transition); post-cold-start, completions on the stale base fail
review_stamp > base_floor (the old-base review predates the current
base's own bound — the same separation the mid-wait stamp provides).
(2) THE RETURNING-OID TRANSITIONS (3875089273): a head that cycles
A->B->A entirely between polls leaves the oid UNCHANGED (the
oid-only compare reports no move) while the reading's head_bound
strictly ADVANCES — the force-push event genuinely moved (round-15/
26 semantics: the event exists only when the ref moved), so the
advance IS the transition. The wait retains observed_head_bound
(cold start initializes oid + bound together, every readable head
updates it) and a probe whose oid EQUALS the observed one but whose
bound strictly advances fires the SAME reset family as a head move
(the fold `moved or returned`), advancing transition_floor to the
new bound (monotone max) — the pre-cycle job's review then fails
review_stamp > transition_floor at the exit and its delayed +1 can
no longer ride the pre-cycle EYES to WAIT DONE.

PR #49 ROUND 30 lives here too (thread 3875623447, P1): the
FF-base OBSERVATION bound — the finding's own sanctioned fallback
for the round-29 residue class. Round 29 closed the force-updated
half with BaseRefForcePushedEvent's own createdAt; the
FAST-FORWARD half (the base advanced to an ALREADY-EXISTING
descendant commit) fires NO PR event (round-29 live verification:
neither BaseRefChangedEvent — the PR was not retargeted — nor
BaseRefForcePushedEvent — the move was not a force update), so the
fallback bound reads the target commit's potentially OLD
committedDate and an old-base review postdating it passed
`review_stamp > base_floor` — with the head unchanged
(review_head == observed_head trivially), its delayed EYES re-armed
the reset base and WAIT DONE exited 0 over the re-derived diff
nobody reviewed. When a base change fires and NO event stamp
contributed to base_bound (the reading's new .base_event_bound —
'' for the FF/null-dated class), base_floor additionally stamps the
wait's OBSERVATION wall clock (the wall_iso_z formatting round 26
deleted, revived for this one sanctioned arm — the finding's text
sanctions exactly this: post-observation review evidence when the
base OID changes without a corresponding event timestamp). The
stamp gates the EXIT leg only (floor = max(transition, boundary,
base)) — the reading/classification is untouched. THE TWO
DOCUMENTED PRICES (owned in the 3875623447 receipt): (a) a
legitimate round completing ENTIRELY within one poll interval after
an FF base move is HELD — its review predates the observing probe —
and only the NEXT wait recovers (its cold start re-initializes
base_floor from the settled base bound; the observation stamp is
wait-local state, never persisted); (b) an old-base job whose review
submits AFTER the observation remains indistinguishable from the
new-base round's own pass at the reaction API (no job identity —
the standing documented-open class, the quiet watch + rulesets the
backstop). The event-backed retarget/force-update shapes keep their
exact behavior: base_event_bound nonempty means the boundary's OWN
timestamp already postdates every pre-move review, and NO
observation stamp is applied (the round-20/22/26 doctrine holds for
every class that has an event).

PR #49 ROUND 31 lives here too (threads 3875830806 P1 /
3875830819 P2): the transition-tied event evidence, the stale
resurfaced-pass absence. (1) TRANSITION-TIED EVENT EVIDENCE
(3875830806): round 30's observation fallback keyed on base_event
bound PRESENCE — but event presence is PERSISTENT (the query
returns the PR's latest HISTORICAL BaseRefChangedEvent/
BaseRefForcePushedEvent forever), so a PR with pre-wait event
history that later fast-forwards (no new event) kept a nonempty
event bound that skipped the observation floor while certifying
nothing about the current transition; an old-base review
submitted after that historical stamp then paired with the
persisting/delayed EYES and +1 to WAIT DONE over the re-derived
diff. The wait now retains base_event_high_water (max event stamp
any readable probe has seen — monotone, baseline-initialized on
the first readable probe beside observed_base), and a `rebased`
transition is event-backed ONLY when the reading's event bound
STRICTLY ADVANCES past it ON THE SAME PROBE as the oid change —
the same high-water discipline as the marker/request streams.
Non-advancing (the historical leftover / FF class) applies the
round-30 observation floor; advancing (the event fired WITH the
move) keeps today's exact event-backed behavior — no observation
stamp (the round-30 event-backed pins hold: their events advance
with the move). (2) THE STALE RESURFACED-PASS ABSENCE (3875830819):
the round-14 completion-absent signal's DONE-not-following shape
never matched a THUMBS_UP_STALE classification — a findings round
that posts a review-thread comment or a submitted review AFTER its
EYES advances the marker past the PRIOR round's +1 it later exposes
by removing the EYES, so the exposed pass read merely stale, reset
findings_absent_streak on every probe, and a real findings round
timed out instead of returning WAIT FINDINGS. The predicate gains
the STALE shape: a STALE-classified +1 whose identity PREDATES the
arming EYES watermark (eyes_watermark — retained at each verified-
EYES probe, because arm_watermark refreshes at every arming probe
and a STALE reading arms, so the refreshed watermark names the
stale object itself and orders nothing) counts as completion
absence and feeds the grace streak. The verified-EYES precursor
stands (no EYES -> no findings exit), the round-14 DONE shape is
unchanged, and the exit-3 evidence gates (round-25/26 head-naming
+ floors) apply to the stale shape exactly as to the others.

PR #49 ROUND 32 lives here too (thread 3876000978, P1): the
COLD-START FF base floor. Round 30 taught the MID-WAIT base change
the observation fallback (no event stamp contributed -> stamp the
wait's wall clock) and round 31 tied event-backed-ness to the
high-water advance, but the COLD START still initialized base_floor
from the base bound ALONE — a wait starting after an event-less
base FAST-FORWARD onto an already-existing commit read that
commit's potentially OLD committedDate, so an old-base review
submitted AFTER the target commit date but BEFORE the wait began
satisfied `review_stamp > base_floor` and, with the head unchanged
(review_head == observed_head trivially), its persisting EYES and
delayed +1 reached WAIT DONE although the current base-derived diff
was never reviewed. The cold-start initialization now gains the
SAME fallback: when the first readable probe's base bound is NOT
event-backed (no .base_event_bound — the round-30/31 criterion),
base_floor additionally stamps the cold-start OBSERVATION wall
clock (the round-28 cold-start rule + the round-30 mid-wait
fallback, one shape; the stamp is wait-local state, never
persisted). THE OWNED PRICE (the cold-start twin of round 30's
price (a)): a round whose review submits between the FF move and
the wait's first readable probe predates the observation and is
held to timeout — the survey is the authority. Event-backed cold
starts are UNCHANGED (the boundary's own event timestamp binds).

PR #49 ROUND 33 lives here too (thread 3876172341, P1): the
UNCONDITIONAL cold-start observation — the conservative rule that
supersedes round 32's event-presence conditional. Fresh evidence:
a PR can carry an OLD historical BaseRefChangedEvent or
BaseRefForcePushedEvent and then undergo an EVENT-LESS base
fast-forward BEFORE the wait starts — the persistent event leaves
.base_event_bound NONEMPTY, so round 32's `"" if base_event_bound
else <wall>` suppressed the observation fallback although the
historical event describes NO transition of the current base; with
the FF'd-to commit's OLD committedDate inside the bound, a
prior-base review submitted AFTER the historical event (but before
the wait began) paired with its persisting EYES and delayed +1 to
satisfy `review_stamp > base_floor` and WAIT DONE over a re-derived
diff nobody reviewed. At COLD START the association between an
event stamp and the CURRENT base transition CANNOT be established:
the round-31 high-water criterion needs a mid-wait comparison (an
event observed ADVANCING WITH the oid change), and no prior probe
exists to compare against — so the conservative rule the finding
sanctions stamps the cold-start base_floor with the OBSERVATION
wall clock UNCONDITIONALLY (max(base_bound, wall) — the max makes
the wall inert whenever the bound is genuinely at/after it, the
2026-stamped-fixture case). WHY UNCONDITIONAL IS SAFE: a PRE-WAIT
review paired with a POST-WAIT-START +1 is exactly the
delayed-verdict race being blocked (the EYES that persisted across
the wait start is the old-base round's own), while every
legitimate completion path is unaffected — a mid-wait `rebased`
transition keeps the round-31 discipline UNCHANGED (the
event-advance comparison stands, event-backed moves take the
boundary's own stamp, only the non-advancing class observes), a
cold-start round whose review SUBMITS after the first readable
probe clears the wall (pinned), and the round-7 replacement path
carries its own fresh post-start review. The OWNED PRICE (the
round-32 cold-start price, now paid by the event-backed class
too): a cold-start round whose review predates the wait's first
readable probe is held to timeout — the survey is the authority;
the stamp is wait-local state, never persisted, and the NEXT wait
recovers (its own first probe re-stamps).

--ACCEPT-STANDING lives here too (user request 2026-08-28, no
thread ID — the standalone repo's first post-extraction feature):
the opt-in fast path for already-passed PRs. A DONE-CLASSIFIED
THUMBS_UP exits 0 immediately, standing or observed, bypassing the
observation gates (rounds 5/7/9) and the review-evidence legs
(rounds 17/18/20/22/25 — the zero-review-object '' shape
included); the +1's own staleness CLASSIFICATION still applies
(THUMBS_UP_STALE holds — only REACTION_DONE accepts). See
wait_reaction's docstring and
pr_guard_wait_accept_standing_test.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round31_test -v
"""

from . import pr_guard_reaction
from datetime import datetime, timezone

# User-taught refinements #2 (vault note SECTION 'User-taught
# refinements #2'): the cold-NONE grace — a review that never
# produced any EYES variant for this many continuous seconds of NONE
# hints that the bot may have failed to start ('@codex review'
# triggers it manually). The note's taught window is ~10s; the hint
# is INFORMATIONAL ONLY (never a comment post, never an exit).
COLD_NONE_GRACE_SECS = 10

# Thread 3873317562 (PR #49 round 23, P2): the FINDINGS GRACE — the
# number of consecutive completion-absent probes (BOTH shapes:
# literal NONE and the THUMBS_UP proven older than the observed
# arming EYES) that confirm the findings transition. Round 12's
# single confirming probe assumed the remove-EYES-then-post-+1
# switch completes within one WAIT_INTERVAL_SECS poll; GitHub or
# the connector can take longer, and a slow PASS was reported as
# findings. Three probes cover ~2 poll intervals of switch latency
# beyond the arming probe; any non-absent reading resets the
# streak (the findings_pending rule unchanged).
FINDINGS_GRACE_PROBES = 3


# Thread 3869453944 (round 13) once kept wall_iso_z here — the
# wait's OBSERVATION wall clock as an ISO-Z stamp, the floor every
# post-transition completion's evidence had to outdate. Thread
# 3874405295 (round 26) DELETED it outright: a between-polls review
# PREDATES the poll that observes the move, so the observation stamp
# rejected current-head work and the completed round timed out. The
# floor is the HEAD'S OWN BOUND now (see the transition_floor header
# in wait_reaction) — the boundary event's own timestamp, never the
# wait's clock (the round-20 boundary-floor discipline applied to
# the head stream).


def wait_reaction(pr: int, timeout_secs: int, accept_standing: bool = False) -> int:
    """The `wait` mode: poll ONLY the reaction until THUMBS_UP/timeout.

    First probe immediate, then every WAIT_INTERVAL_SECS (5s, polite)
    with the deadline-clamped sleep discipline (the quiet-watch
    precedent: never sleep PAST the deadline, so the final probe lands
    at/after it). Prints each STATE CHANGE; a failed read prints
    UNREADABLE and keeps polling (never a done signal), bounded by
    the deadline. Threads 3867503708/3867572256 (PR #49, P2): every
    probe's subprocess timeout is its ACTUAL remaining window —
    probe_timeout_budget clamps it to [1s, two intervals] — so a
    stalled gh api reads UNREADABLE, the at-deadline final probe
    still gets its 1s floor read, and the wait never blocks past
    deadline+interval. Threads 3867503712/3867653639 (PR #49, P1):
    only a CURRENT-ROUND THUMBS_UP — one postdating BOTH the head's
    push AND the latest round-engagement marker (a re-request counts
    even with no head change) — counts; a stale pass reads THUMBS_UP
    (stale — ...) and keeps polling.

    Thread 3867897766 (PR #49 round 5, P1): the postdate checks are
    not enough at wait START — the prior round's +1 can still be the
    latest reaction while the asynchronous new round has posted
    NOTHING yet (no EYES, no submission, no thread comment), so no
    marker exists to stale it and the first probe would read DONE on
    the OLD pass. An initial-+1 wait exits 0 only after observing
    the bot actually go active->done WITHIN the wait: ONE confirmed
    non-DONE reading (EYES, NONE, or a marker-driven THUMBS_UP_STALE
    — never UNREADABLE, a read failure is not round evidence) must
    land between start and the accepted +1; otherwise the wait times
    out with that explanation (survey the threads to see where the
    round stands). Thread 3868047719 (round 6, P1): THUMBS_UP_UNVERIFIED
    (unreadable bounds) is in the same never-arms class — an error
    must not counterfeit the transition; only VERIFIED non-DONE
    states arm (arms_transition_latch). Thread 3868158293 (round 7,
    P2): the OBSERVED-NEW acceptance beside the latch — a fast round
    can go EYES->+1 ENTIRELY between two 5s probes, leaving both
    observed states THUMBS_UP with the latch never armed, so the
    initial-held +1's IDENTITY (created_at|id) is compared across
    probes: a LATER +1 with a DIFFERENT identity is a demonstrably
    new reaction object, and having already passed the
    marker-staleness classification (the state half bound it to the
    round bounds) it completes the wait without the transient EYES
    ever being sampled; an UNCHANGED identity keeps holding to the
    timeout. Thread 3868443452 (round 8, P1): the head oid rides the
    reading too, and a CHANGE resets both certifications — the head
    moving mid-wait to an already-pushed commit whose pushedDate
    predates the standing +1 reclassifies the UNCHANGED reaction
    stale->done with no bot activity, so a latch armed against the
    old head's bounds must not certify the new head: on a detected
    move the latch clears and the baseline re-captures the CURRENT
    reaction, and completion needs a fresh POST-change transition
    (an EYES read under the new head re-arms; a REPLACED +1 exits).
    An unreadable oid ('' — a failed round probe) certifies no
    change in either direction. Thread 3868625463 (round 9, P1):
    the marker HIGH-WATER — the effective marker never goes
    backwards. A request-less round's only marker (a bot comment)
    is evicted from the bounded comments(last:3)/
    reviewThreads(last:10) windows by later comments, so the probe
    that SAW it armed the latch on the prior +1's staleness while a
    later probe (marker evicted) would reclassify the same
    unchanged +1 current and exit 0; each probe classifies against
    the max marker SEEN SO FAR (marker_floor), so the evicted-window
    probe still reads stale. Thread 3868625469 (round 9, P1):
    completion follows the OBSERVED EYES — every arming probe
    refreshes the observed-activity watermark to its latest
    reaction's identity, and BOTH DONE exits (the latch and the
    observed-replacement) require the accepted +1's identity to
    POSTDATE it: when the prior round's +1 coexists with a newer
    EYES and the EYES is removed before a replacement +1 is
    visible, the OLD +1 becoming latest again is not a completion —
    the wait keeps polling to its timeout. The high-water survives
    unreadable probes and head moves alike (engagement markers are
    bot-activity facts, not head-bound dates); the watermark resets
    with the latch on a head move (it is a latch certification).

    USER-TAUGHT REFINEMENTS #2 (vault note '{VAULT_NOTE}', section
    'User-taught refinements #2'): the bot REMOVES its EYES at round
    end — +1 when it passed, NOTHING when it found feedback — so
    TWO None-discriminating behaviors join the loop. (1) EYES ->
    NONE is the FINDINGS exit: a LATCH-ARMING (current-head-verified,
    round 11) EYES arms saw_verified_eyes, and a NONE that PERSISTS
    through the next FINDINGS_GRACE_PROBES probes (the absent-streak
    confirmed; round 23, thread 3873317562 — a single confirming
    probe bounded the switch at one poll interval) returns the
    NEW exit code 3 with the WAIT FINDINGS line — survey the threads
    now (fix + receipt + re-wait). The confirming streak exists
    because the remove-EYES-then-post-+1 switch is NON-ATOMIC (the
    round-9 thread-3868625469 window: the EYES removal lands before
    the replacement +1 is visible): a lone NONE that flips back to
    EYES (or completes to +1) is a transient, and the wait keeps
    polling — only the TERMINAL transition (a NONE that stays)
    exits. EYES_STALE/EYES_UNVERIFIED never arm it (an old round's
    eyes disappearing is not a findings signal — round 11's
    asymmetry), and a head move resets the arming with the latch (a
    certification). (2) The COLD-NONE hint: when NO EYES variant was
    ever observed and the state has been NONE continuously for
    COLD_NONE_GRACE_SECS, the '@codex review' trigger HINT prints
    exactly ONCE (the bot may have failed to start; a HINT ONLY —
    this tool never posts comments, the orchestrator decides) and
    the wait keeps polling to timeout as before. Exit codes: 0 on
    the transitioned (or observed-replaced) THUMBS_UP, 1 on
    timeout, 3 on the confirmed findings transition (2 stays the CLI
    usage error) — the reaction is the DONE/ACTIVE signal ONLY:
    thread state remains the merge authority and the post-merge
    quiet-period watch still guards the landed tree.

    PR #49 ROUND 14 (threads 3869941505 P1 / 3869941509 P2 /
    3869941521 P1) — three tightenings on the refinements-#2 base.
    (1) The TRANSITION-NONE GATE (3869941505): a NONE observed
    on/after a detected head move does NOT arm the latch until
    something certifies the NEW head's round — an EYES past the
    transition floor (post-observation activity) or a round marker
    postdating the transition observation — because the OLD head's
    non-atomic EYES-removal/+1 switch reads NONE at exactly the
    transition probe, and that generic arm would let the old head's
    delayed +1 (created after the observation, passing the new
    head's older bounds and the empty watermark) exit 0 with the new
    head unreviewed. Cold-start NONE (no move) still arms — round
    5's initial-+1 protection. (2) UNKNOWN (3869941509): an
    unrecognized latest reaction content reads REACTION_UNKNOWN —
    never NONE, so it can neither satisfy the findings transition
    nor feed the cold-NONE hint (an unknown reaction is not "no
    reaction"; the streak resets on it), and it BREAKS the NONE
    persistence like any real observation. (3) The RESURFACED prior
    +1 (3869941521): a THUMBS_UP PROVEN older than the observed
    arming EYES (DONE-classified yet not following the watermark —
    already rejected by both pass exits) is the SAME
    completion-absent signal NONE is, with the same two-probe
    persistence, verified-EYES precursor, and head-move reset; the
    prior +1 the EYES-removal EXPOSES confirms findings (exit 3)
    instead of HOLDING to the full timeout, while a +1 FOLLOWING
    the watermark remains the pass (exit 0) and the round-5 HOLDING
    shape (no EYES ever observed) still never exits 3. The watermark
    itself only moves FORWARD now — an arming NONE refreshes nothing
    (its identity is ''), so a transient NONE between the EYES and
    the exposed +1 cannot erase the EYES's watermark and let the old
    +1 "follow" the emptied one.

    PR #49 ROUND 15 (threads 3870293188 P1 / 3870293205 P1) — the
    request-advance latch reset and the cold-NONE arming gate.
    (1) The REQUEST high-water (3870293188): the reading's sixth
    element (round-13's separate FORMAL request) is retained beside
    the composite marker high-water; the FIRST observation
    initializes the baseline (a request predating the wait is the
    normal cold start — no reset), and only a STRICT advancement
    observed mid-wait (a re-request) RESETS the round latches —
    saw_non_done, arm_watermark, the held baseline, saw_verified_eyes,
    the findings absent streak; the cold-NONE hint state is round-agnostic
    proof-of-start evidence and stays — so the preceding job's
    delayed +1 (postdating the new request AND the old EYES
    watermark) finds NO armed latch and only seeds a held baseline:
    the newly requested round must run its own EYES->+1 (or replace
    the held +1) before exit 0. (2) The cold-NONE gate at WAIT START
    (3870293205): none_arming_gated initializes True — a cold NONE
    on the first stable-head probe (the preceding round's
    non-atomic EYES-removal/+1 gap, particularly under a head that
    moved before the wait began) arms NOTHING until the round
    certifies itself (round 16 reduced the opener list to the
    verified EYES below). Round 5's initial-+1 shape still exits
    0 via the REPLACEMENT path, round 7's identity replacement is
    unchanged, and the mid-wait head-move gate (round 14) keeps its
    exact semantics. A legitimate fast round starting inside a
    cold-NONE window may now conservatively hold to timeout — the
    accepted price: the survey is the authority.

    PR #49 ROUND 16 (threads 3870734078 P1 / 3870734085 P1) — the
    EYES-only NONE-gate openers, the convergent invariant of both
    findings. Markers and requests carry NO head/round identity:
    after a head change a still-running review of the OLD head can
    post a thread comment or a submitted-review marker after the
    transition floor (3870734085 — round-14's marker opener
    certified the new head on it, and the old job's remove-EYES-
    then-+1 completion postdated every check and exited 0 with the
    new head unreviewed), and a re-request arriving while the
    reaction is NONE (3870734078 — round-15's request ADVANCE opener
    opened the gate and the same probe armed saw_non_done, undoing
    the request-advance reset of 3870293188 in the same iteration;
    the preceding job's delayed +1 then passed the timestamp and
    empty-watermark checks to WAIT DONE before the newly requested
    review started). The ONLY opener now is a verified EYES
    (state == REACTION_ACTIVE — the one classification binding the
    head push, the formal request, and the transition floor); the
    request-advance RESET survives and RE-CLOSES the gate (the old
    round's EYES-opened gate included — a re-request supersedes
    every certification the preceding round earned), and the
    round-13 request binding guarantees the only EYES reading
    ACTIVE past an advance is a verified POST-REQUEST one, which
    re-opens the gate in the same probe. The conservative price is
    accepted (round-15 precedent): a legitimate round going
    NONE->+1 with NO EYES ever observed holds to timeout (the
    replacement path still exits 0 when a baseline exists); the
    survey is the authority.

    --ACCEPT-STANDING (user request 2026-08-28, no thread ID): the
    opt-in fast path for ALREADY-PASSED PRs — on a PR whose bot
    finished before the wait began, the round-5 rule refuses the
    unobserved +1 and the round-25 rule withholds when no folded
    review names the head (EVERY zero-findings pass: no findings =>
    no review object), so the default wait holds a standing THUMBS_UP
    to the FULL timeout after an explicit verdict. With the flag, a
    DONE-CLASSIFIED THUMBS_UP exits 0 immediately (standing or
    observed): the user's explicit opt-in is the authority for the
    observation and review-evidence gates. The +1's own staleness
    CLASSIFICATION still applies — a +1 predating the head push or
    the boundary markers reads THUMBS_UP_STALE and holds (a stale
    verdict is not "codex said this PR is fine"); only state ==
    REACTION_DONE accepts. The accepted risk: a standing pass may
    predate an unposted new round — thread state remains the merge
    authority.
    """
    start = pr_guard_reaction.time.monotonic()
    deadline = start + timeout_secs
    last = ""
    # Thread 3867897766 (P1) + 3868047719 (round 6, P1): the
    # transition latch — armed only by a VERIFIED non-DONE reading
    # (a real signal: EYES, NONE, or a marker-verified stale;
    # UNREADABLE and THUMBS_UP_UNVERIFIED are read failures and
    # never count). A THUMBS_UP exits 0 only when the latch proves
    # the wait watched the round MOVE: the +1 at start (or behind an
    # UNREADABLE/UNVERIFIED start, which never captured a non-DONE
    # initial state) cannot certify a request-less round that has
    # not yet posted anything.
    saw_non_done = False
    # Thread 3868158293 (round 7, P2): the OBSERVED-NEW baseline —
    # the identity of the FIRST unarmable DONE reading, captured
    # once; a later DONE reading REPLACING it (replaced_plus_one)
    # proves the round completed afresh inside the wait even though
    # no probe sampled the transient EYES.
    held_plus_one = ""
    # Thread 3868443452 (round 8, P1): the head the latch/baseline
    # were certified against — round_bounds' preserved headRefOid.
    # A head move re-binds every date comparison (an already-pushed
    # target can carry a pushedDate older than the standing +1), so
    # the certifications reset the moment the oid changes.
    # Thread 3875089273 (round 28, P1): the BOUND twin — the head's
    # own bound each readable probe observed (cold start initializes
    # oid + bound together; every readable head updates it). A->B->A
    # between polls leaves the oid UNCHANGED while the bound strictly
    # advances (the force-push event genuinely moved), so the bound —
    # never the oid alone — carries the transition (see `returned`).
    observed_head = observed_head_bound = ""
    # Thread 3869453944 (round 13) / 3874405295 (round 26): the
    # transition floor — the moved-to head's OWN bound (the reading's
    # `head_bound` attr: max(pushedDate, committedDate, the
    # headTransition force-push event), exactly what the EYES/+1
    # classifications consume), stamped MONOTONE (max) across moves.
    # A review submitted after the head's push/transition bound is
    # current-head work regardless of when the WAIT noticed the
    # move, and the pre-move leftover class (a retarget coincidence
    # — a review of the commit the ref came back onto) predates the
    # force-push EVENT the bound consumes. Round 13 stamped the
    # wait's observation WALL CLOCK here (wall_iso_z, deleted round
    # 26): it postdated a between-polls review and the completed
    # round timed out; '' on a cold start (head stable since wait
    # start) keeps the floored-only legs skipped (round 25 — no
    # floor is invented).
    transition_floor = ""
    # Thread 3868625463 (round 9, P1): the marker HIGH-WATER — the
    # max round marker any probe has SEEN. A request-less round's
    # only marker (a bot thread comment) is EVICTED from the bounded
    # comments(last:3)/reviewThreads(last:10) windows by later
    # comments, so the probe returns what it sees while the wait
    # never lets the effective marker go backwards: once observed, a
    # marker binds for the rest of the wait.
    marker_high_water = ""
    # Thread 3868625469 (round 9, P1): the observed-activity
    # watermark — the latest reaction identity read at an ARMING
    # probe. The prior +1 coexisting with a newer EYES arms the
    # latch, but if the EYES is removed before a replacement +1 is
    # visible the OLD +1 becomes latest again — an accepted +1 must
    # FOLLOW the watermark (postdate the observed activity), else
    # the wait keeps polling.
    arm_watermark = ""
    # User-taught refinements #2 (vault note section): the findings
    # transition's precursor — set ONLY by a LATCH-ARMING EYES (a
    # current-head-verified EYES; the stale/unverified variants
    # prove an OLD round's activity, never a findings signal), reset
    # with the latch on a head move.
    saw_verified_eyes = False
    # Thread 3875830819 (PR #49 round 31, P2): the arming EYES's own
    # identity — refreshed at every verified-EYES probe. The stale
    # resurfaced-+1 absence leg below must prove the exposed +1
    # PREDATES the observed EYES AGAINST THE EYES ITSELF: arm_watermark
    # refreshes at every arming probe (a THUMBS_UP_STALE reading
    # arms), so by the time `follows` is computed the watermark names
    # the stale +1's OWN identity and orders nothing — the eyes
    # watermark is the stable comparison the round-14 "proven older"
    # class needs (a +1 POSTDATING the observed EYES is the current
    # round's own marker-raced pass, never absence — it follows the
    # eyes and the leg excludes it).
    eyes_watermark = ""
    # User-taught refinements #2: the confirming streak — a
    # completion-absent probe observed after the arming EYES counts
    # up; FINDINGS_GRACE_PROBES consecutive absent probes (round 23,
    # thread 3873317562 — round 12's single confirming probe bounded
    # the non-atomic remove-EYES-then-post-+1 switch at ONE poll
    # interval, so a slow PASS was reported as findings) is the
    # TERMINAL findings transition (exit 3); any other reading resets
    # the streak to zero (a transient in the switch).
    findings_absent_streak = 0
    # User-taught refinements #2: the cold-NONE hint's state — any
    # EYES variant (verified or not) latches saw_any_eyes forever
    # (the bot demonstrably started), and cold_none_since tracks the
    # current continuous NONE streak's first elapsed reading so the
    # hint can fire exactly once at the COLD_NONE_GRACE_SECS mark.
    saw_any_eyes = False
    cold_none_since = None
    cold_hinted = False
    # Thread 3869941505 (PR #49 round 14, P1): the transition-NONE
    # gate — True from a detected head move until something
    # certifies the NEW head's round. While gated, a NONE reading
    # does NOT arm the latch: the old head's non-atomic
    # EYES-removal/+1 switch reads NONE at exactly the transition
    # probe (and until certification), and that generic arm would
    # hand the old head's delayed +1 — created after the
    # observation, passing the new head's older bounds and the EMPTY
    # watermark — a completion exit with the new head reviewed by
    # nobody. Thread 3870293205 (round 15, P1): the gate initializes
    # True at WAIT START too — a cold NONE on the first stable-head
    # probe certifies nothing until the round proves itself. Thread
    # 3870734078 + 3870734085 (round 16, P1): the ONLY opener is a
    # verified EYES (state == REACTION_ACTIVE; see the opener logic
    # in the loop) — round-14's post-floor marker opener and
    # round-15's marker/request ADVANCE openers are retired, and the
    # request-advance reset re-CLOSES this gate (a re-request
    # supersedes the old round's certifications, a gate its EYES
    # opened included). Round 5's initial-+1 protection survives
    # through the REPLACEMENT path (the held baseline + round-13's
    # strictly-newer ordering), and a legitimate fast round starting
    # inside a cold-NONE window may conservatively hold to timeout —
    # the accepted price (the survey is the authority).
    none_arming_gated = True
    # Thread 3870293188 (PR #49 round 15, P1): the REQUEST high-water
    # — round-13's separate formal-request element (the reading's
    # sixth element), retained like the marker high-water but kept
    # SEPARATE from it: the composite marker mixes in post-EYES
    # comments (a request-less round's own engagement), while the
    # REQUEST alone names the formal round boundary a re-request
    # creates. readable_probe_seen pins the cold-start baseline
    # rule: the FIRST readable probe initializes both high-waters
    # (a request/marker predating the wait is the normal cold start
    # — no reset, no gate-opening), and only STRICT advancement
    # observed mid-wait is new bot activity.
    request_high_water = ""
    # Thread 3871485055 (PR #49 round 18, P1): the TRIGGER high-water
    # — the per-kind twin of the request stream. The round-17 merged
    # boundary collapsed a formal request and a trigger comment
    # created in the same timestamp second (max identity string), so
    # when the retained boundary held the LARGER id a genuinely-later
    # boundary of the OTHER kind never advanced the single high-water
    # and the preceding round's armed EYES + delayed +1 still exited
    # 0 before the new round started. The two kinds now retain and
    # advance INDEPENDENTLY; the reset + gate re-close fire when
    # EITHER advances. The EYES binding and the composite marker keep
    # composing through the MERGED boundary inside the reading —
    # classification maxes the kinds' createdAt halves, retention
    # never merges.
    trigger_high_water = ""
    # Thread 3871844576 (PR #49 round 19, P2): the per-kind SEEN-SETS
    # — every boundary identity any probe observed. The high-waters
    # retain only the latest identity, so a same-second boundary that
    # is deleted and later RESURFACED (a distinct node id) counterfeit
    # a new forward boundary through the distinctness tie-break and
    # spuriously reset a running round; the sets remember the
    # resurfacing (boundary_advances in the latch module) and the
    # high-waters only move on UNSEEN identities. Thread 3872194007
    # (round 20, P2): the sets also union the walks' COLLECTED
    # same-second identities — every sibling visible at the boundary
    # second is recorded the moment it is seen, so the newest-of-the-
    # second being deleted can never leave an unrecorded resurfacer.
    # (The round-19 request_floor that stood here is SUPERSEDED —
    # thread 3872194017, see the module docstring's round-20
    # section: the reading's round-13 boundary binding alone is the
    # floor now.)
    request_seen = set()
    trigger_seen = set()
    # Thread 3872980765 (PR #49 round 22, P1): the BOUNDARY floor —
    # the createdAt half of the latest boundary an ADVANCE observed
    # (stamped in the advance block below, the transition floor's
    # twin for the request/trigger stream). Post-advance completions
    # must carry review evidence SUBMITTING past it: the preceding
    # job's review that PREDATES the re-request cannot certify a +1
    # the newly requested round would ride. Monotone (max) like the
    # transition floor; '' (no advance ever observed) binds nothing —
    # the first readable probe's boundary is the cold-start baseline,
    # never a floor (the round-15 baseline rule).
    boundary_floor = ""
    # Thread 3874769245 (PR #49 round 27, P1): the BASE twins of the
    # head stream's observed oid and the boundary floors — the wait
    # compares the reading's .base attr (baseRefOid) across probes
    # exactly as it compares observed_head, and a change stamps
    # base_floor with the boundary's OWN timestamp (the reading's
    # .base_bound: max(base target pushedDate/committedDate, the
    # BaseRefChangedEvent createdAt) — NEVER the wait's observation
    # clock, the round-20/22/26 floor doctrine). '' (no base fact —
    # a legacy page, a cold start) binds nothing: head_changed
    # refuses the empty oid in both directions.
    # Thread 3875830806 (PR #49 round 31, P1): the base EVENT
    # high-water — the max .base_event_bound any readable probe has
    # SEEN (monotone max, never regresses; the first readable probe
    # initializes the baseline beside observed_base — the round-15
    # baseline rule). A `rebased` transition is event-backed ONLY
    # when the reading's event bound STRICTLY ADVANCES past this
    # high-water ON THE SAME PROBE as the oid change: event presence
    # is PERSISTENT (the query always returns the PR's LATEST
    # historical BaseRefChangedEvent/BaseRefForcePushedEvent), so a
    # NON-advancing stamp beside a fresh oid change is a HISTORICAL
    # LEFTOVER corresponding to no event of THIS transition — the
    # fast-forward class, where the round-30 observation floor
    # applies. Advancing stamps (the event fired WITH the move)
    # keep today's exact event-backed behavior: no observation
    # stamp, the boundary's own timestamp binds (the same
    # high-water discipline as the marker/request high-waters).
    observed_base = base_floor = base_event_high_water = ""
    readable_probe_seen = False
    while True:
        # Thread 3874769253 (round 27, P2): the probe's OWN start —
        # the timeout below fires only when a probe BEGAN
        # at-or-after the deadline; a probe that started before it
        # but whose later head/boundary reads crossed it gets ONE
        # more fresh reading (the promised final probe), then the
        # timeout. The old post-probe `monotonic() >= deadline`
        # check burned the final probe on any overlong earlier one
        # while its reaction endpoint had been fetched long before,
        # leaving a +1 that landed between that fetch and the
        # deadline unobserved.
        probe_started = pr_guard_reaction.time.monotonic()
        budget = pr_guard_reaction.probe_timeout_budget(
            deadline - probe_started
        )
        try:
            # Thread 3872740865 (round 22): transition_floor is NO
            # LONGER passed into the reading — the floor's only job
            # now is the EXIT gates below (a between-polls legitimate
            # EYES must certify and complete); the old head's
            # leftover EYES stales AT THE READING through the
            # round-15 headTransition event bound instead (the
            # 3869453944 shape re-owned by 3870293194).
            reading = pr_guard_reaction.bot_reaction_reading(
                pr,
                timeout_secs=budget,
                marker_floor=marker_high_water,
            )
            state, plus_one, head_oid, marker, detail, request, trigger, review_head = reading
            # Threads 3872194007/23 (round 20): the same-second
            # identity sets and the verdict stamp ride the reading's
            # tuple-subclass attrs (a plain-tuple mock reads the
            # legacy fallbacks — the zero-repin seam rule).
            # Thread 3874769245 (round 27): the base twins ride the
            # same attr pattern. Thread 3875623447 (round 30): the
            # EVENT portion of the base bound rides beside them (the
            # FF observation fallback's key — '' on a legacy tuple
            # reads the fallback class, inert while the oid never
            # changes). Thread 3875089273 (round 28): the head's own
            # bound is retained beside them (the RETURNING-OID
            # transition's detector — '' on a legacy tuple never
            # advances).
            request_ids = getattr(reading, "request_ids", None) or set()
            trigger_ids = getattr(reading, "trigger_ids", None) or set()
            review_stamp = getattr(reading, "review_stamp", "") or ""
            base_oid = getattr(reading, "base", "") or ""
            base_bound = getattr(reading, "base_bound", "") or ""; base_event_bound = getattr(reading, "base_event_bound", "") or ""
            head_bound_now = getattr(reading, "head_bound", "") or ""
        except (SystemExit, Exception):
            state = "UNREADABLE"
            plus_one = head_oid = marker = detail = request = ""
            trigger = review_head = base_oid = base_bound = base_event_bound = head_bound_now = ""
            request_ids, trigger_ids, review_stamp = set(), set(), ""
        elapsed = pr_guard_reaction.time.monotonic() - start
        # --accept-standing (user request 2026-08-28, no thread ID —
        # the standalone repo's first post-extraction feature): the
        # OPT-IN fast path for already-passed PRs. A DONE-CLASSIFIED
        # THUMBS_UP exits 0 immediately, standing or observed — the
        # explicit opt-in IS the authority for the observation gates
        # (round 5's saw_non_done, round 7's replaced, round 9's
        # watermark) and the review-evidence legs (rounds 17/18/20/22/
        # 25's head_bound/review_head/review_stamp — the zero-review-
        # object '' shape included: every zero-findings pass posts no
        # review object, so round 25 withholds on it by default).
        # What it NEVER bypasses: the +1's own staleness
        # CLASSIFICATION at the reading (bot_reaction_reading's
        # round-bounds binding) — a +1 predating the head push or the
        # boundary markers reads THUMBS_UP_STALE and holds to timeout
        # (a stale verdict is not "codex said this PR is fine"); only
        # state == REACTION_DONE accepts, never STALE/UNVERIFIED/
        # UNREADABLE. Placement: BEFORE every latch/exit leg and the
        # HOLDING banners, so the opt-in path runs no gate machinery
        # at all; the default (flagless) path is byte-identical.
        if accept_standing and state == pr_guard_reaction.REACTION_DONE:
            print(f"WAIT DONE (ACCEPTED STANDING): THUMBS_UP at {elapsed:.0f}s — the --accept-standing opt-in bypassed the observation and review-evidence gates (rounds 5/25); the staleness classification still applied (only a DONE-classified +1 accepts). The accepted risk: a standing pass may predate an unposted new round — thread state remains the merge authority (run survey/pre-merge before any merge).")
            return 0
        # Thread 3868443452 (round 8, P1): the reset runs BEFORE this
        # probe's own reading contributes — an arming (or a DONE)
        # certified under the NEW head must not ride a latch armed
        # under the OLD one, and the baseline re-captures the CURRENT
        # reaction so the unchanged pre-move +1 can never exit by
        # replacement either. head_changed refuses empty oids: a
        # failed round probe is not a head move, and it never updates
        # the observed baseline.
        # Thread 3868443452 (round 8, P1) + 3874769245 (round 27,
        # P1): the two move detectors — the HEAD oid and the BASE oid
        # each key the SAME reset family (a base retarget/tip advance
        # changes the reviewed diff while headRefOid stays unchanged,
        # so the head-keyed bracket alone could not see it).
        # Thread 3875089273 (PR #49 round 28, P1): the RETURNING-OID
        # fold — `returned` is a probe whose oid EQUALS observed_head
        # while its head_bound strictly ADVANCES past the retained
        # observed_head_bound: A->B->A entirely between polls, where
        # the force-push event genuinely moved (round-15/26 semantics
        # — the event exists only when the ref moved, so the advance
        # is never a false positive) yet the oid-only compare reports
        # no move. It fires the SAME reset family and advances
        # transition_floor (monotone max) below — the pre-cycle job's
        # review then fails the stamp leg at the EXIT (the arm
        # relaxes, the exit guards). '' bounds never advance (the
        # empty rule; a legacy plain-tuple reading reads '').
        moved = pr_guard_reaction.head_changed(observed_head, head_oid)
        returned = bool(observed_head_bound) and head_bound_now > observed_head_bound
        rebased = pr_guard_reaction.head_changed(observed_base, base_oid)
        if moved or returned:
            # Thread 3869453944 (round 13) stamped the transition
            # OBSERVATION here — the wait's own wall clock, which a
            # between-polls review PREDATES; thread 3874405295
            # (round 26) stamps the HEAD'S OWN BOUND instead (the
            # reading's `head_bound` attr — max(pushedDate, the
            # headTransition force-push event), monotone across
            # moves, '' binds nothing: the head leg still guards,
            # round 25). [The round-13 demotion block that stood
            # here was deleted by round 22 / thread 3872740865 — the
            # ARM relaxes, the EXIT guards.] Thread 3875089273
            # (round 28): the stamp consumes the retained
            # head_bound_now (the returning-OID fold's own bound).
            transition_floor = max(transition_floor, head_bound_now)
            print(f"HEAD {'RETURNED' if returned and not moved else 'MOVED'}: {observed_head[:7]} -> {head_oid[:7]} at {elapsed:.0f}s/{timeout_secs}s — the transition latch and the held +1 baseline reset (threads 3868443452 + 3875089273): readings certified against the old head do not certify the new one, so exit 0 needs a fresh post-change transition or a replaced +1.")
        if rebased:
            # Thread 3874769245 (round 27, P1): the base's OWN bound
            # — max(base target stamps, BaseRefChangedEvent createdAt)
            # — monotone like every floor; the review's commit.oid
            # names the HEAD, so head_bound cannot separate bases:
            # the review_stamp > base_floor leg below IS the
            # separation.
            base_floor = max(base_floor, base_bound)
            # Thread 3875623447 (PR #49 round 30, P1): the FF
            # OBSERVATION bound — the finding's own sanctioned
            # fallback, the ONE exception to the round-20/22/26 "no
            # observation floor" doctrine. When NO event stamp
            # contributed to base_bound (the reading's
            # base_event_bound — the fast-forward/null-dated class
            # round 29 documented as residue: round-29 live
            # verification proved the FF move fires NO PR event, so
            # no boundary-OWN timestamp exists), the target's own
            # dates are the potentially-OLD stamps of an
            # already-existing commit and an old-base review
            # postdating them sailed past the stamp leg to WAIT DONE
            # over a re-derived diff nobody reviewed. The wait's
            # OBSERVATION wall clock (the wall_iso_z formatting
            # round 26 deleted, revived for this one sanctioned arm —
            # the clock seam is pr_guard_reaction.time, so every FakeClock
            # fixture's wall advances with the sleeps) closes that
            # window: only review evidence SUBMITTING past the
            # observing probe completes. DOCUMENTED PRICES (owned in
            # the 3875623447 receipt): (a) a round completing
            # entirely within one interval after the FF move is HELD
            # — the next wait's cold start re-inits from the settled
            # bound (the stamp is wait-local, never persisted);
            # (b) an old-base review submitting AFTER the observation
            # stays indistinguishable (the standing documented-open
            # class — quiet watch + rulesets). Event-backed shapes
            # (retarget/force-update) keep their exact behavior: the
            # boundary's OWN timestamp already binds, and no
            # observation stamp is applied.
            # Thread 3875830806 (PR #49 round 31, P1): event-backed
            # means the event bound ADVANCED WITH THIS MOVE — event
            # presence alone is PERSISTENT (the query returns the
            # PR's latest HISTORICAL event forever), so a base that
            # fast-forwards on a PR with pre-wait event history kept
            # a nonempty .base_event_bound that skipped this floor
            # while certifying nothing about the transition (the
            # exact hole). The condition consumes the PRE-update
            # high-water: a stamp failing to strictly advance past
            # everything earlier probes saw is the historical-
            # leftover/FF class, and the observation floor applies
            # (round-30 semantics); an advancing stamp is the
            # event-fired-WITH-the-move class and keeps the exact
            # no-observation behavior (the round-30 event-backed
            # pins — their events advance with the move).
            if not (base_event_bound and base_event_bound > base_event_high_water): base_floor = max(base_floor, datetime.fromtimestamp(pr_guard_reaction.time.time(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            print(f"BASE CHANGED: {observed_base[:7]} -> {base_oid[:7]} at {elapsed:.0f}s/{timeout_secs}s — the base moved under an unchanged head (thread 3874769245): the reviewed diff changed, so the round latches/watermark reset and exit 0 needs review evidence submitted past the base's own bound.")
        # Thread 3875089273 (round 28): `returned` keys the family
        # too — the returning-OID transition supersedes the old
        # head's certifications exactly as an oid move does.
        if moved or returned or rebased:
            saw_non_done = False; arm_watermark = ""
            # Thread 3874405295 (round 26): the held baseline is
            # RETAINED through the move — the round-8 re-capture that
            # stood here (held_plus_one = plus_one) swallowed a
            # between-polls new +1 into the baseline and stranded the
            # completed round to timeout; the replacement now fires
            # against the PRE-move baseline with the round-17/18/20/
            # 25 exit-evidence legs guarding the old head's job at
            # the EXIT (an UNCHANGED pre-move +1 still never replaces
            # itself — identical identity, the round-8 rule's
            # substance).
            # User-taught refinements #2: the findings certifications
            # reset with the latch — an EYES certified under the OLD
            # head whose disappearance follows the move is the old
            # round ending, not the new head's findings signal.
            saw_verified_eyes = False; findings_absent_streak = 0
            # Thread 3869453959 (round 13, P2): the cold-NONE
            # detector resets TOO — head A's EYES must not suppress
            # head B's '@codex review' hint when codex never starts
            # for B (round-specific state, not wait-lifetime fact).
            saw_any_eyes = False; cold_none_since = None; cold_hinted = False
            # Thread 3869941505 (round 14, P1): the gate SETS here —
            # every NONE from this probe on is uncertified until the
            # new head's round proves itself (post-floor EYES or a
            # post-observation marker); see the variable's header.
            # Thread 3874769245 (round 27): a base change closes the
            # gate identically — the old base's round certifications
            # speak for a diff the new base rederives.
            none_arming_gated = True
        if head_oid:
            # Thread 3875089273 (round 28): the bound rides every
            # readable head (cold start initializes the pair; the
            # returning-OID detector above compares against it).
            observed_head, observed_head_bound = head_oid, head_bound_now
        if base_oid:
            # Thread 3875089260 (PR #49 round 28, P1): the COLD-START
            # base bound — the FIRST readable probe initializes
            # base_floor ALONGSIDE observed_base (a pre-wait base is
            # the round's FLOOR, not a transition — the boundary
            # baseline rule); INITIALIZATION, never a change: no
            # reset family fires (readable_probe_seen still False —
            # the round-15 baseline rule's exact keying).
            # Post-cold-start, completions on the stale base fail
            # review_stamp > base_floor — the old-base review
            # predates the current base's own bound (the mid-wait
            # stamp's same separation, thread 3874769245).
            # Thread 3876000978 (PR #49 round 32, P1): the COLD-START
            # FF fallback — when the settled base bound is NOT
            # event-backed (no .base_event_bound — the round-30/31
            # criterion), it is the potentially-OLD committedDate of
            # an already-existing commit (round-29 live verification:
            # the FF move fires NO PR event), and an old-base review
            # submitted after that date but BEFORE this wait began
            # passed the stamp leg to WAIT DONE over a re-derived
            # diff nobody reviewed. The cold start additionally
            # stamps the OBSERVATION wall clock (the round-28
            # cold-start rule + the round-30 mid-wait fallback, one
            # shape — the clock seam pr_guard_reaction.time, so the
            # FakeClock fixtures' wall advances with the sleeps).
            # Thread 3876172341 (PR #49 round 33, P1): the stamp is
            # now UNCONDITIONAL — event PRESENCE certifies nothing at
            # cold start (it is PERSISTENT: a PR with an OLD
            # historical BaseRefChangedEvent/BaseRefForcePushedEvent
            # that later fast-forwards keeps a nonempty
            # .base_event_bound describing no transition of the
            # current base, and round 32's conditional suppressed
            # this floor for exactly that race). No prior probe
            # exists to run the round-31 advance comparison, so the
            # wall stamps alongside base_bound and the MAX keeps it
            # inert whenever the bound is genuinely at/after it.
            # THE OWNED PRICE (owned in the receipt, now paid by the
            # event-backed class too): a round whose review submits
            # before the wait's first readable probe predates the
            # observation and is held — the survey is the authority;
            # post-first-probe work clears the wall (pinned in
            # pr_guard_reaction_round33_test), and the mid-wait
            # `rebased` block above keeps the round-31 discipline.
            if not readable_probe_seen: base_floor = max(base_floor, base_bound, datetime.fromtimestamp(pr_guard_reaction.time.time(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            observed_base = base_oid  # '' never certifies (the head rule)
            # Thread 3875830806 (round 31, P1): the event high-water
            # update — every readable probe, monotone max ('' never
            # regresses it); consumed by the rebased block ABOVE
            # against its PRE-update value, so the move probe's own
            # stamp never certifies itself.
            base_event_high_water = max(base_event_high_water, base_event_bound)
        # Thread 3870293188 (round 15, P1): the mid-wait request
        # ADVANCE detection — computed against the PRE-update
        # high-water, so the FIRST readable probe's baseline (and an
        # unreadable probe's '' contribution, which never lowers the
        # high-water) can never read as an advance. Thread
        # 3870734078 (round 16, P1): the marker twin of this
        # detection is GONE from the gate logic — markers certify
        # nothing (no round or head identity) — and the marker
        # high-water below survives purely as the +1 classification's
        # floor. Thread 3870995905 (round 17, P1): the compare is the
        # IDENTITY rule — strictly-newer createdAt OR a same-second
        # DISTINCT node id (request_advances in the latch module) —
        # so a re-request landing inside the standing request's
        # timestamp second still resets; thread 3870995911 (round
        # 17, P1): the boundary stream merges the documented
        # '@codex review' TOP-LEVEL comment trigger (ANY author,
        # identity createdAt|comment node id) with the formal
        # request — a posted trigger while the wait observes a
        # preceding round ADVANCES exactly like a re-request. Thread
        # 3871844576 (round 19, P2): the compare is SET-guarded
        # (boundary_advances) — an identity ANY earlier probe of the
        # kind observed never advances again, so a deleted-then-
        # resurfaced same-second boundary reads as the round's
        # continuation, never a counterfeit re-request.
        request_advanced = readable_probe_seen and pr_guard_reaction.boundary_advances(
            request, request_high_water, request_seen
        )
        # Thread 3871485055 (round 18, P1): the TRIGGER twin of the
        # advance detection — its OWN high-water, its OWN createdAt +
        # node-id distinctness compare, never a cross-kind max: a
        # same-second boundary of the other kind (however its id
        # sorts) neither fires nor suppresses this stream's advance.
        # Thread 3871844576 (round 19): seen-set guarded like the
        # request stream above.
        trigger_advanced = readable_probe_seen and pr_guard_reaction.boundary_advances(
            trigger, trigger_high_water, trigger_seen
        )
        # Thread 3868625463 (round 9, P1): the high-water update is
        # idempotent through unreadable probes (their '' marker
        # never lowers it) — an eviction or a read failure must not
        # erase a VERIFIED marker. Thread 3870293188 (round 15): the
        # request high-water updates the same way (its walk paginates
        # the full history, so it can only move forward on a readable
        # probe). Thread 3871485055 (round 18): the trigger high-water
        # RETAINS independently — both kinds of one second register.
        # Thread 3871844576 (round 19): the SEEN-SET records every
        # observed identity, and the high-waters move only on UNSEEN
        # ones — a resurfacing never regresses the retention.
        marker_high_water = pr_guard_reaction.effective_round_marker(marker_high_water, marker)
        # Thread 3872980771 (round 22, P2): the retention update is
        # MONOTONE — an unseen identity always records in the
        # seen-set (its later resurfacing must never counterfeit an
        # advance), but the HIGH-WATER moves only when
        # boundary_advances ACCEPTED it (newer-or-unseen-forward) or
        # the first readable probe initializes the baseline. The
        # pre-fix update assigned every unseen identity directly to
        # the high-water: a deleted newest boundary whose older
        # previously-unseen sibling became the stream REGRESSED the
        # retention, so a later resurfacing boundary between the two
        # misread as a FORWARD advance and spuriously reset a valid
        # round (the ROUND RE-REQUESTED reset withholding a live
        # completion to timeout).
        if request and request not in request_seen:
            request_seen.add(request)
            if not readable_probe_seen or request_advanced:
                request_high_water = request
        if trigger and trigger not in trigger_seen:
            trigger_seen.add(trigger)
            if not readable_probe_seen or trigger_advanced:
                trigger_high_water = trigger
        # Thread 3872194007 (round 20, P2): the seen-sets also record
        # every COLLECTED same-second identity (the walk's full-
        # identity stream) — a sibling visible beside the boundary
        # second's newest is remembered the moment it is seen, so the
        # newest's later deletion/omission cannot leave an unrecorded
        # resurfacer to counterfeit an advance.
        request_seen |= request_ids
        trigger_seen |= trigger_ids
        if state != "UNREADABLE":
            readable_probe_seen = True
        if request_advanced or trigger_advanced:
            # Thread 3870293188 (round 15, P1): the formal round
            # boundary MOVED — a re-request certifies a NEW round the
            # old certifications must not speak for, so the round
            # latches reset BEFORE this probe's own reading
            # contributes (the head-move block's rule: an arming or
            # a DONE certified by the OLD request cannot ride into
            # the newly requested one, whose EYES has not landed
            # yet). The high-waters stay (bot-activity facts; the
            # request feeds the composite anyway). Thread 3871485055
            # (round 18, P1): the reset fires when EITHER kind
            # advances on its own — a posted trigger while the wait
            # observes a preceding round is a new boundary exactly
            # like a re-request, however its same-second identity
            # sorts against the other kind's. [The round-19
            # observation-floor stamp that stood here (thread
            # 3871844565) is SUPERSEDED by 3872194017 — the module
            # docstring's round-20 section owns the trade.]
            kinds = "/".join(
                kind
                for kind, on in (("request", request_advanced), ("trigger-comment", trigger_advanced))
                if on
            )
            # Thread 3872980765 (round 22, P1): stamp the BOUNDARY
            # floor — the createdAt half of the latest retained
            # boundary (the advancing kind's fresh identity; the
            # other kind's high-water never sorts newer than a
            # boundary that just advanced against its own stream).
            # Post-advance completions must submit review evidence
            # PAST it: the preceding job whose review predates the
            # re-request cannot certify the +1 its post-request EYES
            # re-armed (the exit-evidence discipline of rounds
            # 17/18/20/21 extended to the request/trigger stream).
            # The residual — the old job's review ALSO postdating the
            # request — is DOCUMENTED-OPEN (the round-19/20 posture:
            # identical observables at the reaction API; the quiet
            # watch + rulesets backstop).
            boundary_floor = max([boundary_floor] + [w.partition("|")[0] for w in (request_high_water, trigger_high_water) if w])
            print(
                f"ROUND RE-REQUESTED: the {kinds} boundary advanced "
                f"to {request_high_water or trigger_high_water} at {elapsed:.0f}s (threads 3870293188 + 3871485055) — the round latches/watermark reset; exit 0 needs the newly requested round's "
                f"own transition."
            )
            saw_non_done = False; arm_watermark = ""
            # Thread 3874405318 (round 26): the held baseline is
            # RETAINED through the reset (the round-15 clearing that
            # stood here — held_plus_one = "" — discarded the
            # preceding +1 the replacement path needs when the
            # re-request AND the entire resulting round land between
            # two probes: the new +1 installed as the fresh baseline
            # at the end of the iteration and held unchanged to
            # timeout). The replacement now fires against the
            # PRE-advance baseline this iteration, and the round-22
            # boundary-floor stamp leg still withholds the preceding
            # job's pre-request review — the false-exit class closes
            # at the EXIT, not the reset.
            saw_verified_eyes = False; findings_absent_streak = 0
            # Thread 3871844567 (round 19, P2): the cold-NONE detector
            # resets TOO (the round-13 head-move symmetry, thread
            # 3869453959) — the prior round's EYES is round-specific
            # proof-of-start, not wait-lifetime fact, so a re-requested
            # round that never starts HINTS at the 10s mark instead of
            # holding the prior round's suppression to the timeout.
            saw_any_eyes = False; cold_none_since = None; cold_hinted = False
            # Thread 3870734078 (round 16, P1): the gate re-CLOSES
            # with the reset — a re-request supersedes every
            # certification the preceding round earned, INCLUDING a
            # none-arming gate its verified EYES opened: the five
            # assignments above were being undone in the same
            # iteration when the old EYES's gate stood open (the
            # switch-window NONE re-armed it, and the old job's
            # delayed +1 — postdating the new request, following the
            # emptied watermark — exited 0 before the newly requested
            # review started). Mirrors the head-move block's gate SET;
            # the round-13 request binding guarantees the only EYES
            # reading ACTIVE past this point is a verified
            # POST-REQUEST one, which re-opens immediately below.
            none_arming_gated = True
        # [The round-19 REQUEST-FLOOR demotion that stood here
        # (thread 3871844565) is REMOVED by round 20 / thread
        # 3872194017 — the reading's round-13 boundary binding alone
        # demotes pre-boundary EYES; the module docstring's round-20
        # section owns the supersession and its trade.]
        # Thread 3870734078 + 3870734085 (round 16, P1): the gate's
        # ONLY opener is a verified EYES (state == REACTION_ACTIVE —
        # the one classification that binds the head push, the formal
        # request, and the transition floor, rounds 11/13/15).
        # Round-14's post-floor marker opener and round-15's
        # request/marker ADVANCE openers are RETIRED: a marker or a
        # request carries NO head/round identity — a still-running
        # review of the OLD head can post a thread comment or a
        # submitted-review marker after the transition floor, and a
        # re-request says nothing about which job's reactions follow
        # it — so neither can certify the current round. The
        # conservative price (round-15 precedent, accepted): a
        # legitimate round that goes NONE→+1 with NO EYES ever
        # observed holds to timeout (the replacement path still exits
        # 0 when a baseline exists); the survey is the authority.
        # 3870734078's alternative "a later bot marker" opener has
        # exactly the same no-identity problem, hence EYES-only.
        if none_arming_gated and state == pr_guard_reaction.REACTION_ACTIVE: none_arming_gated = False
        if pr_guard_reaction.arms_transition_latch(state) and not (
            none_arming_gated and state == pr_guard_reaction.REACTION_NONE
        ):
            saw_non_done = True
            # Thread 3868625469 (round 9, P1): every arming reading
            # refreshes the watermark to ITS latest reaction — the
            # observed activity the accepted +1 must postdate. Round
            # 14 (3869941521): a NONE arms with NO reaction object,
            # and refreshing to '' would REGRESS the watermark to
            # bind-nothing (erasing the observed EYES's identity
            # through the very removal under investigation — the
            # exposed prior +1 would then "follow" the empty
            # watermark and exit 0), so the watermark only ever
            # moves FORWARD (a nonempty identity), mirroring round
            # 13's ordered-replacement rule.
            if plus_one:
                arm_watermark = plus_one
        # Thread 3868625469 (round 9, P1): the round's two acceptance
        # predicates — the +1 follows the observed activity, and (for
        # the replacement exit) it demonstrably replaced the held one.
        follows = pr_guard_reaction.reaction_follows(plus_one, arm_watermark)
        replaced = pr_guard_reaction.replaced_plus_one(held_plus_one, plus_one)
        # Thread 3870995919 (round 17, P1): the HEAD-BOUND completion
        # check — post-move (a transition floor exists), an accepting
        # +1 must carry head-bound evidence: the latest BOT review's
        # commit oid (the head that review ran against — the bot's +1
        # is its POST-review verdict) equals the observed head. The
        # review job for head A that had not posted EYES when the
        # move was detected posts its EYES AFTERWARD (post-floor,
        # ACTIVE — it opens the gate and arms; the arm alone can
        # never exit without a +1, so the gate stays openable), but
        # A's later +1 submits review(A) != B and HOLDs; B's own
        # round submits review(B) and completes — the race dies at
        # the EXIT, not the arm, so no post-move round strands. A
        # COLD START (no floor — the request-less rule) keeps
        # today's behavior: the check is not even consulted, and an
        # unreadable review read ('') WITHHOLDS the completion
        # conservatively (never done-on-ambiguity).
        # Thread 3871485035 + 3871485043 (round 18, P1/P2): the
        # evidence is FOLDED — review_head rides the reading's eighth
        # element, extracted from the SAME round-query subprocess the
        # stable-head bracket certifies (one probe, one bracket: a
        # mid-sequence head move discards the evidence WITH the probe
        # as an UNREADABLE bracket, and a post-bracket lookup window
        # no longer exists), and the author-filtered connection means
        # no fixed ten-review window of other reviewers can evict
        # the connector's review and hold a valid completion to
        # timeout. The pre-round-18 separate latest_review_commit
        # subprocess ran AFTER the bracket and could return the
        # prior head's review against a stale observed_head — the
        # exact race the fold eliminates; the wait never dispatches
        # a second lookup.
        # Thread 3872194023 (PR #49 round 20, P1) — the REVIEW-STATE
        # completion bind. LIVE-VERIFIED read-only 2026-08-27 (PR #49
        # findings rounds + PR #48's pass round, the round-15/18
        # precedent): the reviews' `state` field does NOT separate
        # findings from passes — every connector review on both PRs
        # renders COMMENTED — so the state-based bind the finding
        # names is UNAVAILABLE and the strongest evidence-supported
        # guard binds to the folded VERDICT STAMP instead: post-move,
        # a completing +1 requires the latest head-bound bot review
        # to (a) name the observed head (round 17), (b) SUBMIT after
        # the transition floor (a review predating the floor is a
        # pre-move leftover whose oid matches only by the retarget
        # coincidence — the head was reviewed before the ref came
        # back to it), and (c) be followed by the +1 (the PR #48
        # live verdict shape: submission -> pass; carried through the
        # UNEVICTABLE author-filtered fold, so the latestReviews
        # marker window's ten-human eviction cannot unbind it). ''
        # stamps withhold like '' oids (never evidence). The exact
        # named out-of-order race (a NEW head's findings review
        # submitting BEFORE the old head's delayed +1, all post-
        # boundary) is DOCUMENTED-OPEN: with COMMENTED-only states
        # and no reaction-to-review association at the API, its
        # observable sequence is identical to a legitimate pass —
        # the post-merge quiet watch + the server rulesets remain
        # the standing backstop.
        # Thread 3872980765 (PR #49 round 22, P1): the SAME
        # exit-evidence discipline extends to request/trigger
        # advances — floor is the LATER of the transition floor and
        # the boundary floor, so a post-advance completion's review
        # evidence must submit past the ADVANCING BOUNDARY too (a
        # same-head re-request leaves review_head == observed_head
        # trivially true for the old job — the stamp leg is what
        # binds the +1 to the newly requested round; the old job's
        # review that submitted before the re-request fails it).
        # Thread 3874769245 (round 27, P1): the BASE floor joins the
        # max — the same separation for a base change (the review's
        # oid names the unchanged head; only the stamp leg separates
        # the old base's review from the new base's round).
        # Thread 3873970933 (PR #49 round 25, P1): the head leg is
        # now COLD-START too — the pre-fix `floor and ...` guard
        # skipped review_head validation entirely when floor was ''
        # (a wait starting AFTER a head change: no transition floor,
        # no boundary advance), so the OLD head's still-running job
        # posting its EYES and +1 after the new head was pushed
        # armed the latch and exited 0 even though the folded review
        # named the OLD commit. BOTH +1 exits and the findings exit
        # require the folded review to NAME THE OBSERVED HEAD,
        # floored or not: '' review_head withholds (no review -> no
        # verdict — the +1 is a POST-review verdict per the PR #48
        # live evidence), while the STAMP/FLOOR legs stay
        # floored-only (a cold start has no floor — none is
        # invented).
        # Thread 3874769241 (PR #49 round 27, P2): the
        # +1-follows-stamp leg is EQUALITY-SAFE (`>=`) — the round-27
        # SUPERSESSION of the round-10 strictness FOR THIS LEG ONLY
        # (the classification legs keep strict `>`): the review
        # submission and its +1 verdict can share one API timestamp
        # second, and the reaction object is IMMUTABLE, so a
        # same-second reject strands the passed round FOREVER; the
        # false-accept surface the strict leg guarded is already
        # owned by the other legs (review_head == observed_head,
        # review_stamp > floor), and a stable-id tie-breaker is
        # UNAVAILABLE — the folded review stamp carries no REST id.
        floor = max(transition_floor, boundary_floor, base_floor)
        head_bound = bool(review_head) and review_head == observed_head
        if floor and state == pr_guard_reaction.REACTION_DONE:
            head_bound = head_bound and review_stamp > floor and plus_one.partition("|")[0] >= review_stamp
        # User-taught refinements #2: track the EYES facts — a
        # LATCH-ARMING EYES (the arms set's only EYES: verified
        # current-head) arms the findings precursor; ANY variant
        # (stale/unverified included) permanently proves the bot
        # started, so the cold-NONE hint can never fire afterwards.
        if state == pr_guard_reaction.REACTION_ACTIVE: saw_verified_eyes = True; eyes_watermark = plus_one
        if state in pr_guard_reaction.EYES_VARIANTS:
            saw_any_eyes = True
        if state != last:
            print(
                f"BOT REACTION: {pr_guard_reaction.render_state(state, detail)} "
                f"at {elapsed:.0f}s/{timeout_secs}s"
            )
            if state == pr_guard_reaction.REACTION_DONE and not saw_non_done and not held_plus_one:
                print(
                    f"HOLDING THUMBS_UP: the +1 was already present "
                    f"when the wait started and no confirmed state change (EYES, "
                    f"marker-driven stale, or none) has landed since — it may predate "
                    f"a request-less round that has not yet posted anything (thread "
                    f"3867897766). Exit 0 needs the observed active->done transition "
                    f"or a demonstrably NEW +1 (thread 3868158293); polling continues."
                )
            if state == pr_guard_reaction.REACTION_DONE and saw_non_done and not follows:
                print(
                    f"HOLDING THUMBS_UP: this +1 does not follow the "
                    f"observed activity watermark — a NEWER reaction (e.g. the round's EYES) was observed before this same +1 became latest again (a non-atomic switch may have re-surfaced the prior round's pass; "
                    f"thread 3868625469); polling continues."
                )
            last = state
        if state == pr_guard_reaction.REACTION_DONE and saw_non_done and follows and head_bound:
            print(
                f"WAIT DONE: THUMBS_UP at {elapsed:.0f}s — the review is "
                f"complete and passed (bot {pr_guard_reaction.REACTION_BOT}); the +1 follows the observed activity (thread 3868625469). The reaction is "
                f"the DONE/ACTIVE signal ONLY: thread state remains the merge authority (run survey/pre-merge before any merge), and the "
                f"post-merge quiet-period watch still guards the landed tree "
                f"(vault note '{pr_guard_reaction.VAULT_NOTE}')."
            )
            return 0
        if state == pr_guard_reaction.REACTION_DONE and replaced and follows and head_bound:
            print(
                f"WAIT DONE: THUMBS_UP at {elapsed:.0f}s — a NEW +1 "
                f"(threads 3868158293 + 3868625469: the initial-held one was OBSERVED REPLACED by a different reaction object that already "
                f"passed the round-bounds classification and follows the observed activity watermark, so the fast EYES->+1 round never had to be "
                f"sampled). The reaction is the DONE/ACTIVE signal ONLY: thread state remains the merge authority (run survey/pre-merge before "
                f"any merge), and the post-merge quiet-period watch still guards the landed tree (vault note '{pr_guard_reaction.VAULT_NOTE}')."
            )
            return 0
        accepting = state == pr_guard_reaction.REACTION_DONE and follows and (
            saw_non_done or replaced
        )
        if accepting and not head_bound:
            print(
                f"HOLDING THUMBS_UP: this +1's round cannot be proven "
                f"to have reviewed the current head — the latest bot review's commit is not the observed "
                f"head or no folded review names it, predates the transition, the advancing boundary, or a base change, or postdates this +1 "
                f"(threads 3870995919 + 3872194023 + 3872980765 + 3873970933 + 3874769245 + 3875089260 + 3875352284 + 3875623447 + 3875830806 + 3876000978 + 3876172341: a prior head's, prior request's, or prior base's "
                f"delayed job passes every timestamp check, or its verdict predates the "
                f"current round's own review, while the current head was reviewed "
                f"by nobody); polling continues."
            )
        # User-taught refinements #2 (vault note section 'User-taught
        # refinements #2'): the NONE discrimination. A completion-
        # ABSENT probe either CONFIRMS the pending findings transition
        # (exit 3 — the arming EYES's round ended with feedback; runs
        # BEFORE the deadline check so an at-deadline confirming probe
        # still reports findings, not timeout) or feeds the cold-NONE
        # hint (grace seconds of continuous NONE with no EYES variant
        # ever observed — the hint fires exactly once and polling
        # continues; UNREADABLE probes preserve the streak, a read
        # failure is not a state change). Thread 3869941521 (round
        # 14, P1): the absence signal is TWO-shaped — literal NONE, or
        # a THUMBS_UP PROVEN older than the observed arming EYES
        # (DONE-classified yet NOT following the watermark: the exact
        # shape the pass exits and the replacement predicate already
        # reject — the prior round's +1 EXPOSED by the removal of the
        # current round's EYES). Same discipline as the NONE path: the
        # verified-EYES precursor (a bare non-following +1 with NO
        # EYES ever observed is the round-5 initial-hold shape, never
        # exit 3), streak persistence across absent probes, any other
        # reading resets the streak (UNKNOWN included — thread
        # 3869941509: an unrecognized reaction is a real observation
        # that BREAKS the persistence, never one that satisfies it).
        # Thread 3873317562 (round 23, P2): the confirmation now needs
        # FINDINGS_GRACE_PROBES consecutive absent probes — the
        # non-atomic switch can take MORE than one poll interval to
        # publish the passing round's replacement +1 (GitHub/connector
        # latency), and the round-12 single-confirming-probe design
        # reported that slow PASS as findings.
        # Thread 3875830819 (PR #49 round 31, P2): the absence signal
        # gained its THIRD shape — a THUMBS_UP_STALE-classified +1
        # PROVEN older than the arming EYES (the marker postdates the
        # exposed prior-round pass because the findings round posted a
        # review-thread comment or submitted review AFTER its EYES;
        # the DONE-not-following leg of round 14 never matched the
        # STALE classification, so the resurfaced prior pass reset
        # this streak on every probe and a real findings round timed
        # out instead of exiting 3). The round-14 DONE shape is
        # unchanged; the verified-EYES precursor stands (no EYES ->
        # no findings exit); the exit-3 evidence gates below apply to
        # the stale shape exactly as to the others.
        completion_absent = state == pr_guard_reaction.REACTION_NONE or (
            saw_verified_eyes and not follows and (
                state == pr_guard_reaction.REACTION_DONE or (state == pr_guard_reaction.REACTION_STALE and not pr_guard_reaction.reaction_follows(plus_one, eyes_watermark))
            )
        )
        if completion_absent:
            if saw_verified_eyes:
                findings_absent_streak += 1
                if findings_absent_streak >= FINDINGS_GRACE_PROBES:
                    # Thread 3872631145 (PR #49 round 21, P2): the
                    # findings exit's EVIDENCE BIND — the same
                    # head/stamp legs the THUMBS_UP exits carry, with
                    # the +1-follows-stamp leg MOOT (no +1 is
                    # accepted here): the old head's still-running
                    # job can post a post-floor EYES, finish with
                    # feedback, and remove it, so the NONE pair
                    # carries ITS round's signal under a head it never
                    # reviewed. Unbound -> keep polling (the new
                    # head's round produces its own signal).
                    # Thread 3872980765 (round 22): the boundary
                    # floor joins the transition floor here too — a
                    # completion-absent signal after a re-request
                    # must carry review evidence past the ADVANCING
                    # BOUNDARY or it is the prior round's ending.
                    # Thread 3873970933 (round 25): the head leg is
                    # COLD-START here too — the findings exit
                    # requires the folded review to name the
                    # observed head floored or not ('' withholds:
                    # no review -> no verdict), the stamp leg stays
                    # floored-only.
                    if not (
                        review_head
                        and review_head == observed_head
                        and (not floor or review_stamp > floor)
                    ):
                        print(
                            f"HOLDING FINDINGS: this completion-absent signal cannot be proven to belong to the current head — the folded review evidence names another "
                            f"head or none at all, or predates the transition or the advancing boundary (threads "
                            f"3872631145 + 3872980765 + 3873970933); the new round will produce "
                            f"its own signal — polling continues."
                        )
                    else:
                        signal = (
                            "EYES → NONE"
                            if state == pr_guard_reaction.REACTION_NONE
                            else "EYES → a prior-round +1 (older than the observed EYES)"
                        )
                        print(
                            f"WAIT FINDINGS: {signal} at {elapsed:.0f}s — "
                            f"the review completed WITH feedback; survey the "
                            f"threads now (fix + receipt + re-wait)."
                        )
                        return 3
            if state == pr_guard_reaction.REACTION_NONE and not saw_any_eyes:
                if cold_none_since is None:
                    cold_none_since = elapsed
                elif not cold_hinted and (
                    elapsed - cold_none_since >= COLD_NONE_GRACE_SECS
                ):
                    print(
                        f"HINT: no EYES ever observed and "
                        f"{COLD_NONE_GRACE_SECS}s of NONE — the bot may "
                        f"have failed to start; consider posting a "
                        f"'@codex review' comment to trigger it manually."
                    )
                    cold_hinted = True
        else:
            findings_absent_streak = 0
            if state != "UNREADABLE":
                cold_none_since = None
        if state == pr_guard_reaction.REACTION_DONE and not held_plus_one: held_plus_one = plus_one
        # Thread 3874769253 (PR #49 round 27, P2): the timeout fires
        # only when THIS probe began at-or-after the deadline — a
        # probe that started before it but whose later head/boundary
        # reads crossed it already contributed its reading above and
        # gets exactly ONE more fresh probe (the promised final
        # read, riding the 1s probe_timeout_budget floor), whose own
        # start is necessarily past the deadline (the sleep clamps
        # to zero once past it) and ends the wait here.
        if probe_started >= deadline:
            held = (
                " The THUMBS_UP present since wait start never showed a confirmed transition"
                " away and back (thread 3867897766) nor a replaced reaction identity"
                " (thread 3868158293) — it may predate a request-less round that had not"
                " yet posted anything, so exit 0 was withheld."
                if last == pr_guard_reaction.REACTION_DONE
                else ""
            )
            print(
                f"WAIT TIMEOUT: {timeout_secs}s elapsed, last state "
                f"{pr_guard_reaction.render_state(last)} — the review never signaled a "
                f"current-round THUMBS_UP.{held} Re-run wait, or "
                f"survey the threads to see where the round stands."
            )
            return 1
        pr_guard_reaction.time.sleep(
            pr_guard_reaction.deadline_clamped_sleep(
                deadline, pr_guard_reaction.WAIT_INTERVAL_SECS
            )
        )
