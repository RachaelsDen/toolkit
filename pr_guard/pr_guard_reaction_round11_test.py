"""pr_guard reaction round-11 tests (PR #49 threads 3868979509 P1 +
3868979515 P2 + 3868979526 P2).

Thread 3868979509 (P1): the observed EYES binds the CURRENT head —
a review of head A showing EYES while head B was pushed BEFORE the
wait begins leaves both head reads stably B, yet the EYES predates
B's push; the pre-fix probe returned that EYES unchecked, armed the
transition latch, and A's subsequent completion +1 (genuinely
postdating B's push, passing every round-bound and watermark
check) exited 0 with B reviewed by nobody. Post-fix the EYES
classifies against the head push (eyes_round_state): pre-head
reads EYES_STALE and an unreadable push reads EYES_UNVERIFIED —
NEITHER arms the latch or refreshes the observed-activity
watermark, so the wait keeps polling for a post-head round signal.

Thread 3868979515 (P2): ONE shared probe budget — the head-only
read, the reactions walk, and the round probe all consume the
START-of-probe deadline; the walk receives the RAW remaining (its
own <=0 guard stops the probe UNREADABLE) instead of a fresh grant
of the original timeout_secs after the head read already spent
part of it.

Thread 3868979526 (P2): resolve's FINAL AUDIT survey runs
bannerless (reaction=False) — its DANGER check gates the RESOLVE
DONE verdict, so the banner's bounded informational read may never
sit between that snapshot and the go/no-go (the decision-surface
rule of threads 3867757449/3867897759/3868158297); the OPENING
survey keeps the human-facing banner.

No network: the wait tests patch gh_reactions/round_bounds/
head_ref_oid at their seams on the FakeClock; the budget tests
drive the FakeClock through the stage fakes; the resolve tests
mock survey/refetch/resolve at the CLI seams.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round11_test -v
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import cli
from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_latch
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock, thread

BOT = pr_guard_reaction.REACTION_BOT

HEAD_B = "144da04c430d6df8ff3464ad308596b7e81e9373"
# The thread-3868979509 windows: head B pushed 12:30 BEFORE the
# wait begins, while head A's review (EYES 12:00) is still showing.
B_BOUNDS = (HEAD_B, "2026-08-26T12:30:00Z", "", "")


def react(content, created="2026-08-26T12:00:00Z", rid=None):
    return {
        "content": content,
        "created_at": created,
        "id": rid,
        "user": {"login": BOT},
    }


def run_wait(reads, bounds, timeout_secs):
    """wait_reaction on the FakeClock with per-probe bounds; (code, out)."""
    clock = FakeClock()
    items = iter(reads)
    probes = iter(bounds)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    probe = {}

    def fake_head(pr, timeout_secs=None):
        probe["triple"] = next(probes)
        return probe["triple"][0]

    def fake_bounds(pr, timeout_secs=None):
        # PR #49 round 25 fixture-seam maintenance (thread
        # 3873970933): each probe's tuple rides a RoundBounds carrier
        # whose folded review evidence names the probe's OWN bounds
        # head (the stable-head rule — cold-start completions require
        # review_head == observed head now); the tuples themselves
        # are unchanged.
        bounds = pr_guard_reaction_probe.RoundBounds(probe.pop("triple"))
        bounds.review_head = bounds[0]
        bounds.review_stamp = "2026-08-26T12:45:00Z"
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


class EyesHeadBindingTests(unittest.TestCase):
    def test_eyes_round_state_truth_table(self):
        # Given: the latch module's EYES classification against the
        # head push. When: eyes_round_state evaluates. Then: only a
        # STRICTLY-greater created_at reads EYES (equality carries
        # the round-10 ambiguity, thread 3868782042), a pre-head
        # EYES reads EYES_STALE, and an unreadable push ('') reads
        # EYES_UNVERIFIED (thread 3868979509).
        for created, pushed, expected in (
            ("2026-08-26T12:29:59Z", "2026-08-26T12:30:00Z", "EYES_STALE"),
            ("2026-08-26T12:30:00Z", "2026-08-26T12:30:00Z", "EYES_STALE"),
            ("2026-08-26T12:30:01Z", "2026-08-26T12:30:00Z", "EYES"),
            ("2026-08-26T12:30:01Z", "", "EYES_UNVERIFIED"),
        ):
            self.assertEqual(
                pr_guard_reaction_latch.eyes_round_state(created, pushed),
                expected,
                (created, pushed),
            )

    def test_stale_and_unverified_eyes_never_arm(self):
        # Given: the two new EYES variants. When: the latch's arming
        # predicate evaluates them. Then: NEITHER arms — a pre-head
        # EYES is a prior round's leftover and an unprovable EYES is
        # a read failure; neither may counterfeit the transition an
        # initial-+1 wait exits 0 on (thread 3868979509 beside round
        # 6's 3868047719 rule).
        for state in ("EYES_STALE", "EYES_UNVERIFIED"):
            self.assertFalse(
                pr_guard_reaction_latch.arms_transition_latch(state), state
            )
        self.assertIn(
            "predates the current round's boundary",
            pr_guard_reaction_latch.render_state("EYES_STALE"),
        )
        self.assertIn(
            "unverified",
            pr_guard_reaction_latch.render_state("EYES_UNVERIFIED"),
        )

    def test_pre_head_eyes_never_arms_late_plus_one_times_out(self):
        # Given: the reviewer's exact race — head A's review shows
        # EYES (12:00) while head B was pushed at 12:30 BEFORE the
        # wait began, so every probe's head reads stably B; A's
        # review then completes and posts its +1 at 13:00, genuinely
        # postdating B's push. When: wait polls 12s. Then: exit 1 —
        # the pre-head EYES reads EYES_STALE and NEVER arms, so the
        # post-head-timestamps +1 finds no latch to ride and the
        # wait holds it to the timeout (B was reviewed by nobody;
        # thread 3868979509); the pre-fix wait armed on the stale
        # EYES and exited 0 at t=5.
        code, out = run_wait(
            [
                [react("eyes", created="2026-08-26T12:00:00Z", rid=5)],
                [react("+1", created="2026-08-26T13:00:00Z", rid=6)],
                [react("+1", created="2026-08-26T13:00:00Z", rid=6)],
                [react("+1", created="2026-08-26T13:00:00Z", rid=6)],
            ],
            [B_BOUNDS] * 4,
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn(
            "EYES (stale — predates the current round's boundary", out
        )
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)
        self.assertNotIn("WAIT DONE", out)

    def test_post_head_eyes_arms_fresh_plus_one_exits_zero(self):
        # Given: the same head B (pushed 12:30) but a CURRENT-round
        # EYES at 12:31 — strictly postdating the push — and the
        # round's fresh +1 at 13:00. When: wait polls. Then: exit 0
        # at 5s — the head-bound arming never withholds a genuine
        # post-head round (the conservative-only direction of thread
        # 3868979509).
        code, out = run_wait(
            [
                [react("eyes", created="2026-08-26T12:31:00Z", rid=5)],
                [react("+1", created="2026-08-26T13:00:00Z", rid=6)],
            ],
            [B_BOUNDS] * 2,
            600,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)

    def test_unreadable_push_eyes_reads_unverified(self):
        # Given: an EYES whose head dates read NULL (readable oid,
        # empty pushedDate/committedDate — the live-verified PR #49
        # shape). When: bot_review_reaction reads. Then:
        # EYES_UNVERIFIED — the EYES's round cannot be checked, so it
        # is not round evidence and arms nothing (the round-6 rule
        # carried to the EYES half, thread 3868979509). (PR #49
        # round 13 repin, thread 3869259808: the pre-round-13 shape
        # was the fully-FAILED probe (("", "", "")), which now RAISES
        # ReactionBracketUnreadable — the whole probe UNREADABLE,
        # retry next interval; UNVERIFIED survives via null dates.)
        with mock.patch.object(
            pr_guard_reaction, "gh_reactions", return_value=[react("eyes")]
        ), mock.patch.object(
            pr_guard_reaction, "round_bounds", return_value=(HEAD_B, "", "", "")
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=HEAD_B
        ):
            self.assertEqual(
                pr_guard_reaction.bot_review_reaction(48), "EYES_UNVERIFIED"
            )


class SharedProbeBudgetTests(unittest.TestCase):
    def test_budget_sequence_shared_across_all_three_reads(self):
        # Given: a 30s probe budget; the head-only read consumes 20
        # fake seconds and the reactions walk 10 more. When:
        # bot_reaction_reading probes. Then: every stage receives
        # the REMAINING window against the ONE start-of-probe
        # deadline — head 30.0, walk 10.0, round probe the clamped
        # 1.0 floor — never a fresh grant of the original (thread
        # 3868979515); the pre-fix walk received the full 30.0
        # after the head read had already spent 20s of it.
        clock = FakeClock()
        calls = []

        def fake_head(pr, timeout_secs=None):
            calls.append(("head", timeout_secs))
            clock.sleep(20)
            return HEAD_B

        def fake_walk(pr, timeout_secs=None):
            calls.append(("walk", timeout_secs))
            clock.sleep(10)
            return [react("eyes", created="2026-08-26T12:31:00Z", rid=5)]

        def fake_bounds(pr, timeout_secs=None):
            calls.append(("bounds", timeout_secs))
            return B_BOUNDS

        with mock.patch.object(
            pr_guard_reaction, "head_ref_oid", side_effect=fake_head
        ), mock.patch.object(
            pr_guard_reaction, "gh_reactions", side_effect=fake_walk
        ), mock.patch.object(
            pr_guard_reaction, "round_bounds", side_effect=fake_bounds
        ), mock.patch.object(
            pr_guard_reaction, "time", clock
        ):
            state = pr_guard_reaction.bot_review_reaction(48, timeout_secs=30)
        self.assertEqual(state, "EYES")
        self.assertEqual(
            calls, [("head", 30.0), ("walk", 10.0), ("bounds", 1.0)]
        )

    def test_exhausted_budget_stops_the_probe_unreadable(self):
        # Given: the head-only read consumes the ENTIRE 30s budget.
        # When: bot_reaction_reading probes. Then: the walk receives
        # <= 0 and its guard STOPS the probe — ReactionWalkExpired
        # propagates (the caller's UNREADABLE arm owns it) and the
        # round probe is never dispatched; no stage past an
        # exhausted deadline gets a fresh 1s-floor grant (thread
        # 3868979515).
        clock = FakeClock()
        calls = []

        def fake_head(pr, timeout_secs=None):
            calls.append(("head", timeout_secs))
            clock.sleep(30)
            return HEAD_B

        def fake_walk(pr, timeout_secs=None):
            calls.append(("walk", timeout_secs))
            assert timeout_secs <= 0, timeout_secs
            raise pr_guard_reaction.ReactionWalkExpired("deadline")

        bounds = mock.Mock()

        with mock.patch.object(
            pr_guard_reaction, "head_ref_oid", side_effect=fake_head
        ), mock.patch.object(
            pr_guard_reaction, "gh_reactions", side_effect=fake_walk
        ), mock.patch.object(
            pr_guard_reaction, "round_bounds", bounds
        ), mock.patch.object(
            pr_guard_reaction, "time", clock
        ):
            with self.assertRaises(pr_guard_reaction.ReactionWalkExpired):
                pr_guard_reaction.bot_review_reaction(48, timeout_secs=30)
        self.assertEqual(len(calls), 2)
        bounds.assert_not_called()


class ResolveAuditBannerlessTests(unittest.TestCase):
    def run_resolve(self, surveys):
        flags = []

        def fake_survey(pr, reaction=True):
            flags.append(reaction)
            return next(surveys)

        out = io.StringIO()
        with mock.patch.object(
            cli, "survey", side_effect=fake_survey
        ), mock.patch.object(
            cli, "refetch_thread", side_effect=lambda t: t
        ), mock.patch.object(
            cli, "resolve_thread", return_value=True
        ), redirect_stdout(out):
            code = cli.resolve(48)
        return code, out.getvalue(), flags

    def test_resolve_audit_survey_is_bannerless(self):
        # Given: one receipted thread (a human receipt as the last
        # word) and a clean re-survey for the final audit. When:
        # resolve runs. Then: exit 0 — the OPENING survey keeps the
        # human-facing banner (True) while the FINAL AUDIT passes
        # reaction=False: its snapshot gates the RESOLVE DONE
        # verdict, and the banner's bounded 15s read may never sit
        # between that snapshot and the go/no-go (thread 3868979526).
        code, out, flags = self.run_resolve(
            iter([[thread("11", "receipted")], [thread("11", "receipted")]])
        )
        self.assertEqual(code, 0)
        self.assertEqual(flags, [True, False])
        self.assertIn("RESOLVE DONE: 1/1", out)

    def test_resolve_audit_blocked_survey_still_bannerless(self):
        # Given: a receipted thread to resolve, but a NEW DANGER
        # finding arrives during the pass and surfaces in the final
        # audit. When: resolve runs. Then: exit 1 AUDIT BLOCKED —
        # and the audit STILL ran bannerless: a bot follow-up
        # landing on an already-resolved thread during a banner read
        # must not hide behind the stale clean list whatever the
        # verdict (thread 3868979526).
        code, out, flags = self.run_resolve(
            iter([[thread("11", "receipted")], [thread("12", "DANGER")]])
        )
        self.assertEqual(code, 1)
        self.assertEqual(flags, [True, False])
        self.assertIn("AUDIT BLOCKED", out)


if __name__ == "__main__":
    unittest.main()
