"""pr_guard reaction round-28 probe tests (PR #49 thread 3875089268
P1, the probe half): the base OID joins the pagination bracket —
the pair split's probe half (the wait halves, the cold-start base
floor and the returning-OID transitions, live in
pr_guard_reaction_round28_test).

Thread 3875089268 — "Include the base OID in the pagination
bracket": when a request/trigger lookup paginates and the PR base
changes during those continuation reads, the final ROUND_QUERY
re-run contains the NEW baseRefOid — but the round-24/25 bracket
validated only the head and the boundary connections, so
`_bracket_unchanged` accepted the drift and round_bounds returned
the ORIGINAL base: the waiter saw no base change until the NEXT
poll's oid compare and could accept the old-base round's terminal
+1 in between. The recheck now REQUIRES the re-run node to carry a
baseRefOid equal to the original query's parse — round-25 strict
doctrine (the re-run is our own assembled query, which always
materializes every requested alias): an ABSENT key is the
partial/malformed class exactly like an absent triggerComments,
never a "provably unchanged" base; a MISMATCH is the base-move
window itself. The INITIAL query's legacy absent-key tolerance
stays (the re-run-node-only strictness — the documented asymmetry
in _bracket_unchanged's header).

No network: REAL round_bounds over scripted ROUND_QUERY + walk
pages (the round-24 probe-suite shape); the head_ref_oid seam stays
patched as the FOLD pin — round_bounds must never call it again.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round28_probe_test -v
"""

import json
import subprocess as sp
import unittest
from unittest import mock

from . import pr_guard_reaction_boundaries
from . import pr_guard_reaction_probe

BOT_LOGIN = pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN

HEAD_A = "9f56841000000000000000000000000000000a"
BASE_1 = "3f568410000000000000000000000000000001"
BASE_2 = "3f568410000000000000000000000000000002"
PUSH = "2026-11-14T22:00:00Z"
REQ_AT = "2026-11-14T22:10:00Z"
REQ_ID = f"{REQ_AT}|RA_9"
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


def round_page(paginating="request", base=BASE_1):
    """A well-formed ROUND_QUERY page; paginating names the ONE kind
    whose newest-50 window is marker-FREE with earlier pages pending
    (that walk walks back — the post-query window opens); base names
    the page's baseRefOid (None keeps the key ABSENT — the
    partial-re-run shape thread 3875089268 makes unreadable). The
    bare-oid shape carries no baseRef/baseChange keys, so base_bound
    reads '' (no floor effect on any wait-side consumer)."""
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
        "headTransition": {"nodes": []},
        "latestReviews": {"nodes": []},
        "reviewThreads": {"nodes": []},
    }
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
    head_ref_oid seam MOCKED (the FOLD pin: round_bounds must never
    call it — the re-run's own headRefOid certifies the head);
    (bounds, head-call-count)."""
    script = iter(pages)
    head = mock.Mock(return_value=HEAD_A)
    with mock.patch.object(
        pr_guard_reaction_probe.subprocess,
        "run",
        side_effect=lambda *a, **k: gh_page(next(script)),
    ), mock.patch.object(pr_guard_reaction_probe, "head_ref_oid", head):
        return pr_guard_reaction_probe.round_bounds(48, timeout_secs=None), head.call_count


class BracketBaseCompareTests(unittest.TestCase):
    def test_postpagination_base_move_discards_probe(self):
        # Given: the thread-3875089268 race — the newest-50 request
        # window is codex-FREE with earlier pages pending, so the
        # walk fetches RA_9 (22:10) backwards AFTER ROUND_QUERY
        # captured the newest page; DURING the continuation reads the
        # PR base MOVES base_1 -> base_2, and the re-run's own window
        # carries the NEW baseRefOid. When: round_bounds parses.
        # Then: ('', '', '', '') — the re-run's base oid no longer
        # matches the captured one, so the WHOLE probe discards
        # (retry next interval: the wait must never accept the
        # ORIGINAL base's bounds off a bracket that missed the move —
        # the next poll's oid compare would only catch it a full
        # interval later, after the old-base round's terminal +1
        # could land); the pre-fix bracket validated only the head
        # and the boundaries and returned the READABLE bounds with
        # .base == base_1 (the pre-fix proof: a readable 4-tuple,
        # not EMPTY).
        bounds, _ = run_bounds(
            [
                round_page(paginating="request", base=BASE_1),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                round_page(paginating="request", base=BASE_2),
            ]
        )
        self.assertEqual(bounds, EMPTY)

    def test_absent_base_rerun_discards_probe(self):
        # Given: the strictness twin — the identical paginating walk,
        # but the re-run page carries NO baseRefOid key at all (the
        # partial/malformed response class). When: round_bounds
        # parses. Then: ('', '', '', '') — the re-run is our own
        # assembled query, which always materializes baseRefOid, so
        # an ABSENT key can never certify the base "provably
        # unchanged" (the round-25 triggerComments doctrine applied
        # to the base); the pre-fix bracket accepted the omission and
        # returned the readable bounds (the pre-fix proof).
        page = round_page(paginating="request", base=None)
        bounds, _ = run_bounds(
            [
                round_page(paginating="request", base=BASE_1),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                page,
            ]
        )
        self.assertEqual(bounds, EMPTY)

    def test_postpagination_matching_base_stays_readable(self):
        # Given: the SURVIVOR — the same paginating request walk
        # (RA_9 walked back below the newest window), and the re-run
        # page carries the SAME head AND the SAME base base_1 (no
        # drift of any kind). When: round_bounds parses. Then: the
        # fully readable bounds — the walked request identity rides
        # third, .base names base_1, and the head_ref_oid seam is
        # NEVER called (the FOLD pin survives the widened bracket);
        # green on BOTH sides (the pre-fix bracket accepted the same
        # picture).
        bounds, head_calls = run_bounds(
            [
                round_page(paginating="request", base=BASE_1),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                round_page(paginating="request", base=BASE_1),
            ]
        )
        self.assertEqual(bounds, (HEAD_A, PUSH, REQ_ID, REQ_AT))
        self.assertEqual(bounds.base, BASE_1)
        self.assertEqual(head_calls, 0)


if __name__ == "__main__":
    unittest.main()
