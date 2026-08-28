"""pr_guard reaction round-24 walk tests (PR #49 thread 3873592851
P2 — "Reject pure-deletion shifts during reaction pagination").

Round 19's mutation guard (thread 3871844580) rejected only the
locally PROVABLE page-pair signatures — a duplicate id, an inverted
boundary order, a same-second id regression — and DOCUMENTED the
pure-deletion residue: deleting an item from page 1's range between
the page-1 and page-2 requests shifts every later page's offset so
page 2 SKIPS its former first item with no signature at all, and
offset pagination exposes no cursor/total to prove the absence. If
the skipped item is the bot's current EYES, the mixed walk's latest
BOT reaction is a PRECEDING +1 and an already-armed waiter exits 0
while the review is still active. Round 24 closes the residue with
the page-1 STABILITY RECHECK: after a multi-page walk completes,
gh_reactions RE-READS page 1 (one extra lightweight REST call riding
the walk's existing deadline) and requires the re-read page's newest
item IDENTITY (`created_at|id`) to match the item the ORIGINAL
page-1 read reported as newest — the first page is a POSITIONAL
window (the first 100 items of the current list), so any membership
change in that range moves a different item into the window's last
position and identical newest identities prove the window unchanged.
Drift, a failed/malformed re-read, or an expired deadline raises
ReactionWalkExpired (the round-5/19 unreadable exception): probe
UNREADABLE, retry next interval — SUPERSEDING round 19's documented
residue (receipt 3872138825). Single-page walks never recheck (no
offset window exists).

No network: the walk tests patch the subprocess seam (the round-19
walk fixture shape — ids ride the REST wire vocabulary); the
wait-level harm test runs the REAL walk inside the REAL reading over
a scripted page sequence, with round_bounds/head_ref_oid patched to a
stable plain-tuple bracket.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round24_test -v
"""

import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_reaction
from . import pr_guard_reaction_walk
from .pr_guard_merge_fixtures import FakeClock

BOT = pr_guard_reaction.REACTION_BOT
HEAD_OID = "9f56841a62bcbcfe54177ea0ff99c8007e4fde"


def r(nid, at, login="human"):
    return {"content": "heart", "created_at": at, "id": nid, "user": {"login": login}}


def bot_react(content, at, rid):
    return {"content": content, "created_at": at, "id": rid, "user": {"login": BOT}}


def page(items):
    return subprocess.CompletedProcess([], 0, stdout=json.dumps(items), stderr="")


def fail_page():
    return subprocess.CompletedProcess([], 1, stdout="", stderr="gh: error")


def minute(i):
    """An ascending created_at for fixture index i (10:00 + i minutes)."""
    return f"2026-08-26T{10 + i // 60:02d}:{i % 60:02d}:00Z"


def humans(count, start_id=1, start_i=0):
    return [r(start_id + i, minute(start_i + i)) for i in range(count)]


def tail(count, start_id=302, start_min=40):
    """Humans landing AFTER the EYES (12:40+) — a post-deletion page 2
    whose newest items still follow the bot's reactions ascending."""
    return [
        r(start_id + i, f"2026-08-26T12:{start_min + i:02d}:00Z") for i in range(count)
    ]


class PureDeletionRecheckTests(unittest.TestCase):
    def test_pure_deletion_shift_rejected_by_page_one_reread(self):
        # Given: the thread-3873592851 residue — page 1 read 100
        # reactions (ids 1-100 ascending); between the page-1 and
        # page-2 requests the reaction id 100 is DELETED from page
        # 1's range, so page 2 returns old ids 102-111 and SKIPS its
        # former first item (old id 101) with NO duplicate, order
        # inversion, or id regression for round 19's signatures to
        # see — but the page-1 re-read catches it: the deletion slid
        # old id 101 into the window, so the re-read's newest item
        # (minute-100 id 101) no longer matches the original page-1
        # newest (minute-99 id 100). When: gh_reactions walks. Then:
        # ReactionWalkExpired raises — the mixed walk is UNREADABLE,
        # never a latest-wins input; the pre-fix walk flattened the
        # 110-item shifted snapshot and returned it to the reading
        # (the pre-fix proof).
        p1 = humans(100)
        p2 = humans(10, 102, 101)
        reread = humans(99) + [r(101, minute(100))]
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[page(p1), page(p2), page(reread)],
        ):
            with self.assertRaises(pr_guard_reaction.ReactionWalkExpired):
                pr_guard_reaction.gh_reactions(48)

    def test_stable_multipage_walk_reread_still_flattens(self):
        # Given: the survivor — a clean two-page walk whose page-1
        # re-read returns the IDENTICAL first page (the newest item's
        # identity is unchanged: no mutation shifted any window).
        # When: gh_reactions walks. Then: 120 combined over FOUR
        # subprocess calls (page 1, page 2, the page-1 re-read — the
        # recheck rides every multi-page walk — plus the round-33
        # TERMINAL short-page re-read, thread 3876172349: the
        # appended identical p2 answers it; the count pin moves
        # 3 -> 4) — a legitimate multi-page read never fails.
        p1 = humans(100)
        p2 = humans(20, 101, 100)
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[page(p1), page(p2), page(list(p1)), page(list(p2))],
        ) as fake:
            combined = pr_guard_reaction.gh_reactions(48)
        self.assertEqual(len(combined), 120)
        self.assertEqual(fake.call_count, 4)

    def test_single_page_walk_never_rereads(self):
        # Given: the COMMON read — a single short page (under 100
        # reactions): no offset window exists for a mid-walk
        # deletion to shift. When: gh_reactions walks. Then: the
        # list returns after ONE subprocess call — the recheck is a
        # multi-page-only discipline and the single-page probe keeps
        # its exact subprocess count; green on BOTH sides.
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[page(humans(42))],
        ) as fake:
            combined = pr_guard_reaction.gh_reactions(48)
        self.assertEqual(len(combined), 42)
        self.assertEqual(fake.call_count, 1)

    def test_failed_reread_reads_unreadable(self):
        # Given: a two-page walk whose page-1 RE-READ FAILS (gh
        # exits nonzero — a transient API failure, not a house-die
        # condition: a re-read that cannot run validates nothing).
        # When: gh_reactions walks. Then: ReactionWalkExpired raises
        # — the snapshot is UNVALIDATED, so the walk is UNREADABLE
        # (retry next interval), never a latest-wins input trusted
        # on an unproven bracket; the pre-fix walk returned the
        # readable 120-item list with no recheck at all (the
        # pre-fix proof).
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[page(humans(100)), page(humans(20, 101, 100)), fail_page()],
        ):
            with self.assertRaises(pr_guard_reaction.ReactionWalkExpired):
                pr_guard_reaction.gh_reactions(48)

    def test_expired_deadline_before_reread_reads_unreadable(self):
        # Given: a two-page walk under a 2s budget whose SECOND page
        # burns 5 FAKE seconds (the deadline expires after the walk
        # loop completed but before the recheck could run — the
        # recheck rides the walk's EXISTING deadline, never a fresh
        # grant; the argv match is the exact page-1/page-2 TOKEN —
        # "page=1" is a substring of per_page=100, the first draft's
        # collision made this a mid-walk expiry instead). When:
        # gh_reactions walks. Then: ReactionWalkExpired raises — an
        # expired deadline cannot validate the snapshot either; the
        # pre-fix walk returned the readable list with no recheck
        # (the pre-fix proof).
        clock = FakeClock()

        def fake_run(argv, **kwargs):
            url = argv[-1]
            if url.endswith("page=2"):
                clock.sleep(5.0)
            items = humans(100) if url.endswith("page=1") else humans(1, 101, 100)
            return page(items)

        with mock.patch.object(
            pr_guard_reaction_walk.subprocess, "run", side_effect=fake_run
        ), mock.patch.object(pr_guard_reaction_walk, "time", clock):
            with self.assertRaises(pr_guard_reaction.ReactionWalkExpired):
                pr_guard_reaction_walk.gh_reactions(48, timeout_secs=2.0)

    def test_pure_deletion_eyes_skip_cannot_exit_zero(self):
        # Given: the thread-3873592851 HARM at the wait — t=0 reads
        # NONE (99 human reactions, one page: the round has not
        # started; the reading arms the round-5 saw-non-done latch
        # while the empty watermark binds nothing). Between t=0 and
        # t=5 the bot posts its +1 (12:30, rid 200 — position 100),
        # its EYES (12:31, rid 201 — position 101), and ten humans
        # land behind them (12:40+); the t=5 walk reads page 1 (the
        # 99 humans + the +1), a page-1 deletion (one human) shifts
        # the offset, and page 2 returns the tail humans only — the
        # EYES (old position 101) is SKIPPED with no page-pair
        # signature, so the mixed walk crowns the PRECEDING +1.
        # When: wait polls 10s (probes at t=0/5/10, then the
        # at-deadline check ends it). Then: exit 1 — the page-1
        # re-read catches the drift (the EYES slid into the re-read
        # window: the post-deletion first page is 98 humans + the
        # +1 + the EYES) and the t=5 probe reads UNREADABLE (one
        # state line, printed on the change — the round-2 rule; the
        # EIGHT subprocess calls prove the full walk + recheck
        # ran), the t=10 SETTLED walk reads the EYES (page 1 now
        # ends with it — stable re-read), and the wait times out
        # with the review ACTIVE; the pre-fix wait exited 0 on the
        # mixed walk's +1 at t=5 (WAIT DONE while the EYES was
        # live — the pre-fix proof). (PR #49 round 33 seam
        # maintenance, thread 3876172349: the settled t=10 walk
        # also RE-READS its terminal short page — the appended
        # identical tail page answers it, so the call pin moves
        # 7 -> 8.)
        clock = FakeClock()
        plus = bot_react("+1", "2026-08-26T12:30:00Z", 200)
        eyes = bot_react("eyes", "2026-08-26T12:31:00Z", 201)
        shifted_p1 = humans(98) + [plus, eyes]
        script = [
            page(humans(99)),
            page(humans(99) + [plus]),
            page(tail(10)),
            page(list(shifted_p1)),
            page(list(shifted_p1)),
            page(tail(10)),
            page(list(shifted_p1)),
            page(tail(10)),
        ]
        out = io.StringIO()
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=lambda *a, **k: script.pop(0),
        ) as api_mock, mock.patch.object(
            pr_guard_reaction,
            "round_bounds",
            return_value=(HEAD_OID, "2026-08-26T11:00:00Z", "", ""),
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
        ), mock.patch.object(
            pr_guard_reaction, "time", clock
        ), mock.patch.object(
            pr_guard_common, "time", clock
        ), redirect_stdout(out):
            code = pr_guard_reaction.wait_reaction(48, 10)
        self.assertEqual(code, 1)
        self.assertEqual(api_mock.call_count, 8)
        self.assertEqual(out.getvalue().count("BOT REACTION: UNREADABLE"), 1)
        self.assertNotIn("WAIT DONE", out.getvalue())
        self.assertIn("BOT REACTION: EYES", out.getvalue())


if __name__ == "__main__":
    unittest.main()
