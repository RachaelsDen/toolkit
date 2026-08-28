"""pr_guard reaction round-15 tests — the WAIT half (PR #49 threads
3870293188 P1 / 3870293205 P1).

(1) 3870293188 — the request-advance latch reset: a Codex re-request
arriving AFTER the wait already sampled the preceding round's EYES
advances the marker high-water while saw_non_done / arm_watermark /
saw_verified_eyes stay certified by the OLD round; the old job's
delayed +1 (postdating BOTH the new request and the old EYES
watermark) then printed WAIT DONE and exited 0 before the newly
requested round ran. The wait now retains a REQUEST-marker high-water
(round-13's separate request element, riding the reading's new SIXTH
element): the baseline initializes on FIRST observation (a request
predating the wait is the normal cold start — no reset), and only a
STRICT advancement observed mid-wait resets the round latches
(saw_non_done, arm_watermark, the held baseline, saw_verified_eyes,
findings_pending — the cold-NONE hint state untouched). Round 16
(threads 3870734078/85) retired the gate-opening side-effect this
suite originally pinned and made the reset RE-CLOSE the gate: only a
verified EYES opens it now (the two opener tests below are repinned
to that rule — see pr_guard_reaction_round16_test).

(2) 3870293205 — the cold-NONE arming gate at WAIT START: round 14
gated NONEs only after a detected head move, so a cold NONE on the
FIRST stable-head probe still armed saw_non_done immediately — and a
probe landing in the preceding round's non-atomic EYES-removal/+1 gap
(particularly after a new head was already present before the wait
began) let the preceding job's delayed +1 — postdating the readable
head bounds, following the EMPTY watermark — exit 0 before any
current-round activity occurred. none_arming_gated now initializes
True at wait start; a cold NONE certifies nothing until the round
proves itself. Round 15's opener list (a verified EYES, a
request-high-water advance, or a marker-high-water advance — new bot
activity mid-wait; the FIRST probe's marker/request being the
cold-start baseline, never an advance) was REDUCED by round 16 to
the verified EYES alone: markers and requests carry no head/round
identity, so neither can certify the round (threads 3870734078/85 —
the two advance-opener tests below are repinned to the EYES-only
rule). A legitimate fast round that starts
inside a cold-NONE window may now conservatively hold to timeout —
the accepted price; the survey is the authority (pinned below).
Round 5's initial-+1 shape still exits 0 via the REPLACEMENT path
(the baseline captured at start, the strictly-newer +1 replacing it —
round 13's ordering), round 7's identity replacement is unchanged,
and the mid-wait head-move gate (round 14) keeps its exact semantics
(the round-14 suite carries those pins; its cold-start-none test is
repinned to the reversed round-15 rule — the exact hole).

The PROBE half of round 15 (3870293194 cold-start transition bound /
3870293197 partial-error unreadable) lives in
pr_guard_reaction_round15_probe_test — the suite-pair split at the
250 pure-LOC ceiling, tests included (the round-4/7/14 precedent).

No network: the wait tests patch gh_reactions/round_bounds/
head_ref_oid at their seams on the FakeClock.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round15_test -v
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock

BOT = pr_guard_reaction.REACTION_BOT

HEAD_A = "d84631fa1b2c3d4e5f60718293a4b5c6d7e8f9a0"
HEAD_B = "14ab97fffffffffffffffffffffffffffffff"


def react(content, created="2026-08-26T12:31:00Z", rid=None):
    return {
        "content": content,
        "created_at": created,
        "id": rid,
        "user": {"login": BOT},
    }


def run_wait(reads, bounds, timeout_secs):
    """wait_reaction on the FakeClock with per-probe 4-tuple bounds.

    heads default to each probe's OWN bounds oid (a stable bracket);
    the bounds tuples are round_bounds' (head_oid, pushed, request,
    composite marker) — round 15 tests exercise the REQUEST element
    (thread 3870293188) and the marker element (3870293205).
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
        probe["bounds"] = next(probes)
        return probe["bounds"][0]

    def fake_bounds(pr, timeout_secs=None):
        # PR #49 round 25 fixture-seam maintenance (thread
        # 3873970933): each probe's tuple rides a RoundBounds carrier
        # whose folded review evidence names the probe's OWN bounds
        # head (the stable-head rule — cold-start terminal signals
        # require review_head == observed head now); the tuples
        # themselves are unchanged.
        bounds = pr_guard_reaction_probe.RoundBounds(probe.pop("bounds"))
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


class RequestAdvanceResetTests(unittest.TestCase):
    def test_request_advance_resets_round_latches(self):
        # Given: the thread-3870293188 race — the round's verified
        # EYES (2026-08-02, past the 2026-08-01 push and request) is
        # sampled at t=0 and t=5 (latch armed, watermark captured);
        # a Codex RE-REQUEST lands (2026-08-20) so the t=5 probe's
        # bounds carry the advanced request — the standing EYES now
        # reads EYES_STALE (round 13's request binding) — and the OLD
        # job's delayed +1 (2026-08-26T14:00, postdating BOTH the new
        # request and the old EYES watermark) lands at t=10. When:
        # wait polls 12s. Then: exit 1 — the request advance RESET
        # saw_non_done/arm_watermark/held/saw_verified_eyes before
        # the t=5 reading contributed, so the delayed +1 only seeds a
        # held baseline and HOLDs; the pre-fix wait kept the t=0
        # certifications and printed WAIT DONE at t=10 before the
        # newly requested round ran.
        code, out = run_wait(
            [
                [react("eyes", created="2026-08-02T00:00:00Z", rid=5)],
                [react("eyes", created="2026-08-02T00:00:00Z", rid=5)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=6)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=6)],
            ],
            [
                (HEAD_A, "2026-08-01T00:00:00Z", "2026-08-01T00:05:00Z", "2026-08-01T00:05:00Z"),
                (HEAD_A, "2026-08-01T00:00:00Z", "2026-08-20T00:00:00Z", "2026-08-20T00:00:00Z"),
                (HEAD_A, "2026-08-01T00:00:00Z", "2026-08-20T00:00:00Z", "2026-08-20T00:00:00Z"),
                (HEAD_A, "2026-08-01T00:00:00Z", "2026-08-20T00:00:00Z", "2026-08-20T00:00:00Z"),
            ],
            12,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_first_observed_request_is_the_baseline(self):
        # Given: a request PREDATING the wait (every probe carries
        # the same 2026-08-01T00:05 request — the normal cold start),
        # the round's EYES (2026-08-02, postdating it) at t=0, and
        # the round's passing +1 (2026-08-26T14:00) at t=10. When:
        # wait polls. Then: exit 0 at 10s — the FIRST observation
        # INITIALIZES the request high-water (no reset, no gate
        # churn): an unchanged request never disturbs the round the
        # wait is legitimately watching.
        code, out = run_wait(
            [
                [react("eyes", created="2026-08-02T00:00:00Z", rid=5)],
                [react("eyes", created="2026-08-02T00:00:00Z", rid=5)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=6)],
            ],
            [
                (HEAD_A, "2026-08-01T00:00:00Z", "2026-08-01T00:05:00Z", "2026-08-01T00:05:00Z"),
                (HEAD_A, "2026-08-01T00:00:00Z", "2026-08-01T00:05:00Z", "2026-08-01T00:05:00Z"),
                (HEAD_A, "2026-08-01T00:00:00Z", "2026-08-01T00:05:00Z", "2026-08-01T00:05:00Z"),
            ],
            600,
        )
        self.assertEqual(code, 0)
        self.assertNotIn("ROUND RE-REQUESTED", out)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)

    def test_request_advance_no_longer_opens_the_cold_none_gate(self):
        # ROUND-16 REPIN of test_request_advance_opens_the_cold_none_gate
        # (thread 3870734078, the exact hole): the request advance
        # still RESETS the round latches (thread 3870293188 survives)
        # but no longer OPENS the none-arming gate — a re-request
        # carries no identity binding the reactions that follow it to
        # the newly requested round, and the preceding job's delayed
        # +1 lands after the request, passing every timestamp check.
        # Given: a cold start into NONE (t=0, nothing posted — the
        # 3870293205 gate holds it uncertified), a Codex re-request
        # landing between t=0 and t=5 (the request high-water
        # ADVANCES; the reset is a no-op on empty certifications; the
        # t=5 NONE stays gated), and the OLD job's delayed +1
        # (2026-08-26T14:00, postdating the request) at t=10. When:
        # wait polls 12s. Then: exit 1 — the ROUND RE-REQUESTED reset
        # prints but the gate stays closed (only a verified EYES
        # opens it), the NONE never arms, and the +1 only seeds a
        # held baseline and HOLDs to timeout; the round-15 wait this
        # test originally pinned opened the gate on the advance,
        # armed on the t=5 NONE, and exited 0 at t=10 before the
        # newly requested review started (see
        # pr_guard_reaction_round16_test).
        code, out = run_wait(
            [
                [],
                [],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
            ],
            [
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "2026-08-20T00:00:00Z", "2026-08-20T00:00:00Z"),
                (HEAD_B, "2021-01-01T00:00:00Z", "2026-08-20T00:00:00Z", "2026-08-20T00:00:00Z"),
                (HEAD_B, "2021-01-01T00:00:00Z", "2026-08-20T00:00:00Z", "2026-08-20T00:00:00Z"),
            ],
            12,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)


class ColdNoneGateTests(unittest.TestCase):
    def test_cold_initial_none_does_not_certify_completion(self):
        # Given: the thread-3870293205 race — head B (pushed 2021,
        # ALREADY present before the wait began) with the PRECEDING
        # round's non-atomic end switch in flight: the t=0 probe
        # lands in the EYES-removal/+1 gap and reads NONE (cold — no
        # EYES variant ever observed, no marker, no request), and the
        # preceding job's delayed +1 (2026-08-26T13:00, postdating
        # B's old readable bounds, following the EMPTY watermark)
        # lands at t=5. When: wait polls 12s. Then: exit 1 — the
        # cold initial NONE certifies NOTHING (the gate initializes
        # True at wait start and no opener fired), so the +1 only
        # seeds a held baseline and HOLDs; the pre-fix wait armed
        # saw_non_done on that NONE and printed WAIT DONE at t=5
        # before any current-round activity occurred.
        code, out = run_wait(
            [
                [],
                [react("+1", created="2026-08-26T13:00:00Z", rid=9)],
                [react("+1", created="2026-08-26T13:00:00Z", rid=9)],
                [react("+1", created="2026-08-26T13:00:00Z", rid=9)],
            ],
            [(HEAD_B, "2021-01-01T00:00:00Z", "", "")] * 4,
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_first_probe_marker_does_not_open_the_gate(self):
        # Given: a STANDING marker (2026-08-01, observed on the FIRST
        # probe — the cold-start baseline, never an advance), a cold
        # NONE at t=0/t=5, and a fresh +1 (2026-08-26T14:00,
        # postdating every bound) at t=5. When: wait polls 12s. Then:
        # exit 1 — the ACCEPTED PRICE: a legitimate fast round that
        # starts inside a cold-NONE window now conservatively holds
        # to timeout because nothing the wait can see ADVANCED
        # mid-wait (the survey is the authority); the pre-fix wait
        # armed on the cold NONE and exited 0 at t=5.
        code, out = run_wait(
            [
                [],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
            ],
            [(HEAD_B, "2021-01-01T00:00:00Z", "", "2026-08-01T00:00:00Z")] * 4,
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn("exit 0 was withheld", out)
        self.assertNotIn("ROUND RE-REQUESTED", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_marker_advance_midwait_no_longer_opens_the_gate(self):
        # ROUND-16 REPIN of test_marker_advance_midwait_opens_the_gate
        # (threads 3870734078/85's convergent rule — markers carry no
        # head/round identity): the marker-high-water advance no
        # longer opens the none-arming gate — a bot thread comment
        # landing mid-wait may be the STILL-RUNNING old job's post,
        # so it certifies nothing about the round the wait is
        # holding for. Given: a cold NONE at t=0 (no marker), the
        # round's first bot engagement — a thread comment (marker
        # 2026-08-20) landing BETWEEN t=0 and t=5 — the t=5 probe
        # still reading NONE, and a +1 (2026-08-26T14:00,
        # postdating the marker) at t=10. When: wait polls 12s. Then:
        # exit 1 — the gate stays closed (only a verified EYES opens
        # it), the NONE never arms, and the +1 only seeds a held
        # baseline and HOLDs to timeout (the accepted price — the
        # survey is the authority); the round-15 wait this test
        # originally pinned opened the gate on the advance, armed on
        # the t=5 NONE, and exited 0 at t=10 (see
        # pr_guard_reaction_round16_test).
        code, out = run_wait(
            [
                [],
                [],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
            ],
            [
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "", "2026-08-20T00:00:00Z"),
                (HEAD_B, "2021-01-01T00:00:00Z", "", "2026-08-20T00:00:00Z"),
                (HEAD_B, "2021-01-01T00:00:00Z", "", "2026-08-20T00:00:00Z"),
            ],
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("ROUND RE-REQUESTED", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_verified_eyes_opens_the_gate_and_exits_findings(self):
        # Given: a cold NONE at t=0 (gated), the round's VERIFIED
        # EYES (2026-08-26T12:31, past the 11:00 push) at t=5 — which
        # opens the gate AND arms saw_verified_eyes — then NONE at
        # t=10, t=15, and t=20 (the round removed its EYES and left
        # nothing current behind). When: wait polls. Then: exit 3 at
        # 20s (the round-23 repin, thread 3873317562: the third
        # consecutive absent probe) — the round-12 findings
        # discipline is UNCHANGED by the cold
        # gate: the EYES that opens the gate is the same EYES that
        # arms the findings precursor (the live-demo shape is safe).
        code, out = run_wait(
            [[], [react("eyes", rid=5)], [], [], []],
            [(HEAD_A, "2026-08-26T11:00:00Z", "", "")] * 5,
            600,
        )
        self.assertEqual(code, 3)
        self.assertIn("WAIT FINDINGS: EYES → NONE at 20s", out)

    def test_round5_replacement_survives_the_cold_none_gate(self):
        # Given: the round-5 initial-+1 shape — the prior +1
        # (2026-08-26T12:00, DONE on sight) stands at t=0 and is
        # HELD; a cold NONE lands at t=5 (now gated — it certifies
        # nothing); the genuine round's NEW +1 (2026-08-26T14:00, a
        # different strictly-newer object) replaces it at t=10.
        # When: wait polls. Then: exit 0 at 10s via the REPLACEMENT
        # path — the baseline captured at start plus round-13's
        # strictly-newer ordering — even though the cold NONE no
        # longer arms the latch path; the pre-fix wait exited 0 via
        # the latch instead (no OBSERVED REPLACED line).
        code, out = run_wait(
            [
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [],
                [react("+1", created="2026-08-26T14:00:00Z", rid=2)],
            ],
            [(HEAD_B, "2021-01-01T00:00:00Z", "", "")] * 3,
            600,
        )
        self.assertEqual(code, 0)
        self.assertIn("OBSERVED REPLACED", out)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)


if __name__ == "__main__":
    unittest.main()
