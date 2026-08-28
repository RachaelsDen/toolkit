"""pr_guard reaction round-19 tests — the WAIT half #1 (PR #49 threads
3871844565 P1 / 3871844567 P2).

(1) 3871844565 — "Require request-bound evidence before reopening on
EYES": a same-head re-request arriving AFTER the preceding job was
launched but BEFORE it posts EYES leaves the old job's EYES
POSTDATING the request (the round-13 request binding cannot stale
it), so the advance probe's reset + gate re-close were undone in
the SAME iteration — the old EYES re-opened the gate and re-armed
the freshly reset latch, and the old job's later +1 (also postdating
the request, following the old EYES watermark) printed WAIT DONE
before the newly requested job ran. Round 19 answered with the
wait's OWN wall clock stamped at the advance observation (the
request floor, mirroring the round-13 transition floor).

**ROUND 20 SUPERSESSION (thread 3872194017, the documented exact-
hole repin):** that observation floor also demoted the NEWLY
requested round's OWN EYES posted between two five-second probes
(normal asynchronous startup), permanently staling a legitimate
certification — and the two shapes are THE SAME OBSERVABLE SEQUENCE
at the reaction API (no job identity exists). The reviewer's
P2-vs-residue grading selects the REQUEST/TRIGGER's own createdAt
as the boundary — exactly the reading's standing round-13 binding —
so round 20 DELETED the wait-side stamp machinery: an EYES
certifies iff it postdates the boundary event's createdAt (a
pre-boundary EYES still stales AT THE READING), and the first test
below is REPINNED to pin the superseded semantics (exit 0 — the
owned false-exit trade, backstopped by the post-merge quiet watch +
the server rulesets; see pr_guard_reaction_round20_test for the
between-polls certification pin).

(2) 3871844567 — "Reset the cold-NONE detector on re-request": the
request-advance reset cleared the completion/findings state but
preserved saw_any_eyes/cold_none_since/cold_hinted, so when the
newly requested review never starts and the reaction stays NONE, the
PRIOR round's EYES suppressed the documented 10s manual-trigger hint
until the full timeout. The advance reset now clears the cold-NONE
detector with the latch — the exact symmetry of the round-13
head-move reset (thread 3869453959): round-specific proof-of-start
state, not wait-lifetime fact.

No network: gh_reactions/round_bounds/head_ref_oid patched at the
reaction seams on the FakeClock (WALL_NOW 2023-11-14T22:13:20Z). The
P1 fixtures key their stamps INSIDE the wall window: the re-request
2023-11-14T22:13:22Z, the old job's EYES 22:13:23Z (post-request —
ACTIVE where the round-13 binding stands; round 19 additionally
demoted it as PRE-observation at the t=5 stamp 22:13:25Z — the
demotion round 20 supersedes), the old +1 22:13:24Z.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round19_test -v
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

HEAD = "ba0f1c3ffffffffffffffffffffffffffffff"

# The wall window: probes land at 22:13:20 (t=0), 22:13:25 (t=5),
# 22:13:30 (t=10), 22:13:35 (t=15) — the t=5 advance observation
# stamps the request floor 2023-11-14T22:13:25Z.
PUSH = "2023-11-14T22:00:00Z"
R1 = "2023-11-14T22:10:00Z|RA_1"
R2 = "2023-11-14T22:13:22Z|RA_2"
R1_AT = "2023-11-14T22:10:00Z"
R2_AT = "2023-11-14T22:13:22Z"
OLD_EYES = "2023-11-14T22:13:23Z"
OLD_PLUS = "2023-11-14T22:13:24Z"
NEW_EYES = "2023-11-14T22:13:27Z"
NEW_PLUS = "2023-11-14T22:13:28Z"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def run_wait(reads, bounds, timeout_secs, review=None):
    """wait_reaction on the FakeClock with per-probe plain 4-tuple
    bounds (the round-16 harness shape: a stable head — the race is
    same-head — and the request stream riding index 2). review, when
    a (head, stamp) pair, wraps the tuples in the RoundBounds carrier
    (the round-18/20/22 fixture-seam maintenance: post-round-22 a
    completing round after a boundary advance carries folded review
    evidence; the plain-tuple default keeps the '' fallback)."""
    clock = FakeClock()
    items = iter(reads)
    probes = iter(bounds)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    def fake_bounds(pr, timeout_secs=None):
        bounds = next(probes)
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
        pr_guard_reaction, "head_ref_oid", return_value=HEAD
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue()


class RequestAdvanceFloorTests(unittest.TestCase):
    def test_same_probe_eyes_reopens_and_completes_per_the_request_boundary(self):
        # Given: the thread-3871844565 fixture UNCHANGED — a cold
        # NONE at t=0 with the standing request R1; the same-head
        # RE-REQUEST R2 (22:13:22) lands after the old job launched
        # but before it posted EYES, and the old job's EYES
        # (22:13:23 — POSTDATING R2, so the round-13 request binding
        # reads it ACTIVE) lands before the t=5 probe; the t=5 probe
        # observes the advance AND the old EYES together; the old
        # job's +1 (22:13:24, postdating R2, following the old EYES)
        # lands at t=10. When: wait polls 12s. Then: exit 0 — THE
        # ROUND-20 EXACT-HOLE REPIN (thread 3872194017): this
        # observable sequence is temporally INDISTINGUISHABLE at the
        # reaction API from the P2's legitimate between-polls startup
        # shape (a newly requested round posting its EYES before the
        # probe that first observes the request — no job identity
        # exists), so the round-19 OBSERVATION floor (which held this
        # to exit 1) is SUPERSEDED by the REQUEST-boundary floor: an
        # EYES certifies iff it postdates the boundary event's own
        # createdAt (the reading's round-13 binding), and the old
        # EYES (22:13:23 > 22:13:22) re-opens the freshly reset gate,
        # re-arms the latch, and the +1 completes at t=10. The
        # false-exit class this re-opens is the OWNED trade (the
        # reviewer's P2-vs-residue grading): the post-merge quiet
        # watch + the server rulesets remain the standing backstop.
        # ROUND 22 (thread 3872980765) narrows the owned window: the
        # fixture's review stamp (22:13:23) now rides the folded
        # evidence PAST the boundary — the residual that still exits
        # 0 is the old job whose review ALSO postdates the request
        # (information-theoretically identical to the new job at the
        # reaction API); the old job whose review PREDATES the
        # request is closed (pinned in round22_test).
        code, out = run_wait(
            [
                [],
                [react("eyes", OLD_EYES, 5)],
                [react("+1", OLD_PLUS, 6)],
                [react("+1", OLD_PLUS, 6)],
            ],
            [
                (HEAD, PUSH, R1, R1_AT),
                (HEAD, PUSH, R2, R2_AT),
                (HEAD, PUSH, R2, R2_AT),
                (HEAD, PUSH, R2, R2_AT),
            ],
            12,
            review=(HEAD, "2023-11-14T22:13:23Z"),
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)

    def test_post_observation_eyes_certifies_the_new_round(self):
        # Given: the non-stranding survivor AND the residue witness —
        # a cold NONE at t=0 (R1 baseline), the re-request R2 at t=5
        # (advance observed, floor stamped 22:13:25Z, reaction still
        # NONE), then the newly requested round's OWN EYES
        # (22:13:27 — strictly POSTDATING the observation stamp) at
        # t=10 and its passing +1 (22:13:28, following the EYES
        # watermark) at t=15. When: wait polls. Then: exit 0 at 15s —
        # a post-observation EYES certifies (the floor never strands
        # a genuinely re-requested round). THE RESIDUE, documented
        # (round-15/17 precedent): the reaction API carries no job
        # identity, so an OLD job posting its EYES after the wait's
        # first advance observation is temporally indistinguishable
        # from this new job's EYES and certifies the same way — the
        # pre-fix modules behaved identically here, and the post-
        # merge quiet watch + the server rulesets remain the
        # standing backstop for that window. ROUND 22 (thread
        # 3872980765): the fixture's review stamp (22:13:23) rides
        # the folded evidence past the boundary — the survivor
        # carries the evidence leg every legitimate post-advance
        # completion now carries.
        code, out = run_wait(
            [
                [],
                [],
                [react("eyes", NEW_EYES, 7)],
                [react("+1", NEW_PLUS, 8)],
            ],
            [
                (HEAD, PUSH, R1, R1_AT),
                (HEAD, PUSH, R2, R2_AT),
                (HEAD, PUSH, R2, R2_AT),
                (HEAD, PUSH, R2, R2_AT),
            ],
            600,
            review=(HEAD, "2023-11-14T22:13:23Z"),
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 15s", out)


class ColdNoneReRequestResetTests(unittest.TestCase):
    def test_rerequest_resets_the_cold_none_detector(self):
        # Given: the thread-3871844567 race — the preceding round's
        # verified EYES (2026-08-02, past the 2026-08-01 push and the
        # R1 request) is observed at t=0 (saw_any_eyes latched); the
        # re-request R2 (2026-08-20) lands while the old job is in
        # its non-atomic EYES-removal/+1 switch, so the t=5 advance
        # probe reads NONE — and the newly requested review NEVER
        # STARTS (NONE at t=10 and t=15 too). When: wait polls 15s.
        # Then: exit 1 with the HINT printed exactly once at t=15
        # (cold_none_since=5, 15-5 >= the 10s grace) — the advance
        # reset cleared saw_any_eyes with the latch (the round-13
        # head-move symmetry), no WAIT FINDINGS fires (the reset
        # cleared saw_verified_eyes too), and the timeout explains
        # the hold; the pre-fix wait PRESERVED the prior round's
        # saw_any_eyes across the advance, so the NONE never counted
        # as cold and the hint stayed suppressed to the full timeout.
        code, out = run_wait(
            [
                [react("eyes", "2026-08-02T00:00:00Z", 5)],
                [],
                [],
                [],
            ],
            [
                (HEAD, "2026-08-01T00:00:00Z", "2026-08-01T00:05:00Z|RA_1", "2026-08-01T00:05:00Z"),
                (HEAD, "2026-08-01T00:00:00Z", "2026-08-20T00:00:00Z|RA_2", "2026-08-20T00:00:00Z"),
                (HEAD, "2026-08-01T00:00:00Z", "2026-08-20T00:00:00Z|RA_2", "2026-08-20T00:00:00Z"),
                (HEAD, "2026-08-01T00:00:00Z", "2026-08-20T00:00:00Z|RA_2", "2026-08-20T00:00:00Z"),
            ],
            15,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("HINT:"), 1)
        self.assertNotIn("WAIT FINDINGS", out)
        self.assertIn("WAIT TIMEOUT: 15s elapsed", out)


if __name__ == "__main__":
    unittest.main()
