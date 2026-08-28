"""pr_guard reaction round-14 tests (PR #49 threads 3869941505 P1 /
3869941509 P2 / 3869941521 P1).

The three unresolved findings of the round-13 review:

(1) 3869941505 — the transition probe's NONE armed the completion
latch: when head B is observed during head A's non-atomic
EYES-removal/+1 switch, the probe reads NONE (the old EYES gone, the
replacement +1 not yet visible); the head-move reset clears the old
certifications, then the GENERIC latch arm immediately re-arms
saw_non_done on that NONE (an arming state), and head A's delayed +1
— created after the transition observation, passing head B's older
timestamp bounds and the EMPTY watermark — exits 0 with B reviewed by
nobody. A post-transition NONE now stays GATED (never arms) until
something certifies the NEW head's round: an EYES past the transition
floor (round 16, thread 3870734085 RETIRED the round-14
post-observation-marker opener — markers carry no head identity; only
the verified EYES opens the gate, see
pr_guard_reaction_round16_test). A
cold-start NONE under a STABLE head still armed in round 14 (round
5's initial-+1 protection) — ROUND 15 (thread 3870293205) reversed
that: the gate now initializes True at wait start, and this suite's
cold-start test is repinned to the reversed rule (the exact hole;
see pr_guard_reaction_round15_test).

(2) 3869941509 — an unrecognized latest reaction content (rocket,
heart, ...) read NONE, and two persistent NONEs after a verified EYES
are the terminal findings signal (exit 3): an unexpected reaction
made the wait claim findings while the bot may still be running. The
reading now returns the DISTINCT REACTION_UNKNOWN state — never DONE,
never latch-arming, never satisfying the findings transition or the
cold-NONE hint (an unknown reaction is not "no reaction"; it also
breaks NONE persistence like any other reading) — rendered with its
own line carrying the content. (The UNKNOWN suite-pair companion —
pr_guard_reaction_round14_unknown_test — carries this finding's
tests: the 250 pure-LOC ceiling's split, tests included, the
round-4/round-7 pair precedent.)

(3) 3869941521 — a prior round's +1 remaining beside the current
round's EYES: removing the EYES after the round found feedback
EXPOSES the older +1 (not NONE). The watermark correctly withholds
exit 0 (HOLDING), but the findings confirmation advanced only on
literal NONE, so the waiter sat on the non-following THUMBS_UP to the
full timeout. A persistent +1 PROVEN older than the observed arming
EYES (the DONE-and-not-following shape the watermark/replacement
checks already reject as a pass) is now the SAME absence signal NONE
is: same two-probe persistence, same verified-EYES precursor (the
round-5 HOLDING shape — no EYES ever observed — never exits 3), same
head-move reset.

No network: the wait tests patch gh_reactions/round_bounds/
head_ref_oid at their seams on the FakeClock (WALL_NOW is
2023-11-14T22:13:20Z — the transition-gate fixtures' pre/post-wall
stamps key off it, the round-13 rule).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round14_test -v
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_reaction
from .pr_guard_merge_fixtures import FakeClock
from .pr_guard_reaction_probe import RoundBounds

BOT = pr_guard_reaction.REACTION_BOT

HEAD_A = "d84631fa1b2c3d4e5f60718293a4b5c6d7e8f9a0"
HEAD_B = "14ab97fffffffffffffffffffffffffffffff"

# WALL_NOW (the FakeClock wall start) is 2023-11-14T22:13:20Z: the
# transition-gate stamps split around it (thread 3869941505 — the
# move is detected at the t=5 probe, so the floor reads
# 2023-11-14T22:13:25Z and every pre/post-wall stamp orders against
# THAT, the round-13 demotion rule).
WALL_NOW_ISO = "2023-11-14T22:13:20Z"
PRE_WALL_EYES = "2022-06-01T00:00:00Z"
PRE_WALL_PLUS = "2022-07-01T00:00:00Z"
POST_WALL_EYES = "2024-01-01T00:00:00Z"
POST_WALL_MARKER = "2024-03-01T00:00:00Z"
POST_WALL_PLUS = "2024-04-01T00:00:00Z"

# The stable-head bounds for the UNKNOWN/resurfaced-+1 fixtures: the
# 11:00 push leaves both the 12:31 EYES (verified-current, round 11)
# and a 12:00 +1 (DONE-classified) standing — exactly the
# thread-3869941521 coexistence.
STABLE_BOUNDS = (HEAD_A, "2026-08-26T11:00:00Z", "", "")
HEAD_A_BOUNDS = (HEAD_A, "2022-05-01T00:00:00Z", "", "")
HEAD_B_BOUNDS = (HEAD_B, "2021-01-01T00:00:00Z", "", "")


def react(content, created="2026-08-26T12:31:00Z", rid=None):
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

    heads defaults to each probe's OWN bounds oid (a stable bracket);
    an explicit list stages a move between probes (thread 3869941505).
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
        probe["bounds"] = next(probes)
        return probe["bounds"][0]

    def fake_bounds(pr, timeout_secs=None):
        # PR #49 round 18 (threads 3871485035/3871485043): the review
        # evidence rides the BOUNDS now (the folded attr) — the wrap
        # feeds HEAD_B (the post-floor survivor's own round); inert
        # elsewhere (fixture-seam maintenance in the round-17 GOTCHA
        # precedent, assertions byte-identical). Round 20 (thread
        # 3872194023): the VERDICT STAMP rides beside the oid —
        # 2024-01-15 sits between the surviving round's EYES
        # (2024-01) and its +1 (2024-02), past the 2023 wall floor.
        # PR #49 round 25 (thread 3873970933): the evidence names
        # EACH probe's own bounds head (the stable-head rule) —
        # cold-start terminal signals require review_head == observed
        # head now, so a hardcoded HEAD_B fails every HEAD_A-stable
        # findings fixture; the post-move survivor's completing
        # probes still carry HEAD_B bounds.
        bounds = RoundBounds(probe.pop("bounds") if head_reads is None and "bounds" in probe else next(probes))
        bounds.review_head = bounds[0]
        bounds.review_stamp = "2024-01-15T00:00:00Z"
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


class TransitionNoneGateTests(unittest.TestCase):
    def test_transition_probe_none_does_not_arm_completion(self):
        # Given: the thread-3869941505 race — head A (pushed 2022-05)
        # shows the bot's EYES (2022-06, current, arming at t=0); the
        # ref moves to head B (pushed 2021, PREDATING that EYES) and
        # A's round enters its non-atomic end switch, so the t=5
        # transition probe reads NONE (the EYES removed, A's +1 not
        # yet visible); A's delayed +1 (2022-07, created after the
        # transition observation) lands at t=10 and passes B's older
        # bounds. When: wait polls 12s. Then: exit 1 — the transition
        # probe's NONE is GATED (nothing certifies B's round), so the
        # delayed +1 HOLDS with no latch and no watermark behind it;
        # the pre-fix wait armed saw_non_done on that NONE and exited
        # 0 at t=10 with B reviewed by nobody.
        code, out = run_wait(
            [
                [react("eyes", created=PRE_WALL_EYES, rid=5)],
                [],
                [react("+1", created=PRE_WALL_PLUS, rid=6)],
                [react("+1", created=PRE_WALL_PLUS, rid=6)],
            ],
            [HEAD_A_BOUNDS, HEAD_B_BOUNDS, HEAD_B_BOUNDS, HEAD_B_BOUNDS],
            12,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("HEAD MOVED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_later_probes_none_stay_gated(self):
        # Given: the same move at t=5, then ANOTHER NONE at t=10 (the
        # switch window still open — B's round has still posted
        # nothing), and A's delayed +1 at t=15. When: wait polls 17s.
        # Then: exit 1 — the gate PERSISTS across probes (a later
        # cold NONE certifies B's round no more than the transition
        # probe's did); the pre-fix wait armed on the second NONE and
        # exited 0 at t=15.
        code, out = run_wait(
            [
                [react("eyes", created=PRE_WALL_EYES, rid=5)],
                [],
                [],
                [react("+1", created=PRE_WALL_PLUS, rid=6)],
                [react("+1", created=PRE_WALL_PLUS, rid=6)],
            ],
            [HEAD_A_BOUNDS] + [HEAD_B_BOUNDS] * 4,
            17,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 17s elapsed", out)

    def test_post_floor_eyes_clears_the_gate(self):
        # Given: the move at t=5 with the gated NONE, then B's OWN
        # round engages — a fresh EYES (2024-01, POST-dating the
        # transition observation) at t=15 — and B's round passes (+1
        # 2024-02) at t=20. When: wait polls. Then: exit 0 at 20s —
        # the post-floor EYES certifies B's round (the gate opens,
        # the latch arms, the watermark captures the EYES) and the
        # gate never strands a genuinely-reviewed new head.
        code, out = run_wait(
            [
                [react("eyes", created=PRE_WALL_EYES, rid=5)],
                [],
                [],
                [react("eyes", created=POST_WALL_EYES, rid=7)],
                [react("+1", created="2024-02-01T00:00:00Z", rid=8)],
            ],
            [HEAD_A_BOUNDS] + [HEAD_B_BOUNDS] * 4,
            600,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 20s", out)

    def test_post_floor_marker_no_longer_clears_the_gate(self):
        # ROUND-16 REPIN of test_post_observation_marker_clears_the_gate
        # (thread 3870734085, the exact hole): the marker postdating
        # the transition floor no longer certifies the new head's
        # round — marker timestamps are retained across head moves
        # and carry NO head identity, and a still-running review of
        # the OLD head can post a thread comment (or a
        # submitted-review marker) after the floor. Given: the move
        # at t=5 with the gated NONE; at t=10 the round probe carries
        # a marker POSTDATING the transition observation (2024-03 —
        # the old-head job's post), and a +1 postdating that marker
        # (2024-04) lands at t=12. When: wait polls 12s. Then: exit 1
        # — the gate stays closed (round 16: only a verified EYES
        # opens it), the NONE never arms, and the old job's +1 only
        # seeds a held baseline and HOLDs to timeout; the round-14
        # wait this test originally pinned opened the gate on the
        # post-floor marker and exited 0 at t=12 with the new head
        # unreviewed (see pr_guard_reaction_round16_test).
        code, out = run_wait(
            [
                [react("eyes", created=PRE_WALL_EYES, rid=5)],
                [],
                [],
                [react("+1", created=POST_WALL_PLUS, rid=8)],
            ],
            [
                HEAD_A_BOUNDS,
                HEAD_B_BOUNDS,
                (HEAD_B, "2021-01-01T00:00:00Z", "", POST_WALL_MARKER),
                (HEAD_B, "2021-01-01T00:00:00Z", "", POST_WALL_MARKER),
            ],
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_cold_start_none_now_requires_certification(self):
        # ROUND-15 REPIN of test_cold_start_none_still_arms (thread
        # 3870293205, the exact hole): the cold-start NONE no longer
        # arms — none_arming_gated initializes True at WAIT START,
        # so the initial-+1 protection's latch path is closed until
        # the round certifies itself. Given: a STABLE head (no move)
        # and a cold NONE at t=0 (nothing posted), then a genuine +1
        # at t=10. When: wait polls 12s. Then: exit 1 — the +1 only
        # seeds a held baseline and HOLDs (a legitimate fast round
        # starting inside a cold-NONE window conservatively holds to
        # timeout — the accepted price, the survey is the authority);
        # round 5's shape still exits 0 through the REPLACEMENT path
        # when a strictly-newer +1 replaces the held one (the
        # round-15 suite pins that survivor).
        code, out = run_wait(
            [[], [], [react("+1", created="2024-02-01T00:00:00Z", rid=8)], []],
            [HEAD_B_BOUNDS] * 4,
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)


class ResurfacedPlusOneTests(unittest.TestCase):
    def test_resurfaced_older_plus_one_exits_findings(self):
        # Given: the thread-3869941521 race — the current round's
        # verified EYES (12:31) observed at t=0 with the PRIOR
        # round's +1 (12:00) standing beside it; the round found
        # feedback and removed its EYES, EXPOSING the older +1
        # (DONE-classified — it postdates the 11:00 push — but NOT
        # following the observed-EYES watermark) at t=5, persisting
        # at t=10 and t=15. When: wait polls. Then: exit 3 at 15s
        # (the round-23 repin, thread 3873317562: the third
        # consecutive absent probe, not the second) — a +1
        # PROVEN older than the observed arming EYES is the SAME
        # absence-of-completion signal NONE is (the watermark already
        # withholds exit 0); the pre-fix wait sat on the HOLDING
        # THUMBS_UP to the full timeout instead of exiting findings.
        code, out = run_wait(
            [
                [react("eyes", rid=5)],
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
            ],
            [STABLE_BOUNDS] * 4,
            600,
        )
        self.assertEqual(code, 3)
        self.assertIn(
            "WAIT FINDINGS: EYES → a prior-round +1 (older than "
            "the observed EYES) at 15s",
            out,
        )
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertNotIn("WAIT TIMEOUT", out)

    def test_resurfaced_plus_one_requires_the_eyes_precursor(self):
        # Given: the round-5 HOLDING shape — the prior round's +1
        # (12:00, DONE on sight) stands from t=0 and NO EYES variant
        # is EVER observed. When: wait polls 12s. Then: exit 1 — the
        # findings transition requires the arming-EYES precursor (a
        # bare non-following +1 with no observed EYES is the
        # initial-hold shape, withheld to timeout, never exit 3).
        code, out = run_wait(
            [[react("+1", created="2026-08-26T12:00:00Z", rid=1)]] * 4,
            [STABLE_BOUNDS] * 4,
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("exit 0 was withheld", out)
        self.assertNotIn("WAIT FINDINGS", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_flip_back_to_eyes_clears_the_pending(self):
        # Given: the exposed prior +1 at t=5 (findings pending), then
        # the round goes ACTIVE AGAIN — a fresh EYES (12:32, a new
        # object) at t=10 — and passes with a +1 (14:00) at t=15.
        # When: wait polls. Then: exit 0 at 15s — the absence-streak
        # persistence discipline: the EYES reading resets the streak
        # to zero (a transient exposure, the non-atomic switch's mirror
        # image), the watermark re-arms on the fresh EYES, and the
        # following +1 is the ordinary pass.
        code, out = run_wait(
            [
                [react("eyes", rid=5)],
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("eyes", created="2026-08-26T12:32:00Z", rid=6)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=7)],
            ],
            [STABLE_BOUNDS] * 4,
            600,
        )
        self.assertEqual(code, 0)
        self.assertNotIn("WAIT FINDINGS", out)
        self.assertIn("WAIT DONE: THUMBS_UP at 15s", out)

    def test_none_then_resurfaced_plus_one_confirms(self):
        # Given: a verified EYES, a NONE at t=5 (the removal lands),
        # and the exposed prior +1 at t=10 AND t=15. When: wait
        # polls. Then: exit 3 at 15s (the round-23 repin, thread
        # 3873317562: the third consecutive absent probe) — NONE and
        # the proven-older +1 are the SAME
        # absence signal: any absent reading feeds the streak and
        # the streak's full count CONFIRMS it (the round removed its
        # EYES and left no current-round completion behind, whatever
        # the latest reaction now happens to be).
        code, out = run_wait(
            [
                [react("eyes", rid=5)],
                [],
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
            ],
            [STABLE_BOUNDS] * 4,
            600,
        )
        self.assertEqual(code, 3)
        self.assertIn(
            "WAIT FINDINGS: EYES → a prior-round +1 (older than "
            "the observed EYES) at 15s",
            out,
        )


if __name__ == "__main__":
    unittest.main()
