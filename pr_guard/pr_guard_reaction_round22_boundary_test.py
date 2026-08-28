"""pr_guard reaction round-22 boundary tests — the MONOTONE
HIGH-WATERS (PR #49 thread 3872980771 P2: "Keep boundary high-water
marks monotonic").

The per-kind retention update assigned EVERY unseen identity
directly to the high-water: when the newest trigger comment (or
formal request) is deleted or temporarily omitted, an older
previously-UNSEEN boundary became the stream and REGRESSED the
high-water even though boundary_advances had correctly rejected it
as older — so a later boundary resurfacing BETWEEN the regressed
value and the true newest misclassified as a FORWARD advance
(unseen, strictly-newer than the regressed water), fired a spurious
ROUND RE-REQUESTED reset, and withheld a valid completion to
timeout. The retention now records an unseen identity in the
seen-set but advances the high-water ONLY when boundary_advances
ACCEPTED it (or the first readable probe initializes the baseline)
— both kinds, symmetrically.

No network: the fixtures run REAL round_bounds over scripted
ROUND_QUERY pages (the round-18/19/20/21 shape), one class per kind
(the two retention branches are symmetric but distinct code).
FakeClock WALL_NOW 2023-11-14T22:13:20Z.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round22_boundary_test -v
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

HEAD = "20ab97ffffffffffffffffffffffffffffff9"
PUSH = "2023-11-14T22:00:00Z"

# The oscillating boundary triple: NEWEST (the baseline the first
# probe records), OLDER (unseen — becomes the stream when NEWEST is
# deleted, the pre-fix regression), MID (unseen — newer than OLDER
# but older than NEWEST; the counterfeit forward advance pre-fix).
NEWEST_AT = "2023-11-14T22:13:19Z"
OLDER_AT = "2023-11-14T22:13:17Z"
MID_AT = "2023-11-14T22:13:18Z"
EYES_AT = "2023-11-14T22:13:18Z"
PLUS_AT = "2023-11-14T22:13:26Z"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def gh_page(payload):
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(payload)
    )


def trigger_node(created, node_id):
    return {"createdAt": created, "id": node_id, "body": "@codex review"}


def req_node(created, node_id):
    return {"createdAt": created, "id": node_id, "requestedReviewer": {"login": BOT_LOGIN}}


def bounds_page(boundary_nodes, on_trigger, review=None):
    """A well-formed ROUND_QUERY page whose ONLY boundary rides the
    triggerComments connection (on_trigger) or timelineItems (the
    formal-request twin). (PR #49 round 25 fixture-seam maintenance,
    thread 3873970933: an optional folded botReviews node — the
    completing probe's evidence names the stable head, which
    cold-start completions now require even with no advance; the
    pre-round-25 'no advance -> no evidence leg' rationale is
    superseded.)"""
    node = {
        "headRefOid": HEAD,
        "headRef": {"target": {"pushedDate": PUSH, "committedDate": PUSH}},
        "timelineItems": {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": [] if on_trigger else list(boundary_nodes),
        },
        "headTransition": {"nodes": []},
        "latestReviews": {"nodes": []},
        "reviewThreads": {"nodes": []},
    }
    if on_trigger:
        node["triggerComments"] = {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": list(boundary_nodes),
        }
    if review is not None:
        node["botReviews"] = {"nodes": [review]}
    return {"data": {"repository": {"pullRequest": node}}}


def run_wait_pages(reads, pages, timeout_secs):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    pages; a stable head (the race is retention-only)."""
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


def assert_monotonic_retention(testcase, newest, older, mid, on_trigger):
    # Given: the thread-3872980771 oscillation — t=0 the NEWEST
    # boundary is the visible stream (the first readable probe
    # records the BASELINE — no reset, no floor); t=5 the round's
    # verified EYES (22:13:18, past the push) arms while the NEWEST
    # boundary is DELETED and the older previously-UNSEEN boundary is
    # the stream (boundary_advances correctly rejects it as OLDER);
    # t=10 the passing +1 (22:13:26, following the EYES watermark —
    # a VALID completion) lands while a MID boundary (newer than the
    # regressed value, older than the true newest) resurfaces. When:
    # wait polls 10s. Then: exit 0 at 10s with ZERO ROUND RE-REQUESTED
    # — the unseen-older identity RECORDS in the seen-set but never
    # regresses the high-water, so the MID resurfacing compares
    # against the retained NEWEST (older — no advance) and the
    # completion exits; the pre-fix retention assigned the older
    # identity directly to the high-water, the MID resurfacing then
    # misread as a forward advance, and the spurious reset held the
    # valid completion to timeout (the pre-fix proof: exit 1). (The
    # completing probe's folded evidence names the stable head — the
    # round-25 cold-start leg, thread 3873970933.)
    completing_review = {
        "author": {"login": BOT_LOGIN},
        "commit": {"oid": HEAD},
        "submittedAt": "2023-11-14T22:13:22Z",
    }
    code, out = run_wait_pages(
        [
            [],
            [react("eyes", EYES_AT, 5)],
            [react("+1", PLUS_AT, 6)],
        ],
        [
            bounds_page([newest], on_trigger),
            bounds_page([older], on_trigger),
            bounds_page([mid], on_trigger, review=completing_review),
        ],
        10,
    )
    testcase.assertEqual(code, 0)
    testcase.assertEqual(out.count("ROUND RE-REQUESTED"), 0)
    testcase.assertIn("WAIT DONE: THUMBS_UP at 10s", out)


class MonotonicTriggerHighWaterTests(unittest.TestCase):
    def test_deleted_newest_older_unseen_never_regresses(self):
        # The TRIGGER kind: the newest trigger comment is deleted and
        # an older previously-unseen comment becomes the stream.
        assert_monotonic_retention(
            self,
            trigger_node(NEWEST_AT, "IC_3"),
            trigger_node(OLDER_AT, "IC_2"),
            trigger_node(MID_AT, "IC_2b"),
            on_trigger=True,
        )


class MonotonicRequestHighWaterTests(unittest.TestCase):
    def test_deleted_newest_older_unseen_never_regresses(self):
        # The REQUEST twin (the finding names both kinds): the
        # newest formal request is deleted and an older
        # previously-unseen request becomes the stream.
        assert_monotonic_retention(
            self,
            req_node(NEWEST_AT, "RA_3"),
            req_node(OLDER_AT, "RA_2"),
            req_node(MID_AT, "RA_2b"),
            on_trigger=False,
        )


if __name__ == "__main__":
    unittest.main()
