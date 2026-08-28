"""pr_guard reaction-signal tests (PR #48).

Vault note 'Unified Realms/Notes/Codex Review Bot Reaction Signal.md'
(user-taught + API-verified 2026-08-26): the codex review bot
chatgpt-codex-connector[bot] reacts ON the PR itself — THUMBS_UP =
review complete + passed; EYES = actively reviewing; none = not
started/stale. This suite pins bot_review_reaction's parsing
(latest-wins across multiple bot reactions, unknown latest content ->
UNKNOWN — the round-14 repin, thread 3869941509 — other users
ignored, the REST seam dying on failed/malformed reads), the survey
banner (the first-class line beside SUMMARY,
fail-open on a dead read), the wait mode's poll loop (EYES->THUMBS_UP
flip detection, immediate exit, the deadline-clamped final probe on
timeout, unreadable-keeps-polling), and the CLI wait argv contract.
The PR #49 follow-ups (paginated reads, probe budgets, stale-round
THUMBS_UP discrimination) live in pr_guard_reaction_followup_test.py;
the round-3 request-bound completion in pr_guard_reaction_round3_test.
This file's helpers pin round_bounds at (head oid, head-push
BEFORE the
fixtures' reactions, no round marker), so a THUMBS_UP stands by
default.

No network: gh_reactions is patched at the subprocess seam; the wait
loop runs on the shared FakeClock (thread 3832522300's fake clock,
deadline arithmetic asserts in exact fake seconds). Reaction payloads
mirror the REST WIRE vocabulary (+1/eyes/rocket) — live-verified on
PR #48: the bot's passing reaction arrives as "+1", NOT GraphQL's
THUMBS_UP, and a name-compare read it as NONE before the fix.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_test -v
"""

import io
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import cli
from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_banner
from . import pr_guard_reaction_probe
from . import pr_guard_threads
from .pr_guard_merge_fixtures import FakeClock, thread

BOT = pr_guard_reaction.REACTION_BOT

# PR #49 (thread 3867503712): the round bounds the helpers pin by
# default — head pushed BEFORE the fixtures' 12:00 reaction and NO
# round-engagement marker, so a THUMBS_UP stands unless a test
# overrides it with later bounds (the stale/round cases live in
# pr_guard_reaction_followup_test.py / pr_guard_reaction_round3_test).
HEAD_BEFORE_REACTION = "2026-08-26T11:00:00Z"
# PR #49 round 8 repin (thread 3868443452): round_bounds grew a
# head-first headRefOid element — one stable head throughout these
# fixtures, so the wait's head-change reset never fires here.
HEAD_OID = "3bb3510a1b2c3d4e5f60718293a4b5c6d7e8f9a0"


def react(content, login=BOT, created="2026-08-26T12:00:00Z"):
    return {"content": content, "created_at": created, "user": {"login": login}}


def read_state(payload, head=HEAD_BEFORE_REACTION):
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", return_value=payload
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", return_value=(HEAD_OID, head, "", "")
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
    ):
        return pr_guard_reaction.bot_review_reaction(48)


def run_wait(reads, timeout_secs, head=HEAD_BEFORE_REACTION):
    """wait_reaction on the FakeClock; returns (code, output, clock)."""
    # PR #49 round 25 fixture-seam maintenance (thread 3873970933):
    # the plain bounds tuple rides a RoundBounds carrier whose folded
    # review evidence names the STABLE head (the stamp between the
    # fixtures' EYES 12:00 and +1 12:05) — the +1 is a POST-review
    # verdict and the completion now requires the evidence at cold
    # start too; the marker-window tuple itself is unchanged.
    bounds = pr_guard_reaction_probe.RoundBounds((HEAD_OID, head, "", ""))
    bounds.review_head = HEAD_OID
    bounds.review_stamp = "2026-08-26T12:03:00Z"
    clock = FakeClock()
    items = iter(reads)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_read
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", return_value=bounds
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue(), clock


class BotReviewReactionTests(unittest.TestCase):
    def test_thumbs_up_reaction(self):
        # Given: the bot reacted THUMBS_UP on the PR. When: read.
        # Then: THUMBS_UP — the review-complete signal.
        self.assertEqual(read_state([react("+1")]), "THUMBS_UP")

    def test_eyes_reaction(self):
        # Given: the bot reacted EYES. When: read.
        # Then: EYES — review actively in progress.
        self.assertEqual(read_state([react("eyes")]), "EYES")

    def test_no_reactions_is_none(self):
        # Given: the PR carries no reactions at all. When: read.
        # Then: NONE — not started (or a stale round left nothing).
        self.assertEqual(read_state([]), "NONE")

    def test_other_users_reactions_ignored(self):
        # Given: only HUMANS and other bots reacted. When: read.
        # Then: NONE — the signal is the codex bot's alone.
        self.assertEqual(
            read_state(
                [
                    react("+1", login="RachaelsDen"),
                    react("eyes", login="github-actions[bot]"),
                ]
            ),
            "NONE",
        )

    def test_latest_reaction_wins(self):
        # Given: the bot holds EYES (older) AND THUMBS_UP (newer) —
        # the round finished after the start marker. When: read.
        # Then: THUMBS_UP — the LATEST reaction is authoritative.
        self.assertEqual(
            read_state(
                [react("eyes", created="2026-08-26T12:00:00Z"),
                 react("+1", created="2026-08-26T12:04:00Z")]
            ),
            "THUMBS_UP",
        )

    def test_stale_thumbs_up_superseded_by_eyes(self):
        # Given: a STALE THUMBS_UP from a prior round beside a fresh
        # EYES — a new review round started. When: read.
        # Then: EYES — latest wins; the old pass no longer stands.
        self.assertEqual(
            read_state(
                [react("+1", created="2026-08-26T10:00:00Z"),
                 react("eyes", created="2026-08-26T12:00:00Z")]
            ),
            "EYES",
        )

    def test_unknown_latest_content_is_unknown(self):
        # Given: the bot's only reaction is ROCKET. When: read.
        # Then: UNKNOWN — an unknown content is never a done signal,
        # and (the round-14 repin of this fixture, thread 3869941509)
        # never NONE either: refinements #2 made persistent NONE the
        # terminal findings exit, so the unrecognized shape is its
        # own DISTINCT state.
        self.assertEqual(read_state([react("rocket")]), "UNKNOWN")

    def test_unknown_latest_beats_known_older(self):
        # Given: EYES (older) then ROCKET (newer) from the bot. When:
        # read.
        # Then: UNKNOWN — the latest is unknown, and conservatively
        # that is NOT an active-review or done signal the waiter
        # could act on beyond keeping the poll bounded (the round-14
        # repin: DISTINCT from NONE, per thread 3869941509).
        self.assertEqual(
            read_state(
                [react("eyes", created="2026-08-26T12:00:00Z"),
                 react("rocket", created="2026-08-26T12:01:00Z")]
            ),
            "UNKNOWN",
        )


class GhReactionsTests(unittest.TestCase):
    def test_nonzero_rc_dies(self):
        # Given: gh api exits nonzero. When: read.
        # Then: die (exit 2) — the API error is not silently NONE.
        proc = subprocess.CompletedProcess([], 1, stdout="", stderr="nope")
        with mock.patch.object(
            pr_guard_reaction.subprocess, "run", return_value=proc
        ):
            with self.assertRaises(SystemExit):
                pr_guard_reaction.gh_reactions(48)

    def test_garbage_json_dies(self):
        # Given: rc 0 but the body is not JSON. When: read.
        # Then: die — malformed is not a valid empty reaction set.
        proc = subprocess.CompletedProcess([], 0, stdout="<html>", stderr="")
        with mock.patch.object(
            pr_guard_reaction.subprocess, "run", return_value=proc
        ):
            with self.assertRaises(SystemExit):
                pr_guard_reaction.gh_reactions(48)

    def test_non_list_payload_dies(self):
        # Given: rc 0, valid JSON, but a dict (an error envelope).
        # When: read.
        # Then: die — reactions is a LIST endpoint; anything else is
        # malformed.
        proc = subprocess.CompletedProcess(
            [], 0, stdout='{"message": "Moved"}', stderr=""
        )
        with mock.patch.object(
            pr_guard_reaction.subprocess, "run", return_value=proc
        ):
            with self.assertRaises(SystemExit):
                pr_guard_reaction.gh_reactions(48)


class ReactionBannerTests(unittest.TestCase):
    def test_banner_lists_thread_labels_as_authority(self):
        # Given: THUMBS_UP and a surveyed thread (label 3867000001).
        # When: the banner renders.
        # Then: the UNQUALIFIED-snapshot DONE render (the round-23
        # repin, thread 3873317572: the state-only read cannot run
        # the wait's freshness checks, so the banner never presents
        # the bare +1 as a completed round), the thread-as-authority
        # boundary, and the cheap-wait-signal framing all print.
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_reaction,
            "gh_reactions",
            return_value=[react("+1")],
        ), mock.patch.object(
            pr_guard_reaction,
            "round_bounds",
            return_value=(HEAD_OID, HEAD_BEFORE_REACTION, "", ""),
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
        ), redirect_stdout(out):
            state = pr_guard_reaction_banner.reaction_banner(48, ["3867000001"])
        self.assertEqual(state, "THUMBS_UP")
        text = out.getvalue()
        self.assertIn("BOT REACTION: THUMBS_UP (unqualified snapshot", text)
        self.assertIn("threads 3867000001 are the authority", text)
        self.assertIn("cheap wait signal", text)

    def test_banner_fails_open_on_read_death(self):
        # Given: the reaction read dies (gh failure). When: the banner
        # renders inside survey.
        # Then: UNREADABLE prints and NOTHING propagates — the
        # reaction is the wait signal, never the merge authority, so
        # an unreadable one must not block or kill a survey.
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_reaction,
            "gh_reactions",
            side_effect=SystemExit(2),
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
        ), redirect_stdout(out):
            state = pr_guard_reaction_banner.reaction_banner(48, ["3867000001"])
        self.assertEqual(state, "UNREADABLE")
        self.assertIn("BOT REACTION: UNREADABLE", out.getvalue())
        self.assertIn("authority", out.getvalue())


class SurveyIntegrationTests(unittest.TestCase):
    def test_survey_prints_reaction_beside_summary(self):
        # Given: one resolved thread and the bot at THUMBS_UP.
        # When: survey runs.
        # Then: the SUMMARY line is immediately followed by the
        # first-class BOT REACTION line carrying the thread label.
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_threads, "fetch_threads", return_value=[thread("3867000001", "resolved")]
        ), mock.patch.object(
            pr_guard_reaction, "gh_reactions", return_value=[react("+1")]
        ), mock.patch.object(
            pr_guard_reaction,
            "round_bounds",
            return_value=(HEAD_OID, HEAD_BEFORE_REACTION, "", ""),
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
        ), redirect_stdout(out):
            pr_guard_threads.survey(48)
        text = out.getvalue()
        self.assertIn("SUMMARY pr=48 total=1", text)
        self.assertIn("BOT REACTION: THUMBS_UP", text)
        self.assertLess(text.index("SUMMARY pr=48"), text.index("BOT REACTION:"))


class WaitReactionTests(unittest.TestCase):
    def test_wait_flip_detection(self):
        # Given: EYES at 0s, EYES again at 5s, THUMBS_UP at 10s.
        # When: wait polls at the 5s cadence.
        # Then: exit 0; each STATE CHANGE prints exactly once (the
        # repeated EYES is silent) and two polite 5s sleeps ran.
        code, out, clock = run_wait(
            # PR #49 round 9 repin (thread 3868625469): the completing
            # +1 postdates the observed EYES — a real flip lands a NEW
            # later-dated object, and the wait now requires it to
            # follow the observed-activity watermark.
            [
                [react("eyes")],
                [react("eyes")],
                [react("+1", created="2026-08-26T12:05:00Z")],
            ],
            600,
        )
        self.assertEqual(code, 0)
        self.assertEqual(clock.slept, [5.0, 5.0])
        self.assertEqual(out.count("BOT REACTION: EYES"), 1)
        self.assertIn("BOT REACTION: THUMBS_UP", out)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)
        self.assertIn("merge authority", out)

    def test_wait_initial_thumbs_up_holds_for_a_transition(self):
        # Given: the PR already shows THUMBS_UP — but nothing marks it
        # as THIS round's (a request-less round may not have posted
        # yet, thread 3867897766) — and nothing changes for the whole
        # 10s window. When: wait starts. Then: exit 1 — the
        # un-transitioned +1 never exits 0 on sight anymore; the HOLD
        # note explains the withheld acceptance and the timeout banner
        # carries the thread-3867897766 explanation (the round-1
        # live-verify instant exit is the price this sound bound
        # pays; survey the threads instead).
        code, out, clock = run_wait([[react("+1")]] * 3, 10)
        self.assertEqual(code, 1)
        self.assertEqual(clock.slept, [5.0, 5.0])
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("thread 3867897766", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)
        self.assertIn("exit 0 was withheld", out)
        self.assertNotIn("WAIT DONE", out)

    def test_wait_timeout_runs_final_probe_at_deadline(self):
        # Given: the reaction stays EYES for the whole 12s window.
        # When: wait polls.
        # Then: exit 1; the sleeps are clamped to the deadline
        # (5, 5, then the remaining 2) so the FINAL probe lands AT the
        # deadline — a THUMBS_UP arriving at the last instant still
        # exits 0, and the timeout banner names the last state.
        code, out, clock = run_wait(
            [[react("eyes")]] * 4, 12
        )
        self.assertEqual(code, 1)
        self.assertEqual(clock.slept, [5.0, 5.0, 2.0])
        self.assertIn("WAIT TIMEOUT: 12s elapsed, last state EYES", out)

    def test_wait_unreadable_keeps_polling(self):
        # Given: the first two reads die (transient gh failure), then
        # EYES lands, then THUMBS_UP. When: wait polls. Then: exit 0
        # — a failed read is NEVER a done signal and never aborts the
        # bounded poll; each transition prints. The EYES is doing
        # double duty since thread 3867897766: it is also the
        # confirmed transition that arms the +1 (an UNREADABLE start
        # never captured a non-DONE initial state, so the bare +1
        # could not be accepted on sight either).
        code, out, clock = run_wait(
            # Round 9 repin (thread 3868625469): the completing +1
            # postdates the observed EYES.
            [
                SystemExit(2),
                SystemExit(2),
                [react("eyes")],
                [react("+1", created="2026-08-26T12:05:00Z")],
            ],
            600,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("BOT REACTION: UNREADABLE"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP", out)


class WaitCliTests(unittest.TestCase):
    def test_wait_argv_usage_errors(self):
        # Given: malformed wait argv — a non-digit --timeout-secs, a
        # missing PR number, or extra operands. When: main parses.
        # Then: exit 2 before ANY dispatch (usage is the wait mode's
        # only exit-2 meaning).
        for argv in (
            ["pr_guard.py", "wait", "48", "--timeout-secs", "x"],
            ["pr_guard.py", "wait"],
            ["pr_guard.py", "wait", "48", "extra", "extra2"],
        ):
            with self.subTest(argv=argv):
                self.assertEqual(cli.main(argv), 2)

    def test_wait_dispatch_default_and_override(self):
        # Given: valid wait argv with and without --timeout-secs.
        # When: main dispatches.
        # Then: wait_reaction receives the PR and the timeout — 600
        # by default, the explicit value when given.
        for argv, expected in (
            (["pr_guard.py", "wait", "48"], (48, 600)),
            (["pr_guard.py", "wait", "48", "--timeout-secs", "10"], (48, 10)),
        ):
            with self.subTest(argv=argv):
                with mock.patch.object(
                    cli, "wait_reaction", return_value=0
                ) as fake:
                    self.assertEqual(cli.main(argv), 0)
                fake.assert_called_once_with(*expected)


if __name__ == "__main__":
    unittest.main()
