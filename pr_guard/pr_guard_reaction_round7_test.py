"""pr_guard reaction round-7 tests (PR #49 thread 3868158293, P2).

Thread 3868158293 (P2): an initial-held +1 whose round went
EYES->+1 ENTIRELY between two 5s probes still completes the wait —
the +1's IDENTITY (created_at|id) is compared across probes, and a
DIFFERENT (newer) object that already passed the round-bounds
classification satisfies DONE without the transient EYES ever
being sampled; an UNCHANGED old +1 keeps timing out, and an
UNREADABLE start (the probes hid the transition) captures its
baseline on the first readable +1 so the replacement rule still
applies.

The round-7 gate companions (thread 3868158297's bannerless
pre-merge closing survey, thread 3868158304's paginated
request-event window) live in pr_guard_reaction_round7_gate_test
(the 250 pure-LOC ceiling, tests included — the round-4 suite
pair precedent).

No network: the wait tests patch gh_reactions/round_bounds at
their seams on the FakeClock.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round7_test -v
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_latch
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock

BOT = pr_guard_reaction.REACTION_BOT

# The thread-3868158293 hole's bounds: the old +1 (12:00) postdates
# the head push (11:00) and NO marker exists, so BOTH the old and the
# new +1 classify DONE — only the identity comparison separates them.
# PR #49 round 8 repin (thread 3868443452): round_bounds grew a
# head-first headRefOid element — one stable head throughout, so
# the wait's head-change reset never fires in this suite.
HEAD_OID = "5b3a679c58893ededbf5b9c7a82312db42f70b00"
UNMARKED_BOUNDS = (HEAD_OID, "2026-08-26T11:00:00Z", "", "")


def react(content, created="2026-08-26T12:00:00Z", rid=None):
    return {
        "content": content,
        "created_at": created,
        "id": rid,
        "user": {"login": BOT},
    }


def run_wait(reads, bounds, timeout_secs):
    """wait_reaction on the FakeClock with per-probe bounds; (code, out).

    (PR #49 round 25 fixture-seam maintenance, thread 3873970933:
    every probe's tuple rides a RoundBounds carrier whose folded
    review evidence names the STABLE head — the replacing +1's round
    submitted a review for the current head, and cold-start
    completions require that evidence now; the marker-window tuples
    are unchanged.)
    """
    clock = FakeClock()
    items = iter(reads)
    probes = iter(bounds)

    def carried(tuple_bounds):
        out = pr_guard_reaction_probe.RoundBounds(tuple_bounds)
        out.review_head = HEAD_OID
        out.review_stamp = "2026-08-26T12:30:00Z"
        return out

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
        "round_bounds",
        side_effect=lambda pr, timeout_secs=None: carried(next(probes)),
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue()


class ObservedNewPlusOneTests(unittest.TestCase):
    def test_old_then_new_post_bounds_plus_one_exits_zero(self):
        # Given: the wait starts on the prior round's +1 (12:00, no
        # marker — DONE-classified, HELD); the whole fast round goes
        # EYES->+1 between the t=0 and t=5 probes, so the second probe
        # reads the NEW +1 (14:00, post-bounds, DONE-classified) with
        # NO EYES ever sampled. When: wait polls. Then: exit 0 at 5s —
        # the CHANGED identity proves a different (newer) reaction
        # object completed the round inside the wait (thread
        # 3868158293); the marker-staleness rules still applied to it.
        code, out = run_wait(
            [
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=2)],
            ],
            [UNMARKED_BOUNDS, UNMARKED_BOUNDS],
            600,
        )
        self.assertEqual(code, 0)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)
        self.assertIn("3868158293", out)

    def test_same_second_replacement_by_id_exits_zero(self):
        # Given: the bot flips the reaction within one clock second —
        # created_at alone cannot distinguish the objects. When: the
        # wait reads the old +1 (id 1) then the replacement (id 2).
        # Then: exit 0 — the identity pair created_at|id still proves
        # the replacement (the id participates, thread 3868158293).
        code, out = run_wait(
            [
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("+1", created="2026-08-26T12:00:00Z", rid=2)],
            ],
            [UNMARKED_BOUNDS, UNMARKED_BOUNDS],
            600,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)

    def test_unchanged_old_plus_one_times_out(self):
        # Given: the initial-held +1 never changes — same object on
        # every probe of a 12s window. When: wait polls. Then: exit 1
        # — an UNCHANGED identity is no transition and no replacement;
        # the round-5 conservative core keeps withholding exit 0
        # (thread 3868158293 narrows the hold, it never widens done).
        code, out = run_wait(
            [[react("+1", rid=1)]] * 4,
            [UNMARKED_BOUNDS] * 4,
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("exit 0 was withheld", out)
        self.assertNotIn("WAIT DONE", out)

    def test_unreadable_start_needs_replacement_not_presence(self):
        # Given: the probes HIDE the transition (thread 3868158293's
        # second shape) — t=0 reads UNREADABLE, t=5 reads the old +1
        # (the baseline captures on the first readable DONE), t=10
        # reads the replacement. When: wait polls. Then: exit 0 — the
        # baseline/replace rule works behind an unreadable start; but
        # had the +1 stayed UNCHANGED the wait would time out (no
        # state was ever captured at start to certify it).
        code, out = run_wait(
            [
                SystemExit(2),
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=2)],
            ],
            [UNMARKED_BOUNDS] * 3,
            600,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)

    def test_identity_predicates(self):
        # Given: the latch module's identity pair. When: identity and
        # replacement are evaluated. Then: the pair distinguishes
        # objects on created_at OR id, and only a captured baseline
        # replaced by a strictly NEWER identity accepts (thread
        # 3868158293; thread 3869453955's round-13 ordering).
        # (PR #49 round 13 repin, thread 3869453955: the pre-round-13
        # fixture pinned word placeholders ("old"/"new") under the
        # any-different rule — the exact hole; the identities are
        # ISO-stamped now, the real REST shape the ordering speaks.)
        self.assertNotEqual(
            pr_guard_reaction_latch.plus_one_identity(react("+1", rid=1)),
            pr_guard_reaction_latch.plus_one_identity(react("+1", rid=2)),
        )
        for held, current, expected in (
            ("", "2026-08-26T12:00:00Z|2", False),
            ("2026-08-26T12:00:00Z|2", "", False),
            ("2026-08-26T12:00:00Z|2", "2026-08-26T12:00:00Z|2", False),
            ("2026-08-26T11:00:00Z|1", "2026-08-26T12:00:00Z|2", True),
        ):
            self.assertEqual(
                pr_guard_reaction_latch.replaced_plus_one(held, current),
                expected,
                (held, current),
            )


if __name__ == "__main__":
    unittest.main()
