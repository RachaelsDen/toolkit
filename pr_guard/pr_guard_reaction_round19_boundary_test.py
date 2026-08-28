"""pr_guard reaction round-19 boundary tests (PR #49 thread 3871844576
P2) — the boundary identity SETS.

3871844576 — "Remember all same-second boundary identities": each
boundary kind retained only ONE identity (the latest), so when two
manual-trigger comments share a timestamp second and the NEWER
visible comment is later deleted or temporarily omitted, the older
comment RESURFACES with a different node id and request_advances'
same-second DISTINCTNESS rule classified it as a new forward
boundary — a SPURIOUS round reset that held the current round's
valid completion to timeout, and visibility oscillation repeated the
reset. Round 19 retains, per kind, the SET of every boundary
identity any probe has seen (the walk's latest-per-probe stream
accumulates into it): an advance requires an identity NOT in the
seen-set passing the round-17 identity compare (strictly-newer
createdAt OR a same-second distinct node id) — a resurfacing
identity was recorded when previously visible, so it NEVER reads as
an advance, while a genuinely-new same-second boundary (round-17's
core race) still does. The high-water only moves on unseen
identities now (an in-seen resurfacing never regresses it), and the
reset + gate re-close wiring is unchanged — it fires exactly when a
kind GENUINELY advances.

No network: the wait test runs REAL round_bounds over scripted
ROUND_QUERY pages (the round-18 run_wait_real_bounds shape — the
per-kind trigger identities must ride the REAL probe through the
RoundBounds attrs); the truth table exercises the latch predicate
directly. FakeClock WALL_NOW 2023-11-14T22:13:20Z; the trigger
EYES/+1 stamps postdate the wall (the request floor never demotes
them — the t=10 EYES 2026-08-25 > the t=5 stamp 2023-11-14T22:13:25Z).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round19_boundary_test -v
"""

import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_latch
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock

BOT = pr_guard_reaction.REACTION_BOT

HEAD = "14ab97fffffffffffffffffffffffffffffff"

# The same-second trigger pair (thread 3871844576): IC_2 the older
# comment, IC_9 the newer — both inside second S.
SECOND = "2026-08-01T00:05:00Z"
T1 = f"{SECOND}|IC_2"
T2 = f"{SECOND}|IC_9"
T3 = f"{SECOND}|IC_z"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def gh_page(payload):
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(payload)
    )


def trigger_node(created, node_id):
    return {"createdAt": created, "id": node_id, "body": "@codex review"}


def bounds_page(pushed, oid, trigger, review=None):
    """A well-formed ROUND_QUERY page carrying only the trigger
    boundary (the request walk reads an empty history); review None
    keeps botReviews ABSENT (the round-22 fixture-seam rule: the
    completing round's pages carry the folded evidence)."""
    page = {
        "data": {
            "repository": {
                "pullRequest": {
                    "headRefOid": oid,
                    "headRef": {"target": {"pushedDate": pushed, "committedDate": pushed}},
                    "timelineItems": {
                        "pageInfo": {"hasPreviousPage": False, "startCursor": None},
                        "nodes": [],
                    },
                    "triggerComments": {
                        "pageInfo": {"hasPreviousPage": False, "startCursor": None},
                        "nodes": list(trigger),
                    },
                    "headTransition": {"nodes": []},
                    "latestReviews": {"nodes": []},
                    "reviewThreads": {"nodes": []},
                }
            }
        }
    }
    if review is not None:
        page["data"]["repository"]["pullRequest"]["botReviews"] = {
            "nodes": [review]
        }
    return page


def run_wait(reads, pages, timeout_secs):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    pages (the round-18 shape) on a stable head."""
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


class ResurfacingBoundaryTests(unittest.TestCase):
    def test_resurfaced_seen_identity_never_readvances(self):
        # Given: the thread-3871844576 race — t=0 the older trigger
        # T1 (IC_2) is the visible boundary (the seen-set records
        # it) and the round's verified EYES (2026-08-02, past the
        # shared second) arms; t=5 the newer trigger T2 (IC_9, same
        # second) posts — a GENUINE advance (unseen identity, same-
        # second distinct node id) — while the old job sits in its
        # EYES-removal/+1 switch (NONE); t=10 the NEW round's EYES
        # (2026-08-25) arms on the T2 boundary; t=12 the new round
        # completes EYES->+1 ENTIRELY between probes; t=15 the +1
        # (2026-08-26T14, following the EYES watermark — a VALID
        # completion) lands while T2 is TEMPORARILY OMITTED and T1
        # RESURFACES with its different node id. When: wait polls
        # 20s. Then: exit 0 at 15s with exactly ONE ROUND RE-REQUESTED
        # — T1 is IN the seen-set (recorded at t=0), so the
        # resurfacing never advances and the valid completion
        # exits; the pre-fix single-identity retention compared T1
        # against the T2 high-water (same second, distinct id) and
        # fired a SPURIOUS second reset at t=15 that cleared the
        # armed latch/watermark, held the +1 to a HOLD, and exited 1
        # at the 20s timeout with the completion withheld. ROUND 22:
        # the completion's pages (t=15 on) carry the folded review
        # evidence (2026-08-26T13:00, past the T2 boundary SECOND and
        # before the +1) — the evidence leg post-advance completions
        # now require.
        new_review = {
            "author": {"login": pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN},
            "commit": {"oid": HEAD},
            "submittedAt": "2026-08-26T13:00:00Z",
        }
        code, out = run_wait(
            [
                [react("eyes", "2026-08-02T00:00:00Z", 5)],
                [],
                [react("eyes", "2026-08-25T00:00:00Z", 7)],
                [react("+1", "2026-08-26T14:00:00Z", 8)],
                [react("+1", "2026-08-26T14:00:00Z", 8)],
            ],
            [
                bounds_page("2026-08-01T00:00:00Z", HEAD, [trigger_node(SECOND, "IC_2")]),
                bounds_page("2026-08-01T00:00:00Z", HEAD, [trigger_node(SECOND, "IC_9")]),
                bounds_page("2026-08-01T00:00:00Z", HEAD, [trigger_node(SECOND, "IC_9")]),
                bounds_page("2026-08-01T00:00:00Z", HEAD, [trigger_node(SECOND, "IC_2")], new_review),
                bounds_page("2026-08-01T00:00:00Z", HEAD, [trigger_node(SECOND, "IC_2")], new_review),
            ],
            20,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 15s", out)

    def test_boundary_advances_truth_table(self):
        # Given: the seen-set compare's shapes (thread 3871844576
        # over the round-17 identity rule). When: boundary_advances
        # evaluates them. Then: an identity IN the seen-set never
        # advances — even resurfacing against a different
        # high-water, even same-second distinct (the fix); an
        # UNSEEN identity advances on strictly-newer createdAt OR a
        # same-second distinct node id (round-17's core race
        # preserved); '' never advances; any first-ever boundary
        # against '' advances (the baseline rule stays in the
        # wait's readable_probe_seen).
        adv = pr_guard_reaction_latch.boundary_advances
        seen = {T1, T2}
        self.assertFalse(adv(T1, T2, seen))
        self.assertFalse(adv(T2, T2, seen))
        self.assertTrue(adv(T3, T2, seen))
        self.assertTrue(adv(T1, T2, set()))
        self.assertTrue(adv("2026-08-02T00:00:00Z|IC_a", T2, seen))
        self.assertFalse(adv("", T2, seen))
        self.assertTrue(adv(T2, "", set()))


if __name__ == "__main__":
    unittest.main()
