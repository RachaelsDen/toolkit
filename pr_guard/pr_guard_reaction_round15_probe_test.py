"""pr_guard reaction round-15 tests — the PROBE half (PR #49 threads
3870293194 P1 / 3870293197 P1).

(1) 3870293194 — the cold-start head-transition bound: round-13's
transition_floor populates only after two different head OIDs are
observed mid-wait, so a PR force-pushed/retargeted onto an
ALREADY-PUSHED commit BEFORE the first probe bound its leftover EYES
by the target commit's OLD pushedDate alone — the old head's EYES
postdated that stamp, armed the latch as current, and its delayed +1
exited 0 with the new head never reviewed. ROUND_QUERY now also reads
the latest HeadRefForcePushedEvent (the aliased headTransition
connection — live-verified GOTCHA: the finding named HeadRefPushedEvent
too, but the live schema REJECTS that type, and a retarget onto
already-pushed history is by definition a force push), and
round_bounds MAXes the event's createdAt with the commit's
pushedDate: a normal fresh push lands fresh-commit dates (the pinned
live shapes unchanged), while a retarget-to-old-commit carries a
LATER event stamp so the leftover EYES reads EYES_STALE. The bound
is the EVENT, never the wait's own start clock — a legitimate
mid-round EYES predating wait start still arms (the round-12
live-demo shape, pinned below).

(2) 3870293197 — the partial-error unreadable probe: a SUCCESSFUL
GraphQL response with timelineItems null/omitted (a field-level error
inside a 200) made codex_request_marker read "provably no request"
(''), so the probe stayed READABLE with the current re-request
marker DISCARDED while head/reviews/reactions data survived — a prior
+1 could classify current and satisfy an armed latch. The walk now
requires the CONNECTION SHAPE (timelineItems present, dict, nodes
list) and round_bounds rejects any top-level errors array: a missing
request connection is UNREADABLE (None → ('', '', '', '') → the
round-13 bracket rule makes the WHOLE probe unreadable — retry),
never a readable no-request. Sibling connections audited with the
same hygiene: headRef/latestReviews/reviewThreads/comments nulls read
unreadable (they previously collapsed into the except arm by
TypeError accident — now explicit), and the backwards walk page gets
the same errors+shape check (a null page previously escaped as an
AttributeError instead of the None unreadable contract).

The WAIT half of round 15 (3870293188/3870293205) lives in
pr_guard_reaction_round15_test — the suite-pair split at the 250
pure-LOC ceiling, tests included (the round-4/7/14 precedent).

No network: round_bounds/codex_request_marker run REAL against a
mocked pr_guard_reaction_probe.subprocess.run; the reading tests
patch gh_reactions/head_ref_oid at their usual seams.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round15_probe_test -v
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


def bounds_page(
    pushed,
    event=(),
    request=(),
    reviews=(),
    threads=(),
    oid=HEAD_B,
):
    """A well-formed ROUND_QUERY response; fields mutated inline by
    the partial-error tests (thread 3870293197)."""
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "headRefOid": oid,
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


def read_with_page(reactions, page, head=HEAD_B):
    """bot_reaction_reading with REAL round_bounds over one mocked
    ROUND_QUERY page (gh_reactions/head_ref_oid patched at the
    reaction-namespace seams)."""
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", return_value=reactions
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=head
    ), mock.patch.object(
        pr_guard_reaction_probe.subprocess, "run", return_value=gh_page(page)
    ):
        return pr_guard_reaction.bot_reaction_reading(48)


def run_wait_real_bounds(reads, pages, timeout_secs, head=HEAD_B):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    pages (thread 3870293194's cold-start wait-level race)."""
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
        pr_guard_reaction, "head_ref_oid", return_value=head
    ), mock.patch.object(
        pr_guard_reaction_probe.subprocess, "run",
        side_effect=lambda *a, **k: gh_page(next(script)),
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue()


class ColdStartTransitionBoundTests(unittest.TestCase):
    def test_retarget_event_bounds_the_first_eyes(self):
        # Given: the thread-3870293194 race — the PR was force-pushed
        # (event 2026-08-20T10:00) onto a commit ALREADY pushed
        # (pushedDate 2022-05-01) before the first probe, and the OLD
        # head's leftover EYES (created 2026-08-19 — POSTdating the
        # old pushedDate, PREdating the retarget event) is the latest
        # reaction. When: the reading runs. Then: EYES_STALE — the
        # head-transition bound is max(pushedDate, event) = the event
        # stamp, so the leftover arms nothing; the pre-fix probe
        # bound by pushedDate alone and read EYES (current).
        page = bounds_page(pushed="2022-05-01T00:00:00Z", event=("2026-08-20T10:00:00Z",))
        state, *_ = read_with_page(
            [react("eyes", created="2026-08-19T12:00:00Z", rid=5)], page
        )
        self.assertEqual(state, pr_guard_reaction.REACTION_EYES_STALE)

    def test_normal_push_event_leaves_the_live_shape_current(self):
        # Given: a NORMAL fresh push (pushedDate 11:00:00, its
        # HeadRefPushedEvent 11:00:03 — event≈pushedDate) and the
        # round's EYES created 12:31 — a legitimate MID-ROUND EYES
        # that predates any wait start. When: the reading runs. Then:
        # EYES — the event bound is NOT the wait's own start clock
        # (the round-12 live-demo shape still arms; the finding's
        # forbidden alternative).
        page = bounds_page(
            pushed="2026-08-26T11:00:00Z", event=("2026-08-26T11:00:03Z",)
        )
        state, *_ = read_with_page([react("eyes", rid=5)], page)
        self.assertEqual(state, pr_guard_reaction.REACTION_ACTIVE)

    def test_cold_start_retarget_wait_holds_the_delayed_plus_one(self):
        # Given: the same retarget shape driving the WHOLE wait —
        # the t=0 probe reads the old head's leftover EYES (now
        # EYES_STALE, arming nothing), and the old job's delayed +1
        # (2026-08-26T13:00, postdating the old pushedDate AND the
        # stale watermark of nothing) lands at t=5. When: wait polls
        # 12s. Then: exit 1 — nothing ever armed, so the +1 only
        # seeds a held baseline and HOLDs; the pre-fix wait read the
        # EYES current at t=0 (pushedDate-bound), armed, and printed
        # WAIT DONE at t=5 with the new head reviewed by nobody.
        page = bounds_page(pushed="2022-05-01T00:00:00Z", event=("2026-08-20T10:00:00Z",))
        code, out = run_wait_real_bounds(
            [
                [react("eyes", created="2026-08-19T12:00:00Z", rid=5)],
                [react("+1", created="2026-08-26T13:00:00Z", rid=6)],
                [react("+1", created="2026-08-26T13:00:00Z", rid=6)],
                [react("+1", created="2026-08-26T13:00:00Z", rid=6)],
            ],
            [page] * 4,
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)


class PartialErrorProbeTests(unittest.TestCase):
    def test_null_timeline_items_reads_unreadable_bounds(self):
        # Given: a SUCCESSFUL GraphQL response whose timelineItems is
        # null (the field errored inside a 200) with every sibling
        # field readable. When: round_bounds parses it. Then:
        # ('', '', '', '') — the request connection's ABSENCE is an
        # unreadable bound, never "provably no request"; the pre-fix
        # walk treated null as {} and returned readable bounds with
        # request '' (the missing-marker bias toward done).
        page = bounds_page(pushed="2022-05-01T00:00:00Z")
        page["data"]["repository"]["pullRequest"]["timelineItems"] = None
        with mock.patch.object(
            pr_guard_reaction_probe.subprocess, "run", return_value=gh_page(page)
        ):
            self.assertEqual(pr_guard_reaction.round_bounds(48), EMPTY_BOUNDS)

    def test_top_level_errors_read_unreadable_bounds(self):
        # Given: a 200 response carrying a top-level errors array
        # BESIDE well-formed-looking partial data. When: round_bounds
        # parses it. Then: ('', '', '', '') — any GraphQL error makes
        # the whole probe unreadable (the conservative retry), never
        # a readable snapshot of whatever fields happened to survive.
        page = bounds_page(pushed="2022-05-01T00:00:00Z")
        page["errors"] = [{"message": "Some field failed to resolve"}]
        with mock.patch.object(
            pr_guard_reaction_probe.subprocess, "run", return_value=gh_page(page)
        ):
            self.assertEqual(pr_guard_reaction.round_bounds(48), EMPTY_BOUNDS)

    def test_partial_error_probe_raises_the_bracket(self):
        # Given: the finding's exact ride — the prior round's +1
        # (2026-08-26T13:00, postdating every readable bound) is the
        # latest reaction while the request connection reads null.
        # When: bot_reaction_reading runs. Then: ReactionBracketUnreadable
        # — per round 13's bracket rule the WHOLE probe is unreadable
        # (the wait retries next interval); the pre-fix reading
        # returned THUMBS_UP (DONE) on the readable-with-missing-
        # request snapshot, satisfying an armed latch with the old
        # pass.
        page = bounds_page(pushed="2022-05-01T00:00:00Z")
        page["data"]["repository"]["pullRequest"]["timelineItems"] = None
        with self.assertRaises(pr_guard_reaction.ReactionBracketUnreadable):
            read_with_page(
                [react("+1", created="2026-08-26T13:00:00Z", rid=9)], page
            )

    def test_walk_page_null_connection_returns_none(self):
        # Given: the backwards request walk — the first page carries
        # hasPreviousPage (a codex-free newest-50 window) and the
        # SECOND page's timelineItems reads null. When:
        # codex_request_marker walks. Then: None (unreadable) — the
        # page connection shape is required before any "no request
        # exists" conclusion; the pre-fix walk raised AttributeError
        # (None.get) escaping the except arm's contract.
        pr_node = {
            "timelineItems": {
                "pageInfo": {"hasPreviousPage": True, "startCursor": "c1"},
                "nodes": [],
            }
        }
        page = {"data": {"repository": {"pullRequest": {"timelineItems": None}}}}
        with mock.patch.object(
            pr_guard_reaction_probe.subprocess, "run", return_value=gh_page(page)
        ):
            self.assertIsNone(
                pr_guard_reaction_probe.codex_request_marker(pr_node, 48, None)
            )

    def test_null_reviews_threads_read_unreadable_bounds(self):
        # Given: the sibling-connection audit — latestReviews null in
        # an otherwise-successful response. When: round_bounds parses
        # it. Then: ('', '', '', '') — the null collapsed into the
        # except arm's TypeError by ACCIDENT pre-fix (conservative,
        # but unnamed); the explicit shape check now owns the same
        # unreadable contract as the request connection.
        page = bounds_page(pushed="2022-05-01T00:00:00Z")
        page["data"]["repository"]["pullRequest"]["latestReviews"] = None
        with mock.patch.object(
            pr_guard_reaction_probe.subprocess, "run", return_value=gh_page(page)
        ):
            self.assertEqual(pr_guard_reaction.round_bounds(48), EMPTY_BOUNDS)


if __name__ == "__main__":
    unittest.main()
