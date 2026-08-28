"""pr_guard reaction round-9 tests (PR #49 threads 3868625463 +
3868625469, P1).

Thread 3868625463 (P1): the wait retains a MONOTONE marker
HIGH-WATER — a request-less round's only marker (a bot thread
comment) is evicted from the bounded comments(last:3)/
reviewThreads(last:10) windows by three later comments, so the
probe that SAW it armed the latch on the prior +1's staleness while
a LATER probe (marker evicted, '') would reclassify the same
unchanged +1 current and exit 0 on the armed latch; the effective
marker never goes backwards, so the evicted-window probe still
reads STALE and the wait holds to its timeout — and a genuinely
completing round (its fresh +1 postdating even the retained
high-water) still exits 0.

Thread 3868625469 (P1): completion follows the OBSERVED EYES — the
prior +1 coexisting with a newer EYES arms the latch, but when the
EYES is removed before a replacement +1 becomes visible (a
non-atomic reaction switch) the OLD +1 is latest again; the
accepted +1's identity must POSTDATE the observed-activity
watermark (the arming probe's latest-reaction identity), else the
wait keeps polling to its timeout.

No network: the wait tests patch gh_reactions/round_bounds at
their seams on the FakeClock.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round9_test -v
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

HEAD_OID = "4c654f21a0b3c4d5e6f708192a3b4c5d6e7f8a9b0"

# The thread-3868625463 windows: MARKED_BOUNDS carries the
# request-less round's ONLY marker (the bot's 12:30 thread comment,
# visible inside comments(last:3)); EVICTED_BOUNDS is the SAME
# history after three later comments pushed the marker out of the
# bounded window (the probe faithfully reports ''). The prior round's
# +1 (12:00) predates the marker, so only the RETAINED high-water
# keeps it stale on the evicted probes.
MARKED_BOUNDS = (HEAD_OID, "2026-08-26T11:00:00Z", "", "2026-08-26T12:30:00Z")
EVICTED_BOUNDS = (HEAD_OID, "2026-08-26T11:00:00Z", "", "")
# The thread-3868625469 bounds: no marker at all — the round engaged
# with EYES only, so the prior +1 (12:00) classifies DONE on sight
# and only the watermark withholds it.
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
    review evidence names the STABLE head — the stamp between the
    observed EYES 13:00 and the completing 14:00 +1 (13:30 for the
    findings shape's earlier window) — the terminal signals are
    POST-review verdicts and cold-start completions require the
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


class MarkerHighWaterTests(unittest.TestCase):
    def test_evicted_marker_keeps_prior_plus_one_stale(self):
        # Given: a request-less round marked ONLY by the bot's thread
        # comment (12:30) — the t=0 probe's bounded window still sees
        # it, so the prior +1 (12:00) reads STALE and arms the
        # transition latch; three later comments EVICT the marker from
        # comments(last:3), so every later probe's window reads ''.
        # When: wait polls 12s with the UNCHANGED +1. Then: exit 1 —
        # the retained high-water (12:30) keeps the +1 STALE on every
        # evicted-window probe (thread 3868625463); the pre-fix wait
        # reclassified the same +1 current on the evicted probe and
        # exited 0 on the armed latch with no completion posted.
        code, out = run_wait(
            [[react("+1", rid=1)]] * 4,
            [MARKED_BOUNDS, EVICTED_BOUNDS, EVICTED_BOUNDS, EVICTED_BOUNDS],
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn("THUMBS_UP (stale — predates the current round's start", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)
        self.assertNotIn("WAIT DONE", out)

    def test_retained_marker_never_strands_a_completing_round(self):
        # Given: the same marked start (12:30 marker, the prior +1
        # 12:00 reading STALE and arming), then the round GENUINELY
        # completes — EYES (13:00) observed, then a fresh +1 (14:00) —
        # while the marker stays evicted from every later window.
        # When: wait polls. Then: exit 0 at 10s — the fresh +1
        # postdates even the RETAINED high-water and follows the
        # observed EYES (thread 3868625463 never withholds a real
        # completion; the watermark of 3868625469 accepts it too).
        code, out = run_wait(
            [
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("eyes", created="2026-08-26T13:00:00Z", rid=5)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=2)],
            ],
            [MARKED_BOUNDS, EVICTED_BOUNDS, EVICTED_BOUNDS],
            600,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)

    def test_effective_round_marker_truth_table(self):
        # Given: the latch module's high-water pair. When:
        # effective_round_marker is evaluated. Then: max of the two
        # ('' sorts lowest) — the retained marker survives an evicted
        # ('') observation, a newer observation RAISES it, and an
        # older observation never lowers it (thread 3868625463).
        for retained, observed, expected in (
            ("", "", ""),
            ("", "2026-08-26T12:30:00Z", "2026-08-26T12:30:00Z"),
            ("2026-08-26T12:30:00Z", "", "2026-08-26T12:30:00Z"),
            ("2026-08-26T12:30:00Z", "2026-08-26T13:00:00Z", "2026-08-26T13:00:00Z"),
            ("2026-08-26T13:00:00Z", "2026-08-26T12:30:00Z", "2026-08-26T13:00:00Z"),
        ):
            self.assertEqual(
                pr_guard_reaction_latch.effective_round_marker(retained, observed),
                expected,
                (retained, observed),
            )


class ObservedEyesWatermarkTests(unittest.TestCase):
    def test_plus_one_predating_observed_eyes_exits_findings(self):
        # Given: the prior round's +1 (12:00) stands DONE-classified
        # at t=0 (held); EYES (13:00) lands and is OBSERVED at t=5 —
        # the latch arms, the watermark captures the EYES identity;
        # the EYES is then removed before any replacement +1 is
        # visible, so the SAME old +1 is latest again at t=10, t=15,
        # and t=20 (the deadline probe). When: wait polls 20s.
        # Then: exit 3 — an accepted +1
        # must FOLLOW the observed EYES (thread 3868625469 withholds
        # exit 0), and a +1 PROVEN older than the observed arming
        # EYES is the SAME completion-absent signal NONE is (the
        # round-14 repin of this fixture, thread 3869941521: the
        # round-9 code sat on this HOLDING THUMBS_UP to the timeout
        # instead of exiting findings; the round-23 repin, thread
        # 3873317562: the confirmation is the THIRD consecutive
        # absent probe, so the deadline moved past the old 12s
        # confirming probe — the at-deadline third absent probe still
        # reports findings, never timeout, per the round-12 rule).
        code, out = run_wait(
            [
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("eyes", created="2026-08-26T13:00:00Z", rid=5)],
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
            ],
            [UNMARKED_BOUNDS] * 5,
            20,
        )
        self.assertEqual(code, 3)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("3868625469", out)
        self.assertIn(
            "WAIT FINDINGS: EYES → a prior-round +1 (older than the "
            "observed EYES) at 20s",
            out,
        )
        self.assertNotIn("WAIT DONE", out)

    def test_plus_one_postdating_observed_eyes_exits_zero(self):
        # Given: the same start and the same observed EYES (13:00),
        # but the round COMPLETES — the reaction switches to a +1
        # (14:00, a new object) postdating the EYES. When: wait
        # polls. Then: exit 0 at 10s — the accepted +1 follows the
        # observed-activity watermark (thread 3868625469 accepts
        # every genuine completion).
        code, out = run_wait(
            [
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("eyes", created="2026-08-26T13:00:00Z", rid=5)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=2)],
            ],
            [UNMARKED_BOUNDS] * 3,
            600,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)

    def test_reaction_follows_truth_table(self):
        # Given: the latch module's watermark pair. When:
        # reaction_follows is evaluated. Then: an empty watermark
        # binds nothing; an empty or IDENTICAL candidate never
        # follows; otherwise created_at orders first and the numeric
        # id breaks a same-second tie (thread 3868625469).
        for candidate, watermark, expected in (
            ("2026-08-26T12:00:00Z|8079201065", "", True),
            ("", "2026-08-26T13:00:00Z|8079201066", False),
            ("2026-08-26T13:00:00Z|8079201066", "2026-08-26T13:00:00Z|8079201066", False),
            ("2026-08-26T14:00:00Z|8079201067", "2026-08-26T13:00:00Z|8079201066", True),
            ("2026-08-26T12:00:00Z|8079201067", "2026-08-26T13:00:00Z|8079201066", False),
            ("2026-08-26T12:00:00Z|8079201067", "2026-08-26T12:00:00Z|8079201066", True),
            ("2026-08-26T12:00:00Z|8079201065", "2026-08-26T12:00:00Z|8079201066", False),
            ("2026-08-26T12:00:00Z|", "2026-08-26T12:00:00Z|", False),
        ):
            self.assertEqual(
                pr_guard_reaction_latch.reaction_follows(candidate, watermark),
                expected,
                (candidate, watermark),
            )


if __name__ == "__main__":
    unittest.main()
