"""pr_guard reaction round-8 tests (PR #49 thread 3868443452, P1).

Thread 3868443452 (P1): the wait resets its transition latch and
+1-identity baseline when the observed headRefOid CHANGES mid-wait.
The hole: a head moved onto an already-pushed commit whose
pushedDate predates the standing +1 — the probe before the move
classified that +1 STALE against the OLD head's later push (arming
saw_non_done), and the probe after reclassified the UNCHANGED
reaction DONE against the NEW head's earlier push, so the wait
exited 0 on a pre-move reaction with no review of the new head.
round_bounds now PRESERVES the headRefOid ROUND_QUERY always
carried (head-first), the reading rides every probe (EYES and NONE
included), and a detected move resets BOTH certifications —
completion needs a fresh POST-change transition: a new EYES arming
under the new head, or a demonstrably replaced +1.

No network: the wait tests patch gh_reactions/round_bounds at
their seams on the FakeClock.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round8_test -v
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_latch
from .pr_guard_merge_fixtures import FakeClock
from .pr_guard_reaction_probe import RoundBounds

BOT = pr_guard_reaction.REACTION_BOT

OLD_HEAD = "31ae10e9e5f4189ac89d832f9d2663f311130ee6"
NEW_HEAD = "cad8c064c5b1462e4d74866ddfcb76be700366a4"

# The thread-3868443452 hole's two halves: the OLD head was pushed
# at 12:30 — AFTER the +1 (12:00), so the +1 reads STALE against it
# (the arming probe) — while the NEW head is an already-pushed
# commit whose 11:00 push PREDATES the +1, so the SAME reaction
# reads DONE against it once the ref moves.
OLD_HEAD_BOUNDS = (OLD_HEAD, "2026-08-26T12:30:00Z", "", "")
NEW_HEAD_BOUNDS = (NEW_HEAD, "2026-08-26T11:00:00Z", "", "")
FAILED_PROBE = ("", "", "", "")


def react(content, created="2026-08-26T12:00:00Z", rid=None):
    return {
        "content": content,
        "created_at": created,
        "id": rid,
        "user": {"login": BOT},
    }


def run_wait(reads, bounds, timeout_secs):
    """wait_reaction on the FakeClock with per-probe bounds; (code, out).

    PR #49 round 10 repin (thread 3868782039): head_ref_oid is
    patched at its seam reading the CURRENT probe's own bounds oid
    (the shared triple) — this suite's head moves BETWEEN probes
    (OLD->NEW), never inside one, so every probe's bracket certifies
    a stable head and the flip stays the wait's cross-probe reset to
    exercise (a constant mock would false-raise on every post-flip
    probe).
    """
    clock = FakeClock()
    items = iter(reads)
    probes = iter(bounds)
    probe = {}

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    def fake_head(pr, timeout_secs=None):
        probe["triple"] = next(probes)
        return probe["triple"][0]

    def fake_bounds(pr, timeout_secs=None):
        # PR #49 round 18 (threads 3871485035/3871485043): the review
        # evidence rides the BOUNDS now (the folded attr) — the wrap
        # feeds the NEW head's review (the survivor's own round);
        # inert for every test that never reaches an accepting
        # post-floor probe (fixture-seam maintenance in the round-17
        # GOTCHA precedent, assertions byte-identical). Round 20
        # (thread 3872194023): the VERDICT STAMP rides beside the oid
        # — 13:30 sits between the surviving round's EYES (13:00) and
        # its +1 (14:00), past the 2023 wall floor.
        bounds = RoundBounds(probe["triple"])
        bounds.review_head = NEW_HEAD
        bounds.review_stamp = "2026-08-26T13:30:00Z"
        return bounds

    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_read
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", side_effect=fake_bounds
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", side_effect=fake_head
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue()


class HeadFlipResetsLatchTests(unittest.TestCase):
    def test_head_flip_reclassifying_old_plus_one_times_out(self):
        # Given: the prior round's +1 (12:00) and the head pushed at
        # 12:30 — the t=0 probe reads THUMBS_UP_STALE and ARMS the
        # transition latch; mid-wait the ref moves onto an
        # already-pushed commit (11:00 push, PREDATING the +1), so
        # every later probe reclassifies the SAME reaction DONE
        # against the new head's older bounds. When: wait polls 12s.
        # Then: exit 1 — the head move RESET the latch and
        # re-captured the baseline on the unchanged reaction (thread
        # 3868443452), so the stale->done reclassification is not a
        # transition and never a replacement; exit 0 was withheld to
        # the timeout (a review of the NEW head never signaled).
        code, out = run_wait(
            [[react("+1", rid=1)]] * 4,
            [OLD_HEAD_BOUNDS, NEW_HEAD_BOUNDS, NEW_HEAD_BOUNDS, NEW_HEAD_BOUNDS],
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn("THUMBS_UP (stale — predates the current round's start", out)
        self.assertIn("HEAD MOVED:", out)
        self.assertIn("3868443452", out)
        self.assertIn("exit 0 was withheld", out)
        self.assertNotIn("WAIT DONE", out)

    def test_head_flip_then_fresh_round_eyes_to_plus_one_exits_zero(self):
        # Given: the same stale-classified +1 under the old head
        # (12:30 push, latch armed at t=0); the head moves, and the
        # NEW head's round genuinely engages — EYES lands (13:00,
        # read at t=5 UNDER the new head) and the fresh pass (+1 at
        # 14:00, a different object) lands at t=10. When: wait polls.
        # Then: exit 0 at 10s — the move reset the latch at the EYES
        # probe, that post-change EYES RE-ARMED it, and the new
        # head's own THUMBS_UP is the observed transition (thread
        # 3868443452 requires a FRESH post-change transition; it
        # never strands a genuinely-reviewed new head).
        code, out = run_wait(
            [
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("eyes", created="2026-08-26T13:00:00Z")],
                [react("+1", created="2026-08-26T14:00:00Z", rid=2)],
            ],
            [OLD_HEAD_BOUNDS, NEW_HEAD_BOUNDS, NEW_HEAD_BOUNDS],
            600,
        )
        self.assertEqual(code, 0)
        self.assertIn("HEAD MOVED:", out)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)

    def test_unreadable_head_probe_never_resets_nor_pollutes(self):
        # Given: the stale +1 under the old head (t=0, latch armed);
        # the t=5 probe's round read FAILS entirely (bounds ('','',
        # '') — the EYES still reads, the oid does not); the head
        # NEVER moves. When: wait polls 12s. Then: exit 1 with NO
        # head-move note — an empty oid certifies no change (a read
        # failure is not a head move) and never UPDATES the observed
        # baseline, so the recovered readable probe's OLD head is not
        # counterfeit-detected as a change (thread 3868443452's
        # conservative arm).
        code, out = run_wait(
            [
                [react("+1", rid=1)],
                [react("eyes", created="2026-08-26T13:00:00Z")],
                [react("+1", rid=1)],
                [react("+1", rid=1)],
            ],
            [OLD_HEAD_BOUNDS, FAILED_PROBE, OLD_HEAD_BOUNDS, OLD_HEAD_BOUNDS],
            12,
        )
        self.assertEqual(code, 1)
        self.assertNotIn("HEAD MOVED", out)
        self.assertNotIn("WAIT DONE", out)


class HeadChangedPredicateTests(unittest.TestCase):
    def test_head_changed_truth_table(self):
        # Given: the latch module's head-change pair. When: head_changed
        # is evaluated. Then: only TWO READABLE, DIFFERENT oids accept —
        # an empty observed (nothing certified yet), an empty current
        # (a failed probe), and an unchanged head all refuse (thread
        # 3868443452).
        for observed, current, expected in (
            ("", "", False),
            ("", NEW_HEAD, False),
            (OLD_HEAD, "", False),
            (OLD_HEAD, OLD_HEAD, False),
            (OLD_HEAD, NEW_HEAD, True),
        ):
            self.assertEqual(
                pr_guard_reaction_latch.head_changed(observed, current),
                expected,
                (observed, current),
            )


if __name__ == "__main__":
    unittest.main()
