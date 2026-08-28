"""pr_guard reaction round-3 tests (PR #49 threads 3867653639/3867653642).

Thread 3867653639 (P1): bind completion to the ACTUAL requested round
— a re-requested review WITHOUT a head change leaves the prior +1
postdating the head push, so the head date alone exits the waiter
while the new round is still pending. A THUMBS_UP now counts DONE
only when it postdates BOTH round-start facts (round_bounds): the
head push AND the latest round-engagement marker — the timeline
ReviewRequestedEvent's createdAt (a formal (re-)request; shape
positively live-verified on microsoft/vscode#101656) beside the
bot's latest SUBMITTED review (latestReviews submittedAt — this
repo's PRs carry ZERO request events, REST- and GraphQL-agreed, so
the bot's own submission is the same-head round marker that exists;
the +1 is the bot's POST-review verdict). Otherwise STALE; an
unreadable probe is conservative STALE, never done-on-ambiguity.

Thread 3867653642 (P2): the survey banner's informational read is
bounded by BANNER_TIMEOUT_SECS — a stalled gh api raises
TimeoutExpired into the banner's EXISTING fail-open path (UNREADABLE,
survey continues on thread state) instead of hanging survey — and
with it pre-merge and the post-merge quiet watch — indefinitely.

No network: round_bounds is patched at its seam for the round/wait
tests; the probe tests patch the subprocess seam. The wait loop runs
on the shared FakeClock (thread 3832522300's fake clock). Reaction
payloads use the REST WIRE vocabulary (+1/eyes).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round3_test -v
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
from . import pr_guard_threads
from .pr_guard_merge_fixtures import FakeClock, thread
BOT = pr_guard_reaction.REACTION_BOT


def react(content, login=BOT, created="2026-08-26T12:00:00Z"):
    return {"content": content, "created_at": created, "user": {"login": login}}


def run_wait(reads, timeout_secs, bounds):
    """wait_reaction on the FakeClock; returns (code, output)."""
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
    return code, out.getvalue()


def read(reactions, bounds):
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", return_value=reactions
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", return_value=bounds
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
    ):
        return pr_guard_reaction.bot_review_reaction(48)


# The P1 shape: head pushed 11:00, the prior round's +1 at 12:00, the
# review RE-REQUESTED at 13:00 with NO head change after it.
# PR #49 round 8 repin (thread 3868443452): round_bounds grew a
# head-first headRefOid element (the probe payload's own oid here)
# — one stable head throughout, so the wait's head-change reset
# never fires in this suite.
HEAD_OID = "31ae10e9e5f4189ac89d832f9d2663f311130ee6"
REREQUEST_BOUNDS = (HEAD_OID, "2026-08-26T11:00:00Z", "2026-08-26T13:00:00Z", "2026-08-26T13:00:00Z")


class RoundBindingTests(unittest.TestCase):
    def test_rerequest_after_thumbs_up_keeps_polling_to_timeout(self):
        # Given: the prior round's +1 (12:00) postdates the head push
        # (11:00) but the review was RE-REQUESTED at 13:00 with no
        # head change — the new round never signals inside the window.
        # When: wait polls 12s. Then: exit 1 — the stale pass is not
        # done; the output carries the stale explanation and the
        # timeout banner (thread 3867653639's exact scenario).
        code, out = run_wait(
            [[react("+1", created="2026-08-26T12:00:00Z")]] * 4, 12, REREQUEST_BOUNDS
        )
        self.assertEqual(code, 1)
        self.assertIn("THUMBS_UP (stale — predates the current round's start", out)
        self.assertIn("waiting for the new round's signal", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_thumbs_up_after_the_rerequest_exits_zero(self):
        # Given: the same re-request (13:00), and the NEW round's +1
        # at 14:00 — postdating BOTH round-start facts. When: wait
        # polls. Then: exit 0 — the pass answers the requested round.
        # (Thread 3867897766, round 5: the first probe reads the
        # round's PRIOR +1 (12:00, stale against the 13:00 request) —
        # the confirmed non-DONE reading — and the 14:00 pass that
        # lands next probe is the observed away-and-back, the only
        # shape an accepted THUMBS_UP has anymore.)
        # (PR #49 round 25 fixture-seam maintenance, thread
        # 3873970933: the completing round carries the folded review
        # evidence naming the stable head — the +1 is a POST-review
        # verdict and cold-start completions require it now; the
        # bounds tuple itself is unchanged.)
        bounds = pr_guard_reaction_probe.RoundBounds(REREQUEST_BOUNDS)
        bounds.review_head = HEAD_OID
        bounds.review_stamp = "2026-08-26T13:30:00Z"
        code, out = run_wait(
            [
                [react("+1", created="2026-08-26T12:00:00Z")],
                [react("+1", created="2026-08-26T14:00:00Z")],
            ],
            12,
            bounds,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)

    def test_same_head_new_bot_review_round_is_stale(self):
        # Given: no head change and no formal request — the bot
        # SUBMITTED a new round's review at 13:00 (the marker this
        # repo's request-less rounds leave) while the prior +1 stands
        # at 12:00. When: read. Then: THUMBS_UP_STALE — the +1 is the
        # bot's POST-review verdict, so it must postdate its own
        # latest submission (the reviewer's same-head two-rounds gap).
        self.assertEqual(
            read(
                [react("+1", created="2026-08-26T12:00:00Z")],
                (HEAD_OID, "2026-08-26T11:00:00Z", "2026-08-26T13:00:00Z", "2026-08-26T13:00:00Z"),
            ),
            "THUMBS_UP_STALE",
        )

    def test_pass_after_bot_submission_is_done(self):
        # Given: the real-workflow shape (PR #48 live: submission
        # 11:30, pass 12:00, head 11:00) — the +1 postdates the bot's
        # submission and the head push. When: read. Then: THUMBS_UP.
        self.assertEqual(
            read(
                [react("+1", created="2026-08-26T12:00:00Z")],
                (HEAD_OID, "2026-08-26T11:00:00Z", "", "2026-08-26T11:30:00Z"),
            ),
            "THUMBS_UP",
        )


class RoundBoundsProbeTests(unittest.TestCase):
    def probe(self, pushed, request_events=(), reviews=()):
        # PR #49 round 4 repin: the wire shape grew requestedReviewer
        # on request events (the CODEX filter, thread 3867757442 —
        # the round-3 fixtures meant CODEX re-requests) and the
        # reviewThreads comment window (thread 3867757439).
        body = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "headRefOid": "31ae10e9e5f4189ac89d832f9d2663f311130ee6",
                        "headRef": {"target": {"pushedDate": pushed}},
                        "timelineItems": {
                            "nodes": [
                                {"createdAt": at, "requestedReviewer": {"login": BOT}}
                                for at in request_events
                            ]
                        },
                        "latestReviews": {"nodes": list(reviews)},
                        "reviewThreads": {"nodes": []},
                    }
                }
            }
        }
        proc = subprocess.CompletedProcess([], 0, stdout=json.dumps(body), stderr="")
        # PR #49 round 7 repin: round_bounds moved to
        # pr_guard_reaction_probe (the 250 pure-LOC split) — the
        # subprocess seam follows the probe's new home.
        with mock.patch.object(pr_guard_reaction_probe.subprocess, "run", return_value=proc):
            return pr_guard_reaction.round_bounds(48)

    def review(self, login, submitted):
        return {"author": {"login": login}, "submittedAt": submitted}

    def test_request_event_and_bot_submission_both_bind(self):
        # Given: a formal re-request at 13:00 beside the bot's earlier
        # submission at 11:30 (head 11:00). When: the round probe
        # reads. Then: both markers combine and the NEWEST (the
        # re-request, 13:00) is the round's request fact — whichever
        # way the round was engaged, the latest marker binds.
        self.assertEqual(
            self.probe(
                "2026-08-26T11:00:00Z",
                request_events=["2026-08-26T13:00:00Z"],
                reviews=[self.review(BOT, "2026-08-26T11:30:00Z")],
            ),
            (HEAD_OID, "2026-08-26T11:00:00Z", "2026-08-26T13:00:00Z", "2026-08-26T13:00:00Z"),
        )

    def test_bot_login_without_suffix_maps(self):
        # Given: GraphQL renders the bot's author login WITHOUT the
        # "[bot]" suffix (live-verified 2026-08-27) — its submission
        # at 11:30 beside no request events. When: read. Then: the
        # suffix-less login still counts — the submission is the
        # marker (the request-less repo's round fact).
        self.assertEqual(
            self.probe(
                "2026-08-26T11:00:00Z",
                reviews=[self.review("chatgpt-codex-connector", "2026-08-26T11:30:00Z")],
            ),
            (HEAD_OID, "2026-08-26T11:00:00Z", "", "2026-08-26T11:30:00Z"),
        )

    def test_human_reviews_are_not_round_markers(self):
        # Given: only HUMANS submitted reviews (13:00, newest) — no
        # request events, no bot submission. When: read. Then: no
        # marker ('') — a human's review never gates the bot's
        # verdict; the head push alone carries the binding (the
        # round-1 semantics, exactly the PR #48 no-request norm).
        self.assertEqual(
            self.probe(
                "2026-08-26T11:00:00Z",
                reviews=[
                    self.review("RachaelsDen", "2026-08-26T12:00:00Z"),
                    self.review("octocat", "2026-08-26T13:00:00Z"),
                ],
            ),
            (HEAD_OID, "2026-08-26T11:00:00Z", "", ""),
        )


class BannerBoundedReadTests(unittest.TestCase):
    def stalled_run(self, calls):
        def fake_run(argv, **kwargs):
            calls.append(kwargs.get("timeout"))
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout"))

        return fake_run

    def test_banner_read_carries_the_bounded_cap(self):
        # Given: the banner's gh read (informational, not
        # deadline-driven). When: it dispatches. Then: the subprocess
        # grant is BOUNDED — never the unbounded None that let a stall
        # hang survey — and no larger than BANNER_TIMEOUT_SECS
        # (thread 3867653642).
        calls = []
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_reaction.subprocess, "run", side_effect=self.stalled_run(calls)
        ), redirect_stdout(out):
            pr_guard_reaction_banner.reaction_banner(48, ["3867000001"])
        self.assertIsNotNone(calls[0])
        self.assertLessEqual(calls[0], pr_guard_reaction_banner.BANNER_TIMEOUT_SECS)

    def test_stalled_banner_read_fails_open(self):
        # Given: the banner's gh read stalls past its bounded grant
        # (TimeoutExpired). When: the banner renders. Then: the
        # EXISTING fail-open path finally runs — UNREADABLE prints
        # with the thread-as-authority boundary and the banner
        # RETURNS, so nothing downstream blocks.
        calls = []
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_reaction.subprocess, "run", side_effect=self.stalled_run(calls)
        ), redirect_stdout(out):
            state = pr_guard_reaction_banner.reaction_banner(48, ["3867000001"])
        self.assertEqual(state, "UNREADABLE")
        self.assertIn("BOT REACTION: UNREADABLE", out.getvalue())
        self.assertIn("threads 3867000001 are the authority", out.getvalue())

    def test_survey_completes_past_a_stalled_banner(self):
        # Given: a survey (the pre-merge and quiet-watch shared path)
        # whose banner read stalls. When: survey runs. Then: it
        # COMPLETES — the SUMMARY line prints beside the UNREADABLE
        # banner; the stall never hangs the gate (thread 3867653642).
        calls = []
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_threads,
            "fetch_threads",
            return_value=[thread("3867000001", "resolved")],
        ), mock.patch.object(
            pr_guard_reaction.subprocess, "run", side_effect=self.stalled_run(calls)
        ), redirect_stdout(out):
            pr_guard_threads.survey(48)
        text = out.getvalue()
        self.assertIn("SUMMARY pr=48 total=1", text)
        self.assertIn("BOT REACTION: UNREADABLE", text)


if __name__ == "__main__":
    unittest.main()
