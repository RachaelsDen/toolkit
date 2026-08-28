"""pr_guard reaction round-33 tests (PR #49 threads 3876172341 P1 /
3876172349 P2): the unconditional cold-start base observation's WAIT
half + the terminal short-page revalidation's WALK half.

Thread 3876172341 — "Treat historical base events as unbound at cold
start": round 32 keyed the cold-start observation fallback on
.base_event_bound PRESENCE, but event presence is PERSISTENT — a PR
can carry an OLD historical BaseRefChangedEvent or
BaseRefForcePushedEvent and then undergo an EVENT-LESS base
fast-forward before the wait starts, leaving the event bound nonempty
while describing NO transition of the current base. With the FF'd-to
commit's OLD committedDate inside the bound, a prior-base review
submitted AFTER the historical event (but before the wait began)
paired with its persisting EYES and delayed +1 to satisfy
`review_stamp > base_floor`, producing WAIT DONE over a re-derived
diff nobody reviewed. At COLD START the association between an event
stamp and the CURRENT base transition CANNOT be established (the
round-31 high-water criterion needs a mid-wait comparison — no prior
probe exists), so the conservative rule stamps the cold-start
base_floor with the OBSERVATION wall clock UNCONDITIONALLY:
max(base_bound, wall). Why unconditional is safe: a PRE-WAIT review
paired with a POST-WAIT-START +1 is exactly the delayed-verdict race
being blocked, every legitimate completion path is unaffected (the
mid-wait `rebased` block keeps the round-31 advance discipline; a
cold-start review SUBMITTING after the first readable probe clears
the wall — pinned here), and the max keeps the stamp inert whenever
the bound genuinely postdates it (the 2026-stamped fixture class).

Thread 3876172349 — "Revalidate the short terminal reaction page":
the per-page revalidation loop rechecked only the FULL pages
(recorded in full_newest), excluding the walk's terminal SHORT page.
With more than 100 reactions, a reaction on that short page (the
bot's latest +1) deleted AFTER the page was fetched — while the
full-page rechecks run — left every recheck succeeding and the stale
flattened list still containing the deleted +1; an already-armed
waiter reported WAIT DONE from a reaction no longer present (the
current state NONE, or a new round starting). The walk now records
the terminal short page's (length, newest identity) and re-reads it
after the full-page checks, requiring BOTH unchanged: the terminal
page has no refill, so a deletion shrinks the LENGTH without moving
the identity (the length leg is the only witness — pinned), deleting
the NEWEST moves the identity outright, and a formerly-0-item
terminal page (an exact-multiple count) that gains items (an
earlier-page addition shifting items forward) reads non-zero and
rejects. Any change, a failed re-read, or an expired deadline (the
recheck rides the walk's EXISTING deadline) raises
ReactionWalkExpired — unreadable, retry next interval. Single-page
walks still never recheck (the standing round-24 rule, pinned).

No network: the wait half runs REAL round_bounds/wait_reaction over
scripted ROUND_QUERY pages (the round-30/32 shape); the walk half
runs REAL gh_reactions over scripted REST pages (the round-24/25/32
walk-suite shape). FakeClock WALL_NOW 2023-11-14T22:13:20Z; the race
stamps keyed INSIDE the wall window (the round-19 GOTCHA #2 rule) —
the cold-start observation reads exactly 22:13:20Z, and the old-base
review 22:13:15 sits between the historical event 22:13:05 and that
observation.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round33_test -v
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
# The OLD historical BaseRefChangedEvent — it fired LONG before the
# wait (a pre-FF retarget), yet the query returns it FOREVER.
HIST_EVENT = "2023-11-14T22:13:05Z"
# The FF'd-to descendant's OWN committedDate — the commit EXISTS
# since 22:13:10, before the wait began (22:13:20).
FF_TIP = "2023-11-14T22:13:10Z"
EYES_AT = "2023-11-14T22:13:12Z"
# The old-base review: AFTER the historical event 22:13:05 (so the
# event-backed bound does not separate it) and AFTER the FF tip's own
# date 22:13:10, but BEFORE the wait began — the exact race window.
REVIEW_AT = "2023-11-14T22:13:15Z"
# The survivor's review: SUBMITS after the first readable probe's
# observation 22:13:20 — post-start work clears the wall.
REVIEW_LATE = "2023-11-14T22:13:22Z"
PLUS_AT = "2023-11-14T22:13:27Z"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def gh_page(payload):
    return sp.CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload))


def bot_node(oid, at):
    return {"author": {"login": BOT_LOGIN}, "commit": {"oid": oid}, "submittedAt": at}


def bounds_page(pushed, oid, review=None, base=None, base_stamp=None, base_event=None):
    """A well-formed ROUND_QUERY page (the round-30/32 builder); review/
    base* None keep their keys ABSENT (the round-18/27 legacy rule);
    base carries baseRefOid + the base target's dates, base_event
    adds the historical retarget node (the persistent-event shape)."""
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
    pages (the round-30/32 shape); heads scripts head_ref_oid per probe
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


class HistoricalEventColdStartTests(unittest.TestCase):
    def test_historical_event_ff_cold_start_withheld(self):
        # Given: the thread-3876172341 race — the PR carries an OLD
        # historical BaseRefChangedEvent (22:13:05, a pre-FF
        # retarget the query returns forever) and the base was then
        # FAST-FORWARDED (event-less, the round-29 live verification)
        # to an already-existing descendant (base_2, its OWN
        # committedDate 22:13:10) BEFORE the wait began; the
        # old-base job's EYES (22:13:12) persists across the wait
        # start, its review(S) submitted 22:13:15 (AFTER the
        # historical event — so the event-backed bound separates
        # nothing — and AFTER the tip's own date, but BEFORE the
        # wait's first probe), and its delayed +1 lands 22:13:27.
        # When: wait polls 10s. Then: exit 1 — the cold start stamps
        # base_floor UNCONDITIONALLY with the observation wall clock
        # (max(22:13:10, 22:13:20) = 22:13:20 — no prior probe
        # exists to establish the event/transition association the
        # round-31 criterion needs), so the stamp leg withholds BY
        # NAME (15 > 20 fails); the pre-fix cold start kept round
        # 32's `"" if base_event_bound else <wall>` conditional —
        # the persistent event suppressed the fallback and WAIT DONE
        # exited 0 over the re-derived diff nobody reviewed (the
        # pre-fix proof: 0 != 1, WAIT DONE).
        page = bounds_page(
            PUSH_A, HEAD_S, review=bot_node(HEAD_S, REVIEW_AT),
            base=BASE_2, base_stamp=FF_TIP, base_event=HIST_EVENT,
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
        self.assertIn("3876172341", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_cold_start_review_after_first_probe_completes(self):
        # Given: the survivor — the identical cold start (the
        # historical event 22:13:05, the FF tip 22:13:10, the base
        # on base_2) whose round is LEGITIMATE: the EYES 22:13:12
        # arms at the first probe and the CURRENT-base round's own
        # review SUBMITS 22:13:22 — AFTER the first readable probe's
        # observation 22:13:20 — with its +1 22:13:27. When: wait
        # polls 10s. Then: exit 0 at 5s on BOTH sides — post-start
        # work clears the observation wall (22:13:22 > 22:13:20),
        # so the unconditional stamp never strands a round whose
        # evidence postdates the wait's first read (the owned price
        # is bounded to pre-first-probe work).
        page = bounds_page(
            PUSH_A, HEAD_S, review=bot_node(HEAD_S, REVIEW_LATE),
            base=BASE_2, base_stamp=FF_TIP, base_event=HIST_EVENT,
        )
        code, out = run_wait(
            [
                [react("eyes", EYES_AT, 5)],
                [react("+1", PLUS_AT, 7)],
            ],
            [page, dict(page)],
            [HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("BASE CHANGED"), 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)


def r(nid, at, login="human"):
    return {"content": "heart", "created_at": at, "id": nid, "user": {"login": login}}


def page(items):
    return sp.CompletedProcess([], 0, stdout=json.dumps(items), stderr="")


def minute(i):
    """An ascending created_at for fixture index i (10:00 + i minutes)."""
    return f"2026-08-26T{10 + i // 60:02d}:{i % 60:02d}:00Z"


def humans(count, start_id=1, start_i=0):
    return [r(start_id + i, minute(start_i + i)) for i in range(count)]


class TerminalShortPageTests(unittest.TestCase):
    def test_terminal_short_page_newest_deletion_rejected(self):
        # Given: the thread-3876172349 race — a 130-reaction walk:
        # page 1 full (100 humans), page 2 the SHORT terminal page
        # (29 humans + the bot's +1 as its NEWEST, rid 130); AFTER
        # page 2's initial fetch — while the full-page rechecks run
        # — the +1 is DELETED (the bot removed its verdict; the
        # current state is NONE or a new round is starting), so the
        # terminal re-read returns 29 items whose newest is the old
        # human rid 129. When: gh_reactions walks. Then:
        # ReactionWalkExpired raises — BOTH the length (30 -> 29)
        # and the newest identity (the +1 -> rid 129) changed, the
        # stale flattened list no longer describes the terminal
        # window, so it is UNREADABLE, never a latest-wins input an
        # armed waiter could crown; the pre-fix walk re-read page 1
        # only and returned the 130-item list still containing the
        # deleted +1 (the pre-fix proof: no raise).
        p1 = humans(100)
        p2 = humans(29, 101, 100) + [react("+1", minute(129), 130)]
        p2_after = humans(29, 101, 100)
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[page(p1), page(p2), page(list(p1)), page(p2_after)],
        ):
            with self.assertRaises(pr_guard_reaction.ReactionWalkExpired):
                pr_guard_reaction.gh_reactions(48)

    def test_terminal_short_page_nonnewest_deletion_rejected(self):
        # Given: the LENGTH-only witness — the identical walk whose
        # terminal short page (30 items, the bot's +1 still NEWEST
        # at rid 130) loses a NON-NEWEST human (rid 111) during the
        # full-page rechecks: no refill exists, so the re-read's
        # NEWEST identity is UNCHANGED (the +1, rid 130) and only
        # the length moves (30 -> 29) — an identity-only compare
        # (round 25's) would accept the stale page. When:
        # gh_reactions walks. Then: ReactionWalkExpired raises —
        # the terminal page's LENGTH is the only local witness the
        # list mutated, which is exactly why BOTH must hold (the
        # pre-fix proof: no raise).
        p1 = humans(100)
        p2 = humans(29, 101, 100) + [react("+1", minute(129), 130)]
        p2_after = (
            [r(i, minute(i - 1)) for i in range(101, 111)]
            + [r(i, minute(i - 1)) for i in range(112, 130)]
            + [react("+1", minute(129), 130)]
        )
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[page(p1), page(p2), page(list(p1)), page(p2_after)],
        ):
            with self.assertRaises(pr_guard_reaction.ReactionWalkExpired):
                pr_guard_reaction.gh_reactions(48)

    def test_terminal_empty_page_refill_rejected(self):
        # Given: the 0-item terminal edge — an EXACT-MULTIPLE
        # 200-reaction walk (pages 1 and 2 full, the page-3 request
        # returns the EMPTY list, the walk's terminal short page at
        # length 0); during the full-page rechecks a NEW reaction
        # (rid 201, the newest) lands, shifting items forward so
        # the former page-3 window now holds it. When: gh_reactions
        # walks. Then: ReactionWalkExpired raises — the re-read
        # reads length 1 against the recorded 0 (a refill), the
        # same any-change rule; the pre-fix walk never re-read the
        # terminal page and returned the settled 200 (the pre-fix
        # proof: no raise).
        p1, p2 = humans(100), humans(100, 101, 100)
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[
                page(p1), page(p2), page([]), page(list(p1)), page(list(p2)),
                page([r(201, minute(200))]),
            ],
        ):
            with self.assertRaises(pr_guard_reaction.ReactionWalkExpired):
                pr_guard_reaction.gh_reactions(48)

    def test_single_page_walk_still_never_rereads(self):
        # Given: the COMMON read — a single short page (under 100
        # reactions): no offset window exists for a mid-walk
        # deletion to shift, and the walk's terminal page IS its
        # only page. When: gh_reactions walks. Then: the list
        # returns after ONE subprocess call — the terminal-page
        # revalidation is a multi-page-only discipline (the
        # standing round-24 rule) and the single-page probe keeps
        # its exact subprocess count; green on BOTH sides.
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[page(humans(42))],
        ) as fake:
            combined = pr_guard_reaction.gh_reactions(48)
        self.assertEqual(len(combined), 42)
        self.assertEqual(fake.call_count, 1)


if __name__ == "__main__":
    unittest.main()
