"""pr_guard reaction round-23 tests (PR #49 threads 3873317562 P2 /
3873317572 P2 — the two round-23 findings, fixed together).

(1) THE FINDINGS GRACE PROBES (3873317562, pr_guard_reaction_wait):
the round-12 exit-3 confirming design treated the
remove-EYES-then-post-+1 switch as non-atomic yet bounded its
patience at ONE five-second poll interval — a PASSING round whose
replacement +1 took longer to publish (GitHub/connector latency)
was reported as findings at the second consecutive
completion-absent probe. The confirmation now requires
FINDINGS_GRACE_PROBES (3) consecutive absent probes, BOTH shapes
(literal NONE and the THUMBS_UP proven older than the observed
arming EYES), resetting on any non-absent reading exactly like
today's findings_pending (UNREADABLE included). The exit's TIMING
moves (the third probe, not the second); the round-12 arming
discipline and the round-21/22 exit-evidence legs are unchanged.

(2) THE UNQUALIFIED BANNER +1 (3873317572,
pr_guard_reaction_banner): when a same-head, request-less
follow-up round is queued but has not yet posted EYES, the
state-only bot_review_reaction classifies the preceding round's
still-present +1 as THUMBS_UP and the banner's plain render
claimed the PENDING round passed ("review complete, nothing
further"). The banner now renders a state-only DONE with the
explicit unverified qualification; every other state keeps
render_state's one-line reading, and the WAIT's own renders and
exit logic are untouched (they carry the rounds-5/13 freshness
machinery already).

No network: the wait tests patch gh_reactions/round_bounds/
head_ref_oid at their seams on the FakeClock (the round-12/14
fixture shape); the banner tests patch pr_guard_reaction.
bot_review_reaction (the round-12 banner seam).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round23_test -v
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_banner
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock

HEAD_OID = "c98a68f1a2b3c4d5e6f708192a3b4c5d6e7f8a9b0"
# The head pushed 12:30; an EYES at 12:31 is verified-current (arms
# the findings precursor) — the round-12 fixture convention.
BOUNDS = (HEAD_OID, "2026-08-26T12:30:00Z", "", "")
# The proven-older-+1 shape's bounds (round-14's STABLE_BOUNDS
# convention): the push at 11:00 leaves the PRIOR round's +1 (12:00)
# DONE-classified while the current round's EYES (12:31) still
# postdates the push — the exposed +1 is DONE yet not following the
# observed-EYES watermark, the completion-absent shape.
PRIOR_PASS_BOUNDS = (HEAD_OID, "2026-08-26T11:00:00Z", "", "")


def react(content, created="2026-08-26T12:31:00Z", rid=None):
    return {
        "content": content,
        "created_at": created,
        "id": rid,
        "user": {"login": pr_guard_reaction.REACTION_BOT},
    }


def run_wait(reads, timeout_secs, bounds=BOUNDS):
    """wait_reaction on the FakeClock with stable head bounds; (code, out).

    (PR #49 round 25 fixture-seam maintenance, thread 3873970933:
    the bounds ride a RoundBounds carrier whose folded review
    evidence names the STABLE head — the stamp between the 12:31 EYES
    and the completing 14:00 +1 — the terminal signals are POST-review
    verdicts and cold-start completions require the evidence now; the
    marker-window tuples themselves are unchanged.)
    """
    clock = FakeClock()
    items = iter(reads)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    carried = pr_guard_reaction_probe.RoundBounds(bounds)
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


class FindingsGraceProbesTests(unittest.TestCase):
    def test_slow_switch_plus_one_after_two_nones_exits_zero(self):
        # Given: the thread-3873317562 race — a verified EYES (12:31)
        # observed at t=0; the PASSING round removes it at t=5 and
        # t=10 (two consecutive completion-absent NONE probes — the
        # pre-fix wait exited 3 right here) while GitHub/connector
        # latency delays the replacement +1's publication; the fresh
        # +1 (14:00, a new object) finally lands at t=15. When: wait
        # polls. Then: exit 0 at 15s — the grace probes keep polling
        # through the slow switch (a slow PASS is never findings),
        # and the round-9 watermark accepts the fresh +1 (it follows
        # the observed EYES identity).
        code, out = run_wait(
            [
                [react("eyes", rid=5)],
                [],
                [],
                [react("+1", created="2026-08-26T14:00:00Z", rid=6)],
            ],
            600,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 15s", out)
        self.assertNotIn("WAIT FINDINGS", out)

    def test_slow_switch_plus_one_after_two_older_plus_ones_exits_zero(self):
        # Given: the proven-older +1 absence shape, slow — the prior
        # round's +1 (12:00) stands beside the current round's
        # verified EYES (12:31, observed t=0); the passing round
        # removes its EYES, EXPOSING the older +1 at t=5 and t=10
        # (DONE-classified yet NOT following the observed-EYES
        # watermark — two completion-absent probes, the pre-fix exit
        # 3 point) before the genuine replacement +1 (14:00) lands at
        # t=15. When: wait polls. Then: exit 0 at 15s — the grace
        # applies to BOTH absence shapes identically (round 14's
        # equivalence, now with the wider window), and the exposed
        # +1's replacement completes the wait through the standing
        # watermark acceptance.
        code, out = run_wait(
            [
                [react("+1", created="2026-08-26T12:00:00Z", rid=1), react("eyes", rid=5)],
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("+1", created="2026-08-26T12:00:00Z", rid=1)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=7)],
            ],
            600,
            bounds=PRIOR_PASS_BOUNDS,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 15s", out)
        self.assertNotIn("WAIT FINDINGS", out)

    def test_third_consecutive_none_exits_findings(self):
        # Given: a genuinely-feedback round — a verified EYES at t=0,
        # then NONE at t=5, t=10, AND t=15 (the switch's patience is
        # bounded: FINDINGS_GRACE_PROBES consecutive absent probes).
        # When: wait polls. Then: exit 3 at 15s with the WAIT FINDINGS
        # line — the exit's TIMING moved from the second absent probe
        # (round 12) to the third (round 23), and the round-12/22
        # exit-evidence legs are unchanged beneath it.
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

    def test_unreadable_probe_resets_the_grace_streak(self):
        # Given: a verified EYES at t=0; absent NONEs at t=5 and t=10
        # (streak 2 of 3); an UNREADABLE read at t=15 (a read failure
        # is not a state change — the findings_pending reset rule,
        # carried over); then NONE at t=20, t=25, and t=30. When:
        # wait polls. Then: exit 3 at 30s — the streak RESET on the
        # UNREADABLE probe (three FRESH absent probes follow it), so
        # the confirmation count is not satisfied by absents stradd
        # ling the failed read.
        code, out = run_wait(
            [
                [react("eyes", rid=5)],
                [],
                [],
                RuntimeError("gh api death"),
                [],
                [],
                [],
            ],
            600,
        )
        self.assertEqual(code, 3)
        self.assertIn("WAIT FINDINGS: EYES → NONE at 30s", out)
        self.assertNotIn("WAIT FINDINGS: EYES → NONE at 10s", out)
        self.assertNotIn("WAIT FINDINGS: EYES → NONE at 25s", out)


class BannerUnqualifiedThumbsUpTests(unittest.TestCase):
    def test_banner_renders_thumbs_up_as_unqualified_snapshot(self):
        # Given: the thread-3873317572 race — a same-head,
        # request-less follow-up round is queued but has not yet
        # posted EYES, so the state-only read classifies the
        # PRECEDING round's still-present +1 as THUMBS_UP. When:
        # the banner renders. Then: the +1 prints with the explicit
        # unverified qualification (the wait's freshness checks are
        # NOT applied on this path; threads remain the authority) —
        # never the bare "review complete, nothing further" that
        # claimed the pending round passed.
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_reaction,
            "bot_review_reaction",
            return_value="THUMBS_UP",
        ), redirect_stdout(out):
            state = pr_guard_reaction_banner.reaction_banner(49, ["3873317562"])
        self.assertEqual(state, "THUMBS_UP")
        text = out.getvalue()
        self.assertIn(
            "BOT REACTION: THUMBS_UP (unqualified snapshot — the "
            "wait's freshness checks are not applied here; threads "
            "remain the authority)",
            text,
        )
        self.assertNotIn("review complete, nothing further", text)
        self.assertIn("threads 3873317562 are the authority", text)

    def test_banner_other_states_keep_their_renders(self):
        # Given: an ACTIVE read through the state-only wrapper (the
        # qualification's scope is the DONE state alone). When: the
        # banner renders. Then: render_state's ordinary one-line
        # reading prints — no unqualified-snapshot wording (the
        # round-12 banner wording for every non-DONE state is
        # untouched by the round-23 change).
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_reaction,
            "bot_review_reaction",
            return_value="EYES",
        ), redirect_stdout(out):
            state = pr_guard_reaction_banner.reaction_banner(49)
        self.assertEqual(state, "EYES")
        text = out.getvalue()
        self.assertIn("BOT REACTION: EYES", text)
        self.assertNotIn("unqualified snapshot", text)
        self.assertIn("thread state is the authority", text)

    def test_wait_renders_are_unchanged_by_the_banner_qualification(self):
        # Given: a completing round through the WAIT path (a verified
        # EYES at t=0, its passing +1 at t=5) — the round-5/13
        # freshness machinery runs HERE. When: the wait polls. Then:
        # exit 0 with the WAIT's own verdict lines — the DONE state
        # line keeps render_state's ordinary meaning ("review
        # complete, nothing further") and the WAIT DONE line its own
        # wording; the unqualified-snapshot qualification exists ONLY
        # on the banner path (the scope rule of 3873317572).
        code, out = run_wait(
            [
                [react("eyes", rid=5)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=6)],
            ],
            600,
        )
        self.assertEqual(code, 0)
        self.assertIn("review complete, nothing further", out)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)
        self.assertNotIn("unqualified snapshot", out)


if __name__ == "__main__":
    unittest.main()
