"""pr_guard reaction round-20 probe tests (PR #49 threads 3872194007
P2 / 3872194023 P1) — the full-identity collects + the verdict stamp
at the ROUND_BOUNDS seam.

3872194007 — the walk-level half of the full-identity seen-sets:
the boundary walks deposit EVERY visible same-second identity at
the high-water second into their collect sets (identities at OLDER
seconds stay unrecorded — they are not visible through the stream),
and round_bounds carries the sets out as .request_ids/.trigger_ids
beside the per-kind stream identities. The wait-side consumption
(the union + the never-readvancing resurfacing) lives in
pr_guard_reaction_round20_test.

3872194023 — the fold-level half of the review-state bind: the
author-filtered botReviews node now carries submittedAt (live-
verified 2026-08-27 read-only on PR #49: the field rides beside
commit.oid), and round_bounds extracts it as .review_stamp with the
same ''/None shape contract as the oid (the round-17 evidence
rules): '' when no bot review exists or the key is absent (the
legacy minimal-payload page — never evidence, the caller withholds),
None never escaping round_bounds (a present-but-null connection is
the round-15 partial-error class: the WHOLE probe retries).

No network: REAL round_bounds over in-memory pr_node pages (the
round-17 evidence-test shape — no subprocess script needed; the
walks answer from the newest-50 window, hasPreviousPage False).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round20_probe_test -v
"""

import json
import subprocess as sp
import unittest
from unittest import mock

from . import pr_guard_reaction
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock

BOT_LOGIN = pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN

SECOND = "2026-08-01T00:05:00Z"
OLDER = "2026-08-01T00:04:00Z"
REQ_SECOND = "2026-08-02T00:00:00Z"
STAMP = "2026-08-02T00:00:05Z"
OID = "21ab97ffffffffffffffffffffffffffffffb"


def trigger_node(created, node_id):
    return {"createdAt": created, "id": node_id, "body": "@codex review"}


def req_node(created, node_id):
    return {"createdAt": created, "id": node_id, "requestedReviewer": {"login": BOT_LOGIN}}


def bot_node(at=STAMP, oid=OID):
    return {"author": {"login": BOT_LOGIN}, "commit": {"oid": oid}, "submittedAt": at}


def pr_node(request=(), trigger=None, review=None):
    """A well-formed ROUND_QUERY pullRequest node; trigger/review
    None keep their keys ABSENT (the legacy minimal-payload rule)."""
    node = {
        "headRefOid": "21ab97ffffffffffffffffffffffffffffff0",
        "headRef": {"target": {"pushedDate": "2026-08-01T00:00:00Z"}},
        "timelineItems": {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": list(request),
        },
        "headTransition": {"nodes": []},
        "latestReviews": {"nodes": []},
        "reviewThreads": {"nodes": []},
    }
    if trigger is not None:
        node["triggerComments"] = {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": list(trigger),
        }
    if review is not None:
        node["botReviews"] = {"nodes": list(review)}
    return node


def run_bounds(node):
    # REAL round_bounds over an in-memory pr_node: the one scripted
    # ROUND_QUERY page answers every walk from the newest-50 window
    # (hasPreviousPage False — no pagination), on the FakeClock.
    page = {"data": {"repository": {"pullRequest": node}}}
    proc = sp.CompletedProcess(args=[], returncode=0, stdout=json.dumps(page))
    with mock.patch.object(
        pr_guard_reaction_probe.subprocess, "run", return_value=proc
    ), mock.patch.object(pr_guard_reaction, "time", FakeClock()):
        return pr_guard_reaction.round_bounds(48, timeout_secs=None)


class FullIdentityCollectTests(unittest.TestCase):
    def test_trigger_collect_records_the_high_water_second_only(self):
        # Given: a newest-50 trigger window carrying an OLDER-second
        # comment (IC_1 at 00:04) BESIDE the high-water second's pair
        # (IC_2 then IC_9, chronological — IC_9 the newest, the
        # stream). When: round_bounds reads the page (REAL walks, the
        # newest-50 window answers — hasPreviousPage False). Then:
        # the stream identity is the newest (IC_9), and the collect
        # set carries EVERY identity of the high-water second — IC_2
        # AND IC_9 — while the OLDER second's IC_1 stays unrecorded
        # (it is not visible through the stream; its resurfacing is
        # the mirror direction the round-17 compare already blocks);
        # the pre-fix modules returned only markers[-1] and the attrs
        # did not exist (AttributeError — the round-15 precedent).
        bounds = run_bounds(pr_node(trigger=[trigger_node(OLDER, "IC_1"), trigger_node(SECOND, "IC_2"), trigger_node(SECOND, "IC_9")]))
        self.assertEqual(bounds.trigger, f"{SECOND}|IC_9")
        self.assertEqual(bounds.trigger_ids, {f"{SECOND}|IC_2", f"{SECOND}|IC_9"})
        self.assertNotIn(f"{OLDER}|IC_1", bounds.trigger_ids)

    def test_request_collect_and_review_stamp_ride_the_bounds(self):
        # Given: a window carrying TWO same-second codex requests
        # (RA_a then RA_z, chronological — RA_z the newest) beside a
        # folded bot review carrying commit.oid AND submittedAt (the
        # round-20 ROUND_QUERY node shape). When: round_bounds reads
        # the page. Then: the request stream is RA_z's identity, the
        # collect set carries BOTH same-second request identities
        # (the per-kind discipline — the request twin of the trigger
        # fill), and the folded evidence rides BOTH attrs — the oid
        # (round 17/18) and the NEW verdict stamp; the merged
        # boundary (index 2) is the request identity alone (the
        # trigger kind reads '' — no triggerComments key).
        bounds = run_bounds(
            pr_node(
                request=[req_node(REQ_SECOND, "RA_a"), req_node(REQ_SECOND, "RA_z")],
                review=[bot_node()],
            )
        )
        self.assertEqual(bounds.request, f"{REQ_SECOND}|RA_z")
        self.assertEqual(bounds.request_ids, {f"{REQ_SECOND}|RA_a", f"{REQ_SECOND}|RA_z"})
        self.assertEqual(bounds.review_head, OID)
        self.assertEqual(bounds.review_stamp, STAMP)
        self.assertEqual(bounds[2], f"{REQ_SECOND}|RA_z")

    def test_review_stamp_absent_and_human_shapes_read_empty(self):
        # Given: the '' stamp shapes — a page with NO botReviews key
        # (the legacy minimal-payload fixture) and a page whose
        # botReviews carries only a HUMAN review (the author filter's
        # client-side backstop). When: round_bounds reads each. Then:
        # both read review_stamp '' (and review_head '') — never
        # evidence, the caller withholds — and the probe stays
        # READABLE (the round-17 empty-nodes rule; only a
        # present-but-NULL connection is the partial-error class).
        for node in (
            pr_node(),
            pr_node(review=[{"author": {"login": "some-human"}, "submittedAt": STAMP, "commit": {"oid": OID}}]),
        ):
            bounds = run_bounds(node)
            self.assertEqual(bounds.review_stamp, "")
            self.assertEqual(bounds.review_head, "")


class RoundQuerySyntaxTests(unittest.TestCase):
    def test_round_query_braces_balance(self):
        # Given: the assembled ROUND_QUERY string (a multi-line
        # implicit-concatenation literal edited across rounds). When:
        # every brace is counted with a floor guard. Then: the depth
        # never dips below zero mid-string and ends at exactly zero —
        # the round-20 live incident class (the submittedAt edit
        # shipped one extra RCURLY, every live probe read UNREADABLE
        # for a full 600s wait, while the mocked-subprocess suites
        # stayed 473-green: a query-string syntax break is invisible
        # to every seam that mocks gh).
        depth = 0
        for ch in pr_guard_reaction_probe.ROUND_QUERY:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                self.assertGreaterEqual(depth, 0, pr_guard_reaction_probe.ROUND_QUERY)
        self.assertEqual(depth, 0)


if __name__ == "__main__":
    unittest.main()
