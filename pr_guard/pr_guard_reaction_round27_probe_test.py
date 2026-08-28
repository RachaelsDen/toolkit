"""pr_guard reaction round-27 probe tests (PR #49 thread 3874769245
P1, the probe half): the base facts join ROUND_QUERY / round_bounds
/ the Reading — the pair split's probe half (the wait halves live in
pr_guard_reaction_round27_test / _wait_test).

Thread 3874769245: the base identity rides the round facts as
RoundBounds/.Reading attrs (the zero-repin seam rule — every legacy
plain-tuple fixture stays equal): `.base` is baseRefOid (an OID,
never the mutable ref NAME) and `.base_bound` is the base's OWN
boundary timestamp — max(base target pushedDate/committedDate, the
latest BaseRefChangedEvent createdAt). LIVE-VERIFIED read-only
2026-08-27: baseRefOid + baseRef.target stamps exist on PullRequest
(the live base's pushedDate reads NULL — the committedDate fallback
is live-relevant, the head's round-3 shape); BASE_REF_CHANGED_EVENT
is a valid PullRequestTimelineItemsItemType whose shape materializes
(microsoft/vscode#101656) while PR #49 itself carries ZERO events
(the live present-and-empty connection shape these fixtures mirror).

Shape rules pinned here (the round-15/25 absent/present-null
doctrine): an ABSENT baseRefOid/baseRef/baseChange key is the legacy
minimal-payload page (no base tracking, probe READABLE — the wait's
'' never certifies a change); a PRESENT-but-null/malformed
connection or target is the partial-error class (the whole probe
reads the all-empty unreadable bounds — a missing base fact must
never bias a completion toward done).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round27_probe_test -v
"""

import json
import subprocess
import unittest
from unittest import mock

from . import pr_guard_reaction
from . import pr_guard_reaction_probe

BOT_LOGIN = pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN
HEAD_S = "20ab97ffffffffffffffffffffffffffffff5"
BASE_2 = "30ab97ffffffffffffffffffffffffffffff2"
EMPTY = ("", "", "", "")


def gh_page(pr_node):
    return subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=json.dumps({"data": {"repository": {"pullRequest": pr_node}}}),
    )


def base_page(base=None, target=None, event=None, carry_head=True):
    """A well-formed ROUND_QUERY page; base None keeps baseRefOid/
    baseRef/baseChange ABSENT (the legacy minimal-payload shape);
    target/event None keep their keys present-but-empty when base
    is given (the live PR #49 shape)."""
    pr = {
        "headRefOid": HEAD_S,
        "headRef": {"target": {"pushedDate": "2023-11-14T22:13:21Z", "committedDate": "2023-11-14T22:13:21Z"}},
        "timelineItems": {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": [],
        },
        "headTransition": {"nodes": []},
        "latestReviews": {"nodes": []},
        "reviewThreads": {"nodes": []},
    }
    if not carry_head:
        del pr["headRefOid"]
        del pr["headRef"]
    if base is not None:
        pr["baseRefOid"] = base
        if target is not None:
            pr["baseRef"] = {"target": target}
        pr["baseChange"] = {"nodes": [{"createdAt": event}] if event else []}
    return pr


def run_bounds(pages):
    script = iter(pages)
    with mock.patch.object(
        pr_guard_reaction_probe.subprocess,
        "run",
        side_effect=lambda *a, **k: gh_page(next(script)),
    ):
        return pr_guard_reaction_probe.round_bounds(48, None)


class BaseFactsParseTests(unittest.TestCase):
    def test_base_oid_and_bound_parse_with_event_max(self):
        # Given: a retargeted PR's page — baseRefOid base_2, the base
        # target carrying pushedDate NULL with committedDate fallback
        # 22:00 (the live shape), and a BaseRefChangedEvent createdAt
        # 22:13:22 (the retarget — the boundary's own timestamp).
        # When: round_bounds parses the page. Then: readable bounds
        # whose .base names base_2 and .base_bound is the EVENT's
        # createdAt (max(22:00, 22:13:22) — the headTransition
        # pattern applied to the base stream), with the plain-4-tuple
        # equality intact (the zero-repin seam rule).
        bounds = run_bounds([base_page(base=BASE_2, target={"pushedDate": None, "committedDate": "2023-11-14T22:00:00Z"}, event="2023-11-14T22:13:22Z")])
        self.assertEqual(bounds[0], HEAD_S)
        self.assertEqual(bounds, (HEAD_S, "2023-11-14T22:13:21Z", "", ""))
        self.assertEqual(bounds.base, BASE_2)
        self.assertEqual(bounds.base_bound, "2023-11-14T22:13:22Z")

    def test_base_tip_advance_bound_is_the_targets_own_stamp(self):
        # Given: the tip-advance shape — baseRefOid base_2, NO
        # BaseRefChangedEvent (the base BRANCH moved, not the PR's
        # retarget), the new tip's own committedDate 22:13:23 with
        # pushedDate null. When: round_bounds parses the page. Then:
        # .base names base_2 and .base_bound is the target's OWN
        # stamp (22:13:23 — the only verifiable boundary for a tip
        # advance; no PR timeline event exists, the round-17 FF
        # posture's kin).
        bounds = run_bounds([base_page(base=BASE_2, target={"pushedDate": None, "committedDate": "2023-11-14T22:13:23Z"})])
        self.assertEqual(bounds.base, BASE_2)
        self.assertEqual(bounds.base_bound, "2023-11-14T22:13:23Z")

    def test_absent_base_keys_read_legacy_and_readable(self):
        # Given: the legacy minimal-payload page — baseRefOid,
        # baseRef, and baseChange ALL ABSENT (every pre-round-27
        # fixture's shape). When: round_bounds parses the page. Then:
        # the probe stays READABLE (index 0 carries the head) and the
        # attrs read the '' fallbacks — '' never certifies a base
        # change, the zero-repin seam rule for the wait.
        bounds = run_bounds([base_page()])
        self.assertEqual(bounds[0], HEAD_S)
        self.assertEqual(bounds.base, "")
        self.assertEqual(bounds.base_bound, "")

    def test_present_but_null_base_facts_read_unreadable(self):
        # Given: the partial-error shapes — a present-but-null
        # baseChange connection, a null baseRef target, and a null
        # baseRef. When: round_bounds parses each. Then: the
        # all-empty unreadable bounds every time — a success
        # response always materializes the requested aliases, so a
        # missing base fact is a PARTIAL response (the whole probe
        # retries), never a readable history whose absent base could
        # bias a completion toward done.
        for pr in (
            {"baseRefOid": BASE_2, "baseChange": None},
            {"baseRefOid": BASE_2, "baseRef": {"target": None}, "baseChange": {"nodes": []}},
            {"baseRefOid": BASE_2, "baseRef": None, "baseChange": {"nodes": []}},
        ):
            page = base_page()
            page.update(pr)
            self.assertEqual(run_bounds([page]), EMPTY)

    def test_reading_carries_the_base_attrs(self):
        # Given: a readable page carrying the base facts, with the
        # bot's EYES as the latest reaction and the stable head on
        # both bracket sides. When: bot_reaction_reading runs over
        # the REAL round_bounds. Then: the Reading subclass carries
        # .base/.base_bound beside its plain-8-tuple equality — the
        # wait's zero-repin consumption seam (getattr fallbacks).
        reactions = [{"content": "eyes", "created_at": "2023-11-14T22:13:22Z", "id": 5, "user": {"login": pr_guard_reaction.REACTION_BOT}}]
        with mock.patch.object(
            pr_guard_reaction, "gh_reactions", return_value=reactions
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=HEAD_S
        ), mock.patch.object(
            pr_guard_reaction_probe.subprocess, "run",
            return_value=gh_page(base_page(base=BASE_2, target={"pushedDate": None, "committedDate": "2023-11-14T22:13:23Z"})),
        ):
            reading = pr_guard_reaction.bot_reaction_reading(48)
        self.assertEqual(reading[0], pr_guard_reaction.REACTION_ACTIVE)
        self.assertEqual(reading.base, BASE_2)
        self.assertEqual(reading.base_bound, "2023-11-14T22:13:23Z")


if __name__ == "__main__":
    unittest.main()
