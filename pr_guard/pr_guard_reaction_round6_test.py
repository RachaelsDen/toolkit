"""pr_guard reaction round-6 tests (PR #49 threads 3868047715/3868047719).

Thread 3868047719 (P1): UNREADABLE round bounds never arm the
transition latch — a +1 whose bounds read failed is
THUMBS_UP_UNVERIFIED, a state DISTINCT from a verified
THUMBS_UP_STALE: not done, and not round evidence. The exact hole:
a transient round_bounds GraphQL failure at wait start labeled the
prior +1 stale (arming the latch); when bounds recovered, the
unchanged old +1 read DONE and the wait exited 0 on an ERROR-armed
latch. Now the failure-derived UNVERIFIED keeps polling ->
timeout exit 1 (conservative), while a recovered-bounds EYES (a
real signal) still arms and the later fresh +1 exits 0.

Thread 3868047715 (P2): the round-5 suite rides the aggregate —
pr_guard_test._SUITES registers pr_guard_reaction_round5_test
(319 -> 327) and this round-6 suite beside it (327 -> 333).

No network: the wait tests patch gh_reactions/round_bounds at their
seams on the FakeClock; the classification tests mock the same two
seams directly.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round6_test -v
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

# The thread-3868047719 hole's facts: the prior +1 (12:00) postdates
# the head push (11:00) and NO marker exists (the request-less round
# has not posted) — recovered bounds classify the SAME +1 DONE.
# PR #49 round 8 repin (thread 3868443452): round_bounds grew a
# head-first headRefOid element — one stable head throughout (the
# FAILED probe reads the whole triple ''), so the wait's head-change
# reset never fires in this suite.
HEAD_OID = "8ed444e0d5b1ad3b3ff6c9d3e3b4a5c6d7e8f9a0"
UNMARKED_BOUNDS = (HEAD_OID, "2026-08-26T11:00:00Z", "", "")
FAILED_BOUNDS = ("", "", "", "")
MARKED_BOUNDS = (HEAD_OID, "2026-08-26T11:00:00Z", "", "2026-08-26T13:05:00Z")


def react(content, created="2026-08-26T12:00:00Z"):
    return {"content": content, "created_at": created, "user": {"login": BOT}}


def run_wait(reads, bounds, timeout_secs):
    """wait_reaction on the FakeClock with PER-PROBE bounds; (code, out).

    (PR #49 round 25 fixture-seam maintenance, thread 3873970933:
    every probe's tuple rides a RoundBounds carrier whose folded
    review evidence names the STABLE head — the stamp between the
    13:05 marker and the completing 14:00 +1 — because the +1 is a
    POST-review verdict and cold-start completions require the
    evidence now; the marker-window tuples are unchanged.)
    """
    clock = FakeClock()
    items = iter(reads)
    probes = iter(bounds)

    def carried(tuple_bounds):
        out = pr_guard_reaction_probe.RoundBounds(tuple_bounds)
        out.review_head = HEAD_OID
        out.review_stamp = "2026-08-26T13:30:00Z"
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


class UnverifiedClassificationTests(unittest.TestCase):
    def read(self, reactions, bounds):
        with mock.patch.object(
            pr_guard_reaction, "gh_reactions", return_value=reactions
        ), mock.patch.object(
            pr_guard_reaction, "round_bounds", return_value=bounds
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
        ):
            return pr_guard_reaction.bot_review_reaction(48)

    def test_failed_bounds_read_unverified_not_stale(self):
        # Given: the bot's +1 (12:00) against bounds whose head oid
        # is READABLE but whose pushedDate/committedDate both read
        # null (the live-verified PR #49 shape). When: read. Then:
        # THUMBS_UP_UNVERIFIED — never done (the conservative core
        # keeps) and never STALE (stale now certifies a READABLE fact
        # the +1 predates; an unreadable date certifies nothing).
        # PR #49 round 13 repin (thread 3869259808): the pre-round-13
        # shape here was the fully-FAILED probe (("", "", "")), which
        # now RAISES ReactionBracketUnreadable (the whole probe is
        # UNREADABLE, retry next interval — see round13's suite); the
        # UNVERIFIED state survives through its null-dates shape.
        self.assertEqual(
            self.read([react("+1")], (HEAD_OID, "", "", "")),
            "THUMBS_UP_UNVERIFIED",
        )

    def test_readable_bounds_stale_stays_verified_stale(self):
        # Given: the same +1 with READABLE bounds — the head pushed
        # at 13:00 after the prior round's 12:00 pass. When: read.
        # Then: THUMBS_UP_STALE — a fact-certified stale (a state the
        # latch still arms on; thread 3868047719 narrows the stale
        # class, it does not widen the done one).
        self.assertEqual(
            self.read(
                [react("+1", created="2026-08-26T12:00:00Z")],
                (HEAD_OID, "2026-08-26T13:00:00Z", "", ""),
            ),
            "THUMBS_UP_STALE",
        )


class LatchArmingTests(unittest.TestCase):
    def test_only_verified_non_done_states_arm(self):
        # Given: the wait loop's states. When: the latch consults
        # arms_transition_latch. Then: EYES, NONE, and VERIFIED
        # THUMBS_UP_STALE arm (genuine round evidence); DONE,
        # THUMBS_UP_UNVERIFIED, and UNREADABLE never do (thread
        # 3868047719 — an error-derived stale must not counterfeit
        # the observed active->done transition).
        for state in ("EYES", "NONE", "THUMBS_UP_STALE"):
            self.assertTrue(pr_guard_reaction_latch.arms_transition_latch(state))
        for state in ("THUMBS_UP", "THUMBS_UP_UNVERIFIED", "UNREADABLE"):
            self.assertFalse(pr_guard_reaction_latch.arms_transition_latch(state))

    def test_unverified_renders_its_own_explanation(self):
        # Given: the UNVERIFIED state. When: rendered. Then: its own
        # explanation — never the stale render (the two states carry
        # different evidence: a verified fact vs a read failure).
        rendered = pr_guard_reaction_latch.render_state("THUMBS_UP_UNVERIFIED")
        self.assertIn("unverified", rendered)
        self.assertNotIn("stale", rendered)


class UnverifiedNeverArmsTests(unittest.TestCase):
    def test_transient_bounds_failure_persistent_thumbs_up_times_out(self):
        # Given: the prior round's +1 present at wait start; the
        # FIRST round_bounds probe FAILS (the transient GraphQL
        # failure), then bounds RECOVER — and the same +1 postdates
        # the push with no marker, so every later probe classifies it
        # DONE (the exact thread-3868047719 masquerade). When: wait
        # polls a 12s window. Then: exit 1 — the failed probe reads
        # UNREADABLE and never armed the latch, so the
        # recovered-bounds DONE is HELD to the timeout; exit 0 on an
        # error-certified probe is gone. (PR #49 round 13 repin,
        # thread 3869259808: the failed probe used to read
        # THUMBS_UP_UNVERIFIED — a held STATE; it now discards the
        # WHOLE probe as UNREADABLE, retry next interval — the same
        # never-arms semantics, one step more conservative.)
        code, out = run_wait(
            [[react("+1")]] * 4,
            [FAILED_BOUNDS, UNMARKED_BOUNDS, UNMARKED_BOUNDS, UNMARKED_BOUNDS],
            12,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("BOT REACTION: UNREADABLE"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("exit 0 was withheld", out)
        self.assertNotIn("WAIT DONE", out)

    def test_bounds_recovery_with_real_eyes_still_exits_zero(self):
        # Given: the same transient failure (UNVERIFIED first probe,
        # latch NOT armed); the round then genuinely engages — bounds
        # recover and EYES lands (t=5, the arm), and the fresh +1
        # (14:00, postdating the 13:05 marker) lands (t=10). When:
        # wait polls. Then: exit 0 — the VERIFIED EYES armed the
        # latch and the post-marker pass is the observed
        # away-and-back (thread 3868047719 keeps the working shape
        # working while closing the error-armed hole).
        code, out = run_wait(
            [
                [react("+1", created="2026-08-26T12:00:00Z")],
                [react("eyes")],
                [react("+1", created="2026-08-26T14:00:00Z")],
            ],
            [FAILED_BOUNDS, MARKED_BOUNDS, MARKED_BOUNDS],
            600,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)


if __name__ == "__main__":
    unittest.main()
