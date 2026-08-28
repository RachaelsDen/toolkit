"""pr_guard reaction round-20 tests — the WAIT half (PR #49 threads
3872194007 P2 / 3872194017 P2 / 3872194023 P1).

(1) 3872194007 — "Preserve every visible same-second boundary
identity": the boundary walks returned only markers[-1], so when two
trigger comments share the high-water second the seen-set recorded
only the NEWEST — deleting or omitting that newest later left the
older sibling UNRECORDED, and its resurfacing satisfied
boundary_advances' same-second distinctness rule, spuriously
resetting the current round's latches and withholding a valid
completion to timeout. Round 20's walks deposit EVERY visible
same-second identity at the high-water second into collect sets the
wait's seen-sets union, so the sibling was recorded while visible
and its resurfacing reads as the round's CONTINUATION.

(2) 3872194017 — "Avoid staling new EYES by the poll observation
time": the round-19 observation floor stamped the wait's OWN wall
clock at the advance probe, so a re-request and the newly requested
job's EYES both landing BETWEEN two five-second probes read the
legitimate EYES as pre-observation and permanently demoted it — the
passing +1 then only seeded a held baseline and an otherwise
completed review timed out. Round 20 SUPERSEDES the floor with the
REQUEST/TRIGGER's own createdAt (exactly the reading's standing
round-13 binding): an EYES certifies iff it postdates the boundary
event — the between-polls shape below now COMPLETES, while a
PRE-boundary EYES still stales AT THE READING (the survivor). The
superseded round-19 pin lives in pr_guard_reaction_round19_test
(the documented exact-hole repin).

(3) 3872194023 — "Bind review evidence to the completing reaction":
after a head A->B transition, overlapping reviews can finish out of
order — the latest head-bound bot review may be the NEW head's
findings review while the accepted +1 belongs to the OLD head's
delayed job. LIVE-VERIFIED read-only 2026-08-27 (PR #49 + PR #48):
the reviews' `state` field does NOT separate the classes (findings
rounds AND the pass round all render COMMENTED), so the state-based
bind is UNAVAILABLE; the built guard binds the completing +1 to the
folded VERDICT STAMP — post-move, the latest head-bound review must
SUBMIT after the transition floor (closing the stale-review
retarget coincidence: a pre-move review of the commit the ref later
RETARGETED back onto matches the oid yet reviewed nobody post-move)
AND be FOLLOWED by the +1 (the PR #48 verdict shape, carried through
the UNEVICTABLE author-filtered fold — the latestReviews marker
window cannot unbind it). The exact out-of-order same-era race (the
new head's findings review submitting BEFORE the old head's delayed
+1, all post-boundary) is DOCUMENTED-OPEN: with COMMENTED-only
states and no reaction-to-review association its observable sequence
is identical to a legitimate pass — the post-merge quiet watch + the
server rulesets remain the standing backstop.

No network: the 4007/4023 fixtures run REAL round_bounds over
scripted ROUND_QUERY pages (the round-18/19 shape) so the collect
sets and the stamp ride the REAL probe through the attrs; the 4017
fixtures patch plain 4-tuple bounds at the seam (the round-19
shape). FakeClock WALL_NOW 2023-11-14T22:13:20Z; the 4023 fixtures
key their stamps INSIDE the wall window (the floor stamps
22:13:25 at the t=5 move detection — the round-19 GOTCHA #2 rule).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round20_test -v
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

HEAD = "20ab97ffffffffffffffffffffffffffffff1"
HEAD_A = "20ab97ffffffffffffffffffffffffffffffa"
HEAD_B = "20ab97ffffffffffffffffffffffffffffffb"

# The wall window (round-19 GOTCHA #2): probes land at 22:13:20
# (t=0), 22:13:25 (t=5), 22:13:30 (t=10) — a mid-wait head move
# detected at t=5 stamps the transition floor 2023-11-14T22:13:25Z.
PUSH = "2023-11-14T22:00:00Z"
R1 = "2023-11-14T22:10:00Z|RA_1"
R2 = "2023-11-14T22:13:22Z|RA_2"
R1_AT = "2023-11-14T22:10:00Z"
R2_AT = "2023-11-14T22:13:22Z"

# The 4007 same-second pair: IC_2 the older sibling, IC_9 the newest
# — both inside SECOND; the 4023 stamps sit around the t=5 floor.
SECOND = "2026-08-01T00:05:00Z"
T1 = f"{SECOND}|IC_2"
T2 = f"{SECOND}|IC_9"
STALE_STAMP = "2023-11-14T22:13:10Z"
FRESH_STAMP = "2023-11-14T22:13:27Z"
# PR #49 round 26 (thread 3874405295) fixture-seam maintenance: the
# transition floor is the HEAD'S OWN BOUND now, and a mid-wait
# retarget onto an already-pushed commit is BY DEFINITION a force
# push (round 15, live-verified: HeadRefForcePushedEvent is the only
# retarget event the schema offers) — the stale-review fixture's
# HEAD_B pages carry the event so the coincidence review predates
# the EVENT bound (the no-event retarget the old pages staged is the
# unreal shape; the wall floor used to cover it).
RETARGET_EVENT = "2023-11-14T22:13:22Z"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def gh_page(payload):
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(payload)
    )


def trigger_node(created, node_id):
    return {"createdAt": created, "id": node_id, "body": "@codex review"}


def bot_node(oid, at):
    return {
        "author": {"login": pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN},
        "commit": {"oid": oid},
        "submittedAt": at,
    }


def bounds_page(pushed, oid, trigger=None, review=None, force_push=None):
    """A well-formed ROUND_QUERY page; trigger/review/force_push None
    keep their keys ABSENT (the round-18 legacy-minimal-payload
    rule)."""
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
    if trigger is not None:
        pr["triggerComments"] = {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": list(trigger),
        }
    if review is not None:
        pr["botReviews"] = {"nodes": [review]}
    if force_push is not None:
        pr["headTransition"] = {"nodes": [{"createdAt": force_push}]}
    return page


def run_wait(reads, bounds, timeout_secs, review=None):
    """wait_reaction on the FakeClock with per-probe plain 4-tuple
    bounds (the round-19 harness shape — the request stream riding
    index 2; a stable head). review, when a (head, stamp) pair, wraps
    the tuples in the RoundBounds carrier (the round-22 fixture-seam
    maintenance: post-advance completions carry the folded review
    evidence; the plain-tuple default keeps the '' fallback)."""
    clock = FakeClock()
    items = iter(reads)
    probes = iter(bounds)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    def fake_bounds(pr, timeout_secs=None):
        bounds = next(probes)
        if review is not None:
            carried = pr_guard_reaction_probe.RoundBounds(bounds)
            carried.review_head, carried.review_stamp = review
            bounds = carried
        return bounds

    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_read
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", side_effect=fake_bounds
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=HEAD
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue()


def run_wait_pages(reads, pages, heads, timeout_secs):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    pages (the round-18/19 shape); heads scripts head_ref_oid per
    probe (a CHANGING oid stages the mid-wait head move)."""
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


class FullIdentitySeenSetTests(unittest.TestCase):
    def test_same_second_sibling_resurfacing_never_readvances(self):
        # Given: the thread-3872194007 race — t=0 the trigger page
        # carries BOTH same-second comments (the sibling IC_2 beside
        # the newest IC_9) while the round's verified EYES (2026-08-02,
        # past the shared second and the 2026-08-01 push) arms; t=5
        # the sibling is TEMPORARILY OMITTED (the page carries only
        # IC_9) and the round sits in its EYES-removal/+1 switch
        # (NONE); t=10 the +1 (2026-08-26T14, following the EYES
        # watermark — a VALID completion) lands while the NEWEST
        # comment is DELETED and the sibling IC_2 RESURFACES as the
        # walk's latest. When: wait polls 10s. Then: exit 0 at 10s
        # with ZERO advance lines — the collect set recorded BOTH
        # identities at t=0 (every VISIBLE identity of the high-water
        # second), so the resurfacing sibling is IN the seen-set and
        # never readvances; the pre-fix stream recorded only IC_9,
        # so the sibling's distinct id satisfied boundary_advances,
        # fired a SPURIOUS ROUND RE-REQUESTED at the completion
        # probe, cleared the armed latch/watermark, and held the
        # valid +1 to the timeout (exit 1). (PR #49 round 25
        # fixture-seam maintenance, thread 3873970933: the completing
        # probe carries the folded review evidence naming the stable
        # head — cold-start completions require it now; the page
        # pictures are otherwise unchanged.)
        code, out = run_wait_pages(
            [
                [react("eyes", "2026-08-02T00:00:00Z", 5)],
                [],
                [react("+1", "2026-08-26T14:00:00Z", 8)],
            ],
            [
                bounds_page("2026-08-01T00:00:00Z", HEAD, [trigger_node(SECOND, "IC_2"), trigger_node(SECOND, "IC_9")]),
                bounds_page("2026-08-01T00:00:00Z", HEAD, [trigger_node(SECOND, "IC_9")]),
                bounds_page(
                    "2026-08-01T00:00:00Z",
                    HEAD,
                    [trigger_node(SECOND, "IC_2")],
                    review=bot_node(HEAD, "2026-08-02T00:00:01Z"),
                ),
            ],
            [HEAD, HEAD, HEAD],
            10,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)


class RequestBoundaryFloorTests(unittest.TestCase):
    def test_between_polls_eyes_and_request_certify_and_complete(self):
        # Given: the thread-3872194017 race — a cold NONE at t=0 with
        # the standing request R1; the same-head RE-REQUEST R2
        # (22:13:22) AND the newly requested round's OWN EYES
        # (22:13:23 — posted BEFORE the probe that first observes the
        # request, normal asynchronous startup) both land between the
        # t=0 and t=5 probes; the round's passing +1 (22:13:24,
        # following its EYES watermark) lands at t=10. When: wait
        # polls 10s. Then: exit 0 at 10s — the boundary is R2's own
        # createdAt (22:13:22) and the EYES (22:13:23 > 22:13:22)
        # certifies at the READING's round-13 binding: it re-opens
        # the freshly reset gate, re-arms the latch, and the +1
        # completes; the pre-fix observation floor stamped the wait's
        # OWN wall clock (22:13:25) at the t=5 probe, demoted the
        # legitimate EYES to EYES_STALE forever, and the otherwise
        # completed review timed out (exit 1, the +1 seeding only a
        # held baseline). ROUND 22 (thread 3872980765): the fixture's
        # review stamp (22:13:23) rides the folded evidence past the
        # boundary — the legitimate startup completion carries the
        # evidence leg; the OLD job's pre-request review is the leg
        # round 22 closes (pinned in round22_test).
        code, out = run_wait(
            [
                [],
                [react("eyes", "2023-11-14T22:13:23Z", 5)],
                [react("+1", "2023-11-14T22:13:24Z", 6)],
            ],
            [
                (HEAD, PUSH, R1, R1_AT),
                (HEAD, PUSH, R2, R2_AT),
                (HEAD, PUSH, R2, R2_AT),
            ],
            10,
            review=(HEAD, "2023-11-14T22:13:23Z"),
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)

    def test_pre_request_eyes_still_stales_at_the_reading(self):
        # Given: the SURVIVING demotion — the same advance shape, but
        # the EYES (22:13:21) PREDATES the advancing request R2
        # (22:13:22): a pre-boundary leftover, not a between-polls
        # startup. The +1 (22:13:24) lands at t=10. When: wait polls
        # 10s. Then: exit 1 — the READING's round-13 binding (not the
        # removed wait-side stamp) classifies the EYES EYES_STALE
        # (created <= the boundary's createdAt): it arms nothing and
        # re-opens no gate, so the +1 only seeds a held baseline and
        # HOLDs to the timeout. Green on BOTH sides of the round-20
        # change (the pre-fix floor demoted it identically) — the pin
        # that round 20 RELAXED the floor to the boundary, not removed
        # the demotion itself.
        code, out = run_wait(
            [
                [],
                [react("eyes", "2023-11-14T22:13:21Z", 5)],
                [react("+1", "2023-11-14T22:13:24Z", 6)],
            ],
            [
                (HEAD, PUSH, R1, R1_AT),
                (HEAD, PUSH, R2, R2_AT),
                (HEAD, PUSH, R2, R2_AT),
            ],
            10,
        )
        self.assertEqual(code, 1)
        self.assertIn("EYES (stale — predates the current round's boundary", out)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)


class ReviewStateBindTests(unittest.TestCase):
    def test_stale_headbound_review_cannot_complete(self):
        # Given: the thread-3872194023 retarget coincidence — the
        # bot's review of commit B (submittedAt 22:13:10, BEFORE the
        # wait) is the latest bot review when the ref MOVES A->B at
        # t=5 (B an already-pushed commit — the retarget class): its
        # oid matches the observed head BY COINCIDENCE though nobody
        # reviewed B post-move. A post-floor EYES (22:13:26) arms at
        # t=5; a +1 (22:13:28 — postdating the push, the (empty)
        # composite marker, and the EYES watermark) lands at t=10.
        # When: wait polls 10s. Then: exit 1 — the folded verdict
        # stamp (22:13:10) does NOT postdate the transition floor,
        # so head_bound fails and the +1 HOLDs; the pre-fix check
        # compared ONLY the oid (B == B) and printed WAIT DONE at 10s
        # with the retargeted head reviewed by nobody. [Round 26
        # fixture-seam maintenance, thread 3874405295: the floor is
        # the head's OWN bound now — max(B's 22:00 pushedDate, the
        # force-push EVENT 22:13:22 the HEAD_B pages carry; the
        # stamp 22:13:10 predates the event) — the wall-clock floor
        # that used to reject it is gone.]
        code, out = run_wait_pages(
            [
                [],
                [react("eyes", "2023-11-14T22:13:26Z", 5)],
                [react("+1", "2023-11-14T22:13:28Z", 6)],
            ],
            [
                bounds_page(PUSH, HEAD_A, review=bot_node(HEAD_B, STALE_STAMP)),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_B, STALE_STAMP), force_push=RETARGET_EVENT),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_B, STALE_STAMP), force_push=RETARGET_EVENT),
            ],
            [HEAD_A, HEAD_B, HEAD_B],
            10,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("3872194023", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)

    def test_post_move_stamped_review_still_completes(self):
        # Given: the non-stranding survivor — the identical post-move
        # shape, but the head-bound review SUBMITS after the floor
        # (22:13:27 > 22:13:25) and BEFORE the +1 that follows it
        # (22:13:28 > 22:13:27; the PR #48 verdict shape). When: wait
        # polls 10s. Then: exit 0 at 10s — the stamp satisfies both
        # new bounds and the completion exits; green on BOTH sides of
        # the round-20 change (the pre-fix oid check passed it too),
        # the pin that the bind withholds NOTHING a legitimate
        # post-move round completes with.
        code, out = run_wait_pages(
            [
                [],
                [react("eyes", "2023-11-14T22:13:26Z", 5)],
                [react("+1", "2023-11-14T22:13:28Z", 6)],
            ],
            [
                bounds_page(PUSH, HEAD_A, review=bot_node(HEAD_B, FRESH_STAMP)),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_B, FRESH_STAMP)),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_B, FRESH_STAMP)),
            ],
            [HEAD_A, HEAD_B, HEAD_B],
            10,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 10s", out)

    def test_verdict_predating_the_unevictable_review_holds(self):
        # Given: the thread-3872194023 eviction shape — the fold's
        # raison d'être turned around: latestReviews is EMPTY (ten
        # humans evicted every bot row from the marker window) while
        # the author-filtered botReviews still carries the head-bound
        # review (submittedAt 22:13:27, POST-floor); the +1
        # (22:13:26, same second as its arming EYES 22:13:26 but the
        # greater id — it follows the watermark) landed BEFORE the
        # review submitted: a verdict that PREDATES the review it
        # must answer. When: wait polls 10s. Then: exit 1 — the
        # unevictable stamp binds the completion (the +1 does not
        # postdate the review's submittedAt) and the +1 HOLDs; the
        # pre-fix check passed on the oid alone and printed WAIT DONE
        # at 10s (and the marker window, missing the review entirely,
        # could never have caught it).
        code, out = run_wait_pages(
            [
                [],
                [react("eyes", "2023-11-14T22:13:26Z", 5)],
                [react("+1", "2023-11-14T22:13:26Z", 6)],
            ],
            [
                bounds_page(PUSH, HEAD_A, review=bot_node(HEAD_B, FRESH_STAMP)),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_B, FRESH_STAMP)),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_B, FRESH_STAMP)),
            ],
            [HEAD_A, HEAD_B, HEAD_B],
            10,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("3872194023", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 10s elapsed", out)


if __name__ == "__main__":
    unittest.main()
