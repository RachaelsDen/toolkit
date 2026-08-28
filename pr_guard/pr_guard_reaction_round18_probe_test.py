"""pr_guard reaction round-18 tests — the PROBE half (PR #49 threads
3871485035 P1 / 3871485043 P2 / 3871485055 P1).

The probe-side facts the wait half consumes: (1) the review evidence
is FOLDED into ROUND_QUERY as the author-filtered `botReviews`
connection — 3871485035's one-subprocess/one-bracket rule — and
rides the bounds as an ATTRIBUTE; (2) the filter is the fix for
3871485043: `reviews(author:...)` filters SERVER-SIDE (live-verified
read-only on PR #49, 2026-08-27), so no fixed window of other
reviewers' reviews can evict the connector's — the finding's
`latestReviews(last:10)` eviction cannot recur in the folded read
(live GOTCHA, decisive: the filter argument matches ONLY the
`[bot]`-suffixed login "chatgpt-codex-connector[bot]" — the
suffix-less render that GraphQL `author{login}` displays returns an
EMPTY connection, the exact inverse of the round-3 rendering gotcha;
querying with the rendered login would read "no bot review" forever.
Empty is the live-verified `{"nodes": []}` shape — a LEGITIMATE
no-review, distinct from a null connection, which is the round-15
partial-error class and makes the WHOLE probe unreadable);
(3) 3871485055's per-kind identities ride the bounds as separate
`.request`/`.trigger` attributes while the INDEX-2 boundary stays
the merged identity (latest_boundary) that the EYES classification
and the composite marker consume — classification composes, only the
RETENTION split.

THE ZERO-REPIN SEAM RULE: round_bounds returns a 4-field RoundBounds
(a tuple subclass) whose equality with every legacy plain-4-tuple
fixture is preserved — the three round-18 facts ride as ATTRIBUTES
(`.request`, `.trigger`, `.review_head`; class-default None marks
"unset" so a legacy plain tuple falls back to its index-2 stream).
Every pre-round-18 seam fixture (18 suites patch round_bounds with
plain 4-tuples) stays green UNTOUCHED — the round-15/17 ABSENT-key
tolerance precedent, applied to the return shape.

No network: round_bounds runs REAL against a mocked
pr_guard_reaction_probe.subprocess.run (the round-15/17 probe shape).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round18_probe_test -v
"""

import json
import subprocess
import unittest
from unittest import mock

from . import pr_guard_reaction
from . import pr_guard_reaction_probe

HEAD_B = "14ab97fffffffffffffffffffffffffffffff"

SECOND = "2026-08-01T00:05:00Z"

EMPTY_BOUNDS = ("", "", "", "")


def gh_page(payload):
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(payload)
    )


def req_node(created, node_id):
    return {
        "createdAt": created,
        "id": node_id,
        "requestedReviewer": {"login": pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN},
    }


def trigger_node(created, node_id):
    return {"createdAt": created, "id": node_id, "body": "@codex review"}


def human_review(at):
    return {"author": {"login": "some-human"}, "submittedAt": at}


def bot_review(oid, login=None):
    return {
        "author": {
            "login": login or pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN
        },
        "commit": {"oid": oid},
    }


def bounds_page(
    pushed,
    oid=HEAD_B,
    request=(),
    trigger=None,
    bot_reviews=None,
    bot_reviews_null=False,
    humans=0,
):
    """A well-formed ROUND_QUERY page. bot_reviews=None keeps the
    botReviews key ABSENT (the legacy minimal-payload shape); a list
    or the null flag stages the folded connection explicitly."""
    page = {
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
                    "headTransition": {"nodes": []},
                    "latestReviews": {
                        "nodes": [
                            human_review(f"2026-07-{n:02d}T00:00:00Z")
                            for n in range(1, humans + 1)
                        ]
                    },
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
    if bot_reviews_null:
        pr["botReviews"] = None
    elif bot_reviews is not None:
        pr["botReviews"] = {"nodes": list(bot_reviews)}
    return page


def round_bounds_over(page):
    with mock.patch.object(
        pr_guard_reaction_probe.subprocess, "run", return_value=gh_page(page)
    ):
        return pr_guard_reaction.round_bounds(48)


class FoldedEvidenceTests(unittest.TestCase):
    def test_review_evidence_rides_the_round_query(self):
        # Given: a well-formed page whose folded botReviews connection
        # carries the connector's latest review with commit.oid (the
        # author-filtered connection; live-verified field shape).
        # When: round_bounds parses it. Then: the evidence rides the
        # bounds as the review_head ATTRIBUTE while the INDEX tuple
        # stays the legacy 4-shape byte-identical (equality with the
        # plain tuple — the zero-repin seam rule); the pre-fix probe
        # dispatched a SEPARATE latest_review_commit subprocess after
        # the bracket (thread 3871485035's unbracketed window).
        page = bounds_page(
            "2026-08-01T00:00:00Z", bot_reviews=[bot_review(HEAD_B)]
        )
        bounds = round_bounds_over(page)
        self.assertEqual(
            bounds, (HEAD_B, "2026-08-01T00:00:00Z", "", "")
        )
        self.assertEqual(bounds.review_head, HEAD_B)

    def test_bot_reviews_shapes(self):
        # Given: the folded connection's three degenerate shapes —
        # EMPTY nodes (the live-verified no-bot-review read), an
        # ABSENT key (the legacy minimal-payload page), a HUMAN node
        # surviving into the connection (the client-side BOT_LOGINS
        # filter backstops the server-side one), and a PRESENT-but-
        # null connection (the round-15 partial-error class). When:
        # round_bounds parses each. Then: empty/absent/human-only read
        # '' (a LEGITIMATE no-review: the completion withholds on ''
        # but the probe stays readable) while the null connection
        # makes the WHOLE probe unreadable (the empty 4-tuple) —
        # never a readable history whose missing evidence could fail
        # OPEN).
        empty = round_bounds_over(
            bounds_page("2026-08-01T00:00:00Z", bot_reviews=[])
        )
        self.assertEqual(empty.review_head, "")
        absent = round_bounds_over(bounds_page("2026-08-01T00:00:00Z"))
        self.assertEqual(absent.review_head, "")
        human_only = round_bounds_over(
            bounds_page(
                "2026-08-01T00:00:00Z",
                bot_reviews=[bot_review("dead" * 10, login="some-human")],
            )
        )
        self.assertEqual(human_only.review_head, "")
        with self.subTest("null botReviews reads unreadable bounds"):
            page = bounds_page("2026-08-01T00:00:00Z", bot_reviews_null=True)
            self.assertEqual(round_bounds_over(page), EMPTY_BOUNDS)

    def test_author_filtered_connection_ignores_ten_later_human_reviews(self):
        # Given: the thread-3871485043 eviction shape — ten other
        # reviewers' latest reviews fill the latestReviews(last:10)
        # window (the connector's review pushed out of THAT
        # connection) while the folded author-filtered botReviews
        # connection still carries it (the server-side filter —
        # live-verified: no fixed window applies to it at all). When:
        # round_bounds parses it. Then: the evidence is the BOT
        # review's oid — the pre-fix evidence read shared the evicted
        # 10-window and returned '' (every otherwise-valid completion
        # held to timeout).
        page = bounds_page(
            "2026-08-01T00:00:00Z",
            bot_reviews=[bot_review(HEAD_B)],
            humans=10,
        )
        bounds = round_bounds_over(page)
        self.assertEqual(bounds.review_head, HEAD_B)


class PerKindIdentityTests(unittest.TestCase):
    def test_per_kind_identities_ride_the_bounds(self):
        # Given: a formal request and a trigger comment created in the
        # SAME timestamp second (nodes Zm9v and IC_9 — thread
        # 3871485055's collapsing pair). When: round_bounds parses it.
        # Then: the two kinds ride as SEPARATE identities (.request/
        # .trigger — each stream keeps the round-17 createdAt + node-id
        # distinctness) while the INDEX-2 boundary stays the MERGED
        # identity (latest_boundary's max) that the EYES classification
        # and the composite marker consume — the merge survives for
        # CLASSIFICATION only, never for RETENTION; tuple equality with
        # the plain merged 4-tuple holds (the zero-repin seam rule).
        page = bounds_page(
            "2026-08-01T00:00:00Z",
            request=[req_node(SECOND, "Zm9v")],
            trigger=[trigger_node(SECOND, "IC_9")],
        )
        bounds = round_bounds_over(page)
        self.assertEqual(bounds.request, f"{SECOND}|Zm9v")
        self.assertEqual(bounds.trigger, f"{SECOND}|IC_9")
        self.assertEqual(bounds[2], f"{SECOND}|Zm9v")
        self.assertEqual(
            bounds, (HEAD_B, "2026-08-01T00:00:00Z", f"{SECOND}|Zm9v", SECOND)
        )

    def test_single_kind_pages_keep_one_stream(self):
        # Given: the two single-kind shapes — a request-only page and
        # a trigger-only page (the pre-round-18 fixture vocabulary).
        # When: round_bounds parses both. Then: the present kind's
        # stream carries its identity and the absent kind's reads ''
        # (never None — None marks the UNSET legacy shape), and each
        # page's index-2 boundary equals the present kind's identity
        # (latest_boundary of one stream) — the pre-round-18 behavior
        # through the per-kind plumbing, byte-identical.
        request_only = round_bounds_over(
            bounds_page("2026-08-01T00:00:00Z", request=[req_node(SECOND, "Zm9v")])
        )
        self.assertEqual(request_only.request, f"{SECOND}|Zm9v")
        self.assertEqual(request_only.trigger, "")
        self.assertEqual(request_only[2], f"{SECOND}|Zm9v")
        trigger_only = round_bounds_over(
            bounds_page("2026-08-01T00:00:00Z", trigger=[trigger_node(SECOND, "IC_9")])
        )
        self.assertEqual(trigger_only.request, "")
        self.assertEqual(trigger_only.trigger, f"{SECOND}|IC_9")
        self.assertEqual(trigger_only[2], f"{SECOND}|IC_9")


if __name__ == "__main__":
    unittest.main()
