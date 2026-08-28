"""pr_guard reaction round-30 tests (PR #49 threads 3875623447 P1 /
3875623455 P2): the FF-base observation bound's wait half + the
base_event_bound parse pins (the deterministic budget-test half of
3875623455 lives in pr_guard_reaction_followup_test — the round-2
suite whose flake it fixes).

Thread 3875623447 — "Track fast-forward base moves at ref-update
time": round 29 closed the FORCE-updated half with
BaseRefForcePushedEvent's own createdAt; the FAST-FORWARD half (the
base advanced to an ALREADY-EXISTING descendant commit) fires NO PR
event (round-29 live verification), so the fallback bound read the
commit's OLD committedDate and an old-base review postdating it —
while the head stayed UNCHANGED, review_head == observed_head
trivially — passed `review_stamp > base_floor`, its delayed EYES
re-armed the reset base, and WAIT DONE exited 0 over the re-derived
diff nobody reviewed. The fix is the finding's own sanctioned
fallback (its text: "or conservatively require post-observation
review evidence when the base OID changes without a corresponding
event timestamp"): the probe threads the EVENT portion of the base
bound out separately (.base_event_bound — '' when neither
baseChange nor baseForce contributed), and when a base change fires
with NO event stamp the wait stamps base_floor with its OBSERVATION
wall clock (the ONE sanctioned exception to the round-20/22/26 "no
observation floor" doctrine — no boundary-OWN timestamp exists for
the FF class). The stamp gates the EXIT leg only.

THE TWO DOCUMENTED PRICES (owned here and in the receipt): (a) a
round completing ENTIRELY within one poll interval after an FF base
move is held for that round — its review predates the observing
probe; the NEXT wait recovers (its cold start re-initializes
base_floor from the settled base bound; the observation stamp is
wait-local, never persisted). (b) an old-base job whose review
submits AFTER the observation remains indistinguishable from the
new-base round's own pass at the reaction API (no job identity —
the standing documented-open class, the quiet watch + rulesets the
backstop). The event-backed retarget/force shapes keep their exact
behavior (no observation stamp — pinned by the same-interval
survivors below).

No network: REAL round_bounds/wait_reaction over scripted
ROUND_QUERY pages (the round-27/28/29 shape). FakeClock WALL_NOW
2023-11-14T22:13:20Z; the stamps keyed INSIDE the wall window (the
round-19 GOTCHA #2 rule) — the observation stamp at the t=5 probe
reads exactly 22:13:25Z, and the review stamps 22:13:23/24 sit
between the FF tip's old date 22:13:21 and that observation.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round30_test -v
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
# The FF'd-to descendant commit's OWN committedDate — it EXISTS
# since 22:13:21, long BEFORE the ref fast-forward moved onto it.
FF_TIP = "2023-11-14T22:13:21Z"
BASE_EVENT = "2023-11-14T22:13:22Z"
# The t=5 probe's OBSERVATION wall clock (WALL_NOW + 5s) — the
# observation bound the not-event-backed reset stamps.
OBSERVED_AT = "2023-11-14T22:13:25Z"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def gh_page(payload):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload))


def bot_node(oid, at):
    return {"author": {"login": BOT_LOGIN}, "commit": {"oid": oid}, "submittedAt": at}


def bounds_page(pushed, oid, review=None, base=None, base_stamp=None, base_event=None, base_force=None):
    """A well-formed ROUND_QUERY page (the round-29 builder + the
    retarget node); review/base* None keep their keys ABSENT (the
    round-18/27 legacy-minimal-payload rule); base carries baseRefOid
    + the live present-and-EMPTY event connections (the FF shape:
    neither event exists), base_event/base_force add the nodes."""
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
    if base is not None:
        pr["baseRefOid"] = base
        pr["baseRef"] = {"target": {"pushedDate": None, "committedDate": base_stamp}}
        pr["baseChange"] = {"nodes": [{"createdAt": base_event}] if base_event else []}
        pr["baseForce"] = {"nodes": [{"createdAt": base_force}] if base_force else []}
    return page


def run_wait(reads, pages, heads, timeout_secs):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    pages (the round-27/28/29 shape); heads scripts head_ref_oid per
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


class FFBaseObservationTests(unittest.TestCase):
    def test_ff_base_old_base_verdict_withheld_by_observation(self):
        # Given: the thread-3875623447 race — the wait starts under
        # the old-base job's EYES (created 22:13:19, base_1's tip
        # committed 22:13:18); between t=0 and t=5 the base branch is
        # FAST-FORWARDED to an already-existing descendant (base_2,
        # its OWN committedDate 22:13:21 — pushedDate null, the live
        # base shape; NO BaseRefChangedEvent, NO BaseRefForcePushedEvent
        # — round-29 live verification: the FF move is event-less)
        # while the old-base job submits review(S) at 22:13:23 (AFTER
        # the old tip date 22:13:21 but BEFORE the move/observation —
        # over base_1's diff) and its delayed +1 lands 22:13:27, the
        # EYES persisting across the move to re-arm the reset base.
        # When: wait polls 10s. Then: exit 1 — the t=5 probe's
        # base-change reset re-arms on the persisting EYES, but the
        # not-event-backed move stamps base_floor with the
        # OBSERVATION clock (22:13:25) beside the old tip date, so
        # the t=10 stamp leg withholds BY NAME (23 > 25 fails); the
        # pre-fix floor was the fallback's own old stamp (22:13:21),
        # the old-base review postdated it, and WAIT DONE exited 0
        # over the re-derived diff nobody reviewed (the pre-fix
        # proof: 0 != 1, WAIT DONE).
        code, out = run_wait(
            [
                [react("eyes", "2023-11-14T22:13:19Z", 5)],
                [react("eyes", "2023-11-14T22:13:19Z", 5)],
                [react("+1", "2023-11-14T22:13:27Z", 7)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S, base=BASE_1, base_stamp=BASE_1_TIP),
                bounds_page(PUSH_A, HEAD_S, base=BASE_2, base_stamp=FF_TIP),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:23Z"),
                    base=BASE_2, base_stamp=FF_TIP,
                ),
            ],
            [HEAD_S, HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("BASE CHANGED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("3875623447", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_ff_base_same_interval_round_held_for_one_round(self):
        # Given: THE PRICE (a), pinned honestly — the identical FF
        # move (base_2, tip 22:13:21, no events), but the NEW-base
        # round runs and completes ENTIRELY inside the t=0..t=5
        # interval: the prior round's +1 (22:12) is held at t=0, the
        # new round submits review(S) at 22:13:24 (after the move
        # ~22:13:22, BEFORE the observing probe 22:13:25) and its +1
        # (a new object) lands 22:13:26. When: wait polls 10s. Then:
        # exit 1 — the replacement path fires but the stamp leg fails
        # (24 > the observation floor 22:13:25 fails), so the
        # completed round is HELD for this one wait (the false-hold
        # price the sanctioned fallback buys); the pre-fix floor
        # (22:13:21) let the same replacement exit 0 at t=5 (the
        # pre-fix proof: 0 != 1, WAIT DONE) — the recovery is the
        # NEXT wait (test_next_wait_cold_start_completes...).
        code, out = run_wait(
            [
                [react("+1", "2023-11-14T22:12:00Z", 1)],
                [react("+1", "2023-11-14T22:13:26Z", 6)],
                [react("+1", "2023-11-14T22:13:26Z", 6)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S, base=BASE_1, base_stamp=BASE_1_TIP),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:24Z"),
                    base=BASE_2, base_stamp=FF_TIP,
                ),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:24Z"),
                    base=BASE_2, base_stamp=FF_TIP,
                ),
            ],
            [HEAD_S, HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("BASE CHANGED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_next_wait_cold_start_completes_on_settled_base(self):
        # Given: the price's RECOVERY — a FRESH wait starting over
        # the settled post-FF state (base_2, tip 22:13:21, no
        # events): the new round's own EYES 22:13:28, review(S)
        # 22:13:30, +1 22:13:32. When: wait polls 10s. Then: exit 0
        # at 5s on BOTH sides — the observation stamp is WAIT-LOCAL
        # state (never persisted): the cold start initializes
        # base_floor from the SETTLED base bound (22:13:21), and the
        # review (30 > 21) completes — the false-hold costs exactly
        # one round, never strands the base forever.
        code, out = run_wait(
            [
                [react("eyes", "2023-11-14T22:13:28Z", 8)],
                [react("+1", "2023-11-14T22:13:32Z", 9)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S, base=BASE_2, base_stamp=FF_TIP),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:30Z"),
                    base=BASE_2, base_stamp=FF_TIP,
                ),
            ],
            [HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("BASE CHANGED"), 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)

    def test_retarget_event_backed_same_interval_round_still_completes(self):
        # Given: the EVENT-BACKED no-regression pin — the identical
        # same-interval completion (held +1 22:12; review 22:13:24,
        # +1 22:13:26 landing before the t=5 observation), but the
        # move is a RETARGET (a BaseRefChangedEvent at 22:13:22).
        # When: wait polls 10s. Then: exit 0 at 5s on BOTH sides —
        # the event stamp IS the boundary's own timestamp, so NO
        # observation stamp is applied (the round-20/22/26 doctrine
        # holds for every class that has an event); an over-broad
        # fallback would hold this round to timeout.
        code, out = run_wait(
            [
                [react("+1", "2023-11-14T22:12:00Z", 1)],
                [react("+1", "2023-11-14T22:13:26Z", 6)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S, base=BASE_1, base_stamp=BASE_1_TIP),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:24Z"),
                    base=BASE_2, base_stamp=PUSH_A, base_event=BASE_EVENT,
                ),
            ],
            [HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("BASE CHANGED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)

    def test_force_event_backed_same_interval_round_still_completes(self):
        # Given: the round-29 TWIN of the retarget pin — the same
        # same-interval completion over a FORCE-UPDATED base (a
        # BaseRefForcePushedEvent at 22:13:22; the target's own
        # committedDate 22:00 is older than the event, the
        # old-commit shape the event bound exists for). When: wait
        # polls 10s. Then: exit 0 at 5s on BOTH sides — the force
        # event's own createdAt carries the binding (round 29), the
        # observation fallback keys on event-backed-ness and never
        # fires here.
        code, out = run_wait(
            [
                [react("+1", "2023-11-14T22:12:00Z", 1)],
                [react("+1", "2023-11-14T22:13:26Z", 6)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S, base=BASE_1, base_stamp=BASE_1_TIP),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:24Z"),
                    base=BASE_2, base_stamp=PUSH_A, base_force=BASE_EVENT,
                ),
            ],
            [HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("BASE CHANGED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)


class BaseEventBoundParseTests(unittest.TestCase):
    def round_node(self, base_stamp=None, base_event="ABSENT", base_force="ABSENT"):
        """A well-formed non-paginating ROUND_QUERY pr node for the
        direct round_bounds parse tests; base_stamp None omits every
        base key (the bare-oid legacy page); base_event/base_force
        ABSENT omit the keys, a stamp adds the event node."""
        pr = {
            "headRefOid": HEAD_S,
            "headRef": {"target": {"pushedDate": PUSH_A, "committedDate": PUSH_A}},
            "timelineItems": {
                "pageInfo": {"hasPreviousPage": False, "startCursor": None},
                "nodes": [],
            },
            "triggerComments": {
                "pageInfo": {"hasPreviousPage": False, "startCursor": None},
                "nodes": [],
            },
            "headTransition": {"nodes": []},
            "latestReviews": {"nodes": []},
            "reviewThreads": {"nodes": []},
        }
        if base_stamp is not None:
            pr["baseRefOid"] = BASE_2
            pr["baseRef"] = {"target": {"pushedDate": None, "committedDate": base_stamp}}
            if base_event != "ABSENT":
                pr["baseChange"] = {"nodes": [{"createdAt": base_event}]}
            if base_force != "ABSENT":
                pr["baseForce"] = {"nodes": [{"createdAt": base_force}]}
        return pr

    def run_bounds(self, pr):
        """REAL round_bounds over one scripted subprocess page with
        the head_ref_oid seam MOCKED (the round-28 FOLD pin)."""
        with mock.patch.object(
            pr_guard_reaction_probe.subprocess,
            "run",
            return_value=gh_page({"data": {"repository": {"pullRequest": pr}}}),
        ), mock.patch.object(pr_guard_reaction_probe, "head_ref_oid", mock.Mock(return_value=HEAD_S)):
            return pr_guard_reaction_probe.round_bounds(48, timeout_secs=None)

    def test_event_stamps_thread_base_event_bound(self):
        # Given: the probe-side half — a page whose base target is
        # dated 22:13:21 (the FF tip) while BOTH event connections
        # carry nodes (a retarget at 22:13:22 and an older force
        # event at 22:13:20). When: round_bounds parses. Then:
        # base_bound = max(target, events) = 22:13:22 AND the EVENT
        # portion rides out SEPARATELY as base_event_bound = the max
        # event stamp (22:13:22) — the wait's observation fallback
        # keys on that attr alone (the pre-fix proof: the attr never
        # existed — AttributeError, the round-27 missing-attr class).
        bounds = self.run_bounds(
            self.round_node(
                base_stamp=FF_TIP, base_event=BASE_EVENT, base_force="2023-11-14T22:13:20Z"
            )
        )
        self.assertEqual(bounds, (HEAD_S, PUSH_A, "", ""))
        self.assertEqual(bounds.base, BASE_2)
        self.assertEqual(bounds.base_bound, BASE_EVENT)
        self.assertEqual(bounds.base_event_bound, BASE_EVENT)

    def test_ff_and_absent_event_shapes_leave_base_event_bound_empty(self):
        # Given: the FF shape — the event connections PRESENT and
        # EMPTY (the live PR #49 base shape) — and the legacy
        # absent-key page (the minimal-payload tolerance). When:
        # round_bounds parses. Then: base_event_bound reads '' in
        # BOTH shapes (no event stamp contributed — the observation
        # fallback's exact key) while base_bound keeps the target's
        # own stamp; the pre-fix proof is the AttributeError twin.
        for label, node in (
            ("present-and-empty", self.round_node(base_stamp=FF_TIP)),
            ("absent-keys", self.round_node(base_stamp=FF_TIP)),
        ):
            with self.subTest(shape=label):
                bounds = self.run_bounds(node)
                self.assertEqual(bounds.base_event_bound, "")
                self.assertEqual(bounds.base_bound, FF_TIP)


if __name__ == "__main__":
    unittest.main()
