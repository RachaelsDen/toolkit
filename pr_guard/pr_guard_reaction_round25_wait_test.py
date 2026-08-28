"""pr_guard reaction round-25 wait tests (PR #49 threads 3873970933
P1 + the 3873970919 wait-level harm).

Thread 3873970933 (P1): the round-17/22 head-bound completion legs
were FLOORED-ONLY — `floor` is empty when the wait starts AFTER a
head change (no transition observed during THIS process, no
boundary advance), so the branch skipped `review_head` validation
entirely. If the OLD head's still-running job posts its EYES only
after the new head was pushed, both its EYES and its later +1
postdate the new push bound: the EYES arms the latch and the +1
exits 0 even though the folded review names the OLD commit — the
current head was reviewed by nobody. Round 25 binds cold-start
terminal signals to the observed head too: BOTH +1 exits (primary
and replacement) and the findings exit require the folded review to
NAME the observed head, floored or not — '' review_head withholds
(no review -> no verdict — the +1 is a POST-review verdict per the
PR #48 live evidence) — while the stamp/floor legs stay
floored-only (a cold start has no floor; none is invented). Legit
cold-start passes carry review(B) == observed B (pinned); the
old-head race review(A) != B holds (pinned).

The 3873970919 wait-level harm rides here too (the walk/probe
halves live in pr_guard_reaction_round25_test): a passing +1 held
at t=0, the NEXT round's EYES skipped by a mid-walk page-2 deletion
at t=5 — the pre-fix mixed walk crowned the +1 and exited 0 while
the review was already active.

No network: the wait tests patch gh_reactions/round_bounds/
head_ref_oid at their seams on the FakeClock (the round-12/17
fixture shape — the folded evidence rides the RoundBounds carrier,
the round-22 seam convention); the harm test runs the REAL walk
over scripted REST pages (the round-24 walk-harness shape).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round25_wait_test -v
"""

import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock

BOT = pr_guard_reaction.REACTION_BOT
HEAD_A = "c05573000000000000000000000000000000a"
HEAD_B = "c05574000000000000000000000000000000b"
HEAD_OID = "c05572ba62bcbcfe54177ea0ff99c8007e4fde"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def slot(at_pos):
    """An ascending created_at for a fixture POSITION (10:00 + 2s each
    — position, created_at, and id all ascend together, the REST wire
    order)."""
    total = 2 * at_pos
    return f"2026-08-26T{10 + total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}:00Z"


def human(at_pos):
    return {"content": "heart", "created_at": slot(at_pos), "id": at_pos + 1, "user": {"login": "human"}}


def page_of(items):
    return subprocess.CompletedProcess([], 0, stdout=json.dumps(items), stderr="")


def run_wait(reads, bounds, timeout_secs, review_head):
    """wait_reaction on the FakeClock with per-probe bounds; (code, out).

    The bounds tuples ride a RoundBounds carrier whose folded review
    evidence names review_head (the round-22 seam convention); a cold
    start throughout — one stable head, no boundary advance, no
    floor: exactly the thread-3873970933 window.
    """
    clock = FakeClock()
    items = iter(reads)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    def fake_bounds(pr, timeout_secs=None):
        carried = pr_guard_reaction_probe.RoundBounds(bounds)
        carried.review_head = review_head
        carried.review_stamp = "2026-08-26T12:45:00Z"
        return carried

    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_read
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", side_effect=fake_bounds
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=bounds[0]
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue()


class ColdStartHeadBoundTests(unittest.TestCase):
    def test_cold_start_plus_one_needs_head_named_review(self):
        # Given: the thread-3873970933 race — the wait starts on head
        # B with NO floor (the move predates the process; no advance
        # fires inside it), and the OLD head A's still-running job
        # posts its EYES (12:31, past B's 12:30 push — a verified
        # ACTIVE reading: gate open, latch armed) and then its +1
        # (12:32, following the watermark) — while the folded review
        # evidence names HEAD A. When: wait polls 10s. Then: exit 1 —
        # the +1 cannot be proven to have reviewed the observed head
        # (review(A) != B), so it HOLDs and the wait times out; the
        # pre-fix branch skipped the head leg entirely at an empty
        # floor and printed WAIT DONE at 5s (the pre-fix proof:
        # 0 != 1).
        code, out = run_wait(
            [
                [react("eyes", "2026-08-26T12:31:00Z", 5)],
                [react("+1", "2026-08-26T12:32:00Z", 6)],
                [react("+1", "2026-08-26T12:32:00Z", 6)],
            ],
            (HEAD_B, "2026-08-26T12:30:00Z", "", ""),
            10,
            review_head=HEAD_A,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("3873970933", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_cold_start_replacement_needs_head_named_review(self):
        # Given: the REPLACEMENT-path twin — the wait holds the prior
        # round's +1 (12:00, DONE against the 11:00 push) at t=0 and
        # a strictly-newer +1 (12:32) replaces it at t=5 (the round-7
        # observed-replacement acceptance), but the folded review
        # names the OLD head A. When: wait polls 10s. Then: exit 1 —
        # the replacement exit carries the same cold-start head leg
        # (the replacing +1's round must have reviewed the observed
        # head); the pre-fix wait exited 0 at 5s on the bare identity
        # replacement (the pre-fix proof: 0 != 1).
        code, out = run_wait(
            [
                [react("+1", "2026-08-26T12:00:00Z", 1)],
                [react("+1", "2026-08-26T12:32:00Z", 2)],
                [react("+1", "2026-08-26T12:32:00Z", 2)],
            ],
            (HEAD_B, "2026-08-26T11:00:00Z", "", ""),
            10,
            review_head=HEAD_A,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_cold_start_findings_exit_needs_head_named_review(self):
        # Given: the FINDINGS-exit twin — a verified EYES (12:31 past
        # the 12:30 push) at t=0 and THREE completion-absent probes
        # (the round-23 grace) while the folded review names the OLD
        # head A: the NONE pair carries A's round-ending signal under
        # a head A never reviewed. When: wait polls 15s. Then: exit 1
        # — the findings exit withholds (HOLDING FINDINGS at the
        # confirming probe; the new round produces its own signal)
        # and the wait times out; the pre-fix findings gate consulted
        # its evidence legs only at a nonempty floor and exited 3 at
        # 15s (the pre-fix proof: 3 != 1).
        code, out = run_wait(
            [
                [react("eyes", "2026-08-26T12:31:00Z", 5)],
                [],
                [],
                [],
            ],
            (HEAD_B, "2026-08-26T12:30:00Z", "", ""),
            15,
            review_head=HEAD_A,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING FINDINGS", out)
        self.assertNotIn("WAIT FINDINGS", out)
        self.assertIn("WAIT TIMEOUT: 15s elapsed", out)

    def test_empty_review_head_withholds_cold_start_completion(self):
        # Given: the same cold-start EYES -> +1 shape while the
        # folded review evidence reads '' (no bot review exists for
        # the head — a request-less round that never submitted). When:
        # wait polls 10s. Then: exit 1 — '' is never evidence (no
        # review -> no verdict: the +1 is a POST-review verdict), so
        # the completion withholds conservatively; the pre-fix empty
        # floor skipped the leg and exited 0 (the pre-fix proof:
        # 0 != 1).
        code, out = run_wait(
            [
                [react("eyes", "2026-08-26T12:31:00Z", 5)],
                [react("+1", "2026-08-26T12:32:00Z", 6)],
                [react("+1", "2026-08-26T12:32:00Z", 6)],
            ],
            (HEAD_B, "2026-08-26T12:30:00Z", "", ""),
            10,
            review_head="",
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)

    def test_cold_start_own_head_pass_still_completes(self):
        # Given: the survivor — the same cold-start EYES (12:31) ->
        # +1 (12:32) shape, but the folded review names the OBSERVED
        # head B (the round that actually ran: the legit cold-start
        # pass carries review(B) == observed B). When: wait polls.
        # Then: exit 0 at 5s — the cold-start leg accepts a
        # head-naming verdict; green on BOTH sides (the pre-fix
        # branch accepted it too, floor or not).
        code, out = run_wait(
            [
                [react("eyes", "2026-08-26T12:31:00Z", 5)],
                [react("+1", "2026-08-26T12:32:00Z", 6)],
            ],
            (HEAD_B, "2026-08-26T12:30:00Z", "", ""),
            600,
            review_head=HEAD_B,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)

    def test_round5_replacement_shape_still_exits_zero(self):
        # Given: the round-5 initial-+1 REPLACEMENT shape with the
        # replacing +1's round carrying review evidence for the
        # CURRENT head (the caution's verify test — the fast
        # EYES->+1 round completes entirely between probes and only
        # the changed identity proves it). When: wait polls. Then:
        # exit 0 at 5s — the replacement exit keeps accepting a
        # current-head verdict; green on BOTH sides.
        code, out = run_wait(
            [
                [react("+1", "2026-08-26T12:00:00Z", 1)],
                [react("+1", "2026-08-26T12:32:00Z", 2)],
            ],
            (HEAD_B, "2026-08-26T11:00:00Z", "", ""),
            600,
            review_head=HEAD_B,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)
        self.assertIn("3868158293", out)


class PageTwoDeletionEyesSkipTests(unittest.TestCase):
    def test_page_two_deletion_eyes_skip_cannot_exit_zero(self):
        # Given: the thread-3873970919 HARM at the wait — t=0 reads
        # the PRIOR round's passing +1 (position 99, rid 100 — DONE
        # against the 09:59 push and HELD; the round-5 initial-hold
        # shape) over a two-page walk (page 1's re-read already rides
        # round 24). Between t=0 and t=5 the bot posts a NEW +1
        # (position 199, rid 200 — a second completed round) and the
        # NEXT round's EYES (position 200, rid 201); the t=5 walk
        # reads page 1 (100 humans) and page 2 (humans + the new +1),
        # a page-2-range deletion then shifts the offset, and pages
        # 3/4 return the shifted tail only — the EYES (page 3's
        # former FIRST item) is SKIPPED with no page-pair signature
        # while page 1 stays identical, so the pre-fix walk crowned
        # the new +1 and REPLACED the held baseline (position 199
        # strictly newer than the held 99 — the folded evidence names
        # the head, a genuine pass for it). When: wait polls 10s.
        # Then: exit 1 — the PAGE-2 re-read catches the drift (the
        # EYES slid into page 2's re-read window) and the t=5 probe
        # reads UNREADABLE (18 subprocess calls across the three
        # walks: 4 + 6 + 8 — each settled walk now also re-reads its
        # TERMINAL short page, the round-33 seam maintenance, thread
        # 3876172349; the settled walk carries three full pages), the t=10 SETTLED walk reads the EYES
        # (page 2 now ends with it), and the wait times out with the
        # review ACTIVE; the pre-fix wait exited 0 on the mixed
        # walk's +1 at t=5 (WAIT DONE while the next round's EYES was
        # live — the pre-fix proof: 0 != 1 and 8 != 18 calls).
        # Positions, created_at (the `slot` builder, 2s apart), and
        # ids all ascend together — the REST wire order. t=0: humans
        # at 0..98, the prior round's +1 (position 99), 10 humans.
        # t=5 (311 items): humans at 0..198, a NEW +1 (position 199),
        # the NEXT round's EYES (position 200 — page 3's former first
        # item), 110 more humans; a deletion inside page 2's range
        # (human id 151, position 150) lands between the page-2 and
        # page-3 fetches. t=10: the same list settled.
        clock = FakeClock()
        held_plus = react("+1", slot(99), 100)
        plus = react("+1", slot(199), 200)
        eyes = react("eyes", slot(200), 201)
        t0 = [human(p) for p in range(99)] + [held_plus] + [human(p) for p in range(100, 110)]
        t5 = (
            [human(p) for p in range(199)]
            + [plus, eyes]
            + [human(p) for p in range(201, 311)]
        )
        t5_settled = t5[:150] + t5[151:]
        script = [
            # t=0: page 1 (99 humans + the held +1), short page 2, the
            # page-1 re-read (round 24), and the terminal short-page
            # re-read (round 33, thread 3876172349).
            page_of(t0[:100]),
            page_of(t0[100:]),
            page_of(t0[:100]),
            page_of(t0[100:]),
            # t=5: pages 1/2 read PRE-deletion, pages 3/4 POST-deletion
            # (the EYES at old position 200 skipped), the page-1 re-read
            # identical, the PAGE-2 re-read drifted (ends with the EYES).
            page_of(t5[:100]),
            page_of(t5[100:200]),
            page_of(t5_settled[200:300]),
            page_of(t5_settled[300:]),
            page_of(t5_settled[:100]),
            page_of(t5_settled[100:200]),
            # t=10: the settled list — page 2 ends with the EYES; the
            # three full-page re-reads plus the round-33 terminal
            # short-page re-read (thread 3876172349).
            page_of(t5_settled[:100]),
            page_of(t5_settled[100:200]),
            page_of(t5_settled[200:300]),
            page_of(t5_settled[300:]),
            page_of(t5_settled[:100]),
            page_of(t5_settled[100:200]),
            page_of(t5_settled[200:300]),
            page_of(t5_settled[300:]),
        ]
        carried = pr_guard_reaction_probe.RoundBounds((HEAD_OID, "2026-08-26T09:59:00Z", "", ""))
        carried.review_head = HEAD_OID
        carried.review_stamp = "2026-08-26T10:05:00Z"
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=lambda *a, **k: script.pop(0),
        ) as api_mock, mock.patch.object(
            pr_guard_reaction, "round_bounds", return_value=carried
        ), mock.patch.object(
            pr_guard_reaction,
            "head_ref_oid",
            return_value="c05572ba62bcbcfe54177ea0ff99c8007e4fde",
        ), mock.patch.object(
            pr_guard_reaction, "time", clock
        ), mock.patch.object(
            pr_guard_common, "time", clock
        ), redirect_stdout(out):
            code = pr_guard_reaction.wait_reaction(48, 10)
        self.assertEqual(code, 1)
        self.assertEqual(api_mock.call_count, 18)
        self.assertEqual(out.getvalue().count("BOT REACTION: UNREADABLE"), 1)
        self.assertNotIn("WAIT DONE", out.getvalue())
        self.assertIn("BOT REACTION: EYES", out.getvalue())


if __name__ == "__main__":
    unittest.main()
