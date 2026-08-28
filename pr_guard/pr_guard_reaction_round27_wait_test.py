"""pr_guard reaction round-27 wait tests (PR #49 thread 3874769253
P2): the deadline-crossing final probe — the pair split's deadline
half (the 3874769241/3874769245 halves live in
pr_guard_reaction_round27_test; the probe-parse half in
pr_guard_reaction_round27_probe_test).

Thread 3874769253 — "Run a final reaction read after a slow probe
crosses the deadline": when a probe starts before the deadline but
its later head/boundary reads finish after it, the pre-fix
post-probe `monotonic() >= deadline` check immediately returned
timeout even though the reaction endpoint was fetched much earlier
in that probe — a valid +1 arriving AFTER that reaction fetch but
BEFORE the configured deadline was never observed, contrary to the
promised final probe at or after the deadline. The timeout now
fires only when a probe BEGAN at-or-after the deadline
(`probe_started >= deadline`): a probe that started before it but
ran long gets exactly ONE more fresh reading (the promised final
probe, riding the 1s probe_timeout_budget floor), then the timeout
— the allowance is bounded by construction (the overlong probe
ended past the deadline, the clamped sleep adds nothing, so the
next probe's start is necessarily at-or-after it).

No network: the wait runs over RoundBounds carriers at the
round_bounds seam (the round-25 seam convention) on the FakeClock;
the slow probe burns fake time inside its bounds read (the probe's
later reads — the exact thread shape).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round27_wait_test -v
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
HEAD_S = "20ab97ffffffffffffffffffffffffffffff5"
PUSH_S = "2023-11-14T22:13:21Z"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def carrier(review=None):
    """A stable-head RoundBounds carrier (the round-22/25 seam
    convention); review carries the folded evidence when given."""
    bounds = pr_guard_reaction_probe.RoundBounds((HEAD_S, PUSH_S, "", ""))
    bounds.review_head = review[0] if review else ""
    bounds.review_stamp = review[1] if review else ""
    return bounds


def run_wait(reads, bounds_list, timeout_secs):
    """wait_reaction on the FakeClock; a ["advance", secs, carrier]
    bounds entry (a LIST — every carrier is a RoundBounds tuple
    subclass, so the tuple check would misfire) burns fake time
    inside that probe's bounds read (the slow probe's later reads).
    Returns (code, out, clock)."""
    clock = FakeClock()
    items = iter(reads)
    bnds = iter(bounds_list)

    def fake_bounds(pr, timeout_secs=None):
        entry = next(bnds)
        if isinstance(entry, list):
            clock.now += entry[1]
            entry = entry[2]
        return entry

    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=lambda pr, timeout_secs=None: next(items)
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid",
        side_effect=lambda pr, timeout_secs=None: HEAD_S,
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", side_effect=fake_bounds
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue(), clock


class DeadlineCrossingTests(unittest.TestCase):
    def test_slow_probe_gets_one_final_fresh_reading(self):
        # Given: the thread-3874769253 race — EYES 22:13:22 arms at
        # t=0; the t=5 probe's REACTION fetch (5s, before the 10s
        # deadline) still sees EYES, but its later head/bounds reads
        # burn 8s and the probe ENDS at t=13, past the deadline; a
        # valid +1 (22:13:26, over the folded review submitted
        # 22:13:24) landed AFTER the reaction fetch but BEFORE the
        # deadline. When: wait polls 10s. Then: exit 0 at 13s — the
        # timeout fires only when a probe BEGAN at-or-after the
        # deadline, so the t=5 probe (started before it) yields ONE
        # final fresh probe at t=13 (the 1s budget floor) which
        # observes the +1 and completes; the pre-fix post-probe
        # `monotonic() >= deadline` check burned that final probe on
        # the overlong t=5 one (the pre-fix proof: exit 1, WAIT
        # TIMEOUT, no WAIT DONE).
        code, out, _ = run_wait(
            [
                [react("eyes", "2023-11-14T22:13:22Z", 5)],
                [react("eyes", "2023-11-14T22:13:22Z", 5)],
                [react("+1", "2023-11-14T22:13:26Z", 6)],
            ],
            [
                carrier(),
                ["advance", 8, carrier()],
                carrier(review=(HEAD_S, "2023-11-14T22:13:24Z")),
            ],
            10,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 13s", out)

    def test_slow_probe_allowance_is_bounded_to_one_probe(self):
        # Given: the bounded-allowance twin — the identical slow t=5
        # probe, but the final t=13 probe still reads EYES (the
        # round has not finished). When: wait polls 10s. Then: exit 1
        # — the t=13 probe BEGAN past the deadline, so the wait ends
        # AFTER exactly that one extra reading (slept [5.0, 0.0]:
        # the interval sleep, then the deadline-clamped zero); the
        # pre-fix check timed out at the t=5 probe's end with no
        # final reading at all (the pre-fix proof: the sleep-count
        # pin, slept [5.0]).
        code, out, clock = run_wait(
            [
                [react("eyes", "2023-11-14T22:13:22Z", 5)],
                [react("eyes", "2023-11-14T22:13:22Z", 5)],
                [react("eyes", "2023-11-14T22:13:22Z", 5)],
            ],
            [carrier(), ["advance", 8, carrier()], carrier()],
            10,
        )
        self.assertEqual(code, 1)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)
        self.assertEqual(clock.slept, [5.0, 0.0])

    def test_probe_beginning_at_the_deadline_still_ends_the_wait(self):
        # Given: the ordinary at-deadline shape — no slow probe, the
        # cadence lands probes at t=0/5/10 for timeout 10 (the
        # round-24 GOTCHA #3 arithmetic), EYES holding throughout.
        # When: wait polls 10s. Then: exit 1 — the t=10 probe BEGAN
        # at the deadline and ends the wait right after its reading
        # (green on BOTH sides — the semantics of an at-deadline
        # start are unchanged; only the overlong-EARLIER-probe class
        # moved).
        code, out, clock = run_wait(
            [
                [react("eyes", "2023-11-14T22:13:22Z", 5)],
                [react("eyes", "2023-11-14T22:13:22Z", 5)],
                [react("eyes", "2023-11-14T22:13:22Z", 5)],
            ],
            [carrier(), carrier(), carrier()],
            10,
        )
        self.assertEqual(code, 1)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)
        self.assertEqual(clock.slept, [5.0, 5.0])


if __name__ == "__main__":
    unittest.main()
