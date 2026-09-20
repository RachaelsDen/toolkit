"""Round-34 reaction tests: mid-flight redundant request boundaries.

A connector can start a review from a push before orchestration posts its
usual `@codex review` trigger. That later trigger is still a real wait-side
boundary advance when observed mid-wait, but it must not recast a reaction
that already postdates the current head's own bound as prior-head activity.
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
HEAD_A = "20ab97ffffffffffffffffffffffffffffffa"
HEAD_B = "20ab97ffffffffffffffffffffffffffffffb"
PUSH = "2026-09-20T12:00:00Z"
EYES = "2026-09-20T12:00:07Z"
TRIGGER = "2026-09-20T12:02:00Z|IC_1"
PASS = "2026-09-20T12:03:10Z"
REVIEW = "2026-09-20T12:03:05Z"


def react(content, created, reaction_id):
    return {
        "content": content,
        "created_at": created,
        "id": reaction_id,
        "user": {"login": BOT},
    }


def run_wait(reads, bounds, timeout_secs, review_head=HEAD_A, review_stamp=REVIEW):
    clock = FakeClock()
    reaction_reads = iter(reads)
    bound_reads = iter(bounds)

    def fake_reactions(pr, timeout_secs=None):
        return next(reaction_reads)

    def fake_bounds(pr, timeout_secs=None):
        bound = pr_guard_reaction_probe.RoundBounds(next(bound_reads))
        bound.review_head = review_head
        bound.review_stamp = review_stamp
        bound.head_bound = bound[1]
        return bound

    output = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_reactions
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=HEAD_A
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", side_effect=fake_bounds
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(output):
        code = pr_guard_reaction.wait_reaction(68, timeout_secs)
    return code, output.getvalue()


class MidFlightTriggerTests(unittest.TestCase):
    def test_push_started_eyes_before_pre_wait_trigger_exits_findings(self):
        # Given: a push starts EYES at T0+7s, then orchestration posts
        # @codex review at T0+2m before this wait begins. When: the wait
        # reads EYES then its persisted removal. Then: exit 3 confirms
        # findings; the trigger did not stale current-head activity.
        bounds = [(HEAD_A, PUSH, TRIGGER, TRIGGER)] * 4
        code, output = run_wait([[react("eyes", EYES, 5)], [], [], []], bounds, 15)
        self.assertEqual(code, 3)
        self.assertIn("EYES (review actively in progress", output)
        self.assertIn("WAIT FINDINGS: EYES → NONE at 15s", output)

    def test_push_started_pass_before_pre_wait_trigger_exits_transition(self):
        # Given: the same push-started EYES and later pre-wait trigger,
        # with a current-head review and pass. When: the wait observes
        # EYES then +1. Then: exit 0 uses the transition path, never
        # --accept-standing.
        bounds = [(HEAD_A, PUSH, TRIGGER, TRIGGER)] * 2
        code, output = run_wait(
            [[react("eyes", EYES, 5)], [react("+1", PASS, 6)]], bounds, 10
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", output)
        self.assertNotIn("ACCEPTED STANDING", output)

    def test_eyes_predating_head_stays_stale_despite_newer_trigger(self):
        # Given: an old-head EYES predates the current head, followed by
        # a newer trigger. When: the reading sees it. Then: it remains
        # stale and cannot arm the findings path.
        stale_eyes = "2026-09-20T11:59:59Z"
        bounds = [(HEAD_A, PUSH, TRIGGER, TRIGGER)] * 4
        code, output = run_wait([[react("eyes", stale_eyes, 5)], [], [], []], bounds, 15)
        self.assertEqual(code, 1)
        self.assertIn("EYES (stale — predates the current round's boundary", output)
        self.assertNotIn("WAIT FINDINGS", output)

    def test_mid_wait_trigger_still_resets_latches_and_recloses_gates(self):
        # Given: a push-started EYES arms at t=0 and a newer trigger is
        # observed at t=5. When: the standing EYES and then +1 persist.
        # Then: the trigger resets the old latch and boundary-floor
        # evidence withholds the pre-trigger review.
        before_trigger = "2026-09-20T12:01:00Z|IC_0"
        code, output = run_wait(
            [
                [react("eyes", EYES, 5)],
                [react("eyes", EYES, 5)],
                [react("+1", PASS, 6)],
                [react("+1", PASS, 6)],
            ],
            [
                (HEAD_A, PUSH, before_trigger, before_trigger),
                (HEAD_A, PUSH, TRIGGER, TRIGGER),
                (HEAD_A, PUSH, TRIGGER, TRIGGER),
                (HEAD_A, PUSH, TRIGGER, TRIGGER),
            ],
            15,
            review_stamp="2026-09-20T12:01:30Z",
        )
        self.assertEqual(code, 1)
        self.assertEqual(output.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("HOLDING THUMBS_UP", output)
        self.assertNotIn("WAIT DONE", output)


if __name__ == "__main__":
    unittest.main()
