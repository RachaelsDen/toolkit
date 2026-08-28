"""pr_guard reaction round-17 evidence tests — REPINNED round 18.

The suite-pair companion of pr_guard_reaction_round17_probe_test
(the round-14 split precedent at the 250 pure-LOC ceiling, tests
included): this file pinned latest_review_commit — the head-bound
review read of thread 3870995919 (P1) — whose bot's +1-is-the-
POST-review-verdict semantics round 18 KEEPS. The REPIN (round 18,
threads 3871485035 P1 / 3871485043 P2): the original two tests
encoded the pre-round-18 LOOKUP mechanics — a STANDALONE
latestReviews(last:10){author commit{oid}} subprocess dispatched
AFTER the reading's stable-head bracket (3871485035's unbracketed
window) whose fixed ten-review window ten other reviewers' latest
reviews evicted the connector's review from (3871485043's held-to-
timeout completions). Round 18 folded the read INTO the round probe
as the author-filtered `botReviews` connection (reviews(last:1,
author:"chatgpt-codex-connector[bot]") — live-verified read-only on
PR #49: the filter is server-side and matches ONLY the [bot]-suffixed
login), so latest_review_commit is now the EXTRACTION over the
round-query node and these tests feed it pr_node payloads — the
same semantic survivor (the BOT review's commit oid, never a
human's; '' when none) against the folded seam.

No network: latest_review_commit runs REAL over in-memory pr_node
payloads (the round-18 folded shape).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round17_evidence_test -v
"""

import unittest

from . import pr_guard_reaction
from . import pr_guard_reaction_probe

HEAD_B = "14ab97fffffffffffffffffffffffffffffff"


def pr_node(bot_reviews):
    """A ROUND_QUERY pullRequest node carrying the folded botReviews
    connection (the author-filtered shape)."""
    return {"botReviews": {"nodes": list(bot_reviews)}}


class ReviewCommitTests(unittest.TestCase):
    def test_latest_review_commit_reads_the_bot_head(self):
        # Given: a folded connection whose window carries a HUMAN
        # review then the BOT's (the chronologically LAST bot-authored
        # node — live-verified field: submitted reviews carry
        # commit{oid}, the head the review ran against). When:
        # latest_review_commit extracts it. Then: the BOT review's
        # commit oid (never the human's).
        node = pr_node(
            [
                {
                    "author": {"login": "RachaelsDen"},
                    "commit": {"oid": "dead" * 10},
                },
                {
                    "author": {"login": pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN},
                    "commit": {"oid": HEAD_B},
                },
            ]
        )
        self.assertEqual(
            pr_guard_reaction_probe.latest_review_commit(node), HEAD_B
        )

    def test_latest_review_commit_human_only_absent_and_null_read_empty(self):
        # Given: a connection whose reviews are all HUMAN-authored (a
        # non-bot node cannot be evidence — the client-side BOT_LOGINS
        # filter backstops the server's), a page with NO botReviews
        # key (the legacy minimal-payload shape), and a PRESENT-but-
        # null connection (the round-15 partial-error class). When:
        # latest_review_commit extracts each. Then: '' for the
        # human-only and absent shapes — no bot review is no evidence
        # (the wait's post-move completion check withholds on '',
        # never fails open) — and None for the null connection (the
        # WHOLE probe retries; live-verified: an author with zero
        # reviews reads EMPTY NODES, a legitimate '', not null).
        human_only = pr_node(
            [{"author": {"login": "RachaelsDen"}, "commit": {"oid": "dead" * 10}}]
        )
        self.assertEqual(
            pr_guard_reaction_probe.latest_review_commit(human_only), ""
        )
        self.assertEqual(pr_guard_reaction_probe.latest_review_commit({}), "")
        self.assertIs(
            pr_guard_reaction_probe.latest_review_commit({"botReviews": None}),
            None,
        )


if __name__ == "__main__":
    unittest.main()
