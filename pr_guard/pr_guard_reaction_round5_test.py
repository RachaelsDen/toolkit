"""pr_guard reaction round-5 tests (PR #49 threads 3867897759/64/66).

Thread 3867897759 (P1): the post-merge quiet-period watch is a GATE
— every cycle's DANGER check and the final MERGED CLEAN verdict —
so ALL of its surveys run bannerless (reaction=False); the banner's
only home is the human-facing CLI survey contexts.

Thread 3867897764 (P2): a reactions walk whose deadline expires
mid-pagination RAISES ReactionWalkExpired — the partial list is
UNREADABLE (the banner fails open, the wait keeps polling), never a
latest-wins input for bot_review_reaction.

Thread 3867897766 (P1): a +1 already present at wait start is not
this round's completion — exit 0 needs the wait to OBSERVE one
confirmed non-DONE reading (away-and-back; a fresh EYES) between
start and the accepted +1; UNREADABLE probes never count.

No network: the quiet-watch run rides the shared fake-gh/fake-git/
fake-clock harness; the wait tests patch gh_reactions/round_bounds
at their seams on the FakeClock; the pagination test patches the
subprocess seam (a real sleep burns the budget).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round5_test -v
"""

import io
import json
import subprocess
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_banner
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock, thread
from .pr_guard_merge_harness import MergeHarness, merged

BOT = pr_guard_reaction.REACTION_BOT
RUNNER = MergeHarness()


def react(content, login=BOT, created="2026-08-26T12:00:00Z"):
    return {"content": content, "created_at": created, "user": {"login": login}}


# The thread-3867897766 hole's bounds: the +1 (12:00) postdates the
# head push (11:00) and NO marker exists (the request-less round has
# not posted yet) — so bot_review_reaction itself reads DONE; only
# the wait's transition latch can withhold it.
# PR #49 round 8 repin (thread 3868443452): round_bounds grew a
# head-first headRefOid element — one stable head throughout, so
# the wait's head-change reset never fires in this suite.
HEAD_OID = "b533c61d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b"
UNMARKED_BOUNDS = (HEAD_OID, "2026-08-26T11:00:00Z", "", "")


def run_wait(reads, timeout_secs, bounds=UNMARKED_BOUNDS):
    """wait_reaction on the FakeClock; returns (code, output).

    (PR #49 round 25 fixture-seam maintenance, thread 3873970933: the
    bounds ride a RoundBounds carrier whose folded review evidence
    names the STABLE head with a stamp between the fixtures' EYES
    12:00 and +1 12:05 — the +1 is a POST-review verdict and
    cold-start completions require the evidence now; the unmarked
    marker-window tuple itself is unchanged.)
    """
    clock = FakeClock()
    items = iter(reads)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    out = io.StringIO()
    carried = pr_guard_reaction_probe.RoundBounds(bounds)
    carried.review_head = HEAD_OID
    carried.review_stamp = "2026-08-26T12:03:00Z"
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


class QuietWatchBannerlessTests(unittest.TestCase):
    def test_quiet_cycles_and_final_verdict_dispatch_no_banner(self):
        # Given: a guarded merge over a clean snapshot with a 120s
        # quiet window — the closing gate survey plus THREE watch
        # surveys (t=0 cycle, t=60 cycle, t=120 final). When: the
        # act runs. Then: EVERY survey passed reaction=False — no
        # cycle's DANGER check (nor the final MERGED CLEAN verdict)
        # sat behind the banner's 15s informational read where a bot
        # follow-up could land unanswered on a resolved thread
        # (thread 3867897759) — and the act still exits 0 clean.
        code, out, _, _ = RUNNER.run_guarded(
            iter([[thread("11", "resolved")]] * 4),
            iter(
                [
                    {
                        "head": {"sha": "b979176095b9dd6b6f8e989ed460feab9ce0abc4"},
                        "base": {"ref": "dev"},
                        "state": "open",
                        "merged": False,
                        "merge_commit_sha": "",
                    }
                ]
            ),
            poll_states=[merged()],
            quiet_secs=120,
        )
        self.assertEqual(code, 0)
        self.assertEqual(RUNNER.survey_reactions, [False, False, False, False])
        self.assertIn("MERGED CLEAN", out)


class ExpiredWalkUnreadableTests(unittest.TestCase):
    def test_expired_walk_after_page_1_never_selects(self):
        # Given: a full page-1 whose fetch burns past the probe
        # deadline, carrying the bot's +1 (the masquerade: a newer
        # eyes sits on the unread page 2 of a >100-reaction PR).
        # When: bot_review_reaction reads. Then: the walk RAISES
        # ReactionWalkExpired — no partial list returns, so no
        # latest-wins selection can crown the older page-1 +1
        # (thread 3867897764); page 2 is never fetched.
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(" ".join(argv))
            time.sleep(0.06)
            return subprocess.CompletedProcess(
                [], 0, stdout=json.dumps([react("+1")] * 100), stderr=""
            )

        with mock.patch.object(
            pr_guard_reaction.subprocess, "run", side_effect=fake_run
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
        ):
            with self.assertRaises(pr_guard_reaction.ReactionWalkExpired):
                pr_guard_reaction.bot_review_reaction(48, timeout_secs=0.05)
        self.assertEqual(len(calls), 1)

    def test_wait_treats_expired_walk_as_unreadable(self):
        # Given: every probe's walk expires mid-pagination for a 12s
        # window. When: wait polls. Then: exit 1 with ONE UNREADABLE
        # state line — the expiry is never a done signal and never
        # aborts the poll (the wait's existing unreadable arm owns
        # the raise, thread 3867897764).
        expiry = pr_guard_reaction.ReactionWalkExpired("deadline")
        code, out = run_wait([expiry] * 4, 12)
        self.assertEqual(code, 1)
        self.assertEqual(out.count("BOT REACTION: UNREADABLE"), 1)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_banner_fails_open_on_expired_walk(self):
        # Given: a survey banner whose reaction read expires
        # mid-pagination. When: the banner renders. Then: UNREADABLE
        # prints and survey continues — the informational read fails
        # OPEN (thread state stays the authority); the expiry cannot
        # block or kill a survey (thread 3867897764 beside 3867653642).
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_reaction,
            "bot_review_reaction",
            side_effect=pr_guard_reaction.ReactionWalkExpired("deadline"),
        ), redirect_stdout(out):
            state = pr_guard_reaction_banner.reaction_banner(48, ["3867000001"])
        self.assertEqual(state, "UNREADABLE")
        self.assertIn("BOT REACTION: UNREADABLE", out.getvalue())
        self.assertIn("threads 3867000001 are the authority", out.getvalue())


class InitialThumbsUpTransitionTests(unittest.TestCase):
    def test_initial_thumbs_up_with_no_activity_times_out(self):
        # Given: the prior round's +1 present at wait start — it
        # postdates the head push and NO marker exists (the
        # request-less round has not posted yet: the exact
        # thread-3867897766 hole) — and nothing changes for 12s.
        # When: wait polls. Then: exit 1 — the un-transitioned +1
        # never exits 0; the hold note and the timeout banner carry
        # the explanation.
        code, out = run_wait([[react("+1")]] * 4, 12)
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("thread 3867897766", out)
        self.assertIn("exit 0 was withheld", out)
        self.assertNotIn("WAIT DONE", out)

    def test_initial_thumbs_up_eyes_then_thumbs_up_exits_zero(self):
        # Given: the same initial +1 (the t=0 probe reads DONE and is
        # held), then the round engages — EYES lands (t=5) — and the
        # round passes again (+1 at t=10). When: wait polls. Then:
        # exit 0 at 10s — the wait WATCHED the round go active->done
        # inside itself (the reviewer's exact suggested shape,
        # thread 3867897766).
        code, out = run_wait(
            # PR #49 round 9 repin (thread 3868625469): the completing
            # +1 (12:05) postdates the observed EYES (12:00) — a real
            # flip lands a NEW later-dated object, and the wait now
            # requires it to follow the observed-activity watermark.
            [
                [react("+1")],
                [react("eyes")],
                [react("+1", created="2026-08-26T12:05:00Z")],
            ],
            600,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)

    def test_unreadable_probes_never_count_as_the_transition(self):
        # Given: the initial +1, then two transient read failures,
        # then the SAME +1 for the rest of a 20s window. When: wait
        # polls. Then: exit 1 — a read FAILURE is not round evidence;
        # only a confirmed non-DONE reading arms the latch (thread
        # 3867897766's conservative core).
        code, out = run_wait(
            [[react("+1")], SystemExit(2), SystemExit(2), [react("+1")], [react("+1")]],
            20,
        )
        self.assertEqual(code, 1)
        self.assertNotIn("WAIT DONE", out)

    def test_marker_driven_stale_flip_arms_the_fresh_pass(self):
        # Given: the initial +1 (12:00, no marker yet); the round's
        # first thread comment lands (13:05) so the SAME +1 reads
        # STALE at t=5 (the marker-driven away-transition); the
        # round's fresh +1 (14:00) lands at t=10. When: wait polls.
        # Then: exit 0 — the marker flip IS observed round evidence
        # and the post-marker pass the accepted back (thread
        # 3867897766: the +1 must postdate the round markers AND
        # move inside the wait). (PR #49 round 25 fixture-seam
        # maintenance, thread 3873970933: the probes carry the folded
        # review evidence naming the stable head — cold-start
        # completions require it now; the marker-window tuples are
        # unchanged.)
        clock = FakeClock()
        reads = iter(
            [
                [react("+1", created="2026-08-26T12:00:00Z")],
                [react("+1", created="2026-08-26T12:00:00Z")],
                [react("+1", created="2026-08-26T14:00:00Z")],
            ]
        )
        probes = iter(
            [
                (HEAD_OID, "2026-08-26T11:00:00Z", "", ""),
                (HEAD_OID, "2026-08-26T11:00:00Z", "", "2026-08-26T13:05:00Z"),
                (HEAD_OID, "2026-08-26T11:00:00Z", "", "2026-08-26T13:05:00Z"),
            ]
        )

        def fake_bounds(pr, timeout_secs=None):
            carried = pr_guard_reaction_probe.RoundBounds(next(probes))
            carried.review_head = HEAD_OID
            carried.review_stamp = "2026-08-26T13:30:00Z"
            return carried

        out = io.StringIO()
        with mock.patch.object(
            pr_guard_reaction,
            "gh_reactions",
            side_effect=lambda pr, timeout_secs=None: next(reads),
        ), mock.patch.object(
            pr_guard_reaction,
            "round_bounds",
            side_effect=fake_bounds,
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
        ), mock.patch.object(
            pr_guard_reaction, "time", clock
        ), mock.patch.object(
            pr_guard_common, "time", clock
        ), redirect_stdout(out):
            code = pr_guard_reaction.wait_reaction(48, 600)
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out.getvalue())
        self.assertIn(
            "THUMBS_UP (stale — predates the current round's start",
            out.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
