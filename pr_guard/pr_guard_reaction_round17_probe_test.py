"""pr_guard reaction round-17 tests — the PROBE half (PR #49 threads
3870995905 P1 / 3870995911 P1 / 3870995919 P1).

(1) 3870995905 — the request walk now returns the boundary IDENTITY
`createdAt|node id` (the base64 GraphQL node id — live-verified
field; ReviewRequestedEvent carries NO databaseId, the
PullRequestReviewThread precedent): the timeline node list is
CHRONOLOGICAL, so the LAST codex event in the walked window is the
latest request, and a same-second DISTINCT node id is a detectable
NEW round boundary (the wait-side identity rule lives in
pr_guard_reaction_round17_test).

(2) 3870995911 — "Reset the wait on comment-triggered review
requests": the documented `@codex review` manual trigger is a
TOP-LEVEL PR comment (the pullRequest.comments connection — NOT the
review-thread comments the marker walk reads), and the probe never
read it, so a trigger posted while `wait` observed a preceding round
never surfaced as a round boundary: the old round's already-certified
EYES stayed armed and its delayed +1 produced WAIT DONE before the
comment-triggered round started. ROUND_QUERY's new aliased
triggerComments connection (bounded last:50 window + backwards
before:$cursor pages + the round-15 connection-shape hygiene: ABSENT
key = no-trigger for the legacy minimal fixtures, PRESENT-but-null =
partial error -> unreadable) reads trigger comments by ANY author
(matcher: a case-insensitive substring '@codex review' on the body),
and the boundary identity (createdAt|comment node id) feeds the SAME
request-boundary machinery as a formal re-request — advance, latch
reset, gate re-close; a trigger predating the wait is the cold-start
baseline (no reset).

(3) 3870995919 — latest_review_commit (the head-bound evidence the
wait's post-move completion check consumes) lives in the companion
pr_guard_reaction_round17_evidence_test — the round-14 suite-pair
split at the 250 pure-LOC ceiling, tests included (this file alone
measured past it carrying all three concerns).

Thread 3870995914 (the fast-forward cold-start bound) shipped NO
probe change: the live schema REJECTS every candidate boundary
(pullRequest.pushedDate is an undefinedField; HEAD_REF_PUSHED_EVENT
is still not a PullRequestTimelineItemsItemType; PullRequestCommit
carries no association timestamp) — see the round-17 receipt and the
vault note for the documented residual.

No network: round_bounds/codex_request_marker/latest_review_commit
run REAL against a mocked pr_guard_reaction_probe.subprocess.run;
the wait-level races patch gh_reactions/head_ref_oid at the reaction
seams (the round-15 suite-pair shape).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round17_probe_test -v
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

HEAD_B = "14ab97fffffffffffffffffffffffffffffff"

EMPTY_BOUNDS = ("", "", "", "")

REQ_SECOND = "2026-08-01T00:05:00Z"
REQ_ID_FIRST = f"{REQ_SECOND}|Zm9v"
REQ_ID_SECOND = f"{REQ_SECOND}|YWJj"


def react(content, created="2026-08-26T12:31:00Z", rid=None):
    return {
        "content": content,
        "created_at": created,
        "id": rid,
        "user": {"login": BOT},
    }


def gh_page(payload):
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(payload)
    )


def req_node(created, node_id, reviewer=pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN):
    return {
        "createdAt": created,
        "id": node_id,
        "requestedReviewer": {"login": reviewer},
    }


def trigger_node(created, node_id, body):
    return {"createdAt": created, "id": node_id, "body": body}


def bounds_page(
    pushed,
    event=(),
    request=(),
    reviews=(),
    threads=(),
    oid=HEAD_B,
    trigger=None,
    trigger_previous=False,
    trigger_null=False,
):
    """A well-formed ROUND_QUERY response; the trigger keyword keeps
    the triggerComments key ABSENT by default (the legacy
    minimal-payload fixture shape — an absent alias reads no-trigger)
    and stages it explicitly when given."""
    page = {
        "data": {
            "repository": {
                "pullRequest": {
                    "headRefOid": oid,
                    # PR #49 round 28 fixture-seam maintenance (thread
                    # 3875089268): the paginating trigger-walk probe's
                    # re-run page must carry baseRefOid (the strict
                    # recheck validates the base too now); the bare-oid
                    # shape keeps base_bound '' (no floor effect).
                    "baseRefOid": "9ed444e0d5b1ad3b3ff6c9d3e3b4a5c6d7e8f9a0",
                    "headRef": {
                        "target": {"pushedDate": pushed, "committedDate": pushed}
                    },
                    "timelineItems": {
                        "pageInfo": {"hasPreviousPage": False, "startCursor": None},
                        "nodes": list(request),
                    },
                    "headTransition": {"nodes": [{"createdAt": e} for e in event]},
                    "latestReviews": {"nodes": list(reviews)},
                    "reviewThreads": {
                        "nodes": [{"comments": {"nodes": list(threads)}}]
                    },
                }
            }
        }
    }
    if trigger_null:
        page["data"]["repository"]["pullRequest"]["triggerComments"] = None
    elif trigger is not None:
        page["data"]["repository"]["pullRequest"]["triggerComments"] = {
            "pageInfo": {
                "hasPreviousPage": trigger_previous,
                "startCursor": "c1" if trigger_previous else None,
            },
            "nodes": list(trigger),
        }
    return page


def round_bounds_over(page):
    with mock.patch.object(
        pr_guard_reaction_probe.subprocess, "run", return_value=gh_page(page)
    ):
        return pr_guard_reaction.round_bounds(48)


def run_wait_real_bounds(reads, pages, timeout_secs, head=HEAD_B):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    pages (the round-15 run_wait_real_bounds shape: gh_reactions and
    head_ref_oid patched at the reaction seams)."""
    clock = FakeClock()
    items = iter(reads)
    script = iter(pages)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    out = io.StringIO()
    with mock.patch.object(pr_guard_reaction, "gh_reactions", side_effect=fake_read), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=head
    ), mock.patch.object(
        pr_guard_reaction_probe.subprocess, "run",
        side_effect=lambda *a, **k: gh_page(next(script)),
    ), mock.patch.object(pr_guard_reaction, "time", clock), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue()


class RequestIdentityTests(unittest.TestCase):
    def test_request_identity_carries_the_node_id(self):
        # Given: a ROUND_QUERY page whose newest-50 window carries
        # one codex ReviewRequestedEvent (createdAt 2026-08-01T00:05,
        # node id PRRT_kmQ) — live-verified shape: the event node has
        # a stable base64 id and NO databaseId. When: round_bounds
        # parses it. Then: the boundary rides THIRD as the IDENTITY
        # createdAt|node id — the same-second tie-breaker the
        # round-15 timestamp-only compare lacked (thread 3870995905);
        # the pre-fix probe returned the bare createdAt.
        page = bounds_page(
            pushed="2026-08-01T00:00:00Z",
            request=[req_node(REQ_SECOND, "PRRT_kmQ")],
        )
        head, pushed, boundary, marker = round_bounds_over(page)
        self.assertEqual(head, HEAD_B)
        self.assertEqual(pushed, "2026-08-01T00:00:00Z")
        self.assertEqual(boundary, f"{REQ_SECOND}|PRRT_kmQ")
        self.assertEqual(marker, REQ_SECOND)

    def test_same_second_distinct_request_end_to_end(self):
        # Given: the thread-3870995905 race through the REAL probe —
        # the t=0 page's window ends at codex request node Zm9v
        # (2026-08-01T00:05) while the round's EYES (2026-08-02,
        # postdating push and request) arms; the t=5 page's window
        # ends at a SECOND request node YWJj created in the SAME
        # second (lexicographically SMALLER — the adversarial
        # ordering), posted while the old job sits in its
        # EYES-removal/+1 switch (the probe reads NONE); the
        # preceding job's delayed +1 (2026-08-26T14) lands at t=10.
        # When: wait polls 12s. Then: exit 1 — the walked window's
        # LAST codex node is the chronologically-latest request, its
        # DISTINCT same-second node id advances the high-water, and
        # the reset + gate re-close hold the delayed +1 to timeout;
        # the pre-fix probe returned the bare timestamp for both
        # requests, no advance fired, and the wait printed WAIT DONE
        # at t=10 before the newly requested round started.
        first = bounds_page(
            pushed="2026-08-01T00:00:00Z",
            request=[req_node(REQ_SECOND, "Zm9v")],
        )
        second = bounds_page(
            pushed="2026-08-01T00:00:00Z",
            request=[
                req_node(REQ_SECOND, "Zm9v"),
                req_node(REQ_SECOND, "YWJj"),
            ],
        )
        code, out = run_wait_real_bounds(
            [
                [react("eyes", created="2026-08-02T00:00:00Z", rid=5)],
                [],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
            ],
            [first, second, second, second],
            12,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)


class TriggerBoundaryTests(unittest.TestCase):
    def test_trigger_comment_reads_as_a_request_boundary(self):
        # Given: a page whose triggerComments window carries a HUMAN
        # top-level PR comment (any author by design) whose body
        # contains the documented trigger phrase. When: round_bounds
        # parses it. Then: the boundary rides THIRD as the comment's
        # identity createdAt|node id (thread 3870995911 — the trigger
        # feeds the same request-boundary machinery as a formal
        # re-request); the pre-fix probe never read the connection
        # and returned ''.
        page = bounds_page(
            pushed="2021-01-01T00:00:00Z",
            trigger=[trigger_node("2026-08-20T00:00:00Z", "IC_9", "please run @codex review when free")],
        )
        _, _, boundary, marker = round_bounds_over(page)
        self.assertEqual(boundary, "2026-08-20T00:00:00Z|IC_9")
        self.assertEqual(marker, "2026-08-20T00:00:00Z")

    def test_comment_trigger_resets_and_recloses(self):
        # Given: the thread-3870995911 race — the t=0 page carries
        # the formal codex request (2026-08-01) and the round's
        # verified EYES (2026-08-02) arms; a human posts the
        # documented `@codex review` trigger as a TOP-LEVEL comment
        # while `wait` still observes the preceding round (the t=5
        # page carries it; the probe reads the old job's switch-window
        # NONE); the preceding job's delayed +1 (2026-08-26T14)
        # lands at t=10. When: wait polls 12s. Then: exit 1 — the
        # trigger boundary ADVANCES (2026-08-20 > 2026-08-01), the
        # round-15/16 reset + gate re-close run (ROUND RE-REQUESTED),
        # the NONE never re-arms, and the delayed +1 only HOLDs; the
        # pre-fix query read formal requests and bot output but not
        # PR comments, so the boundary never moved and the wait
        # printed WAIT DONE at t=10 before the triggered round
        # started.
        before = bounds_page(
            pushed="2026-08-01T00:00:00Z",
            request=[req_node("2026-08-01T00:05:00Z", "PRRT_kmQ")],
        )
        after = bounds_page(
            pushed="2026-08-01T00:00:00Z",
            request=[req_node("2026-08-01T00:05:00Z", "PRRT_kmQ")],
            trigger=[trigger_node("2026-08-20T00:00:00Z", "IC_9", "@codex review")],
        )
        code, out = run_wait_real_bounds(
            [
                [react("eyes", created="2026-08-02T00:00:00Z", rid=5)],
                [],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
            ],
            [before, after, after, after],
            12,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_cold_start_trigger_is_the_baseline_no_reset(self):
        # Given: the cold-start baseline rule — the trigger comment
        # (2026-08-20) PREDATES the wait (the first page already
        # carries it), so it initializes the high-water like any
        # first-observation boundary; the round it started runs its
        # own EYES (2026-08-25 — verified POST-trigger, the round-13
        # request-binding rule applied to the merged boundary) and
        # passes (+1 2026-08-26). When: wait polls. Then: exit 0 —
        # no ROUND RE-REQUESTED (a pre-wait trigger is the baseline,
        # never a reset) and no round strands (the non-stranding
        # survivor).
        page = bounds_page(
            pushed="2021-01-01T00:00:00Z",
            trigger=[trigger_node("2026-08-20T00:00:00Z", "IC_1", "@codex review")],
        )
        # PR #49 round 25 fixture-seam maintenance (thread 3873970933):
        # the completing round carries the folded review evidence
        # naming the stable head (the stamp between the 08-25 EYES and
        # the 08-26 +1) — cold-start completions require it now.
        page["data"]["repository"]["pullRequest"]["botReviews"] = {"nodes": [
            {"author": {"login": pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN}, "commit": {"oid": HEAD_B}, "submittedAt": "2026-08-25T12:00:00Z"}
        ]}
        code, out = run_wait_real_bounds(
            [
                [react("eyes", created="2026-08-25T00:00:00Z", rid=7)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
            ],
            [page, page],
            600,
        )
        self.assertEqual(code, 0)
        self.assertNotIn("ROUND RE-REQUESTED", out)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)

    def test_trigger_matcher_is_case_insensitive_substring(self):
        # Given: the documented matcher — a body containing
        # '@codex review' as a CASE-INSENSITIVE SUBSTRING by any
        # author. When: round_bounds parses pages carrying 'Could
        # you run @Codex Review please?', 'ltgm — @CODEX REVIEW —
        # thanks', and a NON-matching 'please review this soon'
        # beside a formal request. Then: both phrase-carrying
        # comments read as boundaries (their own identities) while
        # the non-trigger leaves the boundary at the formal request.
        def boundary_of(request=(), trigger=None):
            page = bounds_page(
                pushed="2021-01-01T00:00:00Z", request=list(request), trigger=trigger
            )
            return round_bounds_over(page)[2]

        self.assertEqual(
            boundary_of(
                trigger=[
                    trigger_node("2026-08-20T00:00:00Z", "IC_1", "Could you run @Codex Review please?")
                ]
            ),
            "2026-08-20T00:00:00Z|IC_1",
        )
        self.assertEqual(
            boundary_of(
                trigger=[
                    trigger_node("2026-08-20T00:00:00Z", "IC_2", "ltgm — @CODEX REVIEW — thanks")
                ]
            ),
            "2026-08-20T00:00:00Z|IC_2",
        )
        self.assertEqual(
            boundary_of(
                request=[req_node("2026-08-01T00:05:00Z", "PRRT_kmQ")],
                trigger=[
                    trigger_node("2026-08-19T00:00:00Z", "IC_3", "please review this soon")
                ],
            ),
            "2026-08-01T00:05:00Z|PRRT_kmQ",
        )

    def test_null_trigger_comments_reads_unreadable_bounds(self):
        # Given: a SUCCESSFUL response whose triggerComments alias
        # reads null (the field-level partial-error shape). When:
        # round_bounds parses it. Then: ('', '', '', '') — a
        # PRESENT-but-null connection is UNREADABLE (the round-15
        # shape rule: a success response always materializes a
        # requested alias), never a readable no-trigger history whose
        # missing boundary could bias the wait; the ABSENT key (every
        # legacy minimal fixture) stays the no-trigger read.
        page = bounds_page(pushed="2021-01-01T00:00:00Z", trigger_null=True)
        self.assertEqual(round_bounds_over(page), EMPTY_BOUNDS)

    def test_trigger_walk_reads_older_pages(self):
        # Given: the bounded window discipline — the newest-50
        # triggerComments window carries NO trigger but
        # hasPreviousPage (older comments exist), and the BACKWARDS
        # before:$cursor page carries one (2026-08-20, IC_9). When:
        # round_bounds parses the scripted subprocess pages (the
        # walk's pagination opens the post-query window, so the
        # round-24 bracket re-run reads a third page — the appended
        # `first` copy carries the SAME trigger-free newest window,
        # the unchanged picture the recheck expects; the patched head
        # seam is the never-called fold pin — fixture-seam
        # maintenance, the assertion unchanged). Then: the boundary
        # is the walked page's trigger identity — the walk stops at
        # the FIRST page carrying a trigger (its LAST match is the
        # latest overall, the request-walk proof), so a trigger older
        # than the newest window still binds; the pre-fix probe never
        # walked comments and read ''.
        first = bounds_page(
            pushed="2021-01-01T00:00:00Z",
            trigger=[trigger_node("2026-08-01T00:00:00Z", "IC_1", "unrelated chatter")],
            trigger_previous=True,
        )
        walk = bounds_page(
            pushed="2021-01-01T00:00:00Z",
            trigger=[trigger_node("2026-08-20T00:00:00Z", "IC_9", "@codex review")],
        )
        with mock.patch.object(
            pr_guard_reaction_probe.subprocess,
            "run",
            side_effect=[gh_page(first), gh_page(walk), gh_page(first)],
        ), mock.patch.object(
            pr_guard_reaction_probe, "head_ref_oid", return_value=HEAD_B
        ):
            _, _, boundary, _ = pr_guard_reaction.round_bounds(48)
        self.assertEqual(boundary, "2026-08-20T00:00:00Z|IC_9")


if __name__ == "__main__":
    unittest.main()
