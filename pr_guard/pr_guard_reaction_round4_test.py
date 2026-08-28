"""pr_guard reaction round-4 tests (PR #49 threads 3867757439/42/45).

Thread 3867757439 (P1): a request-less bot round that has BEGUN
POSTING must not read as done — the round-engagement marker set
gains the bot's latest review-THREAD comment (the bot posts its
round's findings as thread comments, live-verified on PR #49), so
the prior round's +1 predating that comment reads THUMBS_UP_STALE
mid-round and the wait keeps polling.

Thread 3867757442 (P2): only ReviewRequestedEvents whose
requestedReviewer IS the codex bot bind the round — a human or
another bot requested after the +1 extends nothing (no
stale-forever wait).

Thread 3867757445 (P2): gh_reactions STOPS walking once the shared
deadline expires — never a fresh per-page grant through the 1s
floor. Round 5 (thread 3867897764, P2) tightened the stopped walk:
it RAISES ReactionWalkExpired (the partial list is UNREADABLE, never
a latest-wins input) — see pr_guard_reaction_round5_test.

The round-4 gate companion (thread 3867757449, the banner's place
in surveys) lives in pr_guard_reaction_round4_gate_test.

No network: round_bounds is patched at its seam for the round/wait
tests; the probe tests patch the subprocess seam; the pagination
tests patch it too (a real sleep burns the budget). Reaction
payloads use the REST WIRE vocabulary (+1/eyes).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round4_test -v
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
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock

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


# The P1 shape: head pushed 11:00, the prior round's submission 11:30
# and pass 12:00, and the NEW request-less round's first thread
# comment at 13:05 — mid-round, the comment is the round's start.
# PR #49 round 8 repin (thread 3868443452): round_bounds grew a
# head-first headRefOid element (the probe payload's own oid) — one
# stable head throughout, so the wait's head-change reset never
# fires in this suite.
HEAD_OID = "cad8c064c5b1462e4d74866ddfcb76be700366a4"
MIDROUND_COMMENT_BOUNDS = (HEAD_OID, "2026-08-26T11:00:00Z", "", "2026-08-26T13:05:00Z")


class CommentBoundTests(unittest.TestCase):
    def test_thread_comment_after_the_pass_is_stale(self):
        # Given: no head change, no formal request, no new submission
        # — but the bot's round-4 thread comment (13:05) postdates the
        # prior +1 (12:00): the new round has BEGUN POSTING. When:
        # read. Then: THUMBS_UP_STALE — the prior pass never answers a
        # round whose own comments postdate it (thread 3867757439's
        # request-less mid-round shape).
        self.assertEqual(
            read(
                [react("+1", created="2026-08-26T12:00:00Z")],
                MIDROUND_COMMENT_BOUNDS,
            ),
            "THUMBS_UP_STALE",
        )

    def test_pass_after_the_thread_comment_is_done(self):
        # Given: the same round, its +1 at 14:00 — postdating the head
        # push AND the bot's own latest thread comment. When: read.
        # Then: THUMBS_UP — the pass is the round's POST-comment
        # verdict, exactly the postdate rule widened to comments.
        self.assertEqual(
            read(
                [react("+1", created="2026-08-26T14:00:00Z")],
                MIDROUND_COMMENT_BOUNDS,
            ),
            "THUMBS_UP",
        )

    def test_wait_polls_past_a_midround_comment_to_timeout(self):
        # Given: the mid-round comment stands for the whole 12s window
        # (the new round never signals). When: wait polls. Then: exit
        # 1 — the prior pass reads stale, never done mid-round.
        code, out = run_wait(
            [[react("+1", created="2026-08-26T12:00:00Z")]] * 4,
            12,
            MIDROUND_COMMENT_BOUNDS,
        )
        self.assertEqual(code, 1)
        self.assertIn("THUMBS_UP (stale — predates the current round's start", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)


class RoundBoundsMarkerTests(unittest.TestCase):
    def probe(self, pushed, request_events=(), reviews=(), threads=()):
        body = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "headRefOid": "cad8c064c5b1462e4d74866ddfcb76be700366a4",
                        "headRef": {"target": {"pushedDate": pushed}},
                        "timelineItems": {"nodes": list(request_events)},
                        "latestReviews": {"nodes": list(reviews)},
                        "reviewThreads": {"nodes": list(threads)},
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

    def thread_comments(self, *pairs):
        return {
            "comments": {
                "nodes": [
                    {"author": {"login": login}, "createdAt": at}
                    for login, at in pairs
                ]
            }
        }

    def test_bot_thread_comment_binds_the_round(self):
        # Given: head 11:00, the prior submission 11:30, and the new
        # round's bot thread comment 13:05 (a HUMAN reply at 13:06
        # beside it in the same thread's window). When: the probe
        # reads. Then: the newest BOT marker (13:05) is the round's
        # request fact — the comment marks the request-less round.
        self.assertEqual(
            self.probe(
                "2026-08-26T11:00:00Z",
                reviews=[self.review(BOT, "2026-08-26T11:30:00Z")],
                threads=[
                    self.thread_comments(
                        (BOT, "2026-08-26T13:05:00Z"),
                        ("octocat", "2026-08-26T13:06:00Z"),
                    )
                ],
            ),
            (HEAD_OID, "2026-08-26T11:00:00Z", "", "2026-08-26T13:05:00Z"),
        )

    def test_human_thread_comments_do_not_bind(self):
        # Given: threads carrying ONLY human comments (13:00, newest).
        # When: the probe reads. Then: no marker — a human's comment
        # never gates the bot's verdict; the head push alone binds.
        self.assertEqual(
            self.probe(
                "2026-08-26T11:00:00Z",
                threads=[self.thread_comments(("octocat", "2026-08-26T13:00:00Z"))],
            ),
            (HEAD_OID, "2026-08-26T11:00:00Z", "", ""),
        )

    def test_request_events_combine_with_comments(self):
        # Given: a codex re-request 13:00, the bot submission 11:30,
        # and the bot's thread comment 13:05. When: the probe reads.
        # Then: every marker combines and the NEWEST (13:05) binds —
        # whichever way the round engaged.
        self.assertEqual(
            self.probe(
                "2026-08-26T11:00:00Z",
                request_events=[
                    {
                        "createdAt": "2026-08-26T13:00:00Z",
                        "requestedReviewer": {"login": BOT},
                    }
                ],
                reviews=[self.review(BOT, "2026-08-26T11:30:00Z")],
                threads=[self.thread_comments((BOT, "2026-08-26T13:05:00Z"))],
            ),
            (
                HEAD_OID,
                "2026-08-26T11:00:00Z",
                "2026-08-26T13:00:00Z",
                "2026-08-26T13:05:00Z",
            ),
        )

    def test_human_request_after_codex_pass_is_ignored(self):
        # Given: the codex request at 10:00 and a HUMAN requested at
        # 13:00 — after the +1 (12:00). When: the probe reads. Then:
        # the marker is the CODEX request (10:00), never the human's
        # 13:00 — an unrelated request cannot stretch the round into a
        # stale-forever wait (thread 3867757442's exact scenario).
        self.assertEqual(
            self.probe(
                "2026-08-26T11:00:00Z",
                request_events=[
                    {
                        "createdAt": "2026-08-26T10:00:00Z",
                        "requestedReviewer": {"login": BOT},
                    },
                    {
                        "createdAt": "2026-08-26T13:00:00Z",
                        "requestedReviewer": {"login": "octocat"},
                    },
                ],
            ),
            (
                HEAD_OID,
                "2026-08-26T11:00:00Z",
                "2026-08-26T10:00:00Z",
                "2026-08-26T10:00:00Z",
            ),
        )

    def test_other_bot_requests_do_not_bind(self):
        # Given: only ANOTHER bot's request (13:00, suffix-less
        # GraphQL login render). When: the probe reads. Then: no
        # marker — a different bot's request extends nothing.
        self.assertEqual(
            self.probe(
                "2026-08-26T11:00:00Z",
                request_events=[
                    {
                        "createdAt": "2026-08-26T13:00:00Z",
                        "requestedReviewer": {"login": "some-other-bot"},
                    }
                ],
            ),
            (HEAD_OID, "2026-08-26T11:00:00Z", "", ""),
        )

    def test_team_request_without_login_is_ignored(self):
        # Given: a TEAM requested at 13:00 — the union renders no
        # User/Bot login for a Team subject. When: the probe reads.
        # Then: no marker — only the codex bot's own requests bind.
        self.assertEqual(
            self.probe(
                "2026-08-26T11:00:00Z",
                request_events=[
                    {
                        "createdAt": "2026-08-26T13:00:00Z",
                        "requestedReviewer": {"__typename": "Team"},
                    }
                ],
            ),
            (HEAD_OID, "2026-08-26T11:00:00Z", "", ""),
        )


class PaginationDeadlineTests(unittest.TestCase):
    def test_expired_deadline_stops_the_walk_unreadable(self):
        # Given: a 0.05s walk budget whose full page-1 fetch (100
        # reactions) burns 0.06s — the page finishes AFTER the probe
        # deadline. When: gh_reactions walks. Then: page 2 is NEVER
        # fetched (no fresh 1s floor grant per page) and the stopped
        # walk RAISES ReactionWalkExpired — round 4 returned the
        # partial list here; round 5 (thread 3867897764) makes the
        # incomplete read UNREADABLE so latest-wins selection never
        # sees it (the round-5 suite proves the callers' arms).
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(" ".join(argv))
            if len(calls) == 1:
                time.sleep(0.06)
                return subprocess.CompletedProcess(
                    [], 0, stdout=json.dumps([react("heart", login="h")] * 100),
                    stderr="",
                )
            raise AssertionError("page 2 must never be fetched")

        with mock.patch.object(
            pr_guard_reaction.subprocess, "run", side_effect=fake_run
        ):
            with self.assertRaises(pr_guard_reaction.ReactionWalkExpired) as raised:
                pr_guard_reaction.gh_reactions(48, timeout_secs=0.05)
        self.assertEqual(len(calls), 1)
        self.assertIn("thread 3867897764", str(raised.exception))
        self.assertIn("100 reaction(s) read", str(raised.exception))

    def test_unexpired_deadline_still_paginates(self):
        # Given: a full page-1 under a healthy budget. When: the walk
        # continues. Then: page 2 IS fetched — the deadline stop only
        # fires on EXPIRY, never as an early cut. (PR #49 round 24
        # fixture-seam maintenance, thread 3873592851: the two-page
        # walk RE-READS page 1 after the short page — the appended
        # identical full page answers it; the combined assertion is
        # unchanged. PR #49 round 33 seam maintenance, thread
        # 3876172349: the walk also RE-READS the terminal short page
        # after the full-page recheck — the appended identical eyes
        # page answers it.)
        full = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps([react("heart", login="h")] * 100), stderr=""
        )
        short = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps([react("eyes")]), stderr=""
        )
        pages = [full, short, full, short]
        with mock.patch.object(
            pr_guard_reaction.subprocess, "run", side_effect=pages
        ):
            combined = pr_guard_reaction.gh_reactions(48, timeout_secs=2.5)
        self.assertEqual(len(combined), 101)


if __name__ == "__main__":
    unittest.main()
