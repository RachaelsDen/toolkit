"""pr_guard reaction round-32 tests (PR #49 threads 3876000978 P1 /
3876001013 P2): the cold-start FF base floor's WAIT half + the
terminal-page-length WALK half. The probe halves of round 32 —
threads 3876000990/3876001004, the pagination bracket's composite-
marker and head-transition bounds — live in the sibling
pr_guard_reaction_round32_probe_test.

Thread 3876000978 — "Apply the fast-forward fallback at cold
start": round 30 taught the MID-WAIT base change the observation
fallback (no event stamp contributed -> stamp the wait's wall
clock) and round 31 tied event-backed-ness to the high-water
advance, but the COLD START still initialized base_floor from the
base bound ALONE: a wait starting after an event-less base
FAST-FORWARD onto an already-existing commit reads that commit's
potentially OLD committedDate, so an old-base review submitted
AFTER the target commit date but BEFORE the wait began satisfied
`review_stamp > base_floor` — with the head unchanged
(review_head == observed_head trivially), the persisting EYES
re-armed, and WAIT DONE exited 0 although the current base-derived
diff was never reviewed. The cold-start initialization now gains
the SAME fallback: when the first readable probe's base bound is
NOT event-backed (no .base_event_bound — the round-30/31
criterion), base_floor additionally stamps the cold-start
OBSERVATION wall clock (the round-28 cold-start rule + the round-30
fallback, one shape). THE OWNED PRICE (the cold-start twin of
round 30's price (a), owned in the receipt): a round whose review
submits between the FF move and the wait's first readable probe
predates the observation and is held to timeout — the survey is
the authority. Event-backed cold starts are UNCHANGED (pinned).

Thread 3876001013 — "Compare terminal page lengths during reaction
revalidation": when the reaction count is an EXACT MULTIPLE of 100,
the walk's terminal page is FULL, so deleting a NON-FINAL item from
its range after the initial fetch leaves the reread's newest
identity UNCHANGED — the page merely shrinks 100 -> 99 because no
later item exists to refill the window (round 25's identity-only
compare accepts the stale flattened page; if the deleted item is
the bot's +1, an armed waiter still exits 0 from a reaction that is
no longer present). The per-page revalidation additionally requires
the reread of a FULL page to stay FULL (100 items) beside the
unchanged newest identity — the exact-multiple shrink raises
ReactionWalkExpired (unreadable probe, retry next interval); a
settled exact-multiple walk stays readable (pinned).

No network: the wait half runs REAL round_bounds/wait_reaction
over scripted ROUND_QUERY pages (the round-27/28/29/30 shape); the
walk half runs REAL gh_reactions over scripted REST pages (the
round-24/25 walk-suite shape). FakeClock WALL_NOW 2023-11-14T22:
13:20Z; the race stamps keyed INSIDE the wall window (the round-19
GOTCHA #2 rule) — the cold-start observation reads exactly
22:13:20Z, and the old-base review 22:13:15 sits between the FF
tip's old date 22:13:10 and that observation.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round32_test -v
"""

import io
import json
import subprocess as sp
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_probe
from . import pr_guard_reaction_walk
from .pr_guard_merge_fixtures import FakeClock

BOT = pr_guard_reaction.REACTION_BOT
BOT_LOGIN = pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN

HEAD_S = "20ab97ffffffffffffffffffffffffffffff5"
BASE_2 = "30ab97ffffffffffffffffffffffffffffff2"

PUSH_A = "2023-11-14T22:00:00Z"
# The FF'd-to descendant's OWN committedDate — the commit EXISTS
# since 22:13:10, long BEFORE the wait began (22:13:20).
FF_TIP = "2023-11-14T22:13:10Z"
EYES_AT = "2023-11-14T22:13:12Z"
# The old-base review: AFTER the target commit date, BEFORE the
# wait began — the exact thread-3876000978 window.
REVIEW_AT = "2023-11-14T22:13:15Z"
PLUS_AT = "2023-11-14T22:13:27Z"
# The survivor's pre-wait retarget event (an event-backed cold start).
RETARGET_EVENT = "2023-11-14T22:13:12Z"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def gh_page(payload):
    return sp.CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload))


def bot_node(oid, at):
    return {"author": {"login": BOT_LOGIN}, "commit": {"oid": oid}, "submittedAt": at}


def bounds_page(pushed, oid, review=None, base=None, base_stamp=None, base_event=None):
    """A well-formed ROUND_QUERY page (the round-30 builder); review/
    base* None keep their keys ABSENT (the round-18/27 legacy rule);
    base carries baseRefOid + the present-and-EMPTY event
    connections (the FF shape: neither event exists), base_event
    adds the retarget node (the event-backed survivor)."""
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
        pr["baseForce"] = {"nodes": []}
    return page


def run_wait(reads, pages, heads, timeout_secs):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    pages (the round-30 shape); heads scripts head_ref_oid per probe
    (the bracket's BEFORE side — always the stable head S)."""
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


class ColdStartFFFloorTests(unittest.TestCase):
    def test_cold_start_ff_old_base_verdict_withheld(self):
        # Given: the thread-3876000978 race — the base was FAST-
        # FORWARDED to an already-existing descendant (base_2, its
        # OWN committedDate 22:13:10; NO BaseRefChangedEvent, NO
        # BaseRefForcePushedEvent — the round-29 live verification)
        # BEFORE the wait began; the old-base job's EYES (22:13:12)
        # persists across the wait start, its review(S) submitted
        # 22:13:15 (AFTER the target commit date 22:13:10, BEFORE
        # the wait's first probe — over the OLD base's diff), and
        # its delayed +1 lands 22:13:27. When: wait polls 10s.
        # Then: exit 1 — the cold start initializes base_floor from
        # the settled bound AND (no event stamp contributed — the
        # FF class) the OBSERVATION wall clock 22:13:20, so the
        # stamp leg withholds BY NAME (15 > 20 fails); the pre-fix
        # cold start read the fallback's own old stamp alone
        # (22:13:10), the old-base review postdated it, and WAIT
        # DONE exited 0 over the re-derived diff nobody reviewed
        # (the pre-fix proof: 0 != 1, WAIT DONE).
        page = bounds_page(PUSH_A, HEAD_S, review=bot_node(HEAD_S, REVIEW_AT), base=BASE_2, base_stamp=FF_TIP)
        code, out = run_wait(
            [
                [react("eyes", EYES_AT, 5)],
                [react("+1", PLUS_AT, 7)],
                [react("+1", PLUS_AT, 7)],
            ],
            [page, dict(page), dict(page)],
            [HEAD_S, HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("BASE CHANGED"), 0)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("3876000978", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_cold_start_event_backed_round_completes(self):
        # Given: the EVENT-BACKED no-regression pin — the identical
        # cold start over base_2 with the SAME review 22:13:15 and
        # +1 22:13:27, but the base move left a BaseRefChangedEvent
        # (22:13:12, a pre-wait retarget): the event's OWN timestamp
        # is the boundary (base_floor 22:13:12, no observation
        # stamp on either side). When: wait polls 10s. Then: exit 0
        # at 5s — PR #49 ROUND 33 (thread 3876172341) SUPERSEDES
        # this pin: the cold-start observation stamp is now
        # UNCONDITIONAL (a PR can carry an OLD historical event and
        # then undergo an event-less base FF — event PRESENCE
        # certifies nothing at cold start, where no prior probe
        # exists to run the round-31 advance comparison), so
        # base_floor stamps max(22:13:12, the observation 22:13:20)
        # = 22:13:20 and the PRE-WAIT review 22:13:15 fails the
        # stamp leg — the round-32 expectation (exit 0) is repinned
        # to the held outcome: a pre-wait review paired with a
        # post-wait-start +1 is exactly the delayed-verdict race
        # round 33 blocks; the completing shape (a review
        # SUBMITTING after the first readable probe) is pinned
        # green both sides in pr_guard_reaction_round33_test.
        # When: wait polls 10s. Then: exit 1 — the stamp leg
        # withholds BY NAME (15 > 20 fails) and the wait times out.
        page = bounds_page(
            PUSH_A, HEAD_S, review=bot_node(HEAD_S, REVIEW_AT),
            base=BASE_2, base_stamp=FF_TIP, base_event=RETARGET_EVENT,
        )
        code, out = run_wait(
            [
                [react("eyes", EYES_AT, 5)],
                [react("+1", PLUS_AT, 7)],
                [react("+1", PLUS_AT, 7)],
            ],
            [page, dict(page), dict(page)],
            [HEAD_S, HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("BASE CHANGED"), 0)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("3876000978", out)
        self.assertIn("3876172341", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)


def r(nid, at, login="human"):
    return {"content": "heart", "created_at": at, "id": nid, "user": {"login": login}}


def page(items):
    return sp.CompletedProcess([], 0, stdout=json.dumps(items), stderr="")


def minute(i):
    """An ascending created_at for fixture index i (10:00 + i minutes)."""
    return f"2026-08-26T{10 + i // 60:02d}:{i % 60:02d}:00Z"


def humans(count, start_id=1, start_i=0):
    return [r(start_id + i, minute(start_i + i)) for i in range(count)]


class TerminalPageLengthTests(unittest.TestCase):
    def test_exact_multiple_terminal_shrink_rejected(self):
        # Given: the thread-3876001013 race — the count is an EXACT
        # MULTIPLE of 100 (pages 1 and 2 both FULL, the terminal
        # page-3 request returns the EMPTY list), and AFTER page 2's
        # initial fetch the reaction id 150 (a NON-FINAL item of the
        # terminal full page's range) is DELETED: no later item
        # exists to refill the window, so page 2's re-read returns
        # 99 items whose NEWEST identity is the UNCHANGED old id 200
        # — round 25's identity-only compare accepts it (page 1
        # re-reads identical too), and the walk crowns latest-wins
        # over a list that no longer contains the deleted item (the
        # bot's +1 in the harm shape). When: gh_reactions walks.
        # Then: ReactionWalkExpired raises — the shrunk terminal
        # full page proves the reaction set mutated across the walk,
        # so it is UNREADABLE, never a latest-wins input; the
        # pre-fix walk returned the stale flattened page (the
        # pre-fix proof: no raise).
        p1 = humans(100)
        p2 = humans(100, 101, 100)
        p2_shrunk = humans(50, 101, 100) + humans(49, 152, 151)
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[page(p1), page(p2), page([]), page(list(p1)), page(p2_shrunk)],
        ):
            with self.assertRaises(pr_guard_reaction.ReactionWalkExpired):
                pr_guard_reaction.gh_reactions(48)

    def test_exact_multiple_settled_walk_stays_readable(self):
        # Given: the survivor — the identical exact-multiple walk
        # (pages 1 and 2 full, the empty terminal page) whose page
        # re-reads ALL come back full and identical (nothing was
        # deleted; the settled list). When: gh_reactions walks.
        # Then: 200 combined over SIX subprocess calls (3 walk
        # pages + 2 per-page re-reads + the round-33 TERMINAL
        # page-3 re-read, thread 3876172349 — the 0-item terminal
        # page re-reads length 0, identity empty; the count pin
        # moves 5 -> 6 and the last-call argv page=2 -> page=3,
        # fixture-seam maintenance) and no raise — the length leg
        # rejects only a SHRUNK re-read, never a settled one.
        p1, p2 = humans(100), humans(100, 101, 100)
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[page(p1), page(p2), page([]), page(list(p1)), page(list(p2)), page([])],
        ) as fake:
            combined = pr_guard_reaction.gh_reactions(48)
        self.assertEqual(len(combined), 200)
        self.assertEqual(fake.call_count, 6)
        self.assertTrue(fake.call_args.args[0][-1].endswith("page=3"))


if __name__ == "__main__":
    unittest.main()
