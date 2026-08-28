"""pr_guard reaction round-17 tests — the WAIT half (PR #49 threads
3870995905 P1 / 3870995919 P1).

(1) 3870995905 — "Track request identity, not only its timestamp":
two Codex ReviewRequestedEvents created within the SAME timestamp
second are indistinguishable to the round-15 strict `>` compare (the
probe preserved only createdAt), so the second request never advanced
the request high-water; the wait's completion latches — armed by the
preceding round's EYES — stayed certified, and the preceding job's
delayed +1 (postdating the shared timestamp, following the watermark)
printed WAIT DONE before the newly requested round ran. The high-water
now consumes the boundary IDENTITY `createdAt|node id` (the base64
GraphQL node id — ReviewRequestedEvents carry NO databaseId, the
PullRequestReviewThread precedent): an advance fires on a strictly-
newer createdAt OR a same-second DISTINCT node id (distinctness, not
ordering — the base64 id carries no chronology). The advance
machinery itself (reset + gate re-close, threads 3870293188/3870734078)
is unchanged; the request_advances truth table below pins the
identity compare's four shapes.

(2) 3870995919 — "Require head-bound evidence before EYES opens the
gate": an EYES carries no head identity, so after a mid-wait head move
the OLD head's late-posted EYES (postdating the transition floor,
ACTIVE, gate-opening) armed head B's round and its +1 exited 0 with B
reviewed by nobody. The EYES-gate corollary (the implementable
invariant): the EYES still OPENS the gate (it binds the floor
timestamp — the arm alone can never exit without a +1), but the +1's
COMPLETION gains the head-bound review check: post-move (a transition
floor exists), an accepting +1 completes ONLY when the latest BOT
review's commit oid == the observed head (the bot's submitted reviews
carry commit{oid} — the head the review ran against, live-verified
2026-08-27 on PR #49: 5c533c3...). A's late job submits review(A) !=
B, so its +1 HOLDs; B's own round submits review(B) and completes —
the race dies at the EXIT, not the arm, so no post-move round strands.
Request-less COLD STARTS (no floor) keep today's behavior — no review
evidence is demanded (the not-called pin below); an UNREADABLE review
read withholds the completion conservatively.

The PROBE half of round 17 (the identity-carrying request walk, the
@codex review comment-trigger boundary, the partial-error hygiene,
latest_review_commit itself) lives in
pr_guard_reaction_round17_probe_test — the suite-pair split at the
250 pure-LOC ceiling, tests included (the round-4/7/14/15 precedent).

No network: the wait tests patch gh_reactions/round_bounds/
head_ref_oid/latest_review_commit at their seams on the FakeClock
(WALL_NOW 2023-11-14T22:13:20Z; the head-move fixtures' post-floor
stamps key off the t=5 floor 2023-11-14T22:13:25Z, the round-13/14
rule). latest_review_commit patches with create= so the pre-fix
modules (5c533c3, where the seam does not exist yet) run the proofs
without import-time failures — the pre-fix wait simply never calls it.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round17_test -v
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_latch
from .pr_guard_merge_fixtures import FakeClock
from .pr_guard_reaction_probe import RoundBounds

BOT = pr_guard_reaction.REACTION_BOT

HEAD_A = "5c533c3a9b2c8c00eb1d47cb072d24a0975b14f1"
HEAD_B = "14ab97fffffffffffffffffffffffffffffff"

# The same-second pair for thread 3870995905: "YWJj" < "Zm9v" as
# plain strings, so the pre-fix strict `>` compare MISSES the second
# request — the adversarial ordering the identity rule must survive
# (distinctness, not ordering, advances).
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


def run_wait(reads, bounds, timeout_secs, review_head=""):
    """wait_reaction on the FakeClock with per-probe 4-tuple bounds.

    heads default to each probe's OWN bounds oid (a stable bracket; a
    CHANGING oid across the bounds list stages the mid-wait head move
    the 3870995919 fixtures need). review_head feeds the round-17
    latest_review_commit seam (create=True: the pre-fix modules lack
    the attribute and simply never call it — the pre-fix proof shape).
    Returns (code, output, review_mock) so tests can pin call counts.
    """
    clock = FakeClock()
    items = iter(reads)
    probes = iter(bounds)
    probe = {}

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    def fake_head(pr, timeout_secs=None):
        probe["bounds"] = next(probes)
        return probe["bounds"][0]

    def fake_bounds(pr, timeout_secs=None):
        # PR #49 round 18 (threads 3871485035/3871485043): the review
        # evidence rides the BOUNDS now (the folded attr) — review_head
        # feeds the wrap; the latest_review_commit patch below stays
        # as the NEVER-CALLED regression pin (no second lookup).
        # Round 20 (thread 3872194023): the VERDICT STAMP feeds the
        # wrap too — 2024-03-15 sits between the surviving round's
        # EYES (2024-03) and its +1 (2024-04), past the 2023 wall
        # floor; assertions byte-identical (the seam precedent).
        bounds = RoundBounds(probe.pop("bounds"))
        bounds.review_head = review_head
        bounds.review_stamp = "2024-03-15T00:00:00Z"
        return bounds

    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_read
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", side_effect=fake_bounds
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", side_effect=fake_head
    ), mock.patch.object(
        pr_guard_reaction,
        "latest_review_commit",
        return_value=review_head,
        create=True,
    ) as review_mock, mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue(), review_mock


class RequestIdentityAdvanceTests(unittest.TestCase):
    def test_same_second_distinct_request_identity_advances(self):
        # Given: the thread-3870995905 race — the round's verified
        # EYES (2026-08-02, past the 2026-08-01T00:05 request and the
        # 2026-08-01 push) is sampled at t=0 (gate opens, latch arms,
        # watermark captures it); a SECOND Codex request lands inside
        # the SAME timestamp second while the old job sits in its
        # non-atomic EYES-removal/+1 switch (the t=5 probe's boundary
        # identity carries a DIFFERENT node id, lexicographically
        # SMALLER — the adversarial ordering a timestamp/`>` compare
        # cannot see); the preceding job's delayed +1 (2026-08-26T14,
        # postdating the shared second, following the EYES watermark)
        # lands at t=10. When: wait polls 12s. Then: exit 1 — the
        # identity DISTINCTNESS advances the high-water, the
        # round-15/16 reset + gate re-close run (ROUND RE-REQUESTED),
        # the t=5 NONE never re-arms, and the delayed +1 only seeds a
        # held baseline and HOLDs; the pre-fix wait compared
        # "…|YWJj" > "…|Zm9v" -> False, never advanced, armed on the
        # switch-window NONE, and printed WAIT DONE at t=10 before
        # the newly requested round started.
        code, out, _ = run_wait(
            [
                [react("eyes", created="2026-08-02T00:00:00Z", rid=5)],
                [],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
            ],
            [
                (HEAD_B, "2026-08-01T00:00:00Z", REQ_ID_FIRST, REQ_SECOND),
                (HEAD_B, "2026-08-01T00:00:00Z", REQ_ID_SECOND, REQ_SECOND),
                (HEAD_B, "2026-08-01T00:00:00Z", REQ_ID_SECOND, REQ_SECOND),
                (HEAD_B, "2026-08-01T00:00:00Z", REQ_ID_SECOND, REQ_SECOND),
            ],
            12,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("ROUND RE-REQUESTED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)

    def test_same_node_request_identity_never_advances(self):
        # Given: the advance's stability survivor — the boundary
        # identity is BYTE-IDENTICAL across probes (the same request
        # event, node id and all), the round's verified EYES
        # (2026-08-02, past the request and push) opens the gate and
        # arms, and the round's own +1 (2026-08-26T14, following the
        # watermark) lands at t=5. When: wait polls. Then: exit 0 —
        # an UNCHANGED identity never advances (no spurious reset
        # strands a legitimately running round); the identity rule
        # only fires on genuinely NEW boundary events. (PR #49 round
        # 25 fixture-seam maintenance, thread 3873970933: the
        # completing round carries the folded review evidence naming
        # the stable head — cold-start completions require it now.)
        code, out, _ = run_wait(
            [
                [react("eyes", created="2026-08-02T00:00:00Z", rid=5)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=8)],
            ],
            [
                (HEAD_B, "2026-08-01T00:00:00Z", REQ_ID_FIRST, REQ_SECOND),
                (HEAD_B, "2026-08-01T00:00:00Z", REQ_ID_FIRST, REQ_SECOND),
            ],
            600,
            review_head=HEAD_B,
        )
        self.assertEqual(code, 0)
        self.assertNotIn("ROUND RE-REQUESTED", out)
        self.assertIn("WAIT DONE: THUMBS_UP at 5s", out)

    def test_request_advances_truth_table(self):
        # Given: the identity compare's four shapes (thread
        # 3870995905). When: request_advances evaluates them. Then:
        # strictly-newer createdAt advances; same-second DISTINCT
        # node ids advance (BOTH orderings — distinctness, not
        # ordering); the identical identity never advances; '' never
        # advances; a first-ever boundary against '' advances (the
        # high-water baseline rule lives in the wait's
        # readable_probe_seen, not here).
        adv = pr_guard_reaction_latch.request_advances
        self.assertTrue(adv("2026-08-02T00:00:00Z|b", "2026-08-01T00:00:00Z|a"))
        self.assertTrue(adv(f"{REQ_SECOND}|YWJj", REQ_ID_FIRST))
        self.assertTrue(adv(REQ_ID_FIRST, REQ_ID_SECOND))
        self.assertFalse(adv(REQ_ID_FIRST, REQ_ID_FIRST))
        self.assertFalse(adv("", REQ_ID_FIRST))
        self.assertFalse(adv("", ""))
        self.assertTrue(adv(REQ_ID_FIRST, ""))


class HeadBoundCompletionTests(unittest.TestCase):
    def test_post_move_plus_one_requires_head_bound_review(self):
        # Given: the thread-3870995919 race — a cold-NONE t=0 under
        # head A; the ref moves to head B (pushed 2021, an
        # already-pushed commit) at t=5 (floor 2023-11-14T22:13:25Z);
        # the review job for head A — which had posted NOTHING when
        # the move was detected — posts its EYES AFTERWARD (2024-03,
        # past the floor, ACTIVE: it opens B's gate and arms); A's +1
        # (2024-04, following the EYES watermark, postdating B's old
        # bounds) lands at t=15. The round-17 review seam reads the
        # latest BOT review's commit oid = HEAD_A. When: wait polls
        # 15s. Then: exit 1 — post-move the accepting +1 must carry
        # head-bound evidence (review(A) != B), so it HOLDs; the
        # pre-fix wait had no completion check and printed WAIT DONE
        # at t=15 although head B was reviewed by nobody.
        code, out, _ = run_wait(
            [
                [],
                [],
                [react("eyes", created="2024-03-01T00:00:00Z", rid=5)],
                [react("+1", created="2024-04-01T00:00:00Z", rid=6)],
            ],
            [
                (HEAD_A, "2026-08-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
            ],
            15,
            review_head=HEAD_A,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("HEAD MOVED"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("3870995919", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 15s elapsed", out)

    def test_post_move_own_head_round_still_completes(self):
        # Given: the non-stranding survivor — the same post-move
        # shape, but the EYES/+1 belong to head B's OWN round and the
        # bot's submitted review carries commit oid = HEAD_B (the
        # head the review ran against — the +1 is its POST-review
        # verdict, the PR #48 live shape). When: wait polls. Then:
        # exit 0 at 15s — the head-bound check passes and the
        # completion exits; the check kills the race at the EXIT, not
        # the arm, so no genuinely-reviewed post-move round strands.
        code, out, _ = run_wait(
            [
                [],
                [],
                [react("eyes", created="2024-03-01T00:00:00Z", rid=5)],
                [react("+1", created="2024-04-01T00:00:00Z", rid=6)],
            ],
            [
                (HEAD_A, "2026-08-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
            ],
            600,
            review_head=HEAD_B,
        )
        self.assertEqual(code, 0)
        self.assertIn("WAIT DONE: THUMBS_UP at 15s", out)

    def test_cold_start_completion_now_requires_the_review_head_bound(self):
        # Given: the request-less COLD START — a stable head (no
        # transition floor: the move machinery never ran), the
        # round's verified EYES (12:31 past the 12:30 push) at t=0
        # and its +1 (12:32, following the watermark) at t=5; the
        # folded review evidence reads a MISMATCHED commit
        # ("deadbeef" — the old head's still-running job posting its
        # terminal reactions after the new head was pushed, the
        # exact thread-3873970933 race). When: wait polls. Then:
        # exit 1 — the head-bound completion check applies at cold
        # start TOO (round 25, thread 3873970933): the +1 is a
        # POST-review verdict, so a completion whose folded review
        # names another commit holds to timeout while the current
        # head was reviewed by nobody. [REPIN — this test pinned the
        # round-17 cold-start SKIP ("a cold start keeps today's
        # behavior, and the seam is NEVER CALLED") exactly; round 25
        # reverses that semantics, and both docstrings own the
        # supersession. The standalone latest_review_commit seam
        # stays NEVER CALLED — the evidence rides the reading since
        # the round-18 fold, and the not-called pin survives.]
        code, out, review_mock = run_wait(
            [
                [react("eyes", rid=5)],
                [react("+1", created="2026-08-26T12:32:00Z", rid=6)],
            ],
            [
                (HEAD_B, "2026-08-26T12:30:00Z", "", ""),
                (HEAD_B, "2026-08-26T12:30:00Z", "", ""),
            ],
            12,
            review_head="deadbeef",
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)
        review_mock.assert_not_called()

    def test_unreadable_review_head_withholds_post_move_completion(self):
        # Given: the post-move accepting +1 of the 3870995919 race
        # while the review seam reads '' (a failed probe — no bot
        # review readable). When: wait polls 15s. Then: exit 1 — an
        # unreadable review bound WITHHOLDS the completion (never
        # done-on-ambiguity: '' != the observed head), polling
        # continues, and the timeout explains the hold.
        code, out, _ = run_wait(
            [
                [],
                [],
                [react("eyes", created="2024-03-01T00:00:00Z", rid=5)],
                [react("+1", created="2024-04-01T00:00:00Z", rid=6)],
            ],
            [
                (HEAD_A, "2026-08-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
            ],
            15,
            review_head="",
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 15s elapsed", out)


if __name__ == "__main__":
    unittest.main()
