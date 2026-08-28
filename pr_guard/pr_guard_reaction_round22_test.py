"""pr_guard reaction round-22 tests — the WAIT half (PR #49 threads
3872740865 P2 / 3872980765 P1: the coupled floor-trade pair, resolved
ARM-RELAXED/EXIT-GUARDED).

The two findings pull the round-19/20 floor trade in opposite
directions — 3872740865 (the round-20-graded between-polls stranding,
now P2) and 3872980765 (the surviving false-exit, P1). The coherent
resolution: the ARM relaxes, the EXIT guards. (1) 3872740865: the
round-13 wait-side demotion of a pre-floor EYES at the head-move
probe is DELETED, and the transition floor is no longer passed into
the reading — a between-polls legitimate EYES (posted after the
move, before the poll that observes it) now arms and its round
completes through the standing round-17/21 exit-evidence legs
(review_head == observed head AND review_stamp > floor AND +1 >
stamp), which already withhold the OLD head's job regardless of
arming; the old head's leftover EYES still stales AT THE READING
through the round-15 headTransition event bound (the 3869453944
shape re-owned by 3870293194). (2) 3872980765: the same evidence
discipline extends to request/trigger advances — the advancing
boundary's createdAt is retained as boundary_floor and post-advance
completions require the folded review to SUBMIT past it (the old
job whose review predates the re-request cannot certify the +1 its
post-request EYES re-armed). The DOCUMENTED-OPEN residual (the old
job's review ALSO postdating the request — observably identical to
the newly requested round's own pass at the reaction API: no job
identity, COMMENTED-only states, no reaction-to-review association)
is pinned green with the wall owned in its docstring; the quiet
watch + the server rulesets remain the standing backstop.

No network: the fixtures run REAL round_bounds over scripted
ROUND_QUERY pages (the round-18/19/20/21 shape) so the boundary
streams and the folded review evidence ride the REAL probe through
the Reading attrs. FakeClock WALL_NOW 2023-11-14T22:13:20Z; the
stamps key INSIDE the wall window (the round-19 GOTCHA #2 rule —
the t=5 move detection stamps the floor 22:13:25).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round22_test -v
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

# The wall window (the round-19 GOTCHA #2): probes land at 22:13:20
# (t=0), 22:13:25 (t=5 — the head-move detection stamps the
# transition floor 2023-11-14T22:13:25Z), 22:13:30 (t=10), 22:13:35
# (t=15).
PUSH = "2023-11-14T22:00:00Z"
FRESH_B = "2023-11-14T22:13:21Z"
R1 = "2023-11-14T22:10:00Z|RA_1"
R2 = "2023-11-14T22:13:22Z|RA_2"


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
        pr["headTransition"] = {
            "nodes": [{"createdAt": force_push}]
        }
    return page


def run_wait_pages(reads, pages, heads, timeout_secs):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    pages (the round-18/19/20/21 shape); heads scripts head_ref_oid
    per probe (a CHANGING oid stages the mid-wait head move)."""
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


class BetweenPollsEyesAtMoveTests(unittest.TestCase):
    def test_between_polls_eyes_at_move_arms_and_completes(self):
        # Given: the thread-3872740865 race — the ref MOVES A->B
        # (pushed 22:13:21) between the t=0 and t=5 probes while the
        # NEW head's review runs; B's own EYES (22:13:23 — posted
        # AFTER the move, BEFORE the poll that observes it, the
        # between-polls shape) is latest at t=5, its review of B
        # submits 22:13:26, and its passing +1 (22:13:27) lands at
        # t=10. When: wait polls 10s. Then: exit 0 at 10s — the t=5
        # probe stamps the transition floor at its OWN observation
        # time (22:13:25, LATER than the EYES), but with the round-13
        # demotion deleted and the floor no longer fed to the
        # reading, the EYES reads ACTIVE (22:13:23 > B's push
        # 22:13:21), arms the latch, and the +1 completes through the
        # exit-evidence legs (review B == observed B, stamp 26 >
        # floor 25, +1 27 > 26). The pre-fix wait demoted the EYES to
        # EYES_STALE at the move probe and staled it on every later
        # probe (the floor persisted into the reading), seeded no
        # baseline, and the completed review TIMED OUT (the pre-fix
        # proof: exit 1).
        code, out = run_wait_pages(
            [
                [],
                [react("eyes", "2023-11-14T22:13:23Z", 5)],
                [react("+1", "2023-11-14T22:13:27Z", 6)],
            ],
            [
                bounds_page(PUSH, HEAD_A),
                bounds_page(FRESH_B, HEAD_B, review=bot_node(HEAD_B, "2023-11-14T22:13:26Z")),
                bounds_page(FRESH_B, HEAD_B, review=bot_node(HEAD_B, "2023-11-14T22:13:26Z")),
            ],
            [HEAD_A, HEAD_B, HEAD_B],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("HEAD MOVED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)

    def test_old_head_post_move_completion_cannot_exit(self):
        # Given: the SURVIVOR — the identical post-move shape, but
        # the still-running job belongs to the OLD head: its EYES
        # (22:13:26, post-floor — never demoted even pre-fix) arms at
        # t=5, and its +1 (22:13:27) submits review(A) at t=10. When:
        # wait polls 10s. Then: exit 1 — the ARM relaxed (the EYES
        # opens the gate and arms) but the EXIT guards: the folded
        # evidence names head A != the observed head B, so the +1
        # HOLDs at the evidence leg and the wait keeps polling (B's
        # own round would complete); green on BOTH sides of the
        # round-22 change (the round-17/21 legs predate it).
        code, out = run_wait_pages(
            [
                [],
                [react("eyes", "2023-11-14T22:13:26Z", 5)],
                [react("+1", "2023-11-14T22:13:27Z", 6)],
            ],
            [
                bounds_page(PUSH, HEAD_A),
                bounds_page(FRESH_B, HEAD_B, review=bot_node(HEAD_A, "2023-11-14T22:13:26Z")),
                bounds_page(FRESH_B, HEAD_B, review=bot_node(HEAD_A, "2023-11-14T22:13:26Z")),
            ],
            [HEAD_A, HEAD_B, HEAD_B],
            10,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP: this +1's round cannot be proven", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_retarget_leftover_eyes_stales_via_event_bound(self):
        # Given: the thread-3869453944 shape under the round-22
        # deletion — the ref RETARGETS A->B onto an already-pushed
        # commit (B's push 22:00:00 PREDATES the old head's leftover
        # EYES 22:13:21), and the t=5 page carries the
        # HeadRefForcePushedEvent (22:13:22 — the round-15 cold-start
        # bound, live-verified the only retarget event the schema
        # offers). The old job's +1 (22:13:27) lands at t=10. When:
        # wait polls 15s. Then: exit 1 — the EYES stales AT THE
        # READING through the EVENT bound (pushed = max(commit
        # stamps, event 22:13:22); 21 <= 22), never arming post-move,
        # and the +1 holds at the evidence leg (review A != observed
        # B); GREEN ON BOTH SIDES — the deletion only removed the
        # floor's READING-side feed, and the round-15 event bound
        # owns the leftover shape the wait-side floor used to carry.
        code, out = run_wait_pages(
            [
                [react("eyes", "2023-11-14T22:13:21Z", 5)],
                [react("eyes", "2023-11-14T22:13:21Z", 5)],
                [react("+1", "2023-11-14T22:13:27Z", 6)],
                [react("+1", "2023-11-14T22:13:27Z", 6)],
            ],
            [
                bounds_page(PUSH, HEAD_A),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_A, "2023-11-14T22:13:26Z"), force_push="2023-11-14T22:13:22Z"),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_A, "2023-11-14T22:13:26Z"), force_push="2023-11-14T22:13:22Z"),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_A, "2023-11-14T22:13:26Z"), force_push="2023-11-14T22:13:22Z"),
            ],
            [HEAD_A, HEAD_B, HEAD_B, HEAD_B],
            15,
        )
        self.assertEqual(code, 1)
        self.assertIn("EYES (stale — predates the current round's boundary", out)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 15s elapsed", out)


class BoundaryFloorCompletionTests(unittest.TestCase):
    def test_pre_request_review_plus_one_cannot_complete(self):
        # Given: the thread-3872980765 race — a cold NONE at t=0 with
        # the standing request R1; the same-head RE-REQUEST R2
        # (22:13:22) lands after the old job launched but before it
        # posted EYES; the old job's EYES (22:13:23 — POSTDATING R2,
        # so the round-13 request binding reads it ACTIVE) lands
        # before the t=5 probe, which observes the advance AND the
        # EYES together (the gate re-opens, the latch re-arms); the
        # old job's review SUBMITTED 22:13:21 — BEFORE the request —
        # and its +1 (22:13:28) lands at t=10. When: wait polls 10s.
        # Then: exit 1 — the boundary floor (R2's createdAt 22:13:22)
        # withholds the completion: the folded evidence's stamp
        # (22:13:21) PREDATES the advancing boundary, so the +1's
        # round cannot be proven to be the newly requested one; the
        # pre-fix wait had no boundary floor (no head move, no
        # transition floor) and exited 0 at t=10 before the requested
        # job ran (the pre-fix proof: exit 0).
        code, out = run_wait_pages(
            [
                [],
                [react("eyes", "2023-11-14T22:13:23Z", 5)],
                [react("+1", "2023-11-14T22:13:28Z", 6)],
            ],
            [
                bounds_page(PUSH, HEAD_B, request=[req_node("2023-11-14T22:10:00Z", "RA_1")], review=bot_node(HEAD_B, "2023-11-14T22:13:21Z")),
                bounds_page(PUSH, HEAD_B, request=[req_node(R2.partition("|")[0], "RA_2")], review=bot_node(HEAD_B, "2023-11-14T22:13:21Z")),
                bounds_page(PUSH, HEAD_B, request=[req_node(R2.partition("|")[0], "RA_2")], review=bot_node(HEAD_B, "2023-11-14T22:13:21Z")),
            ],
            [HEAD_B, HEAD_B, HEAD_B],
            10,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("HOLDING THUMBS_UP: this +1's round cannot be proven", out)
        self.assertIn("3872980765", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_re_requested_round_still_completes(self):
        # Given: the NON-STRANDING survivor — the same re-request
        # shape, but the newly requested round runs its OWN course:
        # its EYES (22:13:23) lands at t=10 (after the advance-
        # observing probe), its review submits 22:13:24 (PAST the
        # boundary), and its +1 (22:13:28) lands at t=15. When: wait
        # polls 15s. Then: exit 0 at 15s — the boundary floor binds
        # nothing the legitimate round does not carry (stamp 24 >
        # 22:13:22, +1 28 > 24, head B == observed B); green on BOTH
        # sides (the pre-fix completion had no floor to fail).
        code, out = run_wait_pages(
            [
                [],
                [],
                [react("eyes", "2023-11-14T22:13:23Z", 5)],
                [react("+1", "2023-11-14T22:13:28Z", 6)],
            ],
            [
                bounds_page(PUSH, HEAD_B, request=[req_node("2023-11-14T22:10:00Z", "RA_1")], review=bot_node(HEAD_B, "2023-11-14T22:13:21Z")),
                bounds_page(PUSH, HEAD_B, request=[req_node(R2.partition("|")[0], "RA_2")], review=bot_node(HEAD_B, "2023-11-14T22:13:21Z")),
                bounds_page(PUSH, HEAD_B, request=[req_node(R2.partition("|")[0], "RA_2")], review=bot_node(HEAD_B, "2023-11-14T22:13:24Z")),
                bounds_page(PUSH, HEAD_B, request=[req_node(R2.partition("|")[0], "RA_2")], review=bot_node(HEAD_B, "2023-11-14T22:13:24Z")),
            ],
            [HEAD_B, HEAD_B, HEAD_B, HEAD_B],
            15,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 15s", out)

    def test_post_request_old_job_residual_documented_open(self):
        # Given: THE DOCUMENTED-OPEN RESIDUAL (the round-19/20
        # posture, narrowed by round 22 and owned here) — the exact
        # 3872980765 observable sequence, but the OLD job's review
        # ALSO postdates the re-request (R2 22:13:22 -> old EYES
        # 22:13:23 -> old review 22:13:24 -> old +1 22:13:28, all
        # observed same-probe at t=5/t=10). When: wait polls 10s.
        # Then: exit 0 — every leg the boundary floor checks is one
        # the old job's late-written evidence genuinely satisfies,
        # and no reaction-API signal distinguishes it from the newly
        # requested round's own pass (no job identity; every review
        # renders COMMENTED — live-verified rounds 18/20 on #49/#48;
        # no reaction-to-review association): the exact race is
        # INFORMATION-THEORETICALLY CLOSED at this API, and pinning
        # exit 0 is the honest encoding — the post-merge quiet watch
        # + the server rulesets remain the standing backstop (green
        # on BOTH sides: the pre-fix completion had no floor).
        code, out = run_wait_pages(
            [
                [],
                [react("eyes", "2023-11-14T22:13:23Z", 5)],
                [react("+1", "2023-11-14T22:13:28Z", 6)],
            ],
            [
                bounds_page(PUSH, HEAD_B, request=[req_node("2023-11-14T22:10:00Z", "RA_1")], review=bot_node(HEAD_B, "2023-11-14T22:13:21Z")),
                bounds_page(PUSH, HEAD_B, request=[req_node(R2.partition("|")[0], "RA_2")], review=bot_node(HEAD_B, "2023-11-14T22:13:24Z")),
                bounds_page(PUSH, HEAD_B, request=[req_node(R2.partition("|")[0], "RA_2")], review=bot_node(HEAD_B, "2023-11-14T22:13:24Z")),
            ],
            [HEAD_B, HEAD_B, HEAD_B],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)


if __name__ == "__main__":
    unittest.main()
