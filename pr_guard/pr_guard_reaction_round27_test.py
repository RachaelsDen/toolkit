"""pr_guard reaction round-27 tests (PR #49 threads 3874769241 P2 /
3874769245 P1): the same-second verdict, the base-change reset +
floor (the 3874769253 deadline half lives in
pr_guard_reaction_round27_wait_test — the pair split at the 250
pure-LOC ceiling, the round-25 precedent).

Thread 3874769241 — "Accept same-second review and reaction
verdicts": a valid bot review submission and its subsequent +1 can
share one API timestamp second; the strict
`plus_one_created > review_stamp` completion leg then made head_bound
false, and because the reaction object is IMMUTABLE neither
completion branch could ever recover — the wait timed out on a
PASSED current-head review. Round 27 makes the leg equality-safe
(`>=`, superseding the round-10 strictness FOR THIS LEG ONLY — the
classification legs keep strict `>`): the +1 IS the post-review
verdict by the bot's lifecycle, the false-accept surface is already
owned by the review_head == observed_head and stamp > floor legs,
and no stable-id tie-breaker exists on the folded read.

Thread 3874769245 (the P1) — "Reset the round when the PR base
changes": a retarget or base-tip advance changes the reviewed diff
while headRefOid stays unchanged, so the old-base job's review (its
commit.oid still names the head) certified a +1 over a diff the new
base rederives and the wait exited 0. The wait now tracks the
reading's .base attr (baseRefOid) exactly as it tracks observed_head:
a change fires the SAME reset family as a head move and stamps
base_floor = the boundary's OWN timestamp (BaseRefChangedEvent
createdAt for retargets; the base target's own push bound for tip
advances — NEVER an observation clock, the round-20/22/26 doctrine)
into floor = max(transition_floor, boundary_floor, base_floor); the
review's oid names the HEAD, so head_bound cannot separate bases —
the stamp leg IS the separation.

No network: REAL round_bounds over scripted ROUND_QUERY pages (the
round-18..26 shape). FakeClock WALL_NOW 2023-11-14T22:13:20Z; the
stamps keyed INSIDE the wall window (the round-19 GOTCHA #2 rule).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round27_test -v
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
BASE_1 = "30ab97ffffffffffffffffffffffffffffff1"
BASE_2 = "30ab97ffffffffffffffffffffffffffffff2"

PUSH_A = "2023-11-14T22:00:00Z"
PUSH_B_FRESH = "2023-11-14T22:13:21Z"
BASE_STAMP_OLD = "2023-11-14T22:00:00Z"
BASE_EVENT = "2023-11-14T22:13:22Z"
BASE_TIP = "2023-11-14T22:13:23Z"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def gh_page(payload):
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(payload)
    )


def bot_node(oid, at):
    return {"author": {"login": BOT_LOGIN}, "commit": {"oid": oid}, "submittedAt": at}


def bounds_page(
    pushed, oid, request=(), review=None, force_push=None,
    base=None, base_stamp=None, base_event=None,
):
    """A well-formed ROUND_QUERY page; review/force_push/base* None keep
    their keys ABSENT (the round-18/27 legacy-minimal-payload rule)."""
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
    if base is not None:
        pr["baseRefOid"] = base
        pr["baseRef"] = {"target": {"pushedDate": None, "committedDate": base_stamp}}
        # The live PR #49 base shape: the connection PRESENT and empty
        # (no retarget ever happened); base_event adds the event node.
        pr["baseChange"] = {"nodes": [{"createdAt": base_event}] if base_event else []}
    return page


def run_wait(reads, pages, heads, timeout_secs):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    pages (the round-18..26 shape); heads scripts head_ref_oid per
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


class SameSecondVerdictTests(unittest.TestCase):
    def test_same_second_review_and_verdict_completes(self):
        # Given: the thread-3874769241 race — the prior round's +1
        # (22:05) is held at t=0 under head A (pushed 22:00); between
        # the t=0 and t=5 probes the ref MOVES to head B (fresh push
        # 22:13:21) and B's round completes — review(B) submitted
        # 22:13:24 and its +1 verdict (a new object) CREATED IN THE
        # SAME 22:13:24 SECOND (the immutable object can never
        # postdate its own review's second). When: wait polls 10s.
        # Then: exit 0 at 5s — the transition floor is B's own bound
        # (22:13:21), the stamp leg passes (24 > 21), and the
        # verdict-follows-review leg is EQUALITY-SAFE (24 >= 24, the
        # round-27 supersession of the round-10 strictness for THIS
        # leg only); the pre-fix strict compare rejected the identical
        # object on every later probe too and the passed round timed
        # out (the pre-fix proof: exit 1, HOLDING, no WAIT DONE).
        code, out = run_wait(
            [
                [react("+1", "2023-11-14T22:05:00Z", 1)],
                [react("+1", "2023-11-14T22:13:24Z", 2)],
                [react("+1", "2023-11-14T22:13:24Z", 2)],
            ],
            [
                bounds_page(PUSH_A, HEAD_A, base=BASE_1, base_stamp=BASE_STAMP_OLD),
                bounds_page(
                    PUSH_B_FRESH, HEAD_B, review=bot_node(HEAD_B, "2023-11-14T22:13:24Z"),
                    base=BASE_1, base_stamp=BASE_STAMP_OLD,
                ),
                bounds_page(
                    PUSH_B_FRESH, HEAD_B, review=bot_node(HEAD_B, "2023-11-14T22:13:24Z"),
                    base=BASE_1, base_stamp=BASE_STAMP_OLD,
                ),
            ],
            [HEAD_A, HEAD_B, HEAD_B],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("HEAD MOVED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)

    def test_same_second_plus_one_vs_push_still_reads_stale(self):
        # Given: the SURVIVOR — the classification legs keep the
        # round-10 strict rule: a +1 CREATED in the same second as
        # the head push (22:13:21) cannot be PROVEN to postdate it,
        # so the reading classifies THUMBS_UP_STALE (never DONE) and
        # the equality-safe verdict leg is never even consulted. When:
        # wait polls 10s (EYES 22:13:22 arms at t=0; the same-second
        # +1 lands at t=5). Then: exit 1 on both sides — no WAIT
        # DONE, the stale render — the pin that round 27 widened ONLY
        # the verdict leg.
        code, out = run_wait(
            [
                [react("eyes", "2023-11-14T22:13:22Z", 5)],
                [react("+1", "2023-11-14T22:13:21Z", 6)],
                [react("+1", "2023-11-14T22:13:21Z", 6)],
            ],
            [
                bounds_page(PUSH_B_FRESH, HEAD_S, base=BASE_1, base_stamp=BASE_STAMP_OLD),
                bounds_page(PUSH_B_FRESH, HEAD_S, base=BASE_1, base_stamp=BASE_STAMP_OLD),
                bounds_page(PUSH_B_FRESH, HEAD_S, base=BASE_1, base_stamp=BASE_STAMP_OLD),
            ],
            [HEAD_S, HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 1)
        self.assertIn("THUMBS_UP (stale", out)
        self.assertNotIn("WAIT DONE", out)


class BaseChangeResetTests(unittest.TestCase):
    def test_retarget_old_base_review_withheld(self):
        # Given: the thread-3874769245 race — the prior round's +1
        # (22:12) is held at t=0 on the stable head S; between t=0
        # and t=5 the PR is RETARGETED base_1 -> base_2 (a
        # BaseRefChangedEvent at 22:13:22; the head is UNCHANGED) and
        # the OLD-base job finishes late — review(S) submitted
        # 22:13:20 (BEFORE the retarget; its commit.oid still names
        # the head), +1 22:13:24 (a new object replacing the held
        # one). When: wait polls 10s. Then: exit 1 — the base change
        # fires the head-move reset family (BASE CHANGED printed
        # once) and stamps base_floor = the EVENT's own createdAt
        # (22:13:22), so the replacement path's stamp leg withholds
        # BY NAME (20 > 22 fails); the pre-fix wait had NO base
        # tracking — floor '', review_head == head trivially — and
        # exited 0 on the old-base verdict (the pre-fix proof:
        # 0 != 1, WAIT DONE).
        code, out = run_wait(
            [
                [react("+1", "2023-11-14T22:12:00Z", 1)],
                [react("+1", "2023-11-14T22:13:24Z", 6)],
                [react("+1", "2023-11-14T22:13:24Z", 6)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S, base=BASE_1, base_stamp=BASE_STAMP_OLD),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:20Z"),
                    base=BASE_2, base_stamp=BASE_STAMP_OLD, base_event=BASE_EVENT,
                ),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:20Z"),
                    base=BASE_2, base_stamp=BASE_STAMP_OLD, base_event=BASE_EVENT,
                ),
            ],
            [HEAD_S, HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("BASE CHANGED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("3874769245", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_base_tip_advance_old_base_review_withheld(self):
        # Given: the tip-advance twin — no BaseRefChangedEvent exists
        # (the base BRANCH moved, not the PR's retarget), the base
        # oid changes base_1 -> base_2 and the new tip's OWN
        # committedDate (22:13:23, pushedDate null — the live PR #49
        # base shape) is the only verifiable boundary; the old-base
        # review submitted 22:13:21 < 22:13:23. When: wait polls
        # 10s. Then: exit 1 — base_floor = the target's own push
        # bound withholds the stamp leg (the pre-fix proof: 0 != 1,
        # WAIT DONE on the never-re-reviewed diff).
        code, out = run_wait(
            [
                [react("+1", "2023-11-14T22:12:00Z", 1)],
                [react("+1", "2023-11-14T22:13:24Z", 6)],
                [react("+1", "2023-11-14T22:13:24Z", 6)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S, base=BASE_1, base_stamp=BASE_STAMP_OLD),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:21Z"),
                    base=BASE_2, base_stamp=BASE_TIP,
                ),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:21Z"),
                    base=BASE_2, base_stamp=BASE_TIP,
                ),
            ],
            [HEAD_S, HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("BASE CHANGED"), 1)
        self.assertNotIn("WAIT DONE", out)

    def test_post_base_change_round_completes(self):
        # Given: the SURVIVOR — the identical retarget, but the
        # NEW-base round runs: review(S) submitted 22:13:24 (PAST
        # the base floor 22:13:22), +1 22:13:26 replacing the held
        # 22:12 object. When: wait polls 10s. Then: exit 0 at 5s on
        # BOTH sides (the pre-fix wait completed it too — floor '')
        # — the pin that the reset + floor strand NO post-change
        # round: the reset family keys the certifications, the stamp
        # leg certifies the fresh evidence.
        code, out = run_wait(
            [
                [react("+1", "2023-11-14T22:12:00Z", 1)],
                [react("+1", "2023-11-14T22:13:26Z", 6)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S, base=BASE_1, base_stamp=BASE_STAMP_OLD),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:24Z"),
                    base=BASE_2, base_stamp=BASE_STAMP_OLD, base_event=BASE_EVENT,
                ),
            ],
            [HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("BASE CHANGED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)

    def test_stable_base_never_resets(self):
        # Given: the no-spurious-reset SURVIVOR — the base facts are
        # present and IDENTICAL across probes while a normal
        # EYES->+1 round runs (EYES 22:13:22 at t=0, review 22:13:24
        # + verdict 22:13:26 at t=5). When: wait polls 10s. Then:
        # exit 0 at 5s on BOTH sides with NO BASE CHANGED line — the
        # cold-start baseline rule (the first readable probe
        # initializes observed_base; only a CHANGE resets).
        code, out = run_wait(
            [
                [react("eyes", "2023-11-14T22:13:22Z", 5)],
                [react("+1", "2023-11-14T22:13:26Z", 6)],
            ],
            [
                bounds_page(PUSH_B_FRESH, HEAD_S, base=BASE_1, base_stamp=BASE_STAMP_OLD),
                bounds_page(
                    PUSH_B_FRESH, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:24Z"),
                    base=BASE_1, base_stamp=BASE_STAMP_OLD,
                ),
            ],
            [HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("BASE CHANGED"), 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)


if __name__ == "__main__":
    unittest.main()
