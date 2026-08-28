"""pr_guard reaction round-18 tests — the WAIT half (PR #49 threads
3871485035 P1 / 3871485043 P2 / 3871485055 P1).

(1) 3871485035 — "Recheck the head after reading review evidence":
the round-17 head-bound completion check read its evidence through a
SEPARATE latest_review_commit subprocess dispatched AFTER the
reading's stable-head bracket, so a head that moved between the
bracket and that lookup left the comparison running against a STALE
observed_head — the unbracketed later read could still return the
prior head's review and exit 0 on its +1. Round 18 FOLDS the read
into the existing ROUND_QUERY (the vetted preferred fix: one
subprocess, one stable-head bracket — the round-10 bracket discipline
covers the evidence for free): the reading's eighth element carries
the bracket-certified review oid, the wait's completion check
consumes IT (never a second lookup — the not-called pin below), and a
mid-sequence head move discards the evidence WITH the probe (probe
unreadable) while an oid mismatch withholds. The proof below stages
the pre-fix race exactly: the separate-seam scripted to return the
observed head (the value the unbracketed window could still read)
while the probe's OWN folded snapshot carries a DIFFERENT review —
the pre-fix wait trusted the later unbracketed read and printed WAIT
DONE; round 18 trusts only the bracket-certified one and holds.

(2) 3871485043 — "Paginate the bot review lookup": the old
latestReviews(last:10) window omitted the connector's review whenever
ten other reviewers' latest reviews sorted after it, so every
otherwise-valid post-move completion was held to timeout (the empty
oid withholds). Live-verified read-only on PR #49 (2026-08-27): the
reviews(author:...) connection argument filters SERVER-SIDE — so the
folded connection is the author-filtered botReviews (last:1) and the
window cannot evict the bot at all; the wait-level proof feeds ten
human latestReviews (the evicted marker window) beside the filtered
botReviews carrying the bot's review, and the completion EXITS.

(3) 3871485055 — "Retain each same-second boundary identity": the
round-17 merged boundary (latest_boundary max) collapses a formal
request and a trigger comment created in the same timestamp second —
when the retained boundary holds the LARGER identity string, a
genuinely-later boundary of the OTHER kind never advances the single
high-water, so the preceding round's armed EYES and delayed +1 still
print WAIT DONE before the new round starts. Round 18 splits the
retention by KIND: the formal-request and trigger-comment high-waters
advance INDEPENDENTLY (each with the round-17 createdAt + node-id
distinctness), the reset + gate re-close fire when EITHER advances,
and the merged identity survives for CLASSIFICATION only (the EYES
binding still consumes max(formal createdAt, trigger createdAt)).

No network: gh_reactions/head_ref_oid/latest_review_commit are
patched at the reaction seams; round_bounds runs REAL over scripted
ROUND_QUERY pages (the round-15/17 run_wait_real_bounds shape — the
folded evidence and the per-kind identities must ride the REAL
probe). FakeClock WALL_NOW 2023-11-14T22:13:20Z; the head-move
fixtures key off the t=5 floor 2023-11-14T22:13:25Z (the round-13/14
rule).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round18_test -v
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

HEAD_A = "5c533c3a9b2c8c00eb1d47cb072d24a0975b14f1"
HEAD_B = "14ab97fffffffffffffffffffffffffffffff"
HEAD_C = "ba0f1c3ffffffffffffffffffffffffffffff"

SECOND = "2026-08-01T00:05:00Z"
REQ_ID = f"{SECOND}|Zm9v"
TRG_ID = f"{SECOND}|IC_2"


def react(content, created="2026-08-26T12:31:00Z", rid=None):
    return {
        "content": content,
        "created_at": created,
        "id": rid,
        "user": {"login": BOT},
    }


def gh_page(payload):
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(payload)
    )


def req_node(created, node_id):
    return {
        "createdAt": created,
        "id": node_id,
        "requestedReviewer": {"login": pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN},
    }


def trigger_node(created, node_id):
    return {"createdAt": created, "id": node_id, "body": "@codex review"}


def human_review(at):
    return {"author": {"login": "some-human"}, "submittedAt": at}


def bot_review(oid, at="2024-03-15T00:00:00Z"):
    # Round 20 (thread 3872194023): the node carries submittedAt —
    # the VERDICT STAMP the completion guards bind to. The default
    # sits between the post-move fixtures' EYES (2024-03-01) and +1
    # (2024-04-01), past the 2023 wall floor (the seam precedent —
    # assertions byte-identical).
    return {
        "author": {"login": pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN},
        "commit": {"oid": oid},
        "submittedAt": at,
    }


def bounds_page(
    pushed,
    oid=HEAD_B,
    request=(),
    trigger=None,
    bot_reviews=None,
    humans=0,
):
    """A well-formed ROUND_QUERY page. bot_reviews=None keeps the
    botReviews key ABSENT (the legacy minimal-payload shape — no
    evidence carried); a list stages the author-filtered connection.
    The trigger key follows the same absent/present rule (round 17)."""
    page = {
        "data": {
            "repository": {
                "pullRequest": {
                    "headRefOid": oid,
                    "headRef": {
                        "target": {"pushedDate": pushed, "committedDate": pushed}
                    },
                    "timelineItems": {
                        "pageInfo": {"hasPreviousPage": False, "startCursor": None},
                        "nodes": list(request),
                    },
                    "headTransition": {"nodes": []},
                    "latestReviews": {
                        "nodes": [human_review(f"2026-07-{n:02d}T00:00:00Z") for n in range(1, humans + 1)]
                    },
                    "reviewThreads": {"nodes": []},
                }
            }
        }
    }
    if trigger is not None:
        page["data"]["repository"]["pullRequest"]["triggerComments"] = {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": list(trigger),
        }
    if bot_reviews is not None:
        page["data"]["repository"]["pullRequest"]["botReviews"] = {
            "nodes": list(bot_reviews)
        }
    return page


def run_wait(reads, pages, heads, timeout_secs, separate_review=""):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    pages (the run_wait_real_bounds shape) plus a per-probe head
    sequence. separate_review scripts the PRE-ROUND-18 separate
    latest_review_commit lookup — the pre-fix wait consumes it (the
    proof); the post-fix wait never calls it (the mock is returned for
    the not-called pin)."""
    clock = FakeClock()
    items = iter(reads)
    script = iter(pages)
    head_seq = iter(heads)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_read
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", side_effect=lambda pr, timeout_secs=None: next(head_seq)
    ), mock.patch.object(
        pr_guard_reaction_probe.subprocess,
        "run",
        side_effect=lambda *a, **k: gh_page(next(script)),
    ), mock.patch.object(
        pr_guard_reaction, "latest_review_commit", return_value=separate_review
    ) as review_mock, mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue(), review_mock


def post_move_pages(review_oid, humans=0):
    """The 3871485035/43 fixture spine: head A at t=0, the move to
    head B (pushed 2021 — an already-pushed commit) at t=5, the
    post-floor EYES at t=10, the accepting +1 at t=15; the folded
    botReviews carry review(review_oid) from t=5 on."""
    return [
        bounds_page("2026-08-01T00:00:00Z", oid=HEAD_A),
        bounds_page("2021-01-01T00:00:00Z", oid=HEAD_B, bot_reviews=[bot_review(review_oid)], humans=humans),
        bounds_page("2021-01-01T00:00:00Z", oid=HEAD_B, bot_reviews=[bot_review(review_oid)], humans=humans),
        bounds_page("2021-01-01T00:00:00Z", oid=HEAD_B, bot_reviews=[bot_review(review_oid)], humans=humans),
    ]


POST_MOVE_READS = [
    [],
    [],
    [react("eyes", created="2024-03-01T00:00:00Z", rid=5)],
    [react("+1", created="2024-04-01T00:00:00Z", rid=6)],
]
POST_MOVE_HEADS = [HEAD_A, HEAD_B, HEAD_B, HEAD_B]


class BracketedEvidenceTests(unittest.TestCase):
    def test_folded_evidence_beats_the_separate_lookup(self):
        # Given: the thread-3871485035 race — the accepting probe's
        # stable-head bracket certifies head B while its OWN folded
        # snapshot carries the bot's latest review as review(A) (head
        # A's pre-move round; B reviewed by nobody), and the PRE-FIX
        # separate lookup — dispatched after the bracket — reads the
        # observed head's oid (exactly the stale value the unbracketed
        # window could still return). When: wait polls 15s. Then: exit
        # 1 — round 18 trusts only the bracket-certified evidence
        # (review(A) != B), the separate seam is NEVER CALLED (the
        # not-called pin), and the +1 HOLDs to timeout; the pre-fix
        # wait compared the unbracketed read (B) against the equally
        # stale observed_head (B) and printed WAIT DONE at 15s with
        # head B reviewed by nobody.
        code, out, review_mock = run_wait(
            POST_MOVE_READS,
            post_move_pages(HEAD_A),
            POST_MOVE_HEADS,
            15,
            separate_review=HEAD_B,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("HEAD MOVED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 15s elapsed", out)
        review_mock.assert_not_called()

    def test_mid_sequence_move_discards_the_evidence_with_the_probe(self):
        # Given: the head moves INSIDE the accepting probe's sequence
        # — the before-side head read still returns B while the round
        # query reads C, so the bracket itself breaks AFTER the +1 and
        # its folded evidence exist. When: wait polls 15s. Then: exit 1
        # — the mismatched bracket discards the WHOLE probe (round 10
        # ReactionHeadMoved -> UNREADABLE; the evidence dies with it),
        # the next probe re-observes head C and its accepting +1 is
        # held by the folded mismatch, never exit 0 on B's +1 (the
        # "withheld (probe unreadable)" arm of the round-18 rule).
        pages = [
            bounds_page("2026-08-01T00:00:00Z", oid=HEAD_A),
            bounds_page("2021-01-01T00:00:00Z", oid=HEAD_B, bot_reviews=[bot_review(HEAD_B)]),
            bounds_page("2021-01-01T00:00:00Z", oid=HEAD_B, bot_reviews=[bot_review(HEAD_B)]),
            bounds_page("2021-01-01T00:00:00Z", oid=HEAD_C, bot_reviews=[bot_review(HEAD_B)]),
        ]
        code, out, _ = run_wait(POST_MOVE_READS, pages, POST_MOVE_HEADS, 15)
        self.assertEqual(code, 1)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 15s elapsed", out)

    def test_ten_later_human_reviews_do_not_hold_a_valid_completion(self):
        # Given: the thread-3871485043 eviction — ten other reviewers'
        # latest reviews fill the old latestReviews(last:10) marker
        # window (the connector's review pushed out of it) while the
        # FOLDED author-filtered botReviews connection still carries
        # the bot's review of head B (live-verified 2026-08-27: the
        # reviews(author:...) argument filters server-side, so no
        # fixed window can evict the bot). When: wait polls. Then:
        # exit 0 — the completion carries its head-bound evidence and
        # exits; the pre-fix wait's separate 10-review lookup read ''
        # (the finding's shape) and held this exact completion to
        # timeout.
        code, out, _ = run_wait(
            POST_MOVE_READS,
            post_move_pages(HEAD_B, humans=10),
            POST_MOVE_HEADS,
            15,
            separate_review="",
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 15s", out)


class PerKindBoundaryTests(unittest.TestCase):
    def test_same_second_trigger_advances_its_own_stream(self):
        # Given: the thread-3871485055 race — the t=0 page carries the
        # formal request (node Zm9v, the LARGER same-second identity)
        # and the round's verified EYES (2026-08-02) arms; at t=5 a
        # trigger comment lands inside the SAME timestamp second with
        # the SMALLER node id (IC_2) while the old job sits in its
        # EYES-removal/+1 switch (the probe reads NONE); the preceding
        # job's delayed +1 (2026-08-26T14) lands at t=10. When: wait
        # polls 12s. Then: exit 1 — the TRIGGER stream advances on its
        # own (IC_2 is a first-ever trigger boundary), the reset +
        # gate re-close run, the NONE never re-arms, and the delayed
        # +1 only HOLDs; the pre-fix single merged high-water stayed
        # at max("…|Zm9v", "…|IC_2") = "…|Zm9v" across both probes, so
        # no advance fired and the wait printed WAIT DONE at t=10
        # before the triggered round started.
        code, out, _ = run_wait(
            [
                [react("eyes", created="2026-08-02T00:00:00Z", rid=5)],
                [],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
            ],
            [
                bounds_page("2026-08-01T00:00:00Z", request=[req_node(SECOND, "Zm9v")]),
                bounds_page("2026-08-01T00:00:00Z", request=[req_node(SECOND, "Zm9v")], trigger=[trigger_node(SECOND, "IC_2")]),
                bounds_page("2026-08-01T00:00:00Z", request=[req_node(SECOND, "Zm9v")], trigger=[trigger_node(SECOND, "IC_2")]),
                bounds_page("2026-08-01T00:00:00Z", request=[req_node(SECOND, "Zm9v")], trigger=[trigger_node(SECOND, "IC_2")]),
            ],
            [HEAD_B] * 4,
            12,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_same_second_request_advances_despite_standing_trigger(self):
        # Given: the mirror survivor — a standing trigger holds the
        # LARGER same-second identity (IC_9) while a formal request of
        # the SAME second (node Zm9v) appears at t=5, and the old
        # job's delayed +1 lands at t=10. When: wait polls 12s. Then:
        # exit 1 — the REQUEST stream advances on its own and the
        # reset + re-close hold the +1 to timeout; this direction the
        # pre-fix max() also caught (Zm9v > IC_9), so it pins that the
        # per-kind split loses NO advance the merged stream ever saw.
        code, out, _ = run_wait(
            [
                [react("eyes", created="2026-08-02T00:00:00Z", rid=5)],
                [],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
            ],
            [
                bounds_page("2026-08-01T00:00:00Z", trigger=[trigger_node(SECOND, "IC_9")]),
                bounds_page("2026-08-01T00:00:00Z", request=[req_node(SECOND, "Zm9v")], trigger=[trigger_node(SECOND, "IC_9")]),
                bounds_page("2026-08-01T00:00:00Z", request=[req_node(SECOND, "Zm9v")], trigger=[trigger_node(SECOND, "IC_9")]),
                bounds_page("2026-08-01T00:00:00Z", request=[req_node(SECOND, "Zm9v")], trigger=[trigger_node(SECOND, "IC_9")]),
            ],
            [HEAD_B] * 4,
            12,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_same_second_pair_stales_the_preceding_eyes(self):
        # Given: the classification composition — an EYES created
        # BEFORE the shared second (2026-08-01T00:01) under a page
        # carrying BOTH kinds at that second (request Zm9v + trigger
        # IC_2), so the merged classification boundary (max of the two
        # createdAt halves, round 17's latest_boundary) postdates it.
        # When: the reading classifies. Then: EYES_STALE — the EYES
        # binding still consumes the merged boundary timestamp (the
        # round-13 binding backstop preserved through the per-kind
        # split), so a pre-boundary EYES of EITHER preceding round
        # arms nothing; the two kinds ride the reading as SEPARATE
        # identities (the retention split, 3871485055).
        clock = FakeClock()
        page = bounds_page(
            "2026-08-01T00:00:00Z",
            request=[req_node(SECOND, "Zm9v")],
            trigger=[trigger_node(SECOND, "IC_2")],
        )
        with mock.patch.object(
            pr_guard_reaction, "gh_reactions", return_value=[react("eyes", created="2026-08-01T00:01:00Z", rid=3)]
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=HEAD_B
        ), mock.patch.object(
            pr_guard_reaction_probe.subprocess, "run", return_value=gh_page(page)
        ), mock.patch.object(
            pr_guard_reaction, "time", clock
        ):
            reading = pr_guard_reaction.bot_reaction_reading(48)
        self.assertEqual(reading[0], pr_guard_reaction.REACTION_EYES_STALE)
        self.assertEqual(reading[5], REQ_ID)
        self.assertEqual(reading[6], TRG_ID)


if __name__ == "__main__":
    unittest.main()
