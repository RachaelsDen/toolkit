"""pr_guard reaction round-29 tests (PR #49 thread 3875352284 P1):
the base tip's force-update bound — BASE_REF_FORCE_PUSHED_EVENT's own
createdAt MAXes into base_bound, closing the old-commit fallback race.

The race — "Bind base-tip force updates to their ref-move time": a
base branch force-updated to an EXISTING OLDER commit changes
baseRefOid with NO BaseRefChangedEvent (the PR was not retargeted),
while round 27's fallback bound read that commit's OLD committedDate
(pushedDate is null on the live base) — an old-base review submitting
after the old stamp but before the force-update passed
`review_stamp > base_floor`, and its delayed EYES/+1 arriving
post-change re-armed the reset base and exited WAIT DONE over a
re-derived diff nobody reviewed.

LIVE-VERIFIED read-only 2026-08-27 (the round-15/18/20/27 precedent,
BEFORE coding): PullRequestTimelineItemsItemType carries
BASE_REF_FORCE_PUSHED_EVENT (beside BASE_REF_CHANGED_EVENT,
BASE_REF_DELETED_EVENT, AUTOMATIC_BASE_CHANGE_SUCCEEDED_EVENT,
AUTOMATIC_BASE_CHANGE_FAILED_EVENT, AUTO_REBASE_ENABLED_EVENT; there
is NO BaseRefRestoredEvent); the node carries createdAt/id/ref/
pullRequest/beforeCommit/afterCommit and POSITIVELY materializes on
real PRs whose base branch was force-pushed while open (nodejs/node
#60801: createdAt 2026-07-29T14:04:33Z, baseRefOid == afterCommit
.oid, pushedDate null; a five-PR electron mass-carrier set at
2022-11-12T01:49:2xZ; PR #49 itself carries zero events). The fix is
the boundary's OWN timestamp (the round-20/22/26 doctrine — the
reviewer-sanctioned observation-floor fallback is NOT needed): the
new baseForce connection MAXes its createdAt into base_bound, so
base_floor postdates every pre-update review by construction and a
post-update round's own review submits past the event and completes
(no false hold, no observation clock). Documented residue: a
FAST-FORWARD base advance (no force event, the round-15 head
doctrine) whose fresh tip carries an OLD committedDate with
pushedDate null keeps the round-27 honest-documentation posture.

No network: REAL round_bounds/wait_reaction over scripted
ROUND_QUERY pages (the round-27/28 shape). FakeClock WALL_NOW
2023-11-14T22:13:20Z; the stamps keyed INSIDE the wall window (the
round-19 GOTCHA #2 rule).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round29_test -v
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

HEAD_S = "20ab97ffffffffffffffffffffffffffffff5"
BASE_1 = "30ab97ffffffffffffffffffffffffffffff1"
BASE_0 = "30ab97ffffffffffffffffffffffffffffff0"

PUSH_A = "2023-11-14T22:00:00Z"
BASE_1_TIP = "2023-11-14T22:13:18Z"
BASE_0_DATE = "2023-11-14T21:50:00Z"
BASE_FORCE = "2023-11-14T22:13:24Z"

EMPTY = ("", "", "", "")


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def gh_page(payload):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload))


def bot_node(oid, at):
    return {"author": {"login": BOT_LOGIN}, "commit": {"oid": oid}, "submittedAt": at}


def bounds_page(pushed, oid, review=None, base=None, base_stamp=None, base_force=None):
    """A well-formed ROUND_QUERY page; review/base* None keep their keys
    ABSENT (the round-18/27 legacy-minimal-payload rule); base carries
    baseRefOid + the live present-and-empty baseChange connection with
    the target's committedDate (pushedDate null — the live base shape);
    base_force adds the BaseRefForcePushedEvent node (round 29)."""
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
                    "headTransition": {"nodes": []},
                    "latestReviews": {"nodes": []},
                    "reviewThreads": {"nodes": []},
                }
            }
        }
    }
    pr = page["data"]["repository"]["pullRequest"]
    if review is not None:
        pr["botReviews"] = {"nodes": [review]}
    if base is not None:
        pr["baseRefOid"] = base
        pr["baseRef"] = {"target": {"pushedDate": None, "committedDate": base_stamp}}
        pr["baseChange"] = {"nodes": []}
        if base_force is not None:
            pr["baseForce"] = {"nodes": [{"createdAt": base_force}]}
    return page


def run_wait(reads, pages, heads, timeout_secs):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    pages (the round-27/28 shape); heads scripts head_ref_oid per probe
    (the bracket's BEFORE side — always the stable head S)."""
    clock = FakeClock()
    items = iter(reads)
    script = iter(pages)
    head_reads = iter(heads)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_read
    ), mock.patch.object(
        pr_guard_reaction,
        "head_ref_oid",
        side_effect=lambda pr, timeout_secs=None: next(head_reads),
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


def round_node(base_stamp=None, base_force="ABSENT"):
    """A well-formed non-paginating ROUND_QUERY pr node for the direct
    round_bounds parse tests; base_stamp None omits every base key (the
    bare-oid legacy page); base_force ABSENT omits the baseForce key,
    None makes it PRESENT-but-null (the partial-error shape), a stamp
    adds the event node."""
    pr = {
        "headRefOid": HEAD_S,
        "headRef": {"target": {"pushedDate": PUSH_A, "committedDate": PUSH_A}},
        "timelineItems": {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": [],
        },
        "triggerComments": {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": [],
        },
        "headTransition": {"nodes": []},
        "latestReviews": {"nodes": []},
        "reviewThreads": {"nodes": []},
    }
    if base_stamp is not None:
        pr["baseRefOid"] = BASE_0
        pr["baseRef"] = {"target": {"pushedDate": None, "committedDate": base_stamp}}
        pr["baseChange"] = {"nodes": []}
        if base_force == "ABSENT":
            return pr
        pr["baseForce"] = (
            None if base_force is None else {"nodes": [{"createdAt": base_force}]}
        )
    return pr


def run_bounds(pages):
    """REAL round_bounds over scripted subprocess pages with the
    head_ref_oid seam MOCKED (the round-28 FOLD pin: round_bounds must
    never call it); (bounds, head-call-count)."""
    script = iter(pages)
    head = mock.Mock(return_value=HEAD_S)
    with mock.patch.object(
        pr_guard_reaction_probe.subprocess,
        "run",
        side_effect=lambda *a, **k: gh_page(
            {"data": {"repository": {"pullRequest": next(script)}}}
        ),
    ), mock.patch.object(pr_guard_reaction_probe, "head_ref_oid", head):
        return pr_guard_reaction_probe.round_bounds(48, timeout_secs=None), head.call_count


class ForceUpdatedBaseTests(unittest.TestCase):
    def test_force_updated_base_old_base_verdict_withheld(self):
        # Given: the thread-3875352284 race — the wait starts under the
        # old-base job's EYES (created 22:13:19, base_1's tip committed
        # 22:13:18); between t=0 and t=5 the base branch is FORCE-UPDATED
        # to an existing OLDER commit (base_0, committedDate 21:50 —
        # pushedDate null, the live base shape; a BaseRefForcePushedEvent
        # at 22:13:24 is the ref's ACTUAL move time; NO BaseRefChangedEvent
        # — the PR was never retargeted) while the old-base job submits
        # review(S) at 22:13:21 (BEFORE the force-update, over base_1's
        # diff) and its delayed +1 lands 22:13:28. When: wait polls 10s.
        # Then: exit 1 — the t=5 probe's base-change reset re-arms on the
        # persisting EYES, and base_floor = max(21:50, the event 22:13:24)
        # withholds the stamp leg BY NAME (21 > 24 fails); the pre-fix
        # bound was the old commit's OWN committedDate (the finding's
        # indicted fallback), the old-base review postdated it
        # (22:13:21 > the cold-start floor 22:13:18), and WAIT DONE
        # exited 0 over the re-derived diff nobody reviewed (the
        # pre-fix proof: 0 != 1, WAIT DONE).
        code, out = run_wait(
            [
                [react("eyes", "2023-11-14T22:13:19Z", 5)],
                [react("eyes", "2023-11-14T22:13:19Z", 5)],
                [react("+1", "2023-11-14T22:13:28Z", 7)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S, base=BASE_1, base_stamp=BASE_1_TIP),
                bounds_page(
                    PUSH_A, HEAD_S, base=BASE_0, base_stamp=BASE_0_DATE,
                    base_force=BASE_FORCE,
                ),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:21Z"),
                    base=BASE_0, base_stamp=BASE_0_DATE, base_force=BASE_FORCE,
                ),
            ],
            [HEAD_S, HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("BASE CHANGED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("3875352284", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_force_updated_base_new_round_completes(self):
        # Given: the SURVIVOR — the identical force-update (base_0, the
        # event at 22:13:24 observed by the t=5 probe), but the NEW-base
        # round runs: EYES 22:13:25, review(S) submitted 22:13:27 (PAST
        # the event floor), +1 22:13:29. When: wait polls 10s. Then:
        # exit 0 at 10s on BOTH sides (the pre-fix floor 22:13:18
        # completed it too) — the pin that the event floor strands NO
        # post-update round (the boundary's OWN timestamp, never an
        # observation clock: no false-hold price is paid).
        code, out = run_wait(
            [
                [react("eyes", "2023-11-14T22:13:19Z", 5)],
                [react("eyes", "2023-11-14T22:13:25Z", 6)],
                [react("+1", "2023-11-14T22:13:29Z", 7)],
            ],
            [
                bounds_page(PUSH_A, HEAD_S, base=BASE_1, base_stamp=BASE_1_TIP),
                bounds_page(
                    PUSH_A, HEAD_S, base=BASE_0, base_stamp=BASE_0_DATE,
                    base_force=BASE_FORCE,
                ),
                bounds_page(
                    PUSH_A, HEAD_S, review=bot_node(HEAD_S, "2023-11-14T22:13:27Z"),
                    base=BASE_0, base_stamp=BASE_0_DATE, base_force=BASE_FORCE,
                ),
            ],
            [HEAD_S, HEAD_S, HEAD_S],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("BASE CHANGED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)


class BaseForceParseTests(unittest.TestCase):
    def test_base_force_event_maxes_into_bound(self):
        # Given: the probe-side half — a ROUND_QUERY page whose base
        # target is the OLD commit (committedDate 21:50, pushedDate null)
        # beside a BaseRefForcePushedEvent node (createdAt 22:13:24, the
        # ref's actual move time; the nodejs#60801 live shape).
        # When: round_bounds parses. Then: the bound is the EVENT's own
        # stamp (max(21:50, 22:13:24)) and the head seam stays uncalled
        # (the FOLD pin); the pre-fix parse never read the connection
        # and .base_bound was the old commit's date (the pre-fix proof:
        # 21:50 != 22:13:24).
        bounds, head_calls = run_bounds([round_node(BASE_0_DATE, base_force=BASE_FORCE)])
        self.assertEqual(bounds, (HEAD_S, PUSH_A, "", ""))
        self.assertEqual(bounds.base, BASE_0)
        self.assertEqual(bounds.base_bound, BASE_FORCE)
        self.assertEqual(head_calls, 0)

    def test_absent_base_force_key_reads_target_bound(self):
        # Given: the legacy-tolerance SURVIVOR — the identical old-commit
        # base page with the baseForce key ABSENT (the pre-round-29
        # minimal-payload fixture shape; a fast-forward tip advance where
        # no force event exists). When: round_bounds parses. Then: the
        # fully readable bounds with the TARGET's own date carrying the
        # binding — green on BOTH sides (the absent key is never the
        # partial-error class; the round-15/25 shape rule).
        bounds, _ = run_bounds([round_node(BASE_0_DATE, base_force="ABSENT")])
        self.assertEqual(bounds, (HEAD_S, PUSH_A, "", ""))
        self.assertEqual(bounds.base_bound, BASE_0_DATE)

    def test_null_base_force_connection_reads_unreadable(self):
        # Given: the partial-error shape — the identical page with the
        # baseForce connection PRESENT-but-null. When: round_bounds
        # parses. Then: ('', '', '', '') — a success response from our
        # own assembled query always materializes every requested alias,
        # so a null connection is a partial/malformed response and the
        # WHOLE probe retries, never a readable history whose missing
        # ref-move stamp could bias a completion toward done (the
        # round-25 strict doctrine); the pre-fix parse ignored the
        # unknown key and returned the readable bounds (the pre-fix
        # proof: a readable 4-tuple, not EMPTY).
        bounds, _ = run_bounds([round_node(BASE_0_DATE, base_force=None)])
        self.assertEqual(bounds, EMPTY)

    def test_round_query_names_base_force_event_type(self):
        # Given: the assembled ROUND_QUERY (edited this round — the
        # round-20 hotfix GOTCHA class). When: the string is inspected.
        # Then: it selects the BASE_REF_FORCE_PUSHED_EVENT item type
        # through the aliased baseForce connection with the event's
        # createdAt — the pre-fix query carried neither (the pre-fix
        # proof: the substring was absent); the round20_probe suite's
        # brace-balance pin covers the assembled string's syntax and the
        # round-29 evidence records its live read-only execution.
        self.assertIn("baseForce:timelineItems", pr_guard_reaction_probe.ROUND_QUERY)
        self.assertIn("[BASE_REF_FORCE_PUSHED_EVENT]", pr_guard_reaction_probe.ROUND_QUERY)
        self.assertIn("... on BaseRefForcePushedEvent{createdAt}", pr_guard_reaction_probe.ROUND_QUERY)


if __name__ == "__main__":
    unittest.main()
