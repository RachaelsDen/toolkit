"""pr_guard reaction round-26 tests (PR #49 threads 3874405295 P2 /
3874405318 P2): the push-bound stamp floor, the fast-round advance
completion.

Thread 3874405295 — "Do not floor completed reviews at
head-observation time": when the head changes and the new-head review
completes entirely within one five-second polling interval, the probe
observes the new head and its terminal +1 only AFTER the review was
submitted. Round 22 deleted the EYES-demotion half of the race, but
the transition floor is still stamped at the wait's OBSERVATION wall
clock — a LATER time than the review — so the valid review_stamp
fails `review_stamp > floor`, the rejected +1 is captured as the held
baseline (the move block's re-capture), no unchanged later probe can
complete, and the command times out despite a successful review.
Round 26 moves the stamp leg's floor to the HEAD'S OWN BOUND — the
max(pushedDate, headTransition event) the reading's classification
already consumes (thread the reading's `head_bound` attr through):
a review submitted after the head's push/transition bound is
current-head work regardless of when the WAIT noticed the move, and
the pre-move leftover class (the retarget coincidence) is owned by
the force-push EVENT bound, never the wall clock. The move block's
baseline re-capture is deleted with it (the finding's second harm
half): the pre-move baseline is RETAINED so the between-polls
replacement fires naturally — the arm relaxes, the exit guards (the
round-22 doctrine; the round-17/18/20/25 evidence legs withhold the
old head's job at the EXIT, so the re-capture strands legitimate
completions while guarding nothing the legs do not).

Thread 3874405318 — "Retain the old +1 when a re-request finishes
between polls": when a formal request and the entire resulting
EYES->+1 round occur between two probes, the advance probe already
carries a new, request-bound DONE identity with a matching
post-boundary review stamp — but the advance reset CLEARED
held_plus_one, discarding the preceding +1 the replacement path
needs; the new +1 then installed as the baseline at the end of the
iteration and remained unchanged until timeout. Round 26 retains the
baseline through the reset (the cleaner of the vetted seams — the
replacement fires naturally this iteration): the round-22
boundary-floor stamp leg still withholds the preceding job's
pre-request review (pinned here), so the advertised round-7 fast-round
path completes while the false-exit class stays closed.

No network: the fixtures run REAL round_bounds over scripted
ROUND_QUERY pages (the round-18/19/20/21/22 shape) so the boundary
streams, the folded review evidence, and the new head_bound all ride
the REAL probe through the Reading attrs. FakeClock WALL_NOW
2023-11-14T22:13:20Z; the stamps key INSIDE the wall window (the
round-19 GOTCHA #2 rule — the t=5 move detection used to stamp the
floor 22:13:25; post-fix it stamps the head's OWN bound instead).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round26_test -v
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

HEAD_A = "20ab97ffffffffffffffffffffffffffffffa"
HEAD_B = "20ab97ffffffffffffffffffffffffffffffb"
HEAD_S = "20ab97ffffffffffffffffffffffffffffff5"

# The wall window (round-19 GOTCHA #2): probes land at 22:13:20
# (t=0), 22:13:25 (t=5 — the move-detecting probe), 22:13:30 (t=10),
# 22:13:35 (t=15).
PUSH_A = "2023-11-14T22:00:00Z"
PUSH_B_FRESH = "2023-11-14T22:13:21Z"
RETARGET_EVENT = "2023-11-14T22:13:22Z"
R1 = "2023-11-14T22:10:00Z|RA_1"
R2 = "2023-11-14T22:13:22Z|RA_2"
LEFTOVER_STAMP = "2023-11-14T22:13:10Z"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def gh_page(payload):
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(payload)
    )


def bot_node(oid, at):
    return {"author": {"login": BOT_LOGIN}, "commit": {"oid": oid}, "submittedAt": at}


def req_node(created, node_id):
    return {"createdAt": created, "id": node_id, "requestedReviewer": {"login": BOT_LOGIN}}


def bounds_page(pushed, oid, request=(), review=None, force_push=None):
    """A well-formed ROUND_QUERY page; review/force_push None keep
    their keys ABSENT (the round-18 legacy-minimal-payload rule)."""
    page = {
        "data": {
            "repository": {
                "pullRequest": {
                    "headRefOid": oid,
                    "headRef": {"target": {"pushedDate": pushed, "committedDate": pushed}},
                    "timelineItems": {
                        "pageInfo": {"hasPreviousPage": False, "startCursor": None},
                        "nodes": list(request),
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
    if force_push is not None:
        pr["headTransition"] = {"nodes": [{"createdAt": force_push}]}
    return page


def run_wait_pages(reads, pages, heads, timeout_secs):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    pages (the round-18..22 shape); heads scripts head_ref_oid per
    probe (a CHANGING oid stages the mid-wait head move)."""
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


class PushBoundStampFloorTests(unittest.TestCase):
    def test_between_polls_move_round_completes_at_move_probe(self):
        # Given: the thread-3874405295 race — the prior round's +1
        # (22:05) is held at t=0 under head A (pushed 22:00); between
        # the t=0 and t=5 probes the ref MOVES to head B (a fresh
        # push, 22:13:21) and B's ENTIRE round lands — EYES 22:13:22,
        # review(B) submitted 22:13:23, passing +1 (22:13:24, a new
        # object) — so the t=5 probe observes the new head AND its
        # terminal +1 together, the review having submitted BEFORE
        # the probe's own wall clock (22:13:25). When: wait polls
        # 10s. Then: exit 0 at 5s — the transition floor is the
        # head's OWN bound (22:13:21: the pushedDate/headTransition
        # event the reading's classification consumes, threaded
        # through the new `head_bound` attr), the review stamp
        # (22:13:23) postdates it, and the pre-move held baseline is
        # RETAINED so the replacement path fires at the move probe
        # itself (review B == observed B, +1 24 > stamp 23); the
        # pre-fix wait stamped the floor at its observation wall
        # clock (22:13:25), failed the stamp leg, re-captured the new
        # +1 as the held baseline, and timed out on the completed
        # review (the pre-fix proof: exit 1, no WAIT DONE).
        code, out = run_wait_pages(
            [
                [react("+1", "2023-11-14T22:05:00Z", 1)],
                [react("+1", "2023-11-14T22:13:24Z", 2)],
            ],
            [
                bounds_page(PUSH_A, HEAD_A),
                bounds_page(
                    PUSH_B_FRESH, HEAD_B, review=bot_node(HEAD_B, "2023-11-14T22:13:23Z")
                ),
            ],
            [HEAD_A, HEAD_B],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("HEAD MOVED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)
        self.assertIn("3868158293", out)

    def test_move_then_sampled_eyes_stamp_before_observation_completes(self):
        # Given: the EYES-sampled twin of the same stamp hole — the
        # move (fresh push 22:13:21) and B's EYES (22:13:22) land
        # between t=0 and t=5, the review(B) submits 22:13:24 (still
        # BEFORE the t=5 wall clock 22:13:25), and the passing +1
        # (22:13:27) lands at t=10. When: wait polls 10s. Then: exit
        # 0 at 10s — the t=5 EYES arms (22:13:22 > B's push
        # 22:13:21) and the t=10 +1 completes through the evidence
        # legs against the head's OWN bound (stamp 24 > 21); the
        # pre-fix observation floor (22:13:25) failed the stamp leg,
        # the rejected +1 seeded the held baseline, and the wait
        # timed out (the pre-fix proof: exit 1, no WAIT DONE).
        code, out = run_wait_pages(
            [
                [],
                [react("eyes", "2023-11-14T22:13:22Z", 5)],
                [react("+1", "2023-11-14T22:13:27Z", 6)],
            ],
            [
                bounds_page(PUSH_A, HEAD_A),
                bounds_page(
                    PUSH_B_FRESH, HEAD_B, review=bot_node(HEAD_B, "2023-11-14T22:13:24Z")
                ),
                bounds_page(
                    PUSH_B_FRESH, HEAD_B, review=bot_node(HEAD_B, "2023-11-14T22:13:24Z")
                ),
            ],
            [HEAD_A, HEAD_B, HEAD_B],
            10,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)

    def test_pre_move_leftover_review_still_holds(self):
        # Given: the SURVIVOR — the retarget coincidence (the
        # round-20 stamp-leg class, re-owned by the EVENT bound): the
        # ref retargets A->B onto an already-pushed commit (push
        # 22:00) carrying a HeadRefForcePushedEvent (22:13:22 — the
        # only retarget event the live schema offers, round 15),
        # while the latest bot review names B BY COINCIDENCE with a
        # PRE-move stamp (22:13:10); B's own round posts EYES
        # (22:13:26) at t=5 and +1 (22:13:28) at t=10. When: wait
        # polls 15s. Then: exit 1 — the head's own bound is
        # max(22:00, event 22:13:22), the leftover stamp 22:13:10
        # predates it, and the +1 HOLDs to timeout; green on BOTH
        # sides (the pre-fix wall floor 22:13:25 rejected it too) —
        # the pin that the push-bound floor still withholds pre-move
        # work, through the event instead of the observation clock.
        code, out = run_wait_pages(
            [
                [],
                [react("eyes", "2023-11-14T22:13:26Z", 5)],
                [react("+1", "2023-11-14T22:13:28Z", 6)],
                [react("+1", "2023-11-14T22:13:28Z", 6)],
            ],
            [
                bounds_page(PUSH_A, HEAD_A, review=bot_node(HEAD_B, LEFTOVER_STAMP)),
                bounds_page(
                    PUSH_A, HEAD_B, review=bot_node(HEAD_B, LEFTOVER_STAMP),
                    force_push=RETARGET_EVENT,
                ),
                bounds_page(
                    PUSH_A, HEAD_B, review=bot_node(HEAD_B, LEFTOVER_STAMP),
                    force_push=RETARGET_EVENT,
                ),
                bounds_page(
                    PUSH_A, HEAD_B, review=bot_node(HEAD_B, LEFTOVER_STAMP),
                    force_push=RETARGET_EVENT,
                ),
            ],
            [HEAD_A, HEAD_B, HEAD_B, HEAD_B],
            15,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 15s elapsed", out)

    def test_oldhead_between_polls_round_still_holds(self):
        # Given: the false-exit SURVIVOR of the retained baseline —
        # the identical between-polls move shape, but the round that
        # completed inside the interval belongs to the OLD head (the
        # folded review names A, stamp 22:13:23 past B's fresh push
        # bound): the replacement predicate fires against the
        # retained pre-move baseline at the move probe. When: wait
        # polls 10s. Then: exit 1 — review(A) != observed B fails the
        # head leg and the +1 HOLDs (the round-17/25 exit guards);
        # green on BOTH sides (the pre-fix re-capture stranded it
        # too) — the pin that baseline retention opens NOTHING the
        # evidence legs do not already withhold.
        code, out = run_wait_pages(
            [
                [react("+1", "2023-11-14T22:05:00Z", 1)],
                [react("+1", "2023-11-14T22:13:24Z", 2)],
                [react("+1", "2023-11-14T22:13:24Z", 2)],
            ],
            [
                bounds_page(PUSH_A, HEAD_A),
                bounds_page(
                    PUSH_B_FRESH, HEAD_B, review=bot_node(HEAD_A, "2023-11-14T22:13:23Z")
                ),
                bounds_page(
                    PUSH_B_FRESH, HEAD_B, review=bot_node(HEAD_A, "2023-11-14T22:13:23Z")
                ),
            ],
            [HEAD_A, HEAD_B, HEAD_B],
            10,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("HEAD MOVED"), 1)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)


class AdvanceFastRoundTests(unittest.TestCase):
    def test_rerequest_fast_round_between_polls_completes(self):
        # Given: the thread-3874405318 race — the prior round's +1
        # (22:12, past the 22:10 standing request R1) is held at t=0
        # on the stable head S; between the t=0 and t=5 probes a
        # formal RE-REQUEST R2 (22:13:22) lands AND the newly
        # requested round runs its ENTIRE course — EYES 22:13:23,
        # review(S) submitted 22:13:24 (PAST the boundary), passing
        # +1 (22:13:26, a new object) — so the t=5 probe observes the
        # advance and the terminal DONE identity together. When:
        # wait polls 10s. Then: exit 0 at 5s — the advance reset
        # RETAINS the pre-advance held baseline, so replaced_plus_one
        # fires this iteration and the round-22 boundary floor
        # certifies the evidence (stamp 24 > boundary 22:13:22, +1 26
        # > 24, review S == observed S); the pre-fix reset cleared
        # held_plus_one, the new +1 installed as the baseline at the
        # end of the iteration, and no unchanged later probe could
        # complete — the advertised round-7 fast-round path timed out
        # (the pre-fix proof: exit 1, no WAIT DONE).
        code, out = run_wait_pages(
            [
                [react("+1", "2023-11-14T22:12:00Z", 1)],
                [react("+1", "2023-11-14T22:13:26Z", 2)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S, request=[req_node("2023-11-14T22:10:00Z", "RA_1")]),
                bounds_page(
                    PUSH_A,
                    HEAD_S,
                    request=[req_node("2023-11-14T22:13:22Z", "RA_2")],
                    review=bot_node(HEAD_S, "2023-11-14T22:13:24Z"),
                ),
            ],
            [HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)

    def test_pre_boundary_review_rerequest_signal_still_holds(self):
        # Given: the false-exit SURVIVOR of the retained baseline —
        # the identical advance shape, but the completing +1's folded
        # review SUBMITTED BEFORE the re-request (22:13:21 < R2's
        # 22:13:22 — the preceding job's late-written evidence): the
        # replacement fires against the retained baseline at the
        # advance probe. When: wait polls 10s. Then: exit 1 — the
        # round-22 boundary-floor leg withholds the completion (the
        # stamp predates the advancing boundary) and the HOLDING line
        # names the leg; the pre-fix reset silently seeded the +1 as
        # the held baseline (no completion was even evaluated — the
        # pre-fix proof: the HOLDING line absent, exit 1 either way).
        code, out = run_wait_pages(
            [
                [react("+1", "2023-11-14T22:12:00Z", 1)],
                [react("+1", "2023-11-14T22:13:26Z", 2)],
                [react("+1", "2023-11-14T22:13:26Z", 2)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S, request=[req_node("2023-11-14T22:10:00Z", "RA_1")]),
                bounds_page(
                    PUSH_A,
                    HEAD_S,
                    request=[req_node("2023-11-14T22:13:22Z", "RA_2")],
                    review=bot_node(HEAD_S, "2023-11-14T22:13:21Z"),
                ),
                bounds_page(
                    PUSH_A,
                    HEAD_S,
                    request=[req_node("2023-11-14T22:13:22Z", "RA_2")],
                    review=bot_node(HEAD_S, "2023-11-14T22:13:21Z"),
                ),
            ],
            [HEAD_S, HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("3872980765", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)


if __name__ == "__main__":
    unittest.main()
