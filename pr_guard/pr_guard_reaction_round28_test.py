"""pr_guard reaction round-28 wait tests (PR #49 threads 3875089260
P1 / 3875089273 P1): the cold-start base floor, the returning-OID
head transitions — the pair split's wait half (the probe half, the
pagination bracket's base compare, lives in
pr_guard_reaction_round28_probe_test; thread 3875089268).

Thread 3875089260 — "Bind cold-start reviews to the observed base":
when the wait starts AFTER the base already changed, the first
readable probe only initialized observed_base — base_floor stayed
'', the completion stamp checks were skipped, and a review of the
UNCHANGED head against the OLD base (its EYES persisting across the
base move, the delayed +1 landing later) exited 0 with
review_head == observed_head trivially true — the current
base-derived diff was never reviewed. The first readable probe now
initializes base_floor = max(base_floor, base_bound) ALONGSIDE
observed_base: INITIALIZATION, never a change (no reset family
fires — the boundary baseline rule), and post-cold-start
completions on the stale base fail review_stamp > base_floor (the
old-base review predates the current base's own bound — the same
separation the mid-wait stamp of thread 3874769245 provides).

Thread 3875089273 — "Detect head transitions that return to the
same OID": a head cycling A->B->A entirely between polls leaves the
oid UNCHANGED (the oid-only compare reports no move) while the
reading's head_bound strictly ADVANCES — the force-push event
genuinely moved (round-15/26 semantics), so the advance IS the
transition. The wait retains observed_head_bound (cold start
initializes oid + bound together; every readable head updates it);
a probe whose oid EQUALS the observed one but whose bound strictly
advances fires the SAME reset family as a head move (the fold
`moved or returned`) and advances transition_floor to the new bound
(monotone max) — the pre-cycle job's review then fails
review_stamp > transition_floor at the exit and its delayed +1 can
no longer ride the pre-cycle EYES to WAIT DONE.

No network: REAL round_bounds over scripted ROUND_QUERY pages (the
round-18..27 shape). FakeClock WALL_NOW 2023-11-14T22:13:20Z; the
stamps keyed INSIDE the wall window (the round-19 GOTCHA #2 rule).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round28_test -v
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
BASE_EVENT = "2023-11-14T22:13:22Z"
CYCLE_EVENT = "2023-11-14T22:13:26Z"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def gh_page(payload):
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(payload)
    )


def bot_node(oid, at):
    return {"author": {"login": BOT_LOGIN}, "commit": {"oid": oid}, "submittedAt": at}


def bounds_page(pushed, oid, review=None, force_push=None, base=None, base_event=None):
    """A well-formed ROUND_QUERY page; review/force_push/base None keep
    their keys ABSENT (the round-18/27 legacy-minimal-payload rule);
    base carries baseRefOid + the live present-and-empty baseChange
    connection (base_event adds the retarget node)."""
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
    if force_push is not None:
        pr["headTransition"] = {"nodes": [{"createdAt": force_push}]}
    if base is not None:
        pr["baseRefOid"] = base
        pr["baseRef"] = {"target": {"pushedDate": None, "committedDate": PUSH_A}}
        pr["baseChange"] = {"nodes": [{"createdAt": base_event}] if base_event else []}
    return page


def run_wait(reads, pages, heads, timeout_secs):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    pages (the round-18..27 shape); heads scripts head_ref_oid per
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


class ColdStartBaseFloorTests(unittest.TestCase):
    def test_cold_start_base_floor_withholds_old_base_verdict(self):
        # Given: the thread-3875089260 race — the wait starts AFTER
        # the PR was retargeted base_1 -> base_2 (a BaseRefChangedEvent
        # at 22:13:22; the head UNCHANGED at S/pushed 22:00); the
        # OLD-base job left its EYES (created 22:13:20, persisting
        # across the base move) and its review(S) submitted 22:13:21
        # — BEFORE the retarget, over the OLD base's diff — and its
        # delayed +1 lands 22:13:26. When: wait polls 10s. Then: exit
        # 1 — the first readable probe INITIALIZES base_floor = the
        # event's own createdAt (22:13:22) alongside observed_base (an
        # initialization, never a change: NO reset fires), so the
        # completion's stamp leg withholds BY NAME (21 > 22 fails);
        # the pre-fix wait left base_floor '' — floor '' skipped the
        # stamp checks entirely and review_head == observed_head held
        # trivially, so the +1 exited 0 over a diff the new base
        # rederives and nobody re-reviewed (the pre-fix proof:
        # 0 != 1, WAIT DONE).
        code, out = run_wait(
            [
                [react("eyes", "2023-11-14T22:13:20Z", 5)],
                [react("+1", "2023-11-14T22:13:26Z", 6)],
                [react("+1", "2023-11-14T22:13:26Z", 6)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S, base=BASE_2, base_event=BASE_EVENT),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:21Z"),
                    base=BASE_2, base_event=BASE_EVENT,
                ),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:21Z"),
                    base=BASE_2, base_event=BASE_EVENT,
                ),
            ],
            [HEAD_S, HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("3875089260", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_cold_start_post_base_round_completes(self):
        # Given: the SURVIVOR — the identical pre-wait retarget
        # (base_2, event 22:13:22), but the CURRENT-base round runs:
        # EYES 22:13:24, review(S) submitted 22:13:25 (PAST the
        # floor), +1 22:13:26. When: wait polls 10s. Then: exit 0 at
        # 5s on BOTH sides (the pre-fix floor '' completed it too) —
        # the pin that the cold-start floor strands NO post-change
        # round, and the initialization fires NO reset (no BASE
        # CHANGED line — the boundary baseline rule).
        code, out = run_wait(
            [
                [react("eyes", "2023-11-14T22:13:24Z", 5)],
                [react("+1", "2023-11-14T22:13:26Z", 6)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S, base=BASE_2, base_event=BASE_EVENT),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:25Z"),
                    base=BASE_2, base_event=BASE_EVENT,
                ),
            ],
            [HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("BASE CHANGED"), 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)


class ReturningOidTests(unittest.TestCase):
    def test_returning_oid_cycle_withholds_precycle_verdict(self):
        # Given: the thread-3875089273 race — the old job's EYES
        # (22:13:22) is observed at t=0 under head S (pushed 22:00,
        # no force-push events); between t=0 and t=5 the ref cycles
        # S->B->S entirely (the latest force-push event — the B->S
        # leg — at 22:13:26) and the old job submits review(S) at
        # 22:13:24, BEFORE the cycle; the new round's EYES lands
        # 22:13:27 (post-cycle) and the old job's delayed +1 lands
        # 22:13:28. When: wait polls 10s. Then: exit 1 — the t=5
        # probe's oid EQUALS observed_head yet its head_bound
        # strictly ADVANCES (22:13:26 > 22:00: the force-push event
        # genuinely moved), so HEAD RETURNED fires the SAME reset
        # family as a move and transition_floor advances to 22:13:26;
        # the t=10 +1 then fails the stamp leg (24 > 26 fails) — the
        # pre-fix oid-only compare reported NO move, the empty
        # transition_floor skipped the review-stamp guard, and
        # review_head == observed_head exited 0 on the pre-cycle
        # verdict (the pre-fix proof: 0 != 1, WAIT DONE).
        code, out = run_wait(
            [
                [react("eyes", "2023-11-14T22:13:22Z", 5)],
                [react("eyes", "2023-11-14T22:13:27Z", 7)],
                [react("+1", "2023-11-14T22:13:28Z", 8)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S),
                bounds_page(PUSH_A, HEAD_S, force_push=CYCLE_EVENT),
                bounds_page(
                    PUSH_A, HEAD_S, force_push=CYCLE_EVENT,
                    review=bot_node(HEAD_S, "2023-11-14T22:13:24Z"),
                ),
            ],
            [HEAD_S, HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("HEAD RETURNED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_returning_oid_post_cycle_round_completes(self):
        # Given: the SURVIVOR — the identical cycle (the B->S
        # force-push event at 22:13:26 observed at t=5), but the
        # POST-cycle round runs: EYES 22:13:27, review(S) submitted
        # 22:13:28 (PAST the floor), +1 22:13:30. When: wait polls
        # 10s. Then: exit 0 at 10s on BOTH sides (the pre-fix
        # floor '' completed it too) — the pin that the returning-OID
        # reset + floor strand NO post-cycle round.
        code, out = run_wait(
            [
                [react("eyes", "2023-11-14T22:13:22Z", 5)],
                [react("eyes", "2023-11-14T22:13:27Z", 7)],
                [react("+1", "2023-11-14T22:13:30Z", 8)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S),
                bounds_page(PUSH_A, HEAD_S, force_push=CYCLE_EVENT),
                bounds_page(
                    PUSH_A, HEAD_S, force_push=CYCLE_EVENT,
                    review=bot_node(HEAD_S, "2023-11-14T22:13:28Z"),
                ),
            ],
            [HEAD_S, HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("HEAD RETURNED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)

    def test_stable_head_bound_never_fires(self):
        # Given: the no-false-positive SURVIVOR — the head facts are
        # IDENTICAL across probes (S pushed 22:00, NO force-push
        # events: head_bound never advances) while a normal
        # EYES->+1 round runs (EYES 22:13:22, review 22:13:24,
        # verdict 22:13:26). When: wait polls 10s. Then: exit 0 at
        # 5s with NO HEAD RETURNED/MOVED line on EITHER side — the
        # bound compare fires only on a GENUINE advance (round-15/26
        # semantics: the event exists only when the ref moved).
        code, out = run_wait(
            [
                [react("eyes", "2023-11-14T22:13:22Z", 5)],
                [react("+1", "2023-11-14T22:13:26Z", 6)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:24Z")
                ),
            ],
            [HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 0)
        self.assertNotIn("HEAD RETURNED", out)
        self.assertNotIn("HEAD MOVED", out)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)


if __name__ == "__main__":
    unittest.main()
