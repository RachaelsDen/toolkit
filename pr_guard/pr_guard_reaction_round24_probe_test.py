"""pr_guard reaction round-24 probe tests (PR #49 thread 3873592857
P2 — "Recheck round boundaries after paginated walks").

Round 22 (thread 3872980781) extended the head bracket past boundary
pagination with a head-ONLY re-read; but when either boundary lookup
needs backward pagination, a NEW formal request or manual trigger
comment can arrive after ROUND_QUERY captured the newest page and
before the continuation reads finish — the continuation cursors
cannot include that newer event, and an unchanged-head probe could
still return the PRECEDING round's bounds, letting the wait accept
its terminal +1 and exit 0 before the newly requested round began.
Round 24 widens the post-pagination recheck to the FULL bracket and
FOLDS round 22's separate head-only read into it: when the walks
report pagination (paged non-empty), round_bounds RE-RUNS the
bracketed round query (one extra ROUND_QUERY subprocess) and
requires the picture UNCHANGED — the head oid AND each kind's
boundary facts as the original query reported them (a new boundary
lands at the timeline's TOP, inside every newest-50 window: the
re-run's latest VISIBLE request/trigger identity must still equal
the original walk's reported identity, and a walked-back
deeper-than-window boundary is unchanged exactly while the re-run
window still carries none of its kind). ANY drift, a failed or
malformed re-run, or an expired deadline returns the unreadable
all-empty bounds; an unpaginated probe rechecks NOTHING (the common
first-page-answers probe keeps its exact subprocess count).

No network: REAL round_bounds over scripted ROUND_QUERY + walk pages
(pr_guard_reaction_probe.subprocess.run), the round-22 probe-suite
shape; the re-run rides the same script (one more ROUND_QUERY-shaped
page), and the head_ref_oid seam stays patched as the FOLD pin —
round_bounds must never call it again.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round24_probe_test -v
"""

import json
import subprocess as sp
import unittest
from unittest import mock

from . import pr_guard_reaction_boundaries
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock

BOT_LOGIN = pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN

HEAD_A = "9f56841000000000000000000000000000000a"
PUSH = "2026-11-14T22:00:00Z"
REQ_AT = "2026-11-14T22:10:00Z"
REQ_ID = f"{REQ_AT}|RA_9"
TRG_AT = "2026-11-14T22:09:00Z"
TRG_ID = f"{TRG_AT}|TC_9"
EMPTY = ("", "", "", "")


def gh_page(pr_node, rc=0):
    return sp.CompletedProcess(
        args=[],
        returncode=rc,
        stdout=json.dumps({"data": {"repository": {"pullRequest": pr_node}}}),
    )


def human_request(created, minute_id):
    return {"createdAt": created, "id": minute_id, "requestedReviewer": {"login": "octocat"}}


def plain_comment(created, cid):
    return {"createdAt": created, "id": cid, "body": "looks fine"}


def req_node(created, nid, login=BOT_LOGIN):
    return {"createdAt": created, "id": nid, "requestedReviewer": {"login": login}}


def trg_node(created, nid):
    return {"createdAt": created, "id": nid, "body": "@codex review"}


def round_page(paginating="request", head=HEAD_A, request=(), trigger=None, trigger_window=None):
    """A well-formed ROUND_QUERY page. paginating names the ONE kind
    whose newest-50 window is marker-FREE with earlier pages pending
    (that walk walks back — the post-query window opens); "none"
    puts the request ON page one (no walk, no recheck). request/
    trigger seed the newest windows directly (the re-run pages);
    trigger_window seeds the triggerComments newest window when the
    trigger kind is the paginating one. (PR #49 round 25 fixture-seam
    maintenance, thread 3873970927: the triggerComments connection is
    now ALWAYS present and well-formed — the strict recheck requires
    it on every re-run page, and the request-paginating pages
    previously omitted the key.)"""
    pr = {
        "headRefOid": head,
        # PR #49 round 28 fixture-seam maintenance (thread
        # 3875089268): every re-run page now carries baseRefOid (the
        # strict recheck validates the base beside the head); the
        # bare-oid shape keeps base_bound '' (no floor effect).
        "baseRefOid": "9ed444e0d5b1ad3b3ff6c9d3e3b4a5c6d7e8f9a0",
        "headRef": {"target": {"pushedDate": PUSH, "committedDate": PUSH}},
        "timelineItems": {
            "pageInfo": {
                "hasPreviousPage": paginating == "request",
                "startCursor": "c1" if paginating == "request" else None,
            },
            "nodes": list(request)
            or [human_request(f"2026-11-14T22:0{i}:00Z", f"H_{i}") for i in (1, 2, 3)],
        },
        "headTransition": {"nodes": []},
        "latestReviews": {"nodes": []},
        "reviewThreads": {"nodes": []},
    }
    nodes = list(trigger) if trigger is not None else list(trigger_window or [])
    pr["triggerComments"] = {
        "pageInfo": {
            "hasPreviousPage": paginating == "trigger",
            "startCursor": "t1" if paginating == "trigger" else None,
        },
        "nodes": nodes,
    }
    return pr


def walk_page(request=None, trigger=None):
    """A REQUEST/TRIGGER_WALK_QUERY answering page carrying the
    boundary the newest-50 window evicted; no earlier pages."""
    pr = {}
    if trigger is not None:
        pr["triggerComments"] = {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": list(trigger),
        }
    else:
        pr["timelineItems"] = {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": list(request),
        }
    return pr


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


class BracketRerunTests(unittest.TestCase):
    def test_postpagination_new_request_discards_probe(self):
        # Given: the thread-3873592857 race — the newest-50 request
        # window is codex-FREE with earlier pages pending, so the
        # walk fetches RA_9 (22:10) backwards AFTER ROUND_QUERY
        # captured the newest page; DURING the continuation a NEW
        # formal request RA_10 (22:11) arrives — invisible to the
        # cursor, and the re-run's own window carries it at the top.
        # When: round_bounds parses. Then: ('', '', '', '') — the
        # visible request identity no longer matches the walk's
        # reported RA_9, so the WHOLE probe discards (retry next
        # interval: the wait must never accept the preceding round's
        # bounds off a stale bracket); the pre-fix probe returned the
        # readable OLD-round bounds (the pre-fix proof: a 4-tuple).
        bounds, _ = run_bounds(
            [
                round_page(paginating="request"),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                round_page(request=[req_node("2026-11-14T22:11:00Z", "RA_10")]),
            ]
        )
        self.assertEqual(bounds, EMPTY)

    def test_postpagination_new_trigger_discards_probe(self):
        # Given: the trigger twin — the newest-50 comment window
        # carries no trigger with earlier pages pending, so the
        # trigger walk fetches TC_9 (22:09) backwards; DURING the
        # continuation a NEW manual-trigger comment TC_10 (22:12)
        # lands at the timeline's top, where only the re-run's own
        # window sees it. When: round_bounds parses. Then:
        # ('', '', '', '') — the visible trigger identity no longer
        # matches the walk's reported TC_9; the pre-fix probe
        # returned the readable OLD-round bounds (the pre-fix
        # proof).
        bounds, _ = run_bounds(
            [
                round_page(
                    paginating="trigger",
                    trigger_window=[plain_comment("2026-11-14T22:01:00Z", "C_1")],
                ),
                walk_page(trigger=[trg_node(TRG_AT, "TC_9")]),
                round_page(
                    request=[req_node(REQ_AT, "RA_9")],
                    trigger=[trg_node("2026-11-14T22:12:00Z", "TC_10")],
                ),
            ]
        )
        self.assertEqual(bounds, EMPTY)

    def test_postpagination_unchanged_bounds_stay_readable(self):
        # Given: the survivor — the same paginating request walk
        # (RA_9 walked back below the newest window), and the re-run
        # page still reads the SAME head with a codex-FREE newest
        # window (the walked-back boundary is unchanged exactly
        # while the window carries none of its kind; no new request
        # arrived). When: round_bounds parses. Then: the fully
        # readable bounds — the walked request identity rides third
        # and its createdAt fourth — and the head_ref_oid seam is
        # NEVER called (the FOLD pin: the re-run's own headRefOid
        # replaced round 22's separate head read); green on BOTH
        # sides (the pre-fix probe re-read the head only and
        # returned the same tuple).
        bounds, head_calls = run_bounds(
            [
                round_page(paginating="request"),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                round_page(paginating="request"),
            ]
        )
        self.assertEqual(bounds, (HEAD_A, PUSH, REQ_ID, REQ_AT))
        self.assertEqual(head_calls, 0)

    def test_postpagination_head_drift_discards_probe(self):
        # Given: round 22's own race carried forward through the
        # fold — the paginating walk opens the post-query window and
        # the head MOVES to B during it; the re-run page reads the
        # NEW head. When: round_bounds parses. Then: ('', '', '',
        # '') — the re-run's headRefOid no longer matches the
        # captured one (the same drift discipline round 22 built,
        # now certified by the re-run's own oid); the pre-fix probe
        # returned the readable OLD-HEAD bounds (the pre-fix proof).
        bounds, _ = run_bounds(
            [
                round_page(paginating="request"),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                round_page(paginating="request", head=HEAD_A[:-1] + "b"),
            ]
        )
        self.assertEqual(bounds, EMPTY)

    def test_failed_rerun_discards_probe(self):
        # Given: a paginating probe whose re-run FAILS (gh exits
        # nonzero — the re-run cannot validate anything). When:
        # round_bounds parses. Then: ('', '', '', '') — a failed
        # re-run certifies NOTHING (the round-13 ''-endpoint rule:
        # never a certified bracket, never done-on-ambiguity), the
        # whole probe retries next interval; the pre-fix probe
        # re-read the head only (the patched STABLE seam — an
        # unpatched one would fall through to LIVE gh, the round-17
        # GOTCHA) and returned the readable bounds (the pre-fix
        # proof).
        script = iter(
            [
                gh_page(round_page(paginating="request")),
                gh_page(walk_page(request=[req_node(REQ_AT, "RA_9")])),
                gh_page({}, rc=1),
            ]
        )
        with mock.patch.object(
            pr_guard_reaction_probe.subprocess,
            "run",
            side_effect=lambda *a, **k: next(script),
        ), mock.patch.object(
            pr_guard_reaction_probe, "head_ref_oid", return_value=HEAD_A
        ):
            self.assertEqual(pr_guard_reaction_probe.round_bounds(48, timeout_secs=None), EMPTY)

    def test_unpaged_probe_never_reruns(self):
        # Given: the COMMON probe — the newest-50 window carries the
        # codex request itself (hasPreviousPage False: no walk, no
        # continuation — no post-query window opens). When:
        # round_bounds parses over the ONE scripted page. Then: the
        # readable bounds with ZERO re-runs (no window, no extra
        # subprocess — the first-page-answers probe keeps its exact
        # subprocess count); green on BOTH sides.
        bounds, head_calls = run_bounds(
            [round_page(paginating="none", request=[req_node(REQ_AT, "RA_9")])]
        )
        self.assertEqual(bounds, (HEAD_A, PUSH, REQ_ID, REQ_AT))
        self.assertEqual(head_calls, 0)

    def test_expired_deadline_before_rerun_discards_probe(self):
        # Given: a paginating probe on a 2s budget — the WALK page's
        # subprocess (the before=$cursor call alone; the ROUND_QUERY
        # answers instantly) burns 5 FAKE seconds through one
        # FakeClock wired into BOTH time seams (probe's deadline math
        # and the boundaries walk's per-page budget), so the deadline
        # EXPIRES after the walk answered but before the re-run could
        # dispatch. When: round_bounds parses. Then: ('', '', '',
        # '') — an expired deadline cannot certify the bracket either
        # (the recheck rides the SAME probe deadline, never a fresh
        # grant); green on BOTH sides (round 22's expiry arm already
        # discarded here — the discipline carries through the fold).
        clock = FakeClock()
        script = iter(
            [
                round_page(paginating="request"),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                round_page(paginating="request"),
            ]
        )

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
