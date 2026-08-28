"""pr_guard reaction round-16 tests (PR #49 threads 3870734078 P1 /
3870734085 P1) — the EYES-only NONE-gate openers.

The two findings converge on ONE invariant: markers and requests
carry NO head/round identity, so neither can certify the round a
NONE would arm against — the ONLY opener of none_arming_gated is a
verified EYES (state == REACTION_ACTIVE, the one classification that
binds the head push, the formal request, and the transition floor —
rounds 11/13/15).

(1) 3870734078 — "Keep a re-request from arming on NONE": a Codex
re-request arriving while the reaction is NONE advanced the request
high-water and OPENED the cold-start gate (round 15's opener), so the
same probe immediately armed saw_non_done on that NONE — undoing the
request-advance latch reset (thread 3870293188) in the same iteration
— and the preceding job's delayed +1 (landing after the request,
passing every timestamp check against the EMPTY watermark) printed
WAIT DONE before the newly requested review started. The
request-advance RESET itself survives (it is protective); its
gate-opening side-effect is retired, and the reset now RE-CLOSES the
gate (mirroring the head-move block): a re-request supersedes every
certification the preceding round earned, including a gate its
verified EYES opened — the reset's five assignments alone were undone
by the gate the old EYES left open. The round-13 request binding
guarantees the only EYES reading ACTIVE past the advance is a
verified POST-REQUEST one, which re-opens below in the same probe.

(2) 3870734085 — "Do not certify a new head from old-head markers":
after a head change, a still-running review of the OLD head can post
a thread comment or a submitted-review marker after transition_floor,
and round 14's marker opener (marker_high_water > transition_floor)
opened the NEW head's NONE gate on it — the marker is not associated
with the new OID (marker timestamps are retained across head moves
and carry no head identity). The old job removing its EYES and later
posting its +1 then armed on NONE and produced WAIT DONE without the
new head being reviewed. The opener is retired: only current-head
activity (a verified EYES past the floor — the round-13 demotion
already enforces post-floor for ACTIVE post-move readings)
certifies.

THE CONSERVATIVE PRICE (round-15 precedent, accepted): a legitimate
round that goes NONE→+1 with NO EYES ever observed now holds to
timeout (the replacement path still exits 0 when a baseline exists);
the survey is the authority. 3870734078's text offers "or a later
bot marker" as an alternative opener — a post-request marker from
the still-running OLD job has exactly the same no-identity problem
(3870734085's evidence), so the EYES-only rule is preferred and
satisfies both findings.

The exact-hole repins live beside their original suites:
round-14's test_post_observation_marker_clears_the_gate and
round-15's test_request_advance_opens_the_cold_none_gate +
test_marker_advance_midwait_opens_the_gate (each repinned to assert
the gate stays closed; documented in the round-16 commit body).

No network: the wait tests patch gh_reactions/round_bounds/
head_ref_oid at their seams on the FakeClock (WALL_NOW is
2023-11-14T22:13:20Z — the head-move fixtures' pre/post-wall stamps
key off it, the round-13/14 rule).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round16_test -v
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

# WALL_NOW (the FakeClock wall start) is 2023-11-14T22:13:20Z: the
# head-move fixtures' stamps split around the t=5 transition floor
# 2023-11-14T22:13:25Z (the round-14 rule — the move is detected at
# the t=5 probe).
WALL_NOW_ISO = "2023-11-14T22:13:20Z"
PRE_WALL_EYES = "2022-06-01T00:00:00Z"
POST_WALL_MARKER = "2024-03-01T00:00:00Z"
POST_WALL_PLUS = "2024-04-01T00:00:00Z"

HEAD_A_BOUNDS = (HEAD_A, "2022-05-01T00:00:00Z", "", "")
HEAD_B_BOUNDS = (HEAD_B, "2021-01-01T00:00:00Z", "", "")


def react(content, created="2026-08-26T12:31:00Z", rid=None):
    return {
        "content": content,
        "created_at": created,
        "id": rid,
        "user": {"login": BOT},
    }


def run_wait(reads, bounds, timeout_secs, review=None):
    """wait_reaction on the FakeClock with per-probe 4-tuple bounds.

    heads default to each probe's OWN bounds oid (a stable bracket —
    a CHANGING oid across the bounds list stages the mid-wait head
    move, the round-14 harness shape thread 3870734085's race needs);
    the bounds tuples are round_bounds' (head_oid, pushed, request,
    composite marker). review, when a (head, stamp) pair, wraps the
    tuples in the RoundBounds carrier (the round-18/20/22 fixture-
    seam maintenance: the folded review evidence rides the attrs —
    post-round-22 a completing round after a boundary advance needs
    it; the plain-tuple default keeps every other fixture's ''
    fallback).
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
        bounds = probe.pop("bounds")
        if review is not None:
            carried = pr_guard_reaction_probe.RoundBounds(bounds)
            carried.review_head, carried.review_stamp = review
            bounds = carried
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


class ReRequestNoneArmingTests(unittest.TestCase):
    def test_rerequest_race_none_never_arms(self):
        # Given: the thread-3870734078 race — a cold start into NONE
        # (t=0, nothing posted; the 3870293205 gate holds it
        # uncertified), a Codex RE-REQUEST landing between t=0 and
        # t=5 (the t=5 probe's bounds carry it — the request
        # high-water ADVANCES while the reaction is still NONE), and
        # the PRECEDING job's delayed +1 (2026-08-26T14:00,
        # postdating the new request and every other bound, following
        # the EMPTY watermark) at t=10. When: wait polls 12s. Then:
        # exit 1 — the ROUND RE-REQUESTED reset prints (thread
        # 3870293188 survives) but certifies nothing: the gate stays
        # closed, the t=5 NONE never arms, and the delayed +1 only
        # seeds a held baseline and HOLDs to timeout; the pre-fix
        # (round-15) wait OPENED the gate on the advance, armed
        # saw_non_done on the same probe's NONE, and printed WAIT
        # DONE at t=10 before the newly requested review started.
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

    def test_rerequest_recloses_a_gate_the_old_eyes_opened(self):
        # Given: the reset-undoing evidence inside 3870734078 — the
        # round's verified EYES (2026-08-02, past the push and the
        # 2026-08-01 request) is sampled at t=0 (the gate OPENS, the
        # latch arms, the watermark captures it); the re-request
        # (2026-08-20) lands while the OLD job is in its non-atomic
        # EYES-removal/+1 switch, so the t=5 advance probe reads
        # NONE; the old job's delayed +1 (2026-08-26T14:00,
        # postdating the new request AND the old EYES watermark)
        # lands at t=10. When: wait polls 12s. Then: exit 1 — the
        # request-advance reset now RE-CLOSES the gate with the
        # latch (a re-request supersedes every certification the
        # preceding round earned, including a gate its verified EYES
        # opened), so the switch window's NONE cannot re-arm what
        # the reset cleared and the delayed +1 only HOLDs; the
        # pre-fix wait left the gate open, the NONE re-armed it —
        # undoing the reset in the same iteration — and WAIT DONE
        # printed at t=10 with the newly requested round unstarted.
        code, out = run_wait(
            [
                [react("eyes", created="2026-08-02T00:00:00Z", rid=5)],
                [],
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

    def test_postrequest_verified_eyes_still_opens_the_gate(self):
        # Given: the non-stranding survivor — a cold NONE at t=0, the
        # re-request (2026-08-20) between t=0 and t=5, then the newly
        # requested round's OWN EYES (2026-08-25 — a verified
        # POST-REQUEST EYES: the round-13 request binding reads it
        # ACTIVE where the old round's standing EYES would read
        # EYES_STALE) at t=5, its review (2026-08-26T13:00, past the
        # boundary — the round-22 evidence leg, fed through the
        # harness's review seam), and its passing +1 (2026-08-26T14:00,
        # following the EYES watermark and the review stamp) at t=10.
        # When: wait polls. Then: exit 0 at 10s — the EYES-only opener
        # never strands a genuinely re-requested round: the reset
        # re-closes the gate and the SAME probe's verified EYES
        # re-opens it, arms the latch, and captures the watermark the
        # +1 must follow.
        code, out = run_wait(
            [
                [],
                [react("eyes", created="2026-08-25T00:00:00Z", rid=7)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
            ],
            [
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "2026-08-20T00:00:00Z", "2026-08-20T00:00:00Z"),
                (HEAD_B, "2021-01-01T00:00:00Z", "2026-08-20T00:00:00Z", "2026-08-20T00:00:00Z"),
            ],
            600,
            review=(HEAD_B, "2026-08-26T13:00:00Z"),
        )
        self.assertEqual(code, 0)
        self.assertIn("ROUND RE-REQUESTED", out)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)


class PostFloorMarkerTests(unittest.TestCase):
    def test_postfloor_oldhead_marker_race_none_never_arms(self):
        # Given: the thread-3870734085 race — head A (pushed 2022-05)
        # showed the bot's EYES (2022-06, verified, arming at t=0);
        # the ref moves to head B (pushed 2021) at t=5 into A's
        # non-atomic end switch (the transition probe reads NONE, the
        # round-14 gate SETS); A's STILL-RUNNING review then posts a
        # thread comment (marker 2024-03) AFTER the transition floor
        # — the t=10 probe carries it — and A's delayed +1 (2024-04,
        # postdating the marker and B's timestamps) lands at t=12.
        # When: wait polls 12s. Then: exit 1 — the post-floor marker
        # carries NO head identity (marker timestamps are retained
        # across head moves; a still-running OLD-head review posts
        # them), so the gate stays CLOSED (only a verified EYES opens
        # it), the NONE never arms, and the old job's +1 only seeds a
        # held baseline and HOLDs; the pre-fix (round-14) wait opened
        # the gate on marker_high_water > transition_floor and
        # printed WAIT DONE at t=12 with the new head unreviewed.
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
        self.assertEqual(out.count("HEAD MOVED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)


if __name__ == "__main__":
    unittest.main()
