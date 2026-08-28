"""pr_guard reaction follow-up tests (PR #49).

Thread 3867503705 (P2): gh_reactions must follow the ?page=N cursor
until a SHORT page and flatten every page — a newer page-2 bot
reaction is the latest, never an older page-1 masquerade.

Thread 3867503708 (P2) + 3867572256 (PR #49 round 2, P2): every
wait probe hands its budget to the subprocess path as a timeout —
round 2 clamps that budget to the ACTUAL remaining window (capped at
two intervals, floored at 1s so the at-deadline final probe still
reads) and RECOMPUTES it for each subprocess (every reactions page,
the head-date read) — a stalled gh api reads UNREADABLE and the wait
still ends at its deadline with exit 1, never blocking past
deadline+interval.

Thread 3867503712 (P1): a THUMBS_UP predating the current head's
push is the PRIOR round's pass — THUMBS_UP_STALE internally, rendered
as THUMBS_UP (stale — predates the current head...), never exit 0;
an unreadable head date is conservative (stale), never
done-on-ambiguity.

No network: gh_reactions/round_bounds are patched at their seams
(the pagination walks patch the subprocess seam instead); the wait
loop runs on the shared FakeClock (thread 3832522300's fake clock).
Reaction payloads use the REST WIRE vocabulary (+1/eyes) —
live-verified on PR #48 (the bot's pass arrives as "+1").

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_followup_test -v
"""

import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_banner
from . import pr_guard_reaction_probe
from . import pr_guard_reaction_walk
from .pr_guard_merge_fixtures import FakeClock

BOT = pr_guard_reaction.REACTION_BOT


def react(content, login=BOT, created="2026-08-26T12:00:00Z"):
    return {"content": content, "created_at": created, "user": {"login": login}}


def page(items):
    return subprocess.CompletedProcess([], 0, stdout=json.dumps(items), stderr="")


# PR #49 round 8 repin (thread 3868443452): round_bounds grew a
# head-first headRefOid element — one stable head here (the
# graphql_proc payload's own oid), so the wait's head-change reset
# never fires in this suite.
HEAD_OID = "ad333ff80a62bcbcfe54177ea0ff99c8007e4fde"


def run_wait(reads, timeout_secs, head="2026-08-26T11:00:00Z", requested=""):
    """wait_reaction on the FakeClock; returns (code, output, budgets)."""
    clock = FakeClock()
    items = iter(reads)
    budgets = []

    def fake_read(pr, timeout_secs=None):
        budgets.append(timeout_secs)
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_read
    ), mock.patch.object(
        pr_guard_reaction,
        "round_bounds",
        return_value=(HEAD_OID, head, requested, requested),
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue(), budgets


class PaginationTests(unittest.TestCase):
    def test_pages_flattened_until_short_page(self):
        # Given: page 1 full (100 reactions), page 2 short (2). When:
        # gh_reactions reads. Then: BOTH pages fetched (page=1 then
        # page=2) and 102 combined — a short page ends the walk.
        # (PR #49 round 24 fixture-seam maintenance, thread
        # 3873592851: a multi-page walk now RE-READS page 1 after the
        # short page — the third call returns the IDENTICAL first
        # page, so the stability recheck passes; the walk's combined
        # list and page=1/page=2 argv assertions are unchanged.
        # PR #49 round 33 seam maintenance, thread 3876172349: the
        # walk also RE-READS the terminal SHORT page after the
        # full-page recheck — the FOURTH call answers the identical
        # 2-item page (length and newest identity unchanged), so the
        # count pin moves 3 -> 4.)
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(" ".join(argv))
            return page(
                [react("heart", login="human")] * (100 if len(calls) in (1, 3) else 2)
            )

        with mock.patch.object(
            pr_guard_reaction.subprocess, "run", side_effect=fake_run
        ):
            combined = pr_guard_reaction.gh_reactions(48)
        self.assertEqual(len(combined), 102)
        self.assertEqual(len(calls), 4)
        self.assertIn("page=1", calls[0])
        self.assertIn("page=2", calls[1])
        self.assertIn("page=1", calls[2])
        self.assertIn("page=2", calls[3])

    def test_page2_bot_reaction_wins(self):
        # Given: page 1 holds 100 reactions incl. the bot's OLD +1
        # (10:00); page 2 holds the bot's FRESH eyes (12:00). When:
        # read. Then: EYES — the page-2 reaction is the latest; a
        # first-page-only read would masquerade the old +1 as
        # THUMBS_UP and exit the waiter early. (PR #49 round 8 repin:
        # the round probe rides EVERY reading now — EYES included.
        # PR #49 round 10 repin, thread 3868782039: the head read
        # BRACKETS the walk — the same graphql payload answers the
        # head-only BEFORE call, the two REST pages, and the round
        # probe's combined AFTER read, oids matching throughout.)
        # (PR #49 round 24 fixture-seam maintenance, thread
        # 3873592851: the two-page walk RE-READS page 1 before the
        # round probe — the appended identical page1 answers it; the
        # EYES assertion is unchanged. PR #49 round 33 seam
        # maintenance, thread 3876172349: the walk also RE-READS the
        # terminal short page after the full-page recheck — the
        # appended identical page2 answers it.)
        page1 = [react("heart", login="human")] * 99 + [
            react("+1", created="2026-08-26T10:00:00Z")
        ]
        page2 = [react("eyes", created="2026-08-26T12:00:00Z"), react("rocket", login="human")]
        head_probe = subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps(
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "headRefOid": HEAD_OID,
                                "headRef": {"target": {"pushedDate": "2026-08-26T11:00:00Z"}},
                                "timelineItems": {"nodes": []},
                                "latestReviews": {"nodes": []},
                                "reviewThreads": {"nodes": []},
                            }
                        }
                    }
                }
            ),
            stderr="",
        )
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[head_probe, page(page1), page(page2), page(page1), page(page2), head_probe],
        ):
            state = pr_guard_reaction.bot_review_reaction(48)
        self.assertEqual(state, "EYES")


class ProbeBudgetTests(unittest.TestCase):
    def test_subprocess_receives_clamped_timeout(self):
        # Given: a bounded read — a 12.5s budget (above the
        # two-interval cap) and a 0.2s budget (below the 1s floor).
        # When: gh_reactions reads a short page. Then: the
        # subprocess's timeout is the CLAMPED budget (10.0 capped,
        # 1.0 floored) — never the raw grant (thread 3867572256).
        for budget, expected in ((12.5, 10.0), (0.2, 1.0)):
            with self.subTest(budget=budget):
                with mock.patch.object(
                    pr_guard_reaction.subprocess,
                    "run",
                    return_value=page([react("+1")]),
                ) as fake:
                    pr_guard_reaction.gh_reactions(48, timeout_secs=budget)
                self.assertEqual(fake.call_args.kwargs["timeout"], expected)

    def test_pages_recompute_the_remaining_budget(self):
        # Given: a two-page read under a 2.5s budget whose FIRST page
        # burns 0.05s of FAKE time (PR #49 round 30, thread
        # 3875623455: the round-2 real sleep made this assertion
        # wall-clock flaky under CI scheduling load — a valid
        # recomputed 2.436s timeout failed the 10ms tolerance in the
        # full run while isolated reruns passed; the walk's
        # deadline/time seam is pr_guard_reaction_walk.time, the
        # round-25 GOTCHA #2 rule). When: the walk fetches page 2.
        # Then: page 2's timeout is RECOMPUTED against the probe
        # deadline — page 1's elapsed time subtracted — never the
        # same fresh grant twice (thread 3867572256's
        # sequential-reuse arm); EXACT values, no timing tolerance
        # (the FakeClock's sleep advances the walk's monotonic clock
        # deterministically; the third call is the round-24/25
        # page-1 stability re-read and the FOURTH is the round-33
        # terminal short-page re-read, thread 3876172349 — both
        # riding the same spent deadline).
        timeouts = []
        clock = FakeClock()

        def fake_run(argv, **kwargs):
            timeouts.append(kwargs["timeout"])
            if len(timeouts) == 1:
                clock.sleep(0.05)
                full_page = page([react("heart", login="human")] * 100)
                fake_run.full_page = full_page
                return full_page
            # PR #49 round 32 fixture-seam maintenance (thread
            # 3876001013): the THIRD call is page 1's stability
            # re-read and must return the settled FULL page copy (the
            # recheck now requires a full page's re-read to stay
            # full — 100 items — beside the unchanged newest
            # identity; the old single-eyes page read 1 item).
            if len(timeouts) == 3:
                return fake_run.full_page
            return page([react("eyes")])

        with mock.patch.object(
            pr_guard_reaction.subprocess, "run", side_effect=fake_run
        ), mock.patch.object(
            pr_guard_reaction_walk, "time", clock
        ):
            combined = pr_guard_reaction.gh_reactions(48, timeout_secs=2.5)
        self.assertEqual(len(combined), 101)
        self.assertEqual(timeouts, [2.5, 2.45, 2.45, 2.45])
        self.assertLess(timeouts[1], timeouts[0])

    def test_wait_budgets_clamp_to_actual_remaining(self):
        # Given: EYES for a 12s window. When: wait polls. Then: each
        # probe's budget is the ACTUAL remaining window — 10 (the
        # two-interval cap) at t=0, 7 at t=5, 2 at t=10, 1 (the
        # floor) at t=12 — the round-1 fixed 10s floor that granted a
        # stalled FINAL probe a fresh 10s PAST the advertised deadline
        # is gone (thread 3867572256).
        code, _, budgets = run_wait([[react("eyes")]] * 4, 12)
        self.assertEqual(code, 1)
        self.assertEqual(budgets, [10.0, 7.0, 2.0, 1.0])

    def test_final_probe_with_3s_remaining_gets_3s(self):
        # Given: EYES for a 13s window — the probe at t=10 has EXACTLY
        # 3s remaining. When: wait polls. Then: that probe's timeout
        # is 3.0 (<= its remaining window) and the at-deadline final
        # probe gets the 1s floor — the deadline invariant: every
        # budget <= its remaining window (the final probe's 1s floor
        # itself under one interval), so the wait NEVER blocks past
        # deadline+interval and still ends AT its deadline.
        code, out, budgets = run_wait([[react("eyes")]] * 4, 13)
        self.assertEqual(code, 1)
        self.assertEqual(budgets, [10.0, 8.0, 3.0, 1.0])
        self.assertIn("WAIT TIMEOUT: 13s elapsed", out)

    def test_stalled_probe_times_out_at_deadline(self):
        # Given: every probe raises TimeoutExpired (a stalled gh api
        # that the subprocess timeout kills). When: wait polls a 12s
        # window. Then: exit 1 AT the deadline (clamped 5/5/2 sleeps,
        # final probe landing on it) with UNREADABLE states — the
        # bounded-window promise holds, the stall never blocks past
        # it and never reads as done.
        stall = subprocess.TimeoutExpired(cmd=["gh", "api"], timeout=10)
        code, out, _ = run_wait([stall] * 4, 12)
        self.assertEqual(code, 1)
        self.assertEqual(out.count("BOT REACTION: UNREADABLE"), 1)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)


class StaleThumbsUpTests(unittest.TestCase):
    def read(self, reactions, head, requested=""):
        with mock.patch.object(
            pr_guard_reaction, "gh_reactions", return_value=reactions
        ), mock.patch.object(
            pr_guard_reaction,
            "round_bounds",
            return_value=(HEAD_OID, head, requested, requested),
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
        ):
            return pr_guard_reaction.bot_review_reaction(48)

    def test_thumbs_up_predating_head_is_stale(self):
        # Given: the bot's +1 at 12:00; the head pushed at 13:00 (a
        # new commit after the prior round's pass). When: read.
        # Then: THUMBS_UP_STALE — the prior round's pass never counts
        # for the current head.
        self.assertEqual(
            self.read(
                [react("+1", created="2026-08-26T12:00:00Z")],
                "2026-08-26T13:00:00Z",
            ),
            "THUMBS_UP_STALE",
        )

    def test_thumbs_up_after_head_is_done(self):
        # Given: head pushed 11:00; the bot's +1 at 12:00. When: read.
        # Then: THUMBS_UP — the pass postdates the round's start.
        self.assertEqual(
            self.read(
                [react("+1", created="2026-08-26T12:00:00Z")],
                "2026-08-26T11:00:00Z",
            ),
            "THUMBS_UP",
        )

    def test_unreadable_head_date_is_conservative_stale(self):
        # Given: the bot's +1 but the head-date read failed ('').
        # When: read. Then: THUMBS_UP_UNVERIFIED — never
        # done-on-ambiguity; the wait keeps polling to its timeout.
        # (PR #49 round 6, thread 3868047719: the '' -bounds +1 left
        # the STALE class — a read failure is not round evidence, so
        # the transition latch never arms on it; the verified-stale
        # assertions above are unchanged.)
        self.assertEqual(
            self.read([react("+1")], ""), "THUMBS_UP_UNVERIFIED"
        )

    def test_wait_stale_thumbs_up_times_out(self):
        # Given: the bot's +1 predates the head push for the whole 12s
        # window (the new round never signals). When: wait polls.
        # Then: exit 1 — the stale pass is not done; the output says
        # THUMBS_UP (stale — predates the current round's start...) and
        # the timeout banner carries the stale explanation.
        code, out, _ = run_wait(
            [[react("+1")]] * 4, 12, head="2026-08-26T13:00:00Z"
        )
        self.assertEqual(code, 1)
        self.assertIn("THUMBS_UP (stale — predates the current round's start", out)
        self.assertIn("waiting for the new round's signal", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_banner_renders_stale(self):
        # Given: a stale +1 beside a surveyed thread. When: the survey
        # banner renders. Then: THUMBS_UP (stale — ...) with the
        # thread-as-authority boundary — informational, thread state
        # still the merge authority.
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_reaction, "gh_reactions", return_value=[react("+1")]
        ), mock.patch.object(
            pr_guard_reaction,
            "round_bounds",
            return_value=(HEAD_OID, "2026-08-26T13:00:00Z", "", ""),
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
        ), redirect_stdout(out):
            state = pr_guard_reaction_banner.reaction_banner(48, ["3867000001"])
        self.assertEqual(state, "THUMBS_UP_STALE")
        self.assertIn(
            "THUMBS_UP (stale — predates the current round's start", out.getvalue()
        )
        self.assertIn("threads 3867000001 are the authority", out.getvalue())


class RoundBoundsTests(unittest.TestCase):
    def graphql_proc(self, pushed, committed="2026-08-26T09:00:00Z"):
        body = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "headRefOid": "ad333ff80a62bcbcfe54177ea0ff99c8007e4fde",
                        "headRef": {
                            "target": {"pushedDate": pushed, "committedDate": committed}
                        },
                        "timelineItems": {"nodes": []},
                        "latestReviews": {"nodes": []},
                        # PR #49 round 4 repin: the wire shape grew the
                        # reviewThreads comment window (thread
                        # 3867757439) beside requestedReviewer on
                        # request events (thread 3867757442).
                        "reviewThreads": {"nodes": []},
                    }
                }
            }
        }
        return subprocess.CompletedProcess([], 0, stdout=json.dumps(body), stderr="")

    def test_prefers_pushed_date(self):
        # Given: pushedDate 13:00 beside an older committedDate 09:00
        # (a rebase carries old committer dates) and no round markers.
        # When: read. Then: the PUSH date and no marker — the
        # round-start facts.
        proc = self.graphql_proc("2026-08-26T13:00:00Z")
        # PR #49 round 7 repin: round_bounds moved to
        # pr_guard_reaction_probe — the subprocess seam follows it.
        with mock.patch.object(pr_guard_reaction_probe.subprocess, "run", return_value=proc):
            self.assertEqual(
                pr_guard_reaction.round_bounds(48),
                (HEAD_OID, "2026-08-26T13:00:00Z", "", ""),
            )

    def test_falls_back_to_committed_date(self):
        # Given: no pushedDate on the head commit (live-verified on
        # PR #49: pushedDate reads null there). When: read.
        # Then: committedDate — the fallback discriminator.
        proc = self.graphql_proc(None)
        with mock.patch.object(pr_guard_reaction_probe.subprocess, "run", return_value=proc):
            self.assertEqual(
                pr_guard_reaction.round_bounds(48),
                (HEAD_OID, "2026-08-26T09:00:00Z", "", ""),
            )

    def test_failures_return_empty_pair(self):
        # Given: a nonzero rc, garbage JSON, or a missing pullRequest
        # node. When: read. Then: ('', '') — the conservative stale
        # inputs, never facts a THUMBS_UP could be proven newer than.
        cases = (
            subprocess.CompletedProcess([], 1, stdout="", stderr="boom"),
            subprocess.CompletedProcess([], 0, stdout="<html>", stderr=""),
            subprocess.CompletedProcess(
                [], 0, stdout='{"data":{"repository":{"pullRequest":null}}}', stderr=""
            ),
        )
        for proc in cases:
            with self.subTest(stdout=proc.stdout[:12]):
                with mock.patch.object(
                    pr_guard_reaction_probe.subprocess, "run", return_value=proc
                ):
                    self.assertEqual(
                        pr_guard_reaction.round_bounds(48), ("", "", "", "")
                    )


if __name__ == "__main__":
    unittest.main()
