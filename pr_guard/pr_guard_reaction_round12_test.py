"""pr_guard reaction round-12 tests (user-taught refinements #2 —
vault note 'Unified Realms/Notes/Codex Review Bot Reaction
Signal.md', SECTION 'User-taught refinements #2', 2026-08-27).

The bot REMOVES its EYES when a review round finishes — it posts +1
(THUMBS_UP) when the round passed and leaves NO reaction (NONE)
when it found feedback. Two wait behaviors encode that:

(1) EYES -> NONE = the FINDINGS exit (code 3): a transition from a
LATCH-ARMING (current-head-verified, round 11) EYES to a NONE that
PERSISTS through the next probe returns 3 with the WAIT FINDINGS
line. The confirming probe exists because the remove-EYES-then-
post-+1 switch is NON-ATOMIC (the round-9 thread-3868625469
precedent: the removal lands before the replacement +1 is visible)
— a lone NONE that flips back to EYES (or completes to +1) is a
transient and the wait keeps polling; only the TERMINAL transition
(a NONE that stays) exits. EYES_STALE/EYES_UNVERIFIED never arm it
(an old round's eyes disappearing is not a findings signal), and a
head move resets the arming with the latch (a certification).

(2) The COLD-NONE hint: no EYES variant EVER observed and
COLD_NONE_GRACE_SECS (10) of continuous NONE prints the trigger
HINT exactly once — a HINT ONLY (the tool never posts comments),
polling continues to timeout as before.

No network: the wait tests patch gh_reactions/round_bounds/
head_ref_oid at their seams on the FakeClock; the usage arm of the
exit-code table mocks nothing (argv parsing fails before dispatch).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round12_test -v
"""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from . import cli
from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_banner
from . import pr_guard_reaction_latch
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock

HEAD_OID = "c98a68f1a2b3c4d5e6f708192a3b4c5d6e7f8a9b0"
# The head pushed 12:30; an EYES at 12:31 is verified-current (arms
# the findings precursor) while an EYES at 12:00 predates it (reads
# EYES_STALE — round 11's head binding).
BOUNDS = (HEAD_OID, "2026-08-26T12:30:00Z", "", "")


def react(content, created="2026-08-26T12:31:00Z", rid=None):
    return {
        "content": content,
        "created_at": created,
        "id": rid,
        "user": {"login": pr_guard_reaction.REACTION_BOT},
    }


def run_wait(reads, timeout_secs):
    """wait_reaction on the FakeClock with stable head bounds; (code, out).

    (PR #49 round 25 fixture-seam maintenance, thread 3873970933:
    the bounds ride a RoundBounds carrier whose folded review
    evidence names the STABLE head — the stamp between the 12:31
    EYES and the 14:00 completing +1 — the terminal signals are
    POST-review verdicts and cold-start completions require the
    evidence now; the marker-window tuple itself is unchanged.)
    """
    clock = FakeClock()
    items = iter(reads)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    carried = pr_guard_reaction_probe.RoundBounds(BOUNDS)
    carried.review_head = HEAD_OID
    carried.review_stamp = "2026-08-26T13:30:00Z"
    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_read
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", return_value=carried
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue()


class EyesToNoneFindingsTests(unittest.TestCase):
    def test_verified_eyes_to_none_exits_findings(self):
        # Given: a current-head-verified EYES (12:31, postdating the
        # 12:30 push) observed at t=0; the bot removes it at t=5
        # (the absent streak starts) and the NONE PERSISTS at t=10
        # AND t=15 — the terminal transition of user-taught
        # refinements #2, confirmed at the round-23 grace (thread
        # 3873317562 repin: exit-3 timing moved from the second
        # consecutive absent probe to the third; the race guarded is
        # unchanged). When: wait polls. Then: exit 3 with the WAIT
        # FINDINGS line at the CONFIRMING probe's elapsed — never
        # 0/1 (the round ended WITH feedback; the fix+receipt+
        # re-wait loop starts).
        code, out = run_wait(
            [[react("eyes", rid=5)], [], [], []],
            600,
        )
        self.assertEqual(code, 3)
        self.assertIn(
            "WAIT FINDINGS: EYES → NONE at 15s — the review "
            "completed WITH feedback; survey the threads now "
            "(fix + receipt + re-wait).",
            out,
        )
        self.assertNotIn("WAIT FINDINGS: EYES → NONE at 10s", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertNotIn("WAIT TIMEOUT", out)

    def test_stale_eyes_to_none_keeps_polling(self):
        # Given: an EYES that PREDATES the head's push (12:00 vs
        # 12:30 — round 11's EYES_STALE: a prior round's leftover
        # activity) followed by persistent NONE. When: wait polls
        # 12s. Then: exit 1 timeout — an old round's eyes
        # disappearing is NOT a findings signal (only VERIFIED-
        # current EYES arms it), and the stale EYES still proves
        # the bot started, so no cold-NONE hint either.
        code, out = run_wait(
            [[react("eyes", created="2026-08-26T12:00:00Z", rid=5)], [], [], []],
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn("EYES (stale — predates the current round's boundary", out)
        self.assertNotIn("WAIT FINDINGS", out)
        self.assertNotIn("HINT:", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_flip_flop_continues_polling(self):
        # Given: the non-atomic switch window — a verified EYES at
        # t=0, a lone NONE at t=5, then the reaction flips BACK to
        # EYES (t=10) before the round genuinely completes with a
        # fresh +1 (t=15) that postdates the observed EYES. When:
        # wait polls. Then: exit 0 at 15s — the transient NONE did
        # not exit 3 (only the TERMINAL transition exits), the
        # round-9 watermark accepts the fresh +1, and the wait kept
        # polling productively through the flip-flop.
        code, out = run_wait(
            [
                [react("eyes", created="2026-08-26T12:31:00Z", rid=5)],
                [],
                [react("eyes", created="2026-08-26T12:32:00Z", rid=6)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=7)],
            ],
            600,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 15s", out)
        self.assertNotIn("WAIT FINDINGS", out)

    def test_head_move_resets_the_findings_arming(self):
        # Given: a verified EYES under head A, then the head MOVES
        # (t=5) and head B carries persistent NONE. When: wait
        # polls. Then: exit 1 timeout — the findings certifications
        # reset with the latch on a head move (round 8's rule): an
        # EYES certified under the OLD head whose disappearance
        # follows the move is the old round ending, not the new
        # head's findings signal.
        head_b = "ffffffffffffffffffffffffffffffffffffffff"
        clock = FakeClock()
        reads = iter([[react("eyes", rid=5)], [], [], []])
        bounds = iter(
            [
                BOUNDS,
                (head_b, "2026-08-26T13:00:00Z", "", ""),
                (head_b, "2026-08-26T13:00:00Z", "", ""),
                (head_b, "2026-08-26T13:00:00Z", "", ""),
            ]
        )
        heads = iter([HEAD_OID, head_b, head_b, head_b])
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_reaction,
            "gh_reactions",
            side_effect=lambda pr, timeout_secs=None: next(reads),
        ), mock.patch.object(
            pr_guard_reaction,
            "round_bounds",
            side_effect=lambda pr, timeout_secs=None: next(bounds),
        ), mock.patch.object(
            pr_guard_reaction,
            "head_ref_oid",
            side_effect=lambda pr, timeout_secs=None: next(heads),
        ), mock.patch.object(
            pr_guard_reaction, "time", clock
        ), mock.patch.object(
            pr_guard_common, "time", clock
        ), redirect_stdout(out):
            code = pr_guard_reaction.wait_reaction(48, 12)
        self.assertEqual(code, 1)
        self.assertIn("HEAD MOVED", out.getvalue())
        self.assertNotIn("WAIT FINDINGS", out.getvalue())


class ColdNoneHintTests(unittest.TestCase):
    def test_cold_none_hint_fires_once_at_grace(self):
        # Given: no bot reaction EVER (no EYES variant observed) and
        # NONE continuously from t=0. When: wait polls 15s. Then:
        # the trigger HINT prints EXACTLY ONCE at the 10s probe
        # (>= COLD_NONE_GRACE_SECS), never at 5s, and the wait
        # keeps polling to its timeout exit 1 — a hint, not an exit
        # (the orchestrator decides whether to post '@codex
        # review').
        code, out = run_wait([[], [], [], []], 15)
        self.assertEqual(code, 1)
        self.assertEqual(
            out.count(
                "HINT: no EYES ever observed and 10s of NONE — the "
                "bot may have failed to start; consider posting a "
                "'@codex review' comment to trigger it manually."
            ),
            1,
        )
        self.assertIn("WAIT TIMEOUT: 15s elapsed", out)

    def test_cold_none_below_grace_never_hints(self):
        # Given: the same cold NONE but the wait ends at 8s —
        # under the 10s grace. When: wait polls. Then: exit 1 with
        # NO hint (the grace window pins the boundary from below;
        # 5s of NONE proves nothing about a failed start).
        code, out = run_wait([[], [], []], 8)
        self.assertEqual(code, 1)
        self.assertNotIn("HINT:", out)


class ExitCodeTableTests(unittest.TestCase):
    def test_exit_code_table(self):
        # Given: the wait mode's four dispositions. When: each runs
        # to its terminal state. Then: the codes are pinned and
        # pairwise distinct — 0 the watched THUMBS_UP pass, 1 the
        # timeout, 2 the CLI usage error (argv parsing, before any
        # dispatch), 3 the confirmed EYES → NONE findings (the NEW
        # code collides with nothing; user-taught refinements #2 —
        # the round-23 repin: the findings leg needs the THIRD
        # consecutive absent probe, thread 3873317562).
        passed, _ = run_wait(
            [[react("eyes", rid=5)], [react("+1", created="2026-08-26T14:00:00Z", rid=6)]],
            600,
        )
        timed_out, _ = run_wait([[], [], []], 8)
        findings, _ = run_wait([[react("eyes", rid=5)], [], [], []], 600)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            usage = cli.main(["pr_guard.py", "wait", "48", "--timeout-secs", "x"])
        self.assertEqual(
            {passed: "THUMBS_UP watched", timed_out: "timeout", usage: "usage error", findings: "findings"},
            {0: "THUMBS_UP watched", 1: "timeout", 2: "usage error", 3: "findings"},
        )

    def test_none_render_wording_one_line(self):
        # Given: the refinements-#2 NONE semantics. When:
        # render_state evaluates NONE (the banner and the wait's
        # state lines share this one home). Then: ONE line carrying
        # all three taught readings — done WITH findings after a
        # seen EYES, not-started with the '@codex review' trigger,
        # or stale.
        rendered = pr_guard_reaction_latch.render_state("NONE")
        self.assertNotIn("\n", rendered)
        for phrase in ("done WITH findings", "'@codex review' can trigger it", "stale"):
            self.assertIn(phrase, rendered)

    def test_banner_carries_the_none_wording(self):
        # Given: the survey banner's fail-open informational read
        # returning NONE. When: reaction_banner prints. Then: the
        # refinements-#2 wording rides the banner beside the
        # threads-are-the-authority framing (the banner is the
        # reaction family's human-facing home).
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_reaction,
            "bot_review_reaction",
            return_value="NONE",
        ), redirect_stdout(out):
            state = pr_guard_reaction_banner.reaction_banner(48)
        self.assertEqual(state, "NONE")
        self.assertIn("done WITH findings", out.getvalue())
        self.assertIn("thread state is the authority", out.getvalue())


if __name__ == "__main__":
    unittest.main()
