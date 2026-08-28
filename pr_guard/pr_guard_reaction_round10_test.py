"""pr_guard reaction round-10 tests (PR #49 threads 3868782039 +
3868782042, both P1).

Thread 3868782039 (P1): the head STABILITY bracket —
bot_reaction_reading reads the head oid FIRST (the new head_ref_oid
in the probe module), then the reactions, then the round bounds
(whose ONE combined GraphQL query carries the after-side oid beside
the dates it certifies), and a head that MOVED between the reads
raises ReactionHeadMoved: the WHOLE probe is UNREADABLE (retry next
interval), never a mixed snapshot. The reviewer's exact hole: the
probe paired an EYES for head A with head B's OID, the wait treated
the oid change as handled, reset the latch, and immediately
re-armed it from that pre-change EYES — a completion reaction for A
arriving after B was pushed then satisfied B's timestamp bounds and
exited 0 without B being reviewed. Post-fix the discard leaves the
wait's certifications untouched; the move is certified only by a
CLEAN post-move probe (the cross-probe reset stands, so completion
needs a fresh post-change transition or a demonstrably replaced
+1). An unreadable side ('' — a failed head read) certifies
nothing and never discards (head_changed's empty rule).

Thread 3868782042 (P1): equal-second round facts are AMBIGUOUS —
thumbs_up_round_state classifies only STRICTLY-greater created_at as
DONE (the `<` comparisons became `<=`: equality reads
THUMBS_UP_STALE), so a prior-round +1 landing in the SAME second as
a later head push (or a re-request/marker) can no longer ride an
armed latch to exit 0 — the API cannot establish which came first,
so the ambiguous second reads stale (conservative).

No network: the wait tests patch gh_reactions/round_bounds/
head_ref_oid at their seams on the FakeClock.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round10_test -v
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

HEAD_A = "4c654f21a0b3c4d5e6f708192a3b4c5d6e7f8a9b0"
HEAD_B = "b1f2b0b3c4d5e6f708192a3b4c5d6e7f8a9b0c1d2"
# The thread-3868782039 halves: head A pushed 11:00 (the EYES/13:00
# round belongs to it) while head B landed mid-probe with its OWN
# 12:30 push date — a mixed probe would certify B's bounds with A's
# reactions.
A_BOUNDS = (HEAD_A, "2026-08-26T11:00:00Z", "", "")
B_BOUNDS = (HEAD_B, "2026-08-26T12:30:00Z", "", "")


def react(content, created="2026-08-26T12:00:00Z", rid=None):
    return {
        "content": content,
        "created_at": created,
        "id": rid,
        "user": {"login": BOT},
    }


def read(reactions, bounds, head):
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", return_value=reactions
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", return_value=bounds
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=head
    ):
        return pr_guard_reaction.bot_review_reaction(48)


def run_wait(reads, bounds, timeout_secs, heads=None):
    """wait_reaction on the FakeClock with per-probe bounds; (code, out).

    Thread 3868782039: heads defaults to each probe's OWN bounds oid
    (a STABLE bracket — the head never moves inside a probe); an
    explicit heads list stages the MID-PROBE flip a mixed probe
    pairs (head_before from heads[i], the after-side oid from
    bounds[i][0]).
    """
    clock = FakeClock()
    items = iter(reads)
    probes = iter(bounds)
    head_reads = iter(heads) if heads is not None else None
    probe = {}

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    def fake_head(pr, timeout_secs=None):
        if head_reads is not None:
            return next(head_reads)
        probe["triple"] = next(probes)
        return probe["triple"][0]

    def fake_bounds(pr, timeout_secs=None):
        # PR #49 round 18 (threads 3871485035/3871485043): the review
        # evidence rides the BOUNDS now (the folded attr) — the wrap
        # feeds HEAD_B (the mixed-probe survivor's post-move round);
        # inert elsewhere (fixture-seam maintenance in the round-17
        # GOTCHA precedent, assertions byte-identical). Round 20
        # (thread 3872194023): the VERDICT STAMP rides beside the oid
        # — 13:30 sits between the surviving round's EYES (12:00) and
        # its +1 (14:00), past the 2023 wall floor. PR #49 round 25
        # (thread 3873970933): the evidence names EACH probe's own
        # bounds head (the stable-head rule) — cold-start completions
        # require review_head == observed head now, so a hardcoded
        # HEAD_B would fail every HEAD_A-stable fixture; the
        # survivor's completing probes still carry HEAD_B bounds.
        bounds = RoundBounds(probe.pop("triple") if head_reads is None and "triple" in probe else next(probes))
        bounds.review_head = bounds[0]
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


class HeadStableBracketTests(unittest.TestCase):
    def test_mid_probe_head_flip_discards_the_reading(self):
        # Given: the head reads A before the reactions walk, but the
        # round probe (AFTER the walk) reports the ref already on B —
        # the exact mid-probe move of thread 3868782039. When:
        # bot_review_reaction reads. Then: ReactionHeadMoved — the
        # probe is a MIXED snapshot (A's reactions beside B's
        # oid/dates) and the whole reading is UNREADABLE, never a
        # classification the wait could act on.
        with mock.patch.object(
            pr_guard_reaction, "gh_reactions", return_value=[react("eyes")]
        ), mock.patch.object(
            pr_guard_reaction, "round_bounds", return_value=B_BOUNDS
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=HEAD_A
        ):
            with self.assertRaises(pr_guard_reaction.ReactionHeadMoved) as raised:
                pr_guard_reaction.bot_review_reaction(48)
        self.assertIn("3868782039", str(raised.exception))

    def test_stable_head_reads_normally(self):
        # Given: the head reads the SAME oid on both sides of the
        # reactions walk. When: read. Then: the ordinary state — the
        # bracket certifies stability and never interferes.
        self.assertEqual(read([react("eyes")], A_BOUNDS, HEAD_A), "EYES")

    def test_failed_before_read_discards_the_probe(self):
        # Given: the cheap head-only read FAILED ('') while the
        # bounds probe succeeded. When: read. Then:
        # ReactionBracketUnreadable — either EMPTY bracket endpoint
        # makes the whole probe UNREADABLE (retry next interval):
        # an uncertified bracket must never let reactions pair with
        # bounds from a head that may have MOVED between the reads.
        # (PR #49 round 13 repin, thread 3869259808: this fixture
        # pinned the round-10 acceptance — head_changed("",
        # oid) continued the probe and read THUMBS_UP — the exact
        # hole; the empty side now certifies NOTHING in either
        # direction, participation included.)
        with mock.patch.object(
            pr_guard_reaction, "gh_reactions", return_value=[react("+1")]
        ), mock.patch.object(
            pr_guard_reaction, "round_bounds", return_value=A_BOUNDS
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=""
        ):
            with self.assertRaises(
                pr_guard_reaction.ReactionBracketUnreadable
            ) as raised:
                pr_guard_reaction.bot_review_reaction(48)
        self.assertIn("3869259808", str(raised.exception))

    def test_mixed_probe_is_unreadable_latch_untouched(self):
        # Given: the reviewer's exact wait-level race — t=0 reads
        # EYES under head A (the latch arms); between t=5's head
        # read and its round probe the ref MOVES to B, so the t=5
        # probe is MIXED (A's head_before beside B's bounds); B's
        # own review then completes (a fresh 14:00 +1 replacing the
        # 13:00 pass A's round left). When: wait polls 600s. Then:
        # exit 0 only at t=15 via the POST-change replacement — the
        # mixed probe printed UNREADABLE and never certified the
        # move (no HEAD MOVED line at t=5: its oid is ''), so the
        # latch/baseline reset ran on the t=10 CLEAN probe instead
        # and the pre-change EYES never re-armed anything. The
        # pre-fix wait reset-and-re-armed ON the mixed probe and
        # exited 0 at t=10 on A's 13:00 completion against B's
        # bounds — B reviewed by nobody (thread 3868782039).
        code, out = run_wait(
            [
                [react("eyes", created="2026-08-26T12:00:00Z", rid=5)],
                [react("eyes", created="2026-08-26T12:00:00Z", rid=5)],
                [react("+1", created="2026-08-26T13:00:00Z", rid=6)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=7)],
            ],
            [A_BOUNDS, B_BOUNDS, B_BOUNDS, B_BOUNDS],
            600,
            heads=[HEAD_A, HEAD_A, HEAD_B, HEAD_B],
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("BOT REACTION: UNREADABLE"), 1)
        self.assertEqual(out.count("HEAD MOVED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 15s", out)
        self.assertNotIn("WAIT DONE: THUMBS_UP at 10s", out)

    def test_persistent_mid_probe_flips_keep_polling_to_timeout(self):
        # Given: EVERY probe of a 12s window is mixed (the ref
        # retargets between each probe's head read and round probe —
        # the pathological thrash). When: wait polls. Then: exit 1 —
        # every probe is discarded UNREADABLE, no mixed snapshot
        # ever arms, exits, or resets anything, and the bounded poll
        # simply runs out (retry later; thread 3868782039).
        code, out = run_wait(
            [[react("+1", created="2026-08-26T13:00:00Z", rid=6)]] * 4,
            [B_BOUNDS] * 4,
            12,
            heads=[HEAD_A] * 4,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("BOT REACTION: UNREADABLE"), 1)
        self.assertNotIn("WAIT DONE", out)
        self.assertNotIn("HEAD MOVED", out)


class EqualSecondAmbiguityTests(unittest.TestCase):
    def test_strict_postdate_truth_table(self):
        # Given: the latch module's classification against
        # same-second facts. When: thumbs_up_round_state evaluates.
        # Then: EQUALITY reads THUMBS_UP_STALE — a created_at equal
        # to the push or the marker is AMBIGUOUS (the API cannot
        # order same-second writes), so only a STRICTLY-greater
        # created_at is DONE (thread 3868782042); unreadable bounds
        # stay UNVERIFIED (thread 3868047719 unchanged).
        for created, pushed, requested, expected in (
            ("2026-08-26T12:00:00Z", "2026-08-26T12:00:00Z", "", "THUMBS_UP_STALE"),
            ("2026-08-26T12:00:01Z", "2026-08-26T12:00:00Z", "", "THUMBS_UP"),
            (
                "2026-08-26T12:00:00Z",
                "2026-08-26T11:00:00Z",
                "2026-08-26T12:00:00Z",
                "THUMBS_UP_STALE",
            ),
            (
                "2026-08-26T12:00:01Z",
                "2026-08-26T11:00:00Z",
                "2026-08-26T12:00:00Z",
                "THUMBS_UP",
            ),
            ("2026-08-26T12:00:00Z", "", "", "THUMBS_UP_UNVERIFIED"),
        ):
            self.assertEqual(
                pr_guard_reaction_latch.thumbs_up_round_state(
                    created, pushed, requested
                ),
                expected,
                (created, pushed, requested),
            )

    def test_same_second_plus_one_after_observed_eyes_times_out(self):
        # Given: the thread's exact armed-latch race — the wait
        # observes EYES, then the head pushes at 12:00:00 while the
        # prior round's +1 also lands 12:00:00: the SAME second,
        # order unknowable. When: wait polls 12s. Then: exit 1 — the
        # equal-second +1 reads STALE (never done), so the armed
        # latch has nothing to accept; the pre-fix `<` classified it
        # CURRENT and exited 0 at t=5 on a pass that may have
        # PRECEDED the push (thread 3868782042). Round-11 repin
        # (thread 3868979509): an EYES predating the push now reads
        # EYES_STALE and arms nothing, so the timeout no longer
        # depends on the latch — the stale +1 alone withholds exit 0.
        code, out = run_wait(
            [
                [react("eyes", created="2026-08-26T11:59:00Z", rid=5)],
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
            ],
            [(HEAD_A, "2026-08-26T12:00:00Z", "", "")] * 4,
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn("THUMBS_UP (stale — predates the current round's start", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)
        self.assertNotIn("WAIT DONE", out)

    def test_strictly_later_plus_one_exits_zero(self):
        # Given: the EYES 11:59:30 observed AFTER the 11:59:00 push
        # (round-11 repin, thread 3868979509: only a post-head EYES
        # arms the latch) and the round's +1 landing ONE SECOND later
        # still later (12:00:01 — strictly greater than every round
        # fact). When: wait polls. Then: exit 0 at 5s — a provably
        # post-round pass completes the wait; the ambiguity fix
        # never withholds a genuinely ordered completion (thread
        # 3868782042's conservative-only direction).
        code, out = run_wait(
            [
                [react("eyes", created="2026-08-26T11:59:30Z", rid=5)],
                [react("+1", created="2026-08-26T12:00:01Z", rid=6)],
            ],
            [(HEAD_A, "2026-08-26T11:59:00Z", "", "")] * 2,
            600,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)


if __name__ == "__main__":
    unittest.main()
