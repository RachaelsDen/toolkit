"""pr_guard reaction round-32 probe tests (PR #49 threads 3876000990
P1 / 3876001004 P1): the pagination bracket's composite-marker and
head-transition bounds — the pair split's probe half (the wait half,
the cold-start FF floor, and the walk half, the terminal page
length, live in pr_guard_reaction_round32_test).

Thread 3876000990 — "Recheck bot markers after boundary
pagination": when a request/trigger lookup paginates, a request-less
follow-up can submit a bot review or add a review-thread comment
AFTER the original ROUND_QUERY but before its re-run — those fields
advance the COMPOSITE MARKER that makes the previously fetched +1
stale, yet the round-24/25 bracket checked only the request and
trigger connections, so the re-run's latestReviews/reviewThreads
drift went unseen: the waiter accepted the preceding round's +1 and
exited 0 after new findings had landed. `_bracket_unchanged` now
consumes the ORIGINAL query's composite marker (the reading's
`marker` element — the newest of the boundary createdAt and the
bot's latestReviews submittedAt / reviewThreads comment stamps) and
requires the re-run's engagement markers NOT to have advanced past
it: a newer marker means the original +1's staleness classification
is stale itself — unreadable bounds, retry next interval. The
strict-recheck doctrine (round 25) applies: the re-run is our own
assembled query, so latestReviews and reviewThreads must be PRESENT
and well-formed (an absent/null connection is the partial/malformed
class, never "provably no marker").

Thread 3876001004 — "Include the head-transition bound in the
pagination bracket": when the head force-pushes A->B->A during a
paginated boundary walk, the re-run carries the SAME headRefOid, so
the OID-only check accepted it even though its headTransition
timestamp ADVANCED (the B->A force-push event) — the returning-OID
cycle inside the pagination window, the round-28 cross-probe fix's
bracket twin. `_bracket_unchanged` now compares the headTransition
bound between original and re-run: a different (advanced) stamp
with the same OID reads unreadable bounds, and the re-run's
headTransition connection is held to the same strict present-and-
well-formed rule (an absent key can never certify "no transition").

No network: REAL round_bounds over scripted ROUND_QUERY + walk
pages (the round-24/28 probe-suite shape); the head_ref_oid seam
stays patched as the FOLD pin.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round32_probe_test -v
"""

import json
import subprocess as sp
import unittest
from unittest import mock

from . import pr_guard_reaction_probe

BOT_LOGIN = pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN

HEAD_A = "9f56841000000000000000000000000000000a"
BASE_1 = "3f568410000000000000000000000000000001"
PUSH = "2026-11-14T22:00:00Z"
REQ_AT = "2026-11-14T22:10:00Z"
REQ_ID = f"{REQ_AT}|RA_9"
# The original's latest force-push event (A->B); the walk-back
# boundary RA_9 (22:10) postdates it, so the newest-window picture
# is internally consistent.
TR_AT = "2026-11-14T22:05:00Z"
# The B->A cycle's force-push event and the request-less follow-up's
# bot review/thread comment — both land INSIDE the pagination window
# (after the original query, before the re-run).
TR_NEW = "2026-11-14T22:11:00Z"
ENG_NEW = "2026-11-14T22:11:00Z"
# A pre-walk bot review (22:05) the unchanged survivor carries on
# BOTH pages — at/below the original composite, never an advance.
ENG_OLD = "2026-11-14T22:05:00Z"
EMPTY = ("", "", "", "")


def gh_page(pr_node):
    return sp.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps({"data": {"repository": {"pullRequest": pr_node}}}),
    )


def human_request(created, minute_id):
    return {"createdAt": created, "id": minute_id, "requestedReviewer": {"login": "octocat"}}


def req_node(created, nid, login=BOT_LOGIN):
    return {"createdAt": created, "id": nid, "requestedReviewer": {"login": login}}


def review_node(at):
    return {"author": {"login": BOT_LOGIN}, "submittedAt": at}


def thread_comment_node(at):
    return {"author": {"login": BOT_LOGIN}, "createdAt": at}


def round_page(paginating="request", base=BASE_1, transition=(), reviews=None, thread_comments=None, drop_head_transition=False, drop_reviews=False):
    """A well-formed ROUND_QUERY page; paginating names the ONE kind
    whose newest-50 window is marker-FREE with earlier pages pending
    (that walk walks back — the post-query window opens); transition
    seeds the headTransition event stamps; reviews/thread_comments
    seed the ENGAGEMENT-marker connections (latestReviews nodes /
    one review-thread's bot comments); drop_* OMIT the keys (the
    strict-rerun partial shapes)."""
    pr = {
        "headRefOid": HEAD_A,
        "headRef": {"target": {"pushedDate": PUSH, "committedDate": PUSH}},
        "timelineItems": {
            "pageInfo": {
                "hasPreviousPage": paginating == "request",
                "startCursor": "c1" if paginating == "request" else None,
            },
            "nodes": [human_request(f"2026-11-14T22:0{i}:00Z", f"H_{i}") for i in (1, 2, 3)],
        },
        "triggerComments": {
            "pageInfo": {"hasPreviousPage": paginating == "trigger", "startCursor": None},
            "nodes": [],
        },
        "reviewThreads": (
            {"nodes": [{"comments": {"nodes": list(thread_comments)}}]}
            if thread_comments is not None
            else {"nodes": []}
        ),
    }
    if not drop_head_transition:
        pr["headTransition"] = {"nodes": [{"createdAt": t} for t in transition]}
    if not drop_reviews:
        pr["latestReviews"] = {"nodes": list(reviews or [])}
    if base is not None:
        pr["baseRefOid"] = base
    return pr


def walk_page(request):
    """A REQUEST_WALK_QUERY answering page carrying the boundary the
    newest-50 window evicted; no earlier pages."""
    return {
        "timelineItems": {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": list(request),
        }
    }


def run_bounds(pages):
    """REAL round_bounds over scripted subprocess pages with the
    head_ref_oid seam MOCKED (the round-28 FOLD pin: round_bounds
    must never call it — the re-run's own headRefOid certifies the
    head); (bounds, head-call-count)."""
    script = iter(pages)
    head = mock.Mock(return_value=HEAD_A)
    with mock.patch.object(
        pr_guard_reaction_probe.subprocess,
        "run",
        side_effect=lambda *a, **k: gh_page(next(script)),
    ), mock.patch.object(pr_guard_reaction_probe, "head_ref_oid", head):
        return pr_guard_reaction_probe.round_bounds(48, timeout_secs=None), head.call_count


class BracketMarkerRerunTests(unittest.TestCase):
    def test_newer_bot_review_marker_discards_probe(self):
        # Given: the thread-3876000990 race — the newest-50 request
        # window is codex-FREE with earlier pages pending, so the
        # walk fetches RA_9 (22:10) backwards AFTER ROUND_QUERY
        # captured the newest page; DURING the continuation reads a
        # REQUEST-LESS follow-up submits a bot review (22:11) —
        # invisible to the continuation cursors, and the round-24/25
        # bracket validated only the head/base/boundary connections,
        # so the re-run's advanced latestReviews stamp went unseen.
        # When: round_bounds parses. Then: ('', '', '', '') — the
        # re-run's engagement marker (22:11) ADVANCES past the
        # original composite marker (RA_9's 22:10), so the fetched
        # bounds' staleness classification is stale itself and the
        # WHOLE probe discards (retry next interval: the next
        # probe's own newest window reads the new marker); the
        # pre-fix bracket accepted the drift and returned the
        # readable OLD-round bounds (the pre-fix proof: a readable
        # 4-tuple, not EMPTY).
        bounds, _ = run_bounds(
            [
                round_page(),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                round_page(reviews=[review_node(ENG_NEW)]),
            ]
        )
        self.assertEqual(bounds, EMPTY)

    def test_newer_thread_comment_marker_discards_probe(self):
        # Given: the review-thread-comment twin — the identical
        # paginating walk, but the follow-up's engagement is a BOT
        # COMMENT on a review thread (22:11, the composite marker's
        # thread source) rather than a submitted review. When:
        # round_bounds parses. Then: ('', '', '', '') — the same
        # marker-advance rejection (the composite's thread half);
        # the pre-fix bracket never read the re-run's reviewThreads
        # and returned the readable bounds (the pre-fix proof).
        bounds, _ = run_bounds(
            [
                round_page(),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                round_page(thread_comments=[thread_comment_node(ENG_NEW)]),
            ]
        )
        self.assertEqual(bounds, EMPTY)

    def test_unchanged_engagement_marker_stays_readable(self):
        # Given: the SURVIVOR — the same paginating walk whose
        # original AND re-run pages carry the SAME pre-walk bot
        # review (22:05, at/below the walked boundary's 22:10 — the
        # composite marker was already 22:10). When: round_bounds
        # parses. Then: the fully readable bounds — the engagement
        # leg rejects only a marker NEWER than the original
        # composite, never a settled one; green on BOTH sides.
        bounds, head_calls = run_bounds(
            [
                round_page(reviews=[review_node(ENG_OLD)]),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                round_page(reviews=[review_node(ENG_OLD)]),
            ]
        )
        self.assertEqual(bounds, (HEAD_A, PUSH, REQ_ID, REQ_AT))
        self.assertEqual(head_calls, 0)

    def test_absent_latest_reviews_rerun_discards_probe(self):
        # Given: the strict-shape pin — the re-run page OMITS the
        # latestReviews key entirely (the partial/malformed class).
        # When: round_bounds parses. Then: ('', '', '', '') — the
        # re-run of OUR OWN assembled query always materializes the
        # alias, so an absent connection can never certify the
        # markers "provably unchanged" (the round-25 doctrine on the
        # engagement connections); the pre-fix bracket never read
        # latestReviews and returned the readable bounds (the
        # pre-fix proof).
        bounds, _ = run_bounds(
            [
                round_page(),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                round_page(drop_reviews=True),
            ]
        )
        self.assertEqual(bounds, EMPTY)


class BracketTransitionRerunTests(unittest.TestCase):
    def test_returning_oid_transition_advance_discards_probe(self):
        # Given: the thread-3876001004 race — the head force-pushed
        # A->B (event 22:05) BEFORE the original query captured it,
        # then B->A (event 22:11) DURING the paginated walk: the
        # re-run carries the SAME headRefOid A, so the OID-only
        # check accepts it, but its headTransition stamp advanced to
        # 22:11 — the returning-OID cycle inside the pagination
        # window (round_bounds returns the pre-cycle bound and the
        # waiter could accept the old A round's terminal +1 before
        # the next probe notices the transition). When: round_bounds
        # parses. Then: ('', '', '', '') — the transition bound
        # differs between original and re-run under an unchanged
        # OID, so the WHOLE probe discards; the pre-fix bracket
        # compared the OID alone and returned the readable bounds
        # (the pre-fix proof: a readable 4-tuple, not EMPTY).
        bounds, _ = run_bounds(
            [
                round_page(transition=[TR_AT]),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                round_page(transition=[TR_NEW]),
            ]
        )
        self.assertEqual(bounds, EMPTY)

    def test_matching_transition_stamp_stays_readable(self):
        # Given: the SURVIVOR — the same paginating walk whose
        # original and re-run pages carry the SAME headTransition
        # event (22:05; the head stood still through the window).
        # When: round_bounds parses. Then: the fully readable bounds
        # — the transition leg rejects only an ADVANCED stamp, never
        # a stable one (pushed reads max(PUSH, 22:05) = 22:05);
        # green on BOTH sides.
        bounds, head_calls = run_bounds(
            [
                round_page(transition=[TR_AT]),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                round_page(transition=[TR_AT]),
            ]
        )
        self.assertEqual(bounds, (HEAD_A, TR_AT, REQ_ID, REQ_AT))
        self.assertEqual(head_calls, 0)

    def test_absent_head_transition_rerun_discards_probe(self):
        # Given: the strict-shape twin — the re-run page OMITS the
        # headTransition key entirely (a partial response can never
        # certify "no transition happened during the window", which
        # is exactly what an absent key would claim). When:
        # round_bounds parses. Then: ('', '', '', '') — the round-25
        # present-and-readable doctrine on the transition
        # connection; the pre-fix bracket never read headTransition
        # and returned the readable bounds (the pre-fix proof).
        bounds, _ = run_bounds(
            [
                round_page(transition=[TR_AT]),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                round_page(drop_head_transition=True),
            ]
        )
        self.assertEqual(bounds, EMPTY)


if __name__ == "__main__":
    unittest.main()
