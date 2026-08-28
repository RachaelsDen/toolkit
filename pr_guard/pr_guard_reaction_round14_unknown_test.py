"""pr_guard reaction round-14 UNKNOWN tests (PR #49 thread 3869941509
P2) — the 250 pure-LOC ceiling's split of the round-14 suite pair
(the round-4/round-7 suite-pair precedent): this companion carries
the READING-state half (the DISTINCT unrecognized-content state and
its render); the wait-loop halves (the transition-NONE arming gate
of 3869941505 and the resurfaced-prior-+1 findings of 3869941521)
live in pr_guard_reaction_round14_test.

3869941509 — when the bot's latest reaction carries any
UNRECOGNIZED content (rocket, heart, ...), the reading reported
NONE. That was the rounds-1-13 conservative non-success pin, but
wait_reaction now treats two persistent NONE readings after a
verified EYES as the terminal findings signal (refinements #2), so
an unexpected reaction made the command exit 3 and claim the review
completed with feedback even though the bot did not remove its
reaction and may still be running. The reading now returns the
DISTINCT REACTION_UNKNOWN: never DONE, never latch-arming, never
the findings transition's NONE, never the cold-NONE hint's "no
reaction" (the bot demonstrably reacted — the cold streak resets on
it like on any real reading), rendered with its own line carrying
the content, and BREAKING NONE persistence exactly as any non-NONE
reading does.

No network: the wait tests patch gh_reactions/round_bounds/
head_ref_oid at their seams on the FakeClock.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round14_unknown_test -v
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_latch
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock

BOT = pr_guard_reaction.REACTION_BOT

HEAD = "d84631fa1b2c3d4e5f60718293a4b5c6d7e8f9a0"

# The stable-head bounds: the 11:00 push leaves the 12:31 EYES
# verified-current (round 11) — the arming precursor the poisoned
# NONE pin would have consumed.
STABLE_BOUNDS = (HEAD, "2026-08-26T11:00:00Z", "", "")


def react(content, created="2026-08-26T12:31:00Z", rid=None):
    return {
        "content": content,
        "created_at": created,
        "id": rid,
        "user": {"login": BOT},
    }


def read(reactions, bounds, head):
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", return_value=reactions
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", return_value=bounds
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=head
    ):
        return pr_guard_reaction.bot_review_reaction(48)


def run_wait(reads, bounds, timeout_secs):
    """wait_reaction on the FakeClock with stable head bounds; (code, out).

    (PR #49 round 25 fixture-seam maintenance, thread 3873970933:
    the bounds ride a RoundBounds carrier whose folded review
    evidence names the STABLE head — the findings exit is a
    POST-review signal and cold-start terminal signals require the
    evidence now; the marker-window tuple itself is unchanged.)
    """
    clock = FakeClock()
    items = iter(reads)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    carried = pr_guard_reaction_probe.RoundBounds(STABLE_BOUNDS)
    carried.review_head = HEAD
    carried.review_stamp = "2026-08-26T12:45:00Z"
    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_read
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", return_value=carried
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=HEAD
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue()


class UnknownReactionTests(unittest.TestCase):
    def test_unknown_latest_reads_unknown(self):
        # Given: the bot's only reaction is ROCKET; and separately an
        # older EYES superseded by a newer ROCKET. When: read. Then:
        # UNKNOWN both times — an unrecognized content is DISTINCT
        # from NONE (thread 3869941509: the conservative-to-NONE pin
        # is repinned; latest-wins selects the rocket either way).
        self.assertEqual(read([react("rocket")], STABLE_BOUNDS, HEAD), "UNKNOWN")
        self.assertEqual(
            read(
                [
                    react("eyes", created="2026-08-26T12:00:00Z", rid=5),
                    react("rocket", created="2026-08-26T12:01:00Z", rid=6),
                ],
                STABLE_BOUNDS,
                HEAD,
            ),
            "UNKNOWN",
        )

    def test_unknown_render_carries_content(self):
        # Given: the UNKNOWN state, with and without its content.
        # When: render_state evaluates. Then: its OWN one-line render
        # carrying the unrecognized content and the report-if-
        # persists warning — never the NONE meanings (findings/
        # not-started/stale do not apply to a rocket).
        self.assertEqual(
            pr_guard_reaction_latch.render_state("UNKNOWN", "rocket"),
            "UNKNOWN (unrecognized reaction content 'rocket' — "
            "report if this persists)",
        )
        bare = pr_guard_reaction_latch.render_state("UNKNOWN")
        self.assertNotIn("\n", bare)
        self.assertIn("unrecognized reaction content", bare)
        self.assertIn("report if this persists", bare)

    def test_unknown_after_eyes_never_exits_findings(self):
        # Given: the thread-3869941509 race — a verified EYES
        # (12:31) observed at t=0, then the bot's latest reaction
        # becomes ROCKET (persistent). When: wait polls 12s. Then:
        # exit 1 — UNKNOWN is not NONE: the EYES-to-NONE findings
        # transition never fires on an unrecognized reaction (the bot
        # did not remove its reaction; it may still be running); the
        # pre-fix wait read the rocket as NONE and exited 3 at t=10.
        code, out = run_wait(
            [
                [react("eyes", rid=5)],
                [react("rocket", rid=6)],
                [react("rocket", rid=6)],
                [react("rocket", rid=6)],
            ],
            [STABLE_BOUNDS] * 4,
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn("BOT REACTION: UNKNOWN (unrecognized reaction content 'rocket'", out)
        self.assertNotIn("WAIT FINDINGS", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_unknown_never_satisfies_the_cold_none_hint(self):
        # Given: a persistent ROCKET from t=0 (no EYES variant ever).
        # When: wait polls 20s. Then: exit 1 with NO '@codex review'
        # hint — an unknown reaction is not "no reaction": the bot
        # demonstrably reacted, so the failed-start grace never
        # accumulates; the pre-fix wait read NONE and hinted at t=10.
        code, out = run_wait(
            [[react("rocket", rid=6)]] * 5,
            [STABLE_BOUNDS] * 5,
            20,
        )
        self.assertEqual(code, 1)
        self.assertNotIn("HINT:", out)
        self.assertIn("WAIT TIMEOUT: 20s elapsed", out)

    def test_unknown_breaks_none_persistence(self):
        # Given: a verified EYES, a NONE at t=5 (absent streak
        # begins), then ROCKET at t=10, then persistent NONE. When:
        # wait polls. Then: exit 3 at t=25 (NOT t=20) — the UNKNOWN
        # probe is a real observation that BREAKS the NONE
        # persistence (the streak resets to zero; the count restarts),
        # so the findings confirmation needs FINDINGS_GRACE_PROBES
        # NONEs on THIS side of it (the round-23 repin, thread
        # 3873317562: three consecutive absent probes post-UNKNOWN).
        code, out = run_wait(
            [
                [react("eyes", rid=5)],
                [],
                [react("rocket", rid=6)],
                [],
                [],
                [],
            ],
            [STABLE_BOUNDS] * 6,
            600,
        )
        self.assertEqual(code, 3)
        self.assertIn("WAIT FINDINGS: EYES → NONE at 25s", out)
        self.assertNotIn("WAIT FINDINGS: EYES → NONE at 20s", out)


if __name__ == "__main__":
    unittest.main()
