"""pr_guard reaction round-22 probe tests (PR #49 thread 3872980781
P1: "Extend the head bracket past boundary pagination").

The request/trigger boundary walks run additional GraphQL subprocesses
(backwards pages, same-second edge continuations) AFTER ROUND_QUERY
captured the bracket's final headRefOid — a head moving during those
walks left round_bounds returning the OLD oid, so the wait could
accept the old head's terminal reaction before the next poll noticed
the move (the round-10/18 bracket covered only the reactions read and
the combined query itself). The walks report every dispatched cursor
(the optional paged list) and round_bounds rechecks the bracket after
all boundary pagination: drift, a FAILED recheck ('' certifies
nothing — the round-13 ''-endpoint rule), or an EXPIRED deadline
returns the unreadable all-empty bounds — the probe is discarded and
retried next interval; a walk that never paginated rechecks nothing
(no window opened; the common first-page-answers probe spends no
extra subprocess).

PR #49 ROUND 24 (thread 3873592857, P2) fixture-seam maintenance —
THE FOLD: the post-pagination recheck is now the bracket RE-RUN (one
extra ROUND_QUERY subprocess whose headRefOid certifies the head
beside the boundary facts), so these fixtures script the re-run page
where they scripted the head seam, and the patched head_ref_oid seam
is the NEVER-CALLED fold pin. Every outcome assertion is unchanged.

No network: REAL round_bounds over scripted ROUND_QUERY + walk pages
(pr_guard_reaction_probe.subprocess.run); the re-run rides the same
script (one more ROUND_QUERY-shaped page).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round22_probe_test -v
"""

import json
import subprocess as sp
import unittest
from unittest import mock

from . import pr_guard_reaction_boundaries
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock

BOT_LOGIN = pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN

HEAD_A = "20ab97ffffffffffffffffffffffffffffffa"
HEAD_B = "20ab97ffffffffffffffffffffffffffffffb"
PUSH = "2023-11-14T22:00:00Z"
REQ_AT = "2023-11-14T22:10:00Z"
REQ_ID = f"{REQ_AT}|RA_9"
EMPTY = ("", "", "", "")


def gh_page(pr_node, rc=0):
    return sp.CompletedProcess(
        args=[],
        returncode=rc,
        stdout=json.dumps({"data": {"repository": {"pullRequest": pr_node}}}),
    )


def human_request(created, minute_id):
    return {"createdAt": created, "id": minute_id, "requestedReviewer": {"login": "octocat"}}


def round_page(paginating=True, head=HEAD_A):
    """A well-formed ROUND_QUERY page; paginating True leaves the
    newest-50 request window codex-FREE with hasPreviousPage (the
    backwards walk runs — the post-query window opens); False puts
    the codex request ON page one (no walk, no recheck). head names
    the page's headRefOid (the round-24 re-run page carries the
    drifted head for the drift test). (PR #49 round 25 fixture-seam
    maintenance, thread 3873970927: triggerComments is now always a
    present, well-formed empty window — the strict recheck requires
    the connection on every re-run page.)"""
    nodes = [
        human_request(f"2023-11-14T22:0{i}:00Z", f"H_{i}") for i in range(1, 4)
    ]
    if not paginating:
        nodes.append(
            {"createdAt": REQ_AT, "id": "RA_9", "requestedReviewer": {"login": BOT_LOGIN}}
        )
    return {
        "headRefOid": head,
        # PR #49 round 28 fixture-seam maintenance (thread
        # 3875089268): every re-run page now carries baseRefOid (the
        # strict recheck validates the base beside the head); the
        # bare-oid shape keeps base_bound '' (no floor effect).
        "baseRefOid": "9ed444e0d5b1ad3b3ff6c9d3e3b4a5c6d7e8f9a0",
        "headRef": {"target": {"pushedDate": PUSH, "committedDate": PUSH}},
        "timelineItems": {
            "pageInfo": {
                "hasPreviousPage": paginating,
                "startCursor": "c1" if paginating else None,
            },
            "nodes": nodes,
        },
        "triggerComments": {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": [],
        },
        "headTransition": {"nodes": []},
        "latestReviews": {"nodes": []},
        "reviewThreads": {"nodes": []},
    }


def walk_page():
    """The REQUEST_WALK_QUERY answering page: the codex request the
    newest-50 window evicted, no earlier pages."""
    return {
        "timelineItems": {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": [
                {"createdAt": REQ_AT, "id": "RA_9", "requestedReviewer": {"login": BOT_LOGIN}}
            ],
        }
    }


def run_bounds(pages):
    """REAL round_bounds over scripted subprocess pages (a dict is
    wrapped as a successful page; a CompletedProcess passes through —
    the last scripted page answers the round-24 bracket re-run, a
    failed re-run scripted as an rc-1 CompletedProcess, never a
    raised exception); the head_ref_oid seam stays patched as the
    NEVER-CALLED fold pin; (bounds, head-call-count)."""
    script = iter(pages)
    head = mock.Mock(return_value=HEAD_A)

    def fake_run(*a, **k):
        page = next(script)
        return page if isinstance(page, sp.CompletedProcess) else gh_page(page)

    with mock.patch.object(
        pr_guard_reaction_probe.subprocess, "run", side_effect=fake_run
    ), mock.patch.object(pr_guard_reaction_probe, "head_ref_oid", head):
        return pr_guard_reaction_probe.round_bounds(48, timeout_secs=None), head.call_count


class BracketPastPaginationTests(unittest.TestCase):
    def test_paginated_walk_head_drift_discards_probe(self):
        # Given: the thread-3872980781 race — the newest-50 request
        # window is codex-FREE with earlier pages pending, so the
        # backwards walk fetches the request page AFTER ROUND_QUERY
        # captured headRefOid A; the head MOVES to B during the walk
        # (the round-24 re-run page carries B). When: round_bounds
        # parses. Then: ('', '', '', '') — the drift discards the
        # WHOLE probe (the round-10/18 bracket discipline extended
        # past the walks: the wait retries next interval instead of
        # accepting the old head's bounds); the pre-fix probe
        # returned the readable OLD-HEAD bounds (the pre-fix proof:
        # a 4-tuple carrying A).
        bounds, _ = run_bounds(
            [round_page(True), walk_page(), round_page(True, head=HEAD_B)]
        )
        self.assertEqual(bounds, EMPTY)

    def test_paginated_walk_head_stable_stays_readable(self):
        # Given: the same paginating probe, but the head HOLDS at A
        # through the walks (the re-run page reads A — no drift, its
        # codex-free window the unchanged boundary picture). When:
        # round_bounds parses. Then: the fully readable bounds — the
        # walked request identity rides third and its createdAt
        # fourth, exactly the pre-round-22 read; green on BOTH sides
        # (the pre-fix probe never rechecked and returned the same
        # tuple).
        bounds, head_calls = run_bounds(
            [round_page(True), walk_page(), round_page(True)]
        )
        self.assertEqual(bounds, (HEAD_A, PUSH, REQ_ID, REQ_AT))
        self.assertEqual(head_calls, 0)

    def test_unpaged_probe_never_rechecks_head(self):
        # Given: the COMMON probe — the newest-50 window carries the
        # codex request itself (hasPreviousPage False: no walk, no
        # continuation — no post-query window opens). When:
        # round_bounds parses. Then: the readable bounds and ZERO
        # head rechecks (no window, no extra subprocess — the
        # first-page-answers probe keeps its exact pre-round-22
        # subprocess count); green on BOTH sides.
        bounds, head_calls = run_bounds([round_page(False)])
        self.assertEqual(bounds, (HEAD_A, PUSH, REQ_ID, REQ_AT))
        self.assertEqual(head_calls, 0)

    def test_failed_recheck_discards_probe(self):
        # Given: a paginating probe whose bracket re-run FAILS (gh
        # exits nonzero — the recheck cannot validate anything). When:
        # round_bounds parses. Then: ('', '', '', '') — a failed
        # recheck certifies NOTHING (the round-13 ''-endpoint rule:
        # never a certified bracket, never done-on-ambiguity), the
        # whole probe retries next interval; the pre-fix probe never
        # rechecked and returned the readable bounds (the pre-fix
        # proof).
        bounds, _ = run_bounds(
            [round_page(True), walk_page(), gh_page({}, rc=1)]
        )
        self.assertEqual(bounds, EMPTY)

    def test_expired_deadline_discards_probe(self):
        # Given: a paginating probe on a 2s budget — the WALK page's
        # subprocess (the before=$cursor call alone; the ROUND_QUERY
        # answers instantly) burns 5 FAKE seconds through one
        # FakeClock wired into BOTH time seams (probe's deadline math
        # and the boundaries walk's per-page budget), so the deadline
        # EXPIRES after the walk answered but before the bracket
        # recheck could run. When: round_bounds parses. Then:
        # ('', '', '', '') — an expired deadline cannot certify the
        # bracket either (the recheck rides the SAME probe deadline,
        # never a fresh grant); the pre-fix probe never rechecked and
        # returned the readable bounds (the pre-fix proof).
        clock = FakeClock()
        script = iter([round_page(True), walk_page()])

        def fake_run(argv, **kwargs):
            page = next(script)
            if any(str(token).startswith("before=") for token in argv):
                clock.sleep(5.0)
            return gh_page(page)

        with mock.patch.object(
            pr_guard_reaction_probe.subprocess, "run", side_effect=fake_run
        ), mock.patch.object(pr_guard_reaction_probe, "time", clock), mock.patch.object(
            pr_guard_reaction_boundaries, "time", clock
        ):
            self.assertEqual(
                pr_guard_reaction_probe.round_bounds(48, timeout_secs=2.0), EMPTY
            )


if __name__ == "__main__":
    unittest.main()
