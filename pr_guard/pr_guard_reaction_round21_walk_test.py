"""pr_guard reaction round-21 walk tests (PR #49 thread 3872631157
P2: "Collect same-second boundaries across page edges").

Round 20's collect sets recorded every identity sharing the returned
boundary's high-water second ON THE ANSWERING PAGE — but the walks
returned as soon as the newest-50 page carried ANY trigger, so a
same-second pair STRADDLING the page boundary left the older sibling
on the preceding page UNRECORDED: deleting the newer in-page comment
exposed the sibling on the next probe, its equal timestamp and
distinct id satisfied boundary_advances, and the spurious ROUND
RE-REQUESTED reset held a valid round's completion to timeout. Both
walks now continue into the preceding page when the answering page's
OLDEST item shares the selected marker's second, collecting that
second's identities while the fetched pages' NEWEST item still
shares it (the formal-request twin walks the same edge). Deadline/
pagination hygiene unchanged; an unreadable/expired continuation
makes the WHOLE walk unreadable (never a readable boundary whose
collect set may be incomplete); a legacy 3-arg caller (collect None)
never continues.

No network: REAL round_bounds / trigger_comment_marker over scripted
graphql pages (the round-15/18 probe shape); the wait-level race
runs the REAL wait over the REAL walks (the round-20 harness shape).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round21_walk_test -v
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
BOT_LOGIN = pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN

HEAD = "21ab97ffffffffffffffffffffffffffffff0"
PUSH = "2026-08-01T00:00:00Z"
SECOND = "2026-08-01T00:05:00Z"
OLDER = "2026-08-01T00:04:00Z"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def gh_page(payload):
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(payload)
    )


def trigger_node(created, node_id):
    return {"createdAt": created, "id": node_id, "body": "@codex review"}


def req_node(created, node_id):
    return {
        "createdAt": created,
        "id": node_id,
        "requestedReviewer": {"login": BOT_LOGIN},
    }


def round_page(trigger=None, request=(), edge=None, review=None):
    """A well-formed ROUND_QUERY page; trigger None keeps the
    triggerComments key ABSENT (the round-18 legacy rule). edge
    ("trigger"/"request") names the ONE connection whose window
    straddles a page edge (hasPreviousPage True + a cursor); every
    other connection reads exhausted (empty, hasPreviousPage False).
    (PR #49 round 25 fixture-seam maintenance, thread 3873970933 +
    3873970927: an optional folded botReviews node — the completing
    probe's evidence names the stable head, which cold-start
    completions now require; re-run pages pass trigger=[] so the
    STRICT recheck finds the connection present.)"""
    pr = {
        "headRefOid": HEAD,
        # PR #49 round 28 fixture-seam maintenance (thread
        # 3875089268): every re-run page now carries baseRefOid (the
        # strict recheck validates the base beside the head); the
        # bare-oid shape keeps base_bound '' (no floor effect).
        "baseRefOid": "9ed444e0d5b1ad3b3ff6c9d3e3b4a5c6d7e8f9a0",
        "headRef": {"target": {"pushedDate": PUSH, "committedDate": PUSH}},
        "timelineItems": {
            "pageInfo": {"hasPreviousPage": edge == "request", "startCursor": "CUR"},
            "nodes": list(request),
        },
        "headTransition": {"nodes": []},
        "latestReviews": {"nodes": []},
        "reviewThreads": {"nodes": []},
    }
    if trigger is not None:
        pr["triggerComments"] = {
            "pageInfo": {"hasPreviousPage": edge == "trigger", "startCursor": "CUR"},
            "nodes": list(trigger),
        }
    if review is not None:
        pr["botReviews"] = {"nodes": [review]}
    return {"data": {"repository": {"pullRequest": pr}}}


def walk_page(trigger=None, request=(), has_prev=False):
    """A well-formed REQUEST/TRIGGER_WALK_QUERY page (the continuation
    fetch's shape)."""
    pr = {}
    if trigger is not None:
        pr["triggerComments"] = {
            "pageInfo": {"hasPreviousPage": has_prev, "startCursor": "CUR2"},
            "nodes": list(trigger),
        }
    else:
        pr["timelineItems"] = {
            "pageInfo": {"hasPreviousPage": has_prev, "startCursor": "CUR2"},
            "nodes": list(request),
        }
    return {"data": {"repository": {"pullRequest": pr}}}


def run_bounds_scripted(procs):
    # REAL round_bounds over scripted CompletedProcess pages; the
    # call argv list rides along so continuation fetches are
    # countable (timeout_secs None -> no clock dependency).
    calls = []
    script = iter(procs)

    def fake_run(*a, **k):
        calls.append(a)
        return next(script)

    with mock.patch.object(
        pr_guard_reaction_probe.subprocess, "run", side_effect=fake_run
    ), mock.patch.object(
        # Thread 3872980781 (round 22) fixture-seam maintenance,
        # FOLDED by thread 3873592857 (round 24): a paginating probe
        # now RE-RUNS the round query (a scripted page, not the head
        # seam), and the patched STABLE head seam is the NEVER-CALLED
        # fold pin (the re-run's own headRefOid replaced round 22's
        # separate head read) — drift is round22_probe's subject.
        pr_guard_reaction_probe, "head_ref_oid", return_value=HEAD
    ):
        return pr_guard_reaction.round_bounds(48, timeout_secs=None), calls


def run_wait_pages(reads, pages, timeout_secs):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    + walk pages (the round-18/19/20 shape); a stable head."""
    clock = FakeClock()
    items = iter(reads)
    script = iter(pages)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_read
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=HEAD
    ), mock.patch.object(
        pr_guard_reaction_probe.subprocess,
        "run",
        side_effect=lambda *a, **k: gh_page(next(script)),
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue()


class CrossPageSiblingTests(unittest.TestCase):
    def test_cross_page_sibling_resurfacing_never_readvances(self):
        # Given: the thread-3872631157 race — t=0 the newest-50
        # trigger window's OLDEST item is IC_2, sharing SECOND with
        # the newest IC_9 (the pair STRADDLES the page edge: the
        # older sibling IC_1 sits on the PRECEDING page), while the
        # round's verified EYES (2026-08-02, past the push and the
        # boundary second) arms; t=5 BOTH in-page triggers are
        # DELETED (the empty window walks back to the preceding
        # page, IC_1 resurfacing as the walk's latest) while the
        # round sits in its EYES-removal/+1 switch (NONE); t=10 the
        # +1 (2026-08-26T14, following the EYES watermark — a VALID
        # completion) lands. When: wait polls 10s. Then: exit 0 at
        # 10s with ZERO advance lines — the continuation collected
        # IC_1 across the edge at t=0, so the resurfacing sibling is
        # IN the seen-set and never readvances; the pre-fix walk
        # stopped at the first marker-carrying page, so IC_1 was
        # unrecorded, its distinct id satisfied boundary_advances,
        # the SPURIOUS ROUND RE-REQUESTED at t=5 cleared the armed
        # latch/watermark, and the valid +1 held to timeout (exit 1).
        # (PR #49 round 24 fixture-seam maintenance, thread 3873592857:
        # each paginating probe now RE-RUNS the round query — the
        # appended per-probe re-run pages carry the same newest-window
        # pictures (the t=0 in-page pair; t=5's emptied window), the
        # unchanged brackets the recheck expects; every assertion is
        # unchanged.)
        code, out = run_wait_pages(
            [
                [react("eyes", "2026-08-02T00:00:00Z", 5)],
                [],
                [react("+1", "2026-08-26T14:00:00Z", 8)],
            ],
            [
                round_page(
                    trigger=[trigger_node(SECOND, "IC_2"), trigger_node(SECOND, "IC_9")],
                    edge="trigger",
                ),
                walk_page(trigger=[trigger_node(OLDER, "IC_0"), trigger_node(SECOND, "IC_1")]),
                round_page(
                    trigger=[trigger_node(SECOND, "IC_2"), trigger_node(SECOND, "IC_9")],
                ),
                round_page(trigger=[], edge="trigger"),
                walk_page(trigger=[trigger_node(OLDER, "IC_0"), trigger_node(SECOND, "IC_1")]),
                round_page(trigger=[]),
                round_page(
                    trigger=[trigger_node(OLDER, "IC_0"), trigger_node(SECOND, "IC_1")],
                    # PR #49 round 25 fixture-seam maintenance (thread
                    # 3873970933): the completing probe's folded
                    # review evidence names the stable head — cold-start
                    # completions require it now.
                    review={
                        "author": {"login": BOT_LOGIN},
                        "commit": {"oid": HEAD},
                        "submittedAt": "2026-08-26T13:00:00Z",
                    },
                ),
            ],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)

    def test_trigger_collect_spans_the_page_edge(self):
        # Given: the probe-level half — a newest-50 trigger window
        # whose OLDEST item (IC_2) shares the selected marker IC_9's
        # second, hasPreviousPage True, and a preceding page whose
        # NEWEST item (IC_1) shares the second beside an older-second
        # sibling (IC_0 at 00:04). When: round_bounds reads the
        # scripted pages (REAL walks; the pagination opens the
        # post-query window, so the round-24 bracket re-run reads the
        # appended THIRD page — the same in-page pair without the
        # edge, the unchanged picture the recheck expects — thread
        # 3873592857 fixture-seam maintenance, the collect
        # assertions unchanged). Then: the stream identity is still
        # the newest in-page marker (IC_9 — the continuation never
        # changes the RETURN), the collect set carries the second's
        # identities from BOTH pages (IC_1, IC_2, IC_9) while the
        # older second's IC_0 stays unrecorded (the round-20 rule),
        # and exactly THREE subprocesses ran (one round query, one
        # continuation, one bracket re-run); the pre-fix walk made
        # ONE call and trigger_ids missed IC_1.
        bounds, calls = run_bounds_scripted(
            [
                gh_page(
                    round_page(
                        trigger=[
                            trigger_node(SECOND, "IC_2"),
                            trigger_node(SECOND, "IC_9"),
                        ],
                        edge="trigger",
                    )
                ),
                gh_page(
                    walk_page(
                        trigger=[trigger_node(OLDER, "IC_0"), trigger_node(SECOND, "IC_1")]
                    )
                ),
                gh_page(
                    round_page(
                        trigger=[
                            trigger_node(SECOND, "IC_2"),
                            trigger_node(SECOND, "IC_9"),
                        ],
                    )
                ),
            ]
        )
        self.assertEqual(bounds.trigger, f"{SECOND}|IC_9")
        self.assertEqual(
            bounds.trigger_ids,
            {f"{SECOND}|IC_1", f"{SECOND}|IC_2", f"{SECOND}|IC_9"},
        )
        self.assertNotIn(f"{OLDER}|IC_0", bounds.trigger_ids)
        self.assertEqual(len(calls), 3)

    def test_request_collect_spans_the_page_edge(self):
        # Given: the FORMAL-REQUEST twin — the same straddling window
        # of codex ReviewRequestedEvents (RA_2 the oldest in-page
        # item, RA_9 the newest, both at SECOND) with the preceding
        # page carrying RA_1 at the second (beside RA_0 at 00:04).
        # When: round_bounds reads the two scripted pages. Then: the
        # request stream is RA_9's identity, the request collect set
        # carries BOTH pages' same-second identities (RA_1, RA_2,
        # RA_9), and the merged boundary (index 2) is RA_9's identity
        # (the trigger kind reads '' — no triggerComments key); the
        # pre-fix request_ids missed RA_1.
        bounds, _ = run_bounds_scripted(
            [
                gh_page(
                    round_page(
                        request=[req_node(SECOND, "RA_2"), req_node(SECOND, "RA_9")],
                        edge="request",
                    )
                ),
                gh_page(
                    walk_page(request=[req_node(OLDER, "RA_0"), req_node(SECOND, "RA_1")])
                ),
                gh_page(
                round_page(
                    request=[req_node(SECOND, "RA_2"), req_node(SECOND, "RA_9")],
                    trigger=[],
                )
                ),
            ]
        )
        self.assertEqual(bounds.request, f"{SECOND}|RA_9")
        self.assertEqual(
            bounds.request_ids,
            {f"{SECOND}|RA_1", f"{SECOND}|RA_2", f"{SECOND}|RA_9"},
        )
        self.assertEqual(bounds[2], f"{SECOND}|RA_9")

    def test_older_second_page_edge_does_not_continue(self):
        # Given: the STOP-condition survivor — the window's OLDEST
        # item (IC_0 at 00:04) PREDATES the selected marker IC_9's
        # second, so nothing of the second can live on a preceding
        # page even though hasPreviousPage is True. When: round_bounds
        # reads (one scripted page, call-counted). Then: exactly ONE
        # subprocess — no continuation off the second — and the
        # collect set stays the in-page identities alone (IC_9; IC_0
        # is the older second the stream never records). Green on
        # BOTH sides of the round-21 change.
        bounds, calls = run_bounds_scripted(
            [
                gh_page(
                    round_page(
                        trigger=[trigger_node(OLDER, "IC_0"), trigger_node(SECOND, "IC_9")],
                        edge="trigger",
                    )
                )
            ]
        )
        self.assertEqual(bounds.trigger, f"{SECOND}|IC_9")
        self.assertEqual(bounds.trigger_ids, {f"{SECOND}|IC_9"})
        self.assertEqual(len(calls), 1)

    def test_unreadable_continuation_reads_the_walk_unreadable(self):
        # Given: the hygiene leg — the straddling window (IC_2/IC_9
        # at SECOND, hasPreviousPage True) whose continuation page
        # FAILS (rc 1). When: round_bounds reads. Then: the WHOLE
        # probe is UNREADABLE ('', '', '', '') — a walk that stopped
        # before the second's identities are proven recorded is never
        # a readable boundary (the thread 3868158304 bias rule); the
        # pre-fix walk never fetched the page and returned a readable
        # boundary whose collect set was silently incomplete.
        bounds, calls = run_bounds_scripted(
            [
                gh_page(
                    round_page(
                        trigger=[
                            trigger_node(SECOND, "IC_2"),
                            trigger_node(SECOND, "IC_9"),
                        ],
                        edge="trigger",
                    )
                ),
                subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr="gh: fail"
                ),
            ]
        )
        self.assertEqual(tuple(bounds), ("", "", "", ""))
        self.assertEqual(len(calls), 2)

    def test_legacy_caller_without_collect_never_continues(self):
        # Given: the round-20 zero-repin rule — a LEGACY 3-arg caller
        # (collect None) reads the straddling window directly, the
        # shape that would paginate if the continuation ignored the
        # collect param. When: trigger_comment_marker runs with the
        # subprocess seam rigged to FAIL any dispatch. Then: the
        # in-page newest's identity returns with ZERO subprocesses —
        # the continuation exists only to fill the collect set. Green
        # on BOTH sides of the round-21 change.
        node = round_page(
            trigger=[trigger_node(SECOND, "IC_2"), trigger_node(SECOND, "IC_9")],
            edge="trigger",
        )["data"]["repository"]["pullRequest"]
        with mock.patch.object(
            pr_guard_reaction_probe.subprocess,
            "run",
            side_effect=AssertionError("legacy 3-arg caller must not paginate"),
        ):
            marker = pr_guard_reaction_probe.trigger_comment_marker(node, 48, None)
        self.assertEqual(marker, f"{SECOND}|IC_9")


if __name__ == "__main__":
    unittest.main()
