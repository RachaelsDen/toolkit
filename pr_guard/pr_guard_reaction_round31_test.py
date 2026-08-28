"""pr_guard reaction round-31 tests (PR #49 threads 3875830806 P1 /
3875830819 P2): the transition-tied event evidence + the stale
resurfaced-pass absence, both wait-side halves.

Thread 3875830806 — "Tie event evidence to the current base
transition": round 30's observation fallback keyed on base_event_
bound PRESENCE, but event presence is PERSISTENT (the query always
returns the PR's LATEST historical BaseRefChangedEvent/
BaseRefForcePushedEvent), so a PR with pre-wait event history whose
base later FAST-FORWARDS (no new event, round-29 live verification)
kept a nonempty bound that skipped the observation floor while
certifying nothing about the current transition. The fix: the wait
retains base_event_high_water (monotone max over every readable
probe, baseline-initialized on the first), and a `rebased`
transition is event-backed ONLY when the reading's event bound
STRICTLY ADVANCES past it ON THE SAME PROBE as the oid change —
non-advancing (the historical leftover) applies the round-30
observation floor; advancing (the event fired WITH the move) keeps
today's exact event-backed behavior (the round-30 pins hold —
their events advance with the move, verified below with history).

Thread 3875830819 — "Count stale resurfaced passes as completion
absence": a findings round that posts a review-thread comment or a
submitted review AFTER its EYES advances the marker past the PRIOR
round's +1, so removing the EYES exposes a THUMBS_UP_STALE-classified
pass the round-14 DONE-not-following leg never matched — the streak
reset on every probe and a real findings round timed out instead of
returning WAIT FINDINGS. The predicate gains the STALE shape: a
STALE-classified +1 whose identity PREDATES the arming EYES
watermark (eyes_watermark, retained at each verified-EYES probe —
arm_watermark refreshes at every arming probe and a STALE reading
arms, so the refreshed watermark names the stale object itself and
orders nothing) counts as completion absence. The verified-EYES
precursor stands, the round-14 DONE shape is unchanged, and the
exit-3 evidence gates (round-25/26 head-naming + floors) apply
unchanged.

No network: REAL round_bounds/wait_reaction over scripted
ROUND_QUERY pages (the round-27/28/29/30 shape). FakeClock WALL_NOW
2023-11-14T22:13:20Z; every stamp keyed INSIDE the wall window (the
round-19 GOTCHA #2 rule) — the t=5 observation stamp reads exactly
22:13:25Z.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round31_test -v
"""

import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock

BOT = pr_guard_reaction.REACTION_BOT
BOT_LOGIN = pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN

HEAD_S = "20ab97ffffffffffffffffffffffffffffff5"
BASE_1 = "30ab97ffffffffffffffffffffffffffffff1"
BASE_2 = "30ab97ffffffffffffffffffffffffffffff2"

PUSH_A = "2023-11-14T22:00:00Z"
BASE_1_TIP = "2023-11-14T22:13:18Z"
# The pre-wait HISTORICAL BaseRefChangedEvent — a retarget from
# BEFORE this wait ever started; the query returns it FOREVER.
HIST_EVENT = "2023-11-14T22:05:00Z"
# The FF'd-to descendant commit's OWN committedDate (round-30's
# FF_TIP shape) and a NEW event firing WITH a move.
FF_TIP = "2023-11-14T22:13:21Z"
NEW_EVENT = "2023-11-14T22:13:22Z"
# The t=5 probe's OBSERVATION wall clock (WALL_NOW + 5s).
OBSERVED_AT = "2023-11-14T22:13:25Z"

# The stale-resurfaced timeline: the prior round's pass, the current
# round's verified EYES, its findings review, the marker (a thread
# comment / submitted review) that classifies the exposed prior pass
# STALE, and the marker-raced NEW +1 of the survivor pin.
PRIOR_PLUS_ONE = "2023-11-14T22:12:00Z"
EYES_AT = "2023-11-14T22:13:21Z"
FINDINGS_REVIEW = "2023-11-14T22:13:22Z"
MARKER_AT = "2023-11-14T22:13:23Z"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def gh_page(payload):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload))


def bot_node(oid, at):
    return {"author": {"login": BOT_LOGIN}, "commit": {"oid": oid}, "submittedAt": at}


def bounds_page(
    pushed, oid, review=None, marker=None, base=None, base_stamp=None, base_event=None
):
    """A well-formed ROUND_QUERY page (the round-30 builder); review/
    marker/base None keep their keys ABSENT (the round-18/27 legacy-
    minimal-payload rule); marker adds a bot-authored latestReviews
    node (the composite marker's submitted-review source), base
    carries baseRefOid + the live present-and-EMPTY event connections
    (base_event adds the historical BaseRefChangedEvent node)."""
    page = {
        "data": {
            "repository": {
                "pullRequest": {
                    "headRefOid": oid,
                    "headRef": {"target": {"pushedDate": pushed, "committedDate": pushed}},
                    "timelineItems": {
                        "pageInfo": {"hasPreviousPage": False, "startCursor": None},
                        "nodes": [],
                    },
                    "headTransition": {"nodes": []},
                    "latestReviews": {"nodes": []},
                    "reviewThreads": {"nodes": []},
                }
            }
        }
    }
    pr = page["data"]["repository"]["pullRequest"]
    if review is not None:
        pr["botReviews"] = {"nodes": [review]}
    if marker is not None:
        pr["latestReviews"] = {
            "nodes": [{"author": {"login": BOT_LOGIN}, "submittedAt": marker}]
        }
    if base is not None:
        pr["baseRefOid"] = base
        pr["baseRef"] = {"target": {"pushedDate": None, "committedDate": base_stamp}}
        pr["baseChange"] = {"nodes": [{"createdAt": base_event}] if base_event else []}
        pr["baseForce"] = {"nodes": []}
    return page


def run_wait(reads, pages, heads, timeout_secs):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    pages (the round-27/28/29/30 shape); heads scripts head_ref_oid per
    probe (the bracket's BEFORE side — always the stable head S)."""
    clock = FakeClock()
    items = iter(reads)
    script = iter(pages)
    head_reads = iter(heads)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_read
    ), mock.patch.object(
        pr_guard_reaction,
        "head_ref_oid",
        side_effect=lambda pr, timeout_secs=None: next(head_reads),
    ), mock.patch.object(
        pr_guard_reaction_probe.subprocess,
        "run",
        side_effect=lambda *a, **k: gh_page(next(script)),
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue()


class TransitionTiedEventEvidenceTests(unittest.TestCase):
    def test_historical_event_ff_move_withheld_by_transition_tied_evidence(self):
        # Given: the thread-3875830806 race — the PR carries a
        # HISTORICAL BaseRefChangedEvent from 22:05 (a pre-wait
        # retarget; the query returns it forever), and the wait
        # starts under the old-base job's EYES (22:13:19, base_1's
        # tip committed 22:13:18); between t=0 and t=5 the base
        # branch is FAST-FORWARDED to an already-existing descendant
        # (base_2, its OWN committedDate 22:13:21 — NO new event:
        # the historical 22:05 stamp is all the event connections
        # carry) while the old-base job submits review(S) at 22:13:23
        # (over base_1's diff) and its delayed +1 lands 22:13:27, the
        # EYES persisting across the move to re-arm the reset base.
        # When: wait polls 10s. Then: exit 1 — the t=5 base-change
        # reset consumes the PRE-update event high-water (22:05,
        # initialized by the t=0 probe), the reading's event bound
        # (the SAME historical stamp) does NOT advance past it, so
        # the move is NOT event-backed and the observation floor
        # (22:13:25) applies beside the old tip date — the t=10 stamp
        # leg withholds BY NAME (23 > 25 fails). The pre-fix round-30
        # check keyed on event PRESENCE (22:05 is nonempty), skipped
        # the observation stamp, and WAIT DONE exited 0 over the
        # re-derived diff nobody reviewed (the pre-fix proof:
        # 0 != 1, WAIT DONE).
        code, out = run_wait(
            [
                [react("eyes", "2023-11-14T22:13:19Z", 5)],
                [react("eyes", "2023-11-14T22:13:19Z", 5)],
                [react("+1", "2023-11-14T22:13:27Z", 7)],
            ],
            [
                bounds_page(
                    PUSH_A, HEAD_S, base=BASE_1, base_stamp=BASE_1_TIP,
                    base_event=HIST_EVENT,
                ),
                bounds_page(
                    PUSH_A, HEAD_S, base=BASE_2, base_stamp=FF_TIP,
                    base_event=HIST_EVENT,
                ),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:23Z"),
                    base=BASE_2, base_stamp=FF_TIP, base_event=HIST_EVENT,
                ),
            ],
            [HEAD_S, HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("BASE CHANGED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("3875830806", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_historical_event_advancing_with_move_keeps_event_backed_exit(self):
        # Given: the EVENT-BACKED no-regression pin WITH HISTORY —
        # the identical pre-wait historical event (22:05), but the
        # move probe carries a NEW BaseRefChangedEvent (22:13:22)
        # that fired WITH the retarget: the prior round's +1 (22:12)
        # is held at t=0, the new-base round submits review(S) at
        # 22:13:24 and its +1 (a new object) lands 22:13:26 — both
        # inside the t=0..t=5 interval. When: wait polls 10s. Then:
        # exit 0 at 5s on BOTH sides — the event bound STRICTLY
        # ADVANCES past the retained high-water (22:13:22 > 22:05)
        # on the move probe, so the transition IS event-backed, no
        # observation stamp is applied, and the event's own timestamp
        # (24 > 22) completes the replacement (an over-broad floor
        # would hold this round to timeout).
        code, out = run_wait(
            [
                [react("+1", PRIOR_PLUS_ONE, 1)],
                [react("+1", "2023-11-14T22:13:26Z", 6)],
            ],
            [
                bounds_page(
                    PUSH_A, HEAD_S, base=BASE_1, base_stamp=BASE_1_TIP,
                    base_event=HIST_EVENT,
                ),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:24Z"),
                    base=BASE_2, base_stamp=PUSH_A, base_event=NEW_EVENT,
                ),
            ],
            [HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("BASE CHANGED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)


class StaleResurfacedAbsenceTests(unittest.TestCase):
    def test_stale_resurfaced_pass_reaches_findings_after_grace(self):
        # Given: the thread-3875830819 race — the prior round's +1
        # (22:12) stands; the current round's EYES (22:13:21) is
        # observed VERIFIED at t=0; the round finishes WITH feedback:
        # review(S) submitted 22:13:22, a review-thread comment (the
        # marker, 22:13:23) lands AFTER the EYES, and the EYES is
        # removed — so every later probe reads the EXPOSED prior +1
        # classified THUMBS_UP_STALE (the new marker postdates it),
        # proven older than the observed EYES by identity. When:
        # wait polls 15s. Then: exit 3 — the STALE shape counts as
        # completion absence, the grace streak reaches
        # FINDINGS_GRACE_PROBES at t=15, and the evidence gates pass
        # (the folded review names the observed head, no floor
        # binds). The pre-fix predicate matched only a DONE state,
        # reset the streak on every STALE probe, and the wait timed
        # out instead of steering the survey (the pre-fix proof:
        # 1 != 3, WAIT TIMEOUT).
        code, out = run_wait(
            [
                [react("eyes", EYES_AT, 5)],
                [react("+1", PRIOR_PLUS_ONE, 1)],
                [react("+1", PRIOR_PLUS_ONE, 1)],
                [react("+1", PRIOR_PLUS_ONE, 1)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, FINDINGS_REVIEW),
                    marker=MARKER_AT,
                ),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, FINDINGS_REVIEW),
                    marker=MARKER_AT,
                ),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, FINDINGS_REVIEW),
                    marker=MARKER_AT,
                ),
            ],
            [HEAD_S, HEAD_S, HEAD_S, HEAD_S],
            15,
        )
        self.assertEqual(code, 3)
        self.assertIn("WAIT FINDINGS", out)
        self.assertIn("prior-round +1", out)
        self.assertNotIn("WAIT TIMEOUT", out)

    def test_stale_resurfaced_without_verified_eyes_times_out(self):
        # Given: the PRECURSOR pin — the identical stale exposure
        # (prior +1 22:12, marker 22:13:23, folded review naming the
        # head) but NO EYES variant is EVER observed: the wait starts
        # straight onto the exposed prior pass. When: wait polls 15s.
        # Then: exit 1 on BOTH sides — the verified-EYES precursor
        # stands (a bare stale +1 with no EYES ever observed is the
        # round-5 initial-hold shape, never a findings signal), so
        # no findings exit fires however long the streak would run.
        code, out = run_wait(
            [[react("+1", PRIOR_PLUS_ONE, 1)]] * 4,
            [
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, FINDINGS_REVIEW),
                    marker=MARKER_AT,
                ),
            ]
            * 4,
            [HEAD_S, HEAD_S, HEAD_S, HEAD_S],
            15,
        )
        self.assertEqual(code, 1)
        self.assertNotIn("WAIT FINDINGS", out)
        self.assertIn("WAIT TIMEOUT: 15s elapsed", out)

    def test_newer_stale_plus_one_following_eyes_not_absent(self):
        # Given: the PASS-RACE survivor — the current round's EYES
        # (22:13:21) observed verified at t=0, the round PASSES: its
        # own NEW +1 (22:13:22, a different object POSTDATING the
        # EYES) lands while the round's thread comment (the marker,
        # 22:13:23) postdates the +1 — so the reading classifies it
        # THUMBS_UP_STALE exactly like the resurfaced prior pass, but
        # its identity FOLLOWS the observed EYES. When: wait polls
        # 15s. Then: exit 1 on BOTH sides — the stale-absence leg
        # requires the +1 PROVEN older than the arming EYES
        # (eyes_watermark); a stale-classified pass that follows the
        # EYES is the current round's own marker-raced verdict, never
        # completion absence (without the proven-older leg this
        # shape would counterfeit WAIT FINDINGS on a PASS).
        code, out = run_wait(
            [
                [react("eyes", EYES_AT, 5)],
                [react("+1", "2023-11-14T22:13:22Z", 6)],
                [react("+1", "2023-11-14T22:13:22Z", 6)],
                [react("+1", "2023-11-14T22:13:22Z", 6)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, FINDINGS_REVIEW),
                    marker=MARKER_AT,
                ),
            ]
            * 2,
            [HEAD_S, HEAD_S, HEAD_S, HEAD_S],
            15,
        )
        self.assertEqual(code, 1)
        self.assertNotIn("WAIT FINDINGS", out)
        self.assertIn("WAIT TIMEOUT: 15s elapsed", out)

    def test_done_not_following_resurfaced_pass_still_exits_findings(self):
        # Given: the ROUND-14 SCOPE pin — the identical exposure
        # (verified EYES 22:13:21 at t=0, then the prior round's +1
        # 22:12 latest again) but with NO marker postdating the pass,
        # so the reading classifies it DONE (22:12 > the 22:00 push)
        # and the round-14 DONE-not-following leg carries it. When:
        # wait polls 15s. Then: exit 3 on BOTH sides — the sibling
        # DONE shape is UNCHANGED by the round-31 arm (the streak,
        # the grace, and the evidence gates behave identically), and
        # the folded review naming the head still satisfies the
        # exit-3 gates.
        code, out = run_wait(
            [
                [react("eyes", EYES_AT, 5)],
                [react("+1", PRIOR_PLUS_ONE, 1)],
                [react("+1", PRIOR_PLUS_ONE, 1)],
                [react("+1", PRIOR_PLUS_ONE, 1)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S),
                bounds_page(PUSH_A, HEAD_S, review=bot_node(HEAD_S, FINDINGS_REVIEW)),
            ]
            * 3,
            [HEAD_S, HEAD_S, HEAD_S, HEAD_S],
            15,
        )
        self.assertEqual(code, 3)
        self.assertIn("WAIT FINDINGS", out)
        self.assertNotIn("WAIT TIMEOUT", out)


if __name__ == "__main__":
    unittest.main()
