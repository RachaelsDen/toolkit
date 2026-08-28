"""pr_guard reaction round-13 tests (PR #49 threads 3869259808 P1 /
3869259813 P1 / 3869453944 P1 / 3869453955 P1 / 3869453959 P2).

The five unresolved DANGER findings of the round-12 review:

(1) 3869259808 — the head STABILITY bracket accepted a probe whose
either endpoint read '': a failed head_ref_oid (the BEFORE side)
left head_changed("", oid) accepting, so an EYES from a head that
moved A->B inside the failed-before/reactions/bounds sequence armed
the latch under B and A's later +1 satisfied B's bounds — exit 0
with B reviewed by nobody. Either empty endpoint now RAISES
ReactionBracketUnreadable: the whole probe is UNREADABLE (retry next
interval), never a certified mixed snapshot. THUMBS_UP_UNVERIFIED
survives for the READABLE-oid/null-DATES shape only.

(2) 3869259813 — eyes_round_state ignored the formal Codex request
marker round_bounds already carried: a re-request on an UNCHANGED
head left the preceding round's EYES arming, and the preceding
job's delayed +1 (postdating the new request) exited 0 before the
requested round ran. round_bounds now returns the request marker
SEPARATELY (4-tuple: head_oid, pushed, request, composite marker)
and an accepted EYES must postdate the request — the round-11
asymmetry keeps: post-EYES thread-comment markers NEVER bind the
EYES (a request-less round's only marker lands after its own EYES).

(3) 3869453944 — an EYES compared only with the commit's push
timestamp misreads under a retarget/force-push onto an ALREADY-
PUSHED commit (its pushedDate predates the old head's EYES): the
transition probe re-armed the latch from that EYES and the old
round's delayed +1 exited 0. Post-transition the EYES binds the
transition OBSERVATION (the wait's own wall clock at the move
detection — passed to the reading as transition_floor, and applied
to the transition probe's own reading by demotion), and a demoted
probe seeds neither the latch nor the held-+1 replacement baseline.
Cold-start (head stable since wait start) keeps the pushedDate
binding.

(4) 3869453955 — replaced_plus_one accepted ANY different identity:
removing the newer bot +1 B re-surfaced an OLDER +1 A which
'replaced' B and exited 0 with no new review activity. The
replacement now requires the candidate to be strictly NEWER
(reaction_follows ordering, created_at first / numeric id
same-second tie).

(5) 3869453959 — the head-move reset left saw_any_eyes and the
cold-NONE hint state untouched, so head A's EYES suppressed the
'@codex review' hint for head B's never-starting round to the
600s timeout. The cold-NONE detector resets with the other
round-specific state on a head move.

No network: the wait tests patch gh_reactions/round_bounds/
head_ref_oid at their seams on the FakeClock (WALL_NOW is
2023-11-14T22:13:20Z — the transition-floor tests' pre/post-wall
stamps key off it).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round13_test -v
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

HEAD = "50b598a26f0d1e2a3b4c5d6e7f8a9b0c1d2e3f4a"
HEAD_A = "50b598a26f0d1e2a3b4c5d6e7f8a9b0c1d2e3f4a"
HEAD_B = "13ab598ffffffffffffffffffffffffffffffff"

# WALL_NOW (the FakeClock wall start) is 2023-11-14T22:13:20Z: the
# transition-floor stamps split around it (thread 3869453944).
WALL_NOW_ISO = "2023-11-14T22:13:20Z"
PRE_WALL_EYES = "2022-06-01T00:00:00Z"
PRE_WALL_PLUS = "2022-07-01T00:00:00Z"
POST_WALL_EYES = "2024-01-01T00:00:00Z"
POST_WALL_PLUS = "2024-02-01T00:00:00Z"

STABLE_BOUNDS = (HEAD, "2026-08-26T12:30:00Z", "", "")


def react(content, created="2026-08-26T12:31:00Z", rid=None):
    return {
        "content": content,
        "created_at": created,
        "id": rid,
        "user": {"login": BOT},
    }


def read(reactions, bounds, head):
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", return_value=reactions
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", return_value=bounds
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", return_value=head
    ):
        return pr_guard_reaction.bot_review_reaction(48)


def run_wait(reads, bounds, timeout_secs, heads=None):
    """wait_reaction on the FakeClock with per-probe bounds; (code, out).

    heads defaults to each probe's OWN bounds oid (a stable bracket);
    an explicit list stages a failed head read ('') or a move between
    probes (threads 3869259808/3869453944).
    """
    clock = FakeClock()
    items = iter(reads)
    probes = iter(bounds)
    head_reads = iter(heads) if heads is not None else None
    probe = {}

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    def fake_head(pr, timeout_secs=None):
        if head_reads is not None:
            return next(head_reads)
        probe["bounds"] = next(probes)
        return probe["bounds"][0]

    def fake_bounds(pr, timeout_secs=None):
        # PR #49 round 18 (threads 3871485035/3871485043): the review
        # evidence rides the BOUNDS now (the folded attr) — the wrap
        # feeds HEAD_B (the post-floor survivor's own round); inert
        # elsewhere (fixture-seam maintenance in the round-17 GOTCHA
        # precedent, assertions byte-identical). Round 20 (thread
        # 3872194023): the VERDICT STAMP rides beside the oid —
        # 2024-01-15 sits between the surviving round's EYES
        # (2024-01) and its +1 (2024-02), past the 2023 wall floor.
        bounds = RoundBounds(probe.pop("bounds") if head_reads is None and "bounds" in probe else next(probes))
        bounds.review_head = HEAD_B
        bounds.review_stamp = "2024-01-15T00:00:00Z"
        return bounds

    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_read
    ), mock.patch.object(
        pr_guard_reaction, "round_bounds", side_effect=fake_bounds
    ), mock.patch.object(
        pr_guard_reaction, "head_ref_oid", side_effect=fake_head
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue()


class UnreadableHeadBracketTests(unittest.TestCase):
    def test_failed_before_endpoint_discards_the_probe(self):
        # Given: the cheap head-only read FAILED ('') while the
        # bounds probe succeeded (thread 3869259808's fresh evidence
        # — head_changed("", oid) accepted the probe). When:
        # bot_review_reaction reads. Then: ReactionBracketUnreadable
        # — either empty bracket endpoint makes the WHOLE probe
        # UNREADABLE (retry next interval), never a certified mixed
        # snapshot the wait could arm a moved head's round from.
        with mock.patch.object(
            pr_guard_reaction, "gh_reactions", return_value=[react("eyes")]
        ), mock.patch.object(
            pr_guard_reaction, "round_bounds", return_value=STABLE_BOUNDS
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=""
        ):
            with self.assertRaises(
                pr_guard_reaction.ReactionBracketUnreadable
            ) as raised:
                pr_guard_reaction.bot_review_reaction(48)
        self.assertIn("3869259808", str(raised.exception))

    def test_failed_after_endpoint_discards_the_probe(self):
        # Given: the head-only read succeeded but the round probe
        # failed (oid ''). When: read. Then: the SAME unreadable
        # bracket — a probe whose head_oid is empty is an UNREADABLE
        # reading (retry), superseding the empty-bounds UNVERIFIED
        # read of rounds 6/7.
        self.assertRaises(
            pr_guard_reaction.ReactionBracketUnreadable,
            read,
            [react("+1", created="2026-08-26T14:00:00Z", rid=6)],
            ("", "", "", ""),
            HEAD,
        )

    def test_null_dates_with_readable_oid_stay_unverified(self):
        # Given: a READABLE oid whose pushedDate/committedDate both
        # read null (live-verified shape on PR #49). When: read.
        # Then: THUMBS_UP_UNVERIFIED — the state survives round 13
        # through its null-dates shape (never done, never arming).
        self.assertEqual(
            read(
                [react("+1", created="2026-08-26T14:00:00Z", rid=6)],
                (HEAD, "", "", ""),
                HEAD,
            ),
            "THUMBS_UP_UNVERIFIED",
        )

    def test_uncertified_bracket_never_arms_moved_head(self):
        # Given: the thread's exact race — the t=0 probe's head read
        # FAILS while the ref sits on B (pushed 12:30) and the bot's
        # EYES (13:00, round A's leftover postdating B's push) is
        # latest; A's +1 (14:00) then lands and postdates B's bounds.
        # When: wait polls 12s. Then: exit 1 — the uncertified probe
        # read UNREADABLE (never armed), the +1 HOLDS (no transition
        # was ever observed), and exit 0 needs a real round signal;
        # the pre-fix wait armed on the mixed snapshot and exited 0
        # at t=5 with B reviewed by nobody (thread 3869259808).
        code, out = run_wait(
            [
                [react("eyes", created="2026-08-26T13:00:00Z", rid=5)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=6)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=6)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=6)],
            ],
            [STABLE_BOUNDS] * 4,
            12,
            heads=["", HEAD, HEAD, HEAD],
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("BOT REACTION: UNREADABLE"), 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)
        self.assertIn("WAIT TIMEOUT: 12s elapsed", out)


class RequestBoundEyesTests(unittest.TestCase):
    def test_eyes_round_state_truth_table(self):
        # Given: the EYES classification against the head push, the
        # formal codex REQUEST (3869259813), and the transition
        # floor (3869453944). When: eyes_round_state evaluates.
        # Then: only a STRICTLY-greater created_at past EVERY bound
        # reads EYES; a pre-request EYES is the prior round's
        # leftover (EYES_STALE) exactly as a pre-head one is; an
        # unreadable push stays EYES_UNVERIFIED.
        for created, pushed, requested, floor, expected in (
            ("2026-08-26T12:00:00Z", "2026-08-26T11:00:00Z", "2026-08-26T13:00:00Z", "", "EYES_STALE"),
            ("2026-08-26T13:00:00Z", "2026-08-26T11:00:00Z", "2026-08-26T13:00:00Z", "", "EYES_STALE"),
            ("2026-08-26T13:30:00Z", "2026-08-26T11:00:00Z", "2026-08-26T13:00:00Z", "", "EYES"),
            (PRE_WALL_EYES, "2021-01-01T00:00:00Z", "", WALL_NOW_ISO, "EYES_STALE"),
            (POST_WALL_EYES, "2021-01-01T00:00:00Z", "", WALL_NOW_ISO, "EYES"),
            ("2026-08-26T12:00:00Z", "", "2026-08-26T13:00:00Z", "", "EYES_UNVERIFIED"),
        ):
            self.assertEqual(
                pr_guard_reaction_latch.eyes_round_state(
                    created, pushed, requested, floor
                ),
                expected,
                (created, pushed, requested, floor),
            )

    def test_re_request_cannot_ride_old_eyes_to_exit_zero(self):
        # Given: codex RE-REQUESTED at 13:00 on an UNCHANGED head
        # (pushed 11:00) while the preceding round's EYES (12:00)
        # remains; the preceding job's delayed +1 (14:00) postdates
        # the new request. When: wait polls 12s. Then: exit 1 — the
        # old EYES reads EYES_STALE against the request boundary and
        # arms nothing, so the +1 HOLDS; the pre-fix wait armed from
        # the request-blind EYES and exited 0 at t=5 before the
        # newly requested round ran (thread 3869259813).
        code, out = run_wait(
            [
                [react("eyes", created="2026-08-26T12:00:00Z", rid=5)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=6)],
                [react("+1", created="2026-08-26T14:00:00Z", rid=6)],
            ],
            [
                (HEAD, "2026-08-26T11:00:00Z", "2026-08-26T13:00:00Z", "2026-08-26T13:00:00Z")
            ]
            * 3,
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn("EYES (stale — predates the current round's boundary", out)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertNotIn("WAIT DONE", out)

    def test_post_eyes_comment_marker_never_binds_the_eyes(self):
        # Given: a REQUEST-LESS round whose only marker (the bot's
        # 13:05 thread comment — its comments land AFTER its own
        # 12:00 EYES; the round-11 asymmetry). When: read. Then:
        # EYES — the composite marker binds the +1 completion only;
        # binding it here would strand every request-less round.
        self.assertEqual(
            read(
                [react("eyes", created="2026-08-26T12:00:00Z", rid=5)],
                (HEAD, "2026-08-26T11:00:00Z", "", "2026-08-26T13:05:00Z"),
                HEAD,
            ),
            "EYES",
        )


class TransitionBoundEyesTests(unittest.TestCase):
    def test_retarget_to_old_commit_requires_post_transition_activity(self):
        # Given: the thread-3869453944 race — head A (pushed
        # 2022-05) shows the bot's EYES (2022-06, current, arming at
        # t=0); the ref then RETARGETS onto an already-pushed commit
        # B whose 2021 push PREDATES that EYES, so the raw
        # push-timestamp comparison re-classifies the SAME EYES
        # current under B. A's delayed +1 (2022-07) lands at t=10;
        # B's OWN round then runs (EYES 2024-01 at t=15, +1 2024-02
        # at t=20) — both postdating the transition observation.
        # When: wait polls. Then: exit 0 ONLY at 20s.
        # [ROUND-22 REPIN, thread 3872740865 — the documented exact
        # hole: the pre-fix assertion pinned the round-13 WAIT-SIDE
        # DEMOTION (the transition probe re-classified the
        # pre-observation EYES EYES_STALE, suppressing the
        # replacement baseline); round 22 DELETED the demotion — the
        # floor is stamped at the LATER observation time, so the new
        # head's own between-polls EYES was demoted with the old
        # head's leftover and a completed review timed out. The EYES
        # now ARMS at the move probe (no stale render appears), and
        # A's +1 withholds at the EXIT instead — the round-17/21
        # evidence legs (review_head == observed head
        # AND review_stamp > floor AND +1 > stamp): its +1 2022-07
        # PREDATES the folded review stamp 2024-01-15, so the arm
        # relaxed and the exit guarded — the old head's job still
        # cannot complete.]
        code, out = run_wait(
            [
                [react("eyes", created=PRE_WALL_EYES, rid=5)],
                [react("eyes", created=PRE_WALL_EYES, rid=5)],
                [react("+1", created=PRE_WALL_PLUS, rid=6)],
                [react("eyes", created=POST_WALL_EYES, rid=7)],
                [react("+1", created=POST_WALL_PLUS, rid=8)],
                [react("+1", created=POST_WALL_PLUS, rid=8)],
            ],
            [
                (HEAD_A, "2022-05-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
                (HEAD_B, "2021-01-01T00:00:00Z", "", ""),
            ],
            600,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.count("HEAD MOVED"), 1)
        self.assertIn("HOLDING THUMBS_UP: this +1's round cannot be proven", out)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("WAIT DONE: THUMBS_UP at 20s", out)
        self.assertNotIn("WAIT DONE: THUMBS_UP at 10s", out)


class OrderedReplacementTests(unittest.TestCase):
    def test_replacement_requires_newer_identity(self):
        # Given: two bot +1 objects — A older (11:00, id 1), B newer
        # (12:00, id 2). When: replaced_plus_one evaluates both
        # directions (plus the same-second id tie). Then: only the
        # strictly-NEWER candidate replaces — removing B must not
        # let A masquerade as B's replacement (thread 3869453955);
        # reaction_follows' ordering (created_at first, numeric id
        # on a same-second tie) decides.
        for held, current, expected in (
            ("2026-08-26T12:00:00Z|2", "2026-08-26T11:00:00Z|1", False),
            ("2026-08-26T11:00:00Z|1", "2026-08-26T12:00:00Z|2", True),
            ("2026-08-26T12:00:00Z|1", "2026-08-26T12:00:00Z|2", True),
            ("2026-08-26T12:00:00Z|2", "2026-08-26T12:00:00Z|1", False),
            ("2026-08-26T12:00:00Z|2", "", False),
            ("", "2026-08-26T12:00:00Z|2", False),
        ):
            self.assertEqual(
                pr_guard_reaction_latch.replaced_plus_one(held, current),
                expected,
                (held, current),
            )

    def test_removed_newer_plus_one_falls_back_to_older_times_out(self):
        # Given: the wait starts holding the bot's NEWER +1 B
        # (12:00, id 2 — postdating the 10:00 push) while an OLDER
        # +1 A (11:00, id 1) also exists; B is then REMOVED, making
        # A the latest reaction. When: wait polls 12s. Then: exit 1
        # — A predates B (no new review activity), so it is NOT a
        # replacement and the held +1 keeps holding to the timeout;
        # the pre-fix predicate treated any different identity as a
        # replacement and exited 0 at t=5 (thread 3869453955).
        code, out = run_wait(
            [
                [react("+1", created="2026-08-26T12:00:00Z", rid=2)],
                [react("+1", created="2026-08-26T11:00:00Z", rid=1)],
                [react("+1", created="2026-08-26T11:00:00Z", rid=1)],
                [react("+1", created="2026-08-26T11:00:00Z", rid=1)],
            ],
            [(HEAD, "2026-08-26T10:00:00Z", "", "")] * 4,
            12,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING THUMBS_UP", out)
        self.assertIn("exit 0 was withheld", out)
        self.assertNotIn("WAIT DONE", out)


class ColdNoneHeadResetTests(unittest.TestCase):
    def test_head_move_rearms_the_cold_none_hint(self):
        # Given: the bot showed EYES under head A (12:31 past the
        # 12:30 push); the ref then moves to head B and codex NEVER
        # STARTS for B (NONE from t=5 on). When: wait polls 20s.
        # Then: the '@codex review' HINT fires EXACTLY ONCE at t=15
        # (10s of continuous cold NONE under B) — the head-move reset
        # cleared saw_any_eyes and the hint state WITH the latch
        # (thread 3869453959); the pre-fix wait carried head A's
        # EYES forward and suppressed the hint to the timeout.
        code, out = run_wait(
            [[react("eyes", rid=5)], [], [], [], []],
            [
                (HEAD_A, "2026-08-26T12:30:00Z", "", ""),
                (HEAD_B, "2026-08-26T12:29:00Z", "", ""),
                (HEAD_B, "2026-08-26T12:29:00Z", "", ""),
                (HEAD_B, "2026-08-26T12:29:00Z", "", ""),
                (HEAD_B, "2026-08-26T12:29:00Z", "", ""),
            ],
            20,
        )
        self.assertEqual(code, 1)
        self.assertEqual(
            out.count(
                "HINT: no EYES ever observed and 10s of NONE — the "
                "bot may have failed to start; consider posting a "
                "'@codex review' comment to trigger it manually."
            ),
            1,
        )
        self.assertIn("WAIT TIMEOUT: 20s elapsed", out)


if __name__ == "__main__":
    unittest.main()
