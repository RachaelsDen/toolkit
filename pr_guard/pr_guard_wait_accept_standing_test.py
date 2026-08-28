"""pr_guard wait --accept-standing tests (user request 2026-08-28 — no
thread ID; the first post-extraction feature of the standalone repo).

THE PAIN: on already-passed PRs (the bot finished before the wait
began) the wait holds a standing THUMBS_UP to full timeout BY DESIGN
— the round-5 rule (thread 3867897766) refuses an unobserved +1, and
the round-25 rule (thread 3873970933) withholds when no folded review
names the head, which is EVERY zero-findings pass (no findings => no
review object). With --timeout-secs 600+ that is a lot of pointless
waiting after an explicit verdict.

THE FLAG (user request 2026-08-28, the vetted design): a valueless
wait-mode argv flag — `pr-guard wait <pr> [--timeout-secs N]
[--accept-standing]` — whose explicit opt-in makes a DONE-CLASSIFIED
THUMBS_UP exit 0 immediately, standing or observed, bypassing the
observation gates (saw_non_done/replaced/watermark, round 5/7/9) AND
the review-evidence legs (head_bound/review_head/review_stamp, rounds
17/18/20/22/25). What it NEVER bypasses: the +1's own staleness
CLASSIFICATION — a +1 predating the head push or the boundary markers
reads THUMBS_UP_STALE at the reading and still holds (a stale verdict
is not "codex said this PR is fine"); only state == REACTION_DONE
accepts. Threads remain the merge authority.

No network: the wait tests patch gh_reactions/round_bounds/
head_ref_oid at their seams on the FakeClock (the round-25 wait-suite
fixture shape); the argv tests mock cli.wait_reaction (the
pr_guard_reaction_test dispatch precedent).

Run: python3 -m unittest pr_guard.pr_guard_wait_accept_standing_test -v
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import cli
from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock

HEAD_B = "c05574000000000000000000000000000000b"
PUSHED = "2026-08-26T12:30:00Z"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": pr_guard_reaction.REACTION_BOT}}


def run_wait(reads, review_head, timeout_secs, accept_standing=True, bounds=None):
    """wait_reaction on the FakeClock; (code, out). The bounds ride a
    RoundBounds carrier (the round-22 seam convention) on one stable
    cold-start head — no floor, no boundary advance: exactly the
    already-passed-PR window the flag serves."""
    clock = FakeClock()
    items = iter(reads)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    def fake_bounds(pr, timeout_secs=None):
        carried = pr_guard_reaction_probe.RoundBounds(bounds or (HEAD_B, PUSHED, "", ""))
        carried.review_head = review_head
        carried.review_stamp = "2026-08-26T12:45:00Z"
        return carried

    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_read
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", side_effect=fake_bounds
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=HEAD_B
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs, accept_standing)
    return code, out.getvalue()


class AcceptStandingTests(unittest.TestCase):
    def test_standing_done_plus_one_with_flag_exits_zero_fast(self):
        # Given: the user's exact pain — the wait starts on an
        # ALREADY-PASSED PR: the bot's +1 (12:32) postdates the head
        # push (12:30) so the reading classifies DONE, it has stood
        # since before the wait began (no EYES/no marker will ever
        # land), and the folded review names the observed head. When:
        # wait polls 10s WITH --accept-standing. Then: exit 0 on the
        # FIRST probe (0s, not the 10s timeout) with the distinctive
        # ACCEPTED STANDING verdict — the opt-in bypassed the round-5
        # observation gate and the round-17/22 evidence legs; the
        # default-path WAIT DONE wording is NOT used. Pre-fix proof:
        # the keyword did not exist (TypeError) and the flagless wait
        # on this shape times out exit 1 (pinned below).
        code, out = run_wait(
            [[react("+1", "2026-08-26T12:32:00Z", 6)]], review_head=HEAD_B, timeout_secs=10
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE (ACCEPTED STANDING): THUMBS_UP at 0s", out)
        self.assertIn("bypassed the observation and review-evidence gates", out)
        self.assertIn("merge authority", out)
        self.assertNotIn("WAIT DONE: THUMBS_UP", out)

    def test_standing_stale_plus_one_with_flag_still_holds(self):
        # Given: a standing +1 that PREDATES the head push (created
        # 11:00 < pushed 12:30) — the reading classifies it
        # THUMBS_UP_STALE (the round-3/10 strict postdate binding: a
        # stale verdict is not "codex said this PR is fine"). When:
        # wait polls 10s WITH --accept-standing. Then: exit 1 at the
        # full timeout — the flag bypasses the observation/evidence
        # gates but NEVER the +1's own staleness classification (only
        # REACTION_DONE accepts); the pre-fix behavior is unchanged
        # (green on both sides by design).
        code, out = run_wait(
            [[react("+1", "2026-08-26T11:00:00Z", 1)]] * 3,
            review_head=HEAD_B,
            timeout_secs=10,
        )
        self.assertEqual(code, 1)
        self.assertIn("THUMBS_UP (stale", out)
        self.assertNotIn("ACCEPTED STANDING", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_standing_done_plus_one_without_flag_holds_to_timeout(self):
        # Given: the same standing DONE-classified +1, flag ABSENT.
        # When: wait polls 10s. Then: exit 1 — the round-5 initial-hold
        # (no confirmed non-DONE reading ever lands) holds the +1 to
        # the timeout with the HOLDING banner; the default path is
        # pinned byte-identical (zero behavior change without the
        # opt-in; green on both sides).
        code, out = run_wait(
            [[react("+1", "2026-08-26T12:32:00Z", 6)]] * 3,
            review_head=HEAD_B,
            timeout_secs=10,
            accept_standing=False,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("3867897766", out)
        self.assertNotIn("ACCEPTED STANDING", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_zero_review_object_with_flag_exits_zero(self):
        # Given: the round-25 corner the design names — the folded
        # review evidence reads '' (NO bot review exists: a
        # zero-findings pass posts no review object), so the default
        # path withholds (no review -> no verdict) and holds to
        # timeout. When: wait polls 10s WITH --accept-standing. Then:
        # exit 0 at 0s — the opt-in is the authority for the
        # review-evidence legs too; the classification still ran (the
        # +1 postdates the push). Pre-fix proof: TypeError on the
        # keyword; flagless this shape is the pinned round-25
        # ''-withhold (exit 1).
        code, out = run_wait(
            [[react("+1", "2026-08-26T12:32:00Z", 6)]], review_head="", timeout_secs=10
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE (ACCEPTED STANDING): THUMBS_UP at 0s", out)
        self.assertNotIn("HOLDING THUMBS_UP", out)

    def test_eyes_then_done_with_flag_exits_zero(self):
        # Given: a round the wait OBSERVES — EYES (12:31, past the
        # 12:30 push: a verified ACTIVE reading) at t=0, then the
        # passing +1 (12:32) at t=5. When: wait polls WITH
        # --accept-standing. Then: exit 0 at 5s — either path accepts
        # a DONE classification; under the flag the distinctive
        # ACCEPTED STANDING verdict fires (the flag check precedes
        # the observed-transition exit, so the flagless wording never
        # prints while it is set).
        code, out = run_wait(
            [
                [react("eyes", "2026-08-26T12:31:00Z", 5)],
                [react("+1", "2026-08-26T12:32:00Z", 6)],
            ],
            review_head=HEAD_B,
            timeout_secs=20,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE (ACCEPTED STANDING): THUMBS_UP at 5s", out)


class AcceptStandingArgvTests(unittest.TestCase):
    def test_wait_argv_strips_accept_standing_in_either_order(self):
        # Given: valid wait argv carrying --accept-standing before or
        # after --timeout-secs (the trailing-flag family: valueless,
        # strippable wherever --timeout-secs is strippable). When:
        # main dispatches. Then: wait_reaction receives the PR, the
        # timeout, and accept_standing=True — the flagless dispatch
        # keeps its historic two-arg shape (the zero-repin rule; the
        # argv-contract pins in pr_guard_reaction_test stand).
        for argv, expected in (
            (["pr_guard.py", "wait", "48", "--accept-standing"], (48, 600, True)),
            (
                ["pr_guard.py", "wait", "48", "--timeout-secs", "10", "--accept-standing"],
                (48, 10, True),
            ),
            (
                ["pr_guard.py", "wait", "48", "--accept-standing", "--timeout-secs", "10"],
                (48, 10, True),
            ),
        ):
            with self.subTest(argv=argv):
                with mock.patch.object(cli, "wait_reaction", return_value=0) as fake:
                    self.assertEqual(cli.main(argv), 0)
                fake.assert_called_once_with(*expected)

    def test_wait_argv_without_flag_dispatches_two_args(self):
        # Given: flagless wait argv. When: main dispatches. Then: the
        # call is the historic two-arg (pr, timeout) shape — the
        # default path is byte-identical (zero repins).
        with mock.patch.object(cli, "wait_reaction", return_value=0) as fake:
            self.assertEqual(cli.main(["pr_guard.py", "wait", "48"]), 0)
        fake.assert_called_once_with(48, 600)


if __name__ == "__main__":
    unittest.main()
