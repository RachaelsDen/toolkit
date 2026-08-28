"""pr_guard reaction round-19 walk tests (PR #49 thread 3871844580
P2) — the REST reactions-walk mutation detection.

3871844580 — "Detect mutations across reaction pages": the walk is
OFFSET-paginated (per_page=100 page numbers, no cursors), so a
reaction added or removed on an earlier page between two page-number
requests shifts the next page's offset — the shifted walk is an
internally inconsistent snapshot (a duplicate item across the page
boundary, an inverted boundary order, or an omitted boundary item),
and latest-wins over it can report NONE or an older reaction —
repeated shifts across the findings-confirmation probes can even
return WAIT FINDINGS while the passing +1 exists. Round 19 rejects
the walk at the LOCALLY PROVABLE mutation signatures (thread
3871844580's pragmatic guard): any reaction id REPEATING across
consecutive pages (an addition shifted the offset into overlap), a
page boundary whose first item's created_at strictly PREDATES the
previous page's last item (a reorder), or a same-second boundary
whose ids REGRESS (REST ids increase monotonically) — each raises
ReactionWalkExpired (the existing walk-unreadable exception, round
5's thread 3867897764: an unusable walk is UNREADABLE, never a
latest-wins input), so the wait probe retries next interval and the
banner fails open. THE DOCUMENTED RESIDUE (the round-15/17 honesty
precedent): a PURE mid-walk deletion that omits exactly the boundary
item leaves NO local signature — page N+1 starts one item later with
no duplicate, inversion, or regression to see — and offset
pagination exposes no cursor/total to prove the absence; the next
probe's fresh walk re-reads the settled list (the omitted reaction
reappears one page earlier), so the mis-read lasts one probe and the
survey authority + post-merge quiet watch remain the backstop.

No network: the walk tests patch the subprocess seam (the
follow-up suite's pagination shape — ids ride the REST wire
vocabulary); the wait-level harm test runs the REAL walk inside the
REAL reading over a scripted page sequence, with round_bounds and
head_ref_oid patched to a stable plain-tuple bracket.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round19_walk_test -v
"""

import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_reaction_probe
from . import pr_guard_reaction
from .pr_guard_merge_fixtures import FakeClock

BOT = pr_guard_reaction.REACTION_BOT
HEAD_OID = "ad333ff80a62bcbcfe54177ea0ff99c8007e4fde"


def r(nid, at, login="human"):
    return {"content": "heart", "created_at": at, "id": nid, "user": {"login": login}}


def bot_react(content, at, rid):
    return {"content": content, "created_at": at, "id": rid, "user": {"login": BOT}}


def page(items):
    return subprocess.CompletedProcess([], 0, stdout=json.dumps(items), stderr="")


def minute(i):
    """An ascending created_at for fixture index i (10:00 + i minutes)."""
    return f"2026-08-26T{10 + i // 60:02d}:{i % 60:02d}:00Z"


def humans(count, start_id=1, start_i=0):
    return [r(start_id + i, minute(start_i + i)) for i in range(count)]


class WalkMutationTests(unittest.TestCase):
    def test_shifted_page_duplicate_rejected(self):
        # Given: the thread-3871844580 addition shift — page 1 read
        # 100 reactions (ids 1-100, ascending); between the page-1
        # and page-2 requests a reaction lands on an earlier page,
        # so the offset shifts INTO OVERLAP and page 2 begins with
        # id 99 — the previous page's last item REPEATS across the
        # boundary. When: gh_reactions walks. Then: ReactionWalkExpired
        # raises — the walk is UNREADABLE, never a latest-wins input;
        # the pre-fix walk flattened both pages (200 combined, the
        # duplicated item crowning whatever mis-read the shifted
        # snapshot carried) and returned it to the reading.
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[page(humans(100)), page([r(99, minute(99))] + humans(99, 101, 100))],
        ):
            with self.assertRaises(pr_guard_reaction.ReactionWalkExpired):
                pr_guard_reaction.gh_reactions(48)

    def test_boundary_inversions_rejected(self):
        # Given: the two boundary-order signatures — (a) page 2's
        # FIRST item predates page 1's LAST item by created_at (a
        # reorder), (b) a same-second boundary whose ids REGRESS
        # (page 1 ends at id 200, page 2 begins at id 199 — REST ids
        # increase monotonically, so a consistent walk never
        # regresses). When: gh_reactions walks each. Then: both
        # raise ReactionWalkExpired (the thread-3867897764 arm owns
        # the raise); the pre-fix walk returned both shifted
        # snapshots as readable lists.
        late = humans(99) + [r(200, minute(99))]
        inverted = [r(150, minute(98))] + humans(50, 201, 99)
        regressed = [r(199, "2026-08-26T11:39:00Z")] + humans(50, 202, 100)
        for p2 in (inverted, regressed):
            with self.subTest(first_id=p2[0]["id"]):
                with mock.patch.object(
                    pr_guard_reaction.subprocess,
                    "run",
                    side_effect=[page(late), page(p2)],
                ):
                    with self.assertRaises(pr_guard_reaction.ReactionWalkExpired):
                        pr_guard_reaction.gh_reactions(48)

    def test_consistent_multipage_walk_still_flattens(self):
        # Given: the survivor — a clean two-page walk whose boundary
        # carries a SAME-SECOND straddle with INCREASING ids (100th
        # item 11:39:00 id 100, 101st item 11:39:00 id 101 — equal
        # seconds are the round-10 ambiguity, NOT a provable shift).
        # When: gh_reactions walks. Then: 120 combined, both pages
        # fetched — the mutation guard rejects only PROVABLE
        # signatures; a legitimate multi-page read never fails.
        # (PR #49 round 24 fixture-seam maintenance, thread
        # 3873592851: the walk now RE-READS page 1 after the short
        # page — the appended identical p1 answers the stability
        # recheck, so the count moves 2 -> 3 and the flattening
        # assertion is unchanged. PR #49 round 33 seam maintenance,
        # thread 3876172349: the walk also RE-READS the terminal
        # short page — the appended identical p2 answers it, so the
        # count moves 3 -> 4.)
        p1 = humans(99) + [r(100, "2026-08-26T11:39:00Z")]
        p2 = [r(101, "2026-08-26T11:39:00Z")] + humans(19, 102, 100)
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[page(p1), page(p2), page(list(p1)), page(list(p2))],
        ) as fake:
            combined = pr_guard_reaction.gh_reactions(48)
        self.assertEqual(len(combined), 120)
        self.assertEqual(fake.call_count, 4)

    def test_mutating_findings_probe_reads_unreadable_not_findings(self):
        # Given: the thread-3871844580 harm at the wait — the bot's
        # EYES (12:00, rid 5) observed on a clean one-page walk at
        # t=0 (the latch arms, the watermark captures it); the
        # findings-confirmation probes at t=5 and t=10 run TWO-PAGE
        # walks whose pages MUTATE mid-walk (the boundary inverts —
        # page 2 opens with an item predating page 1's last) and
        # carry NO bot reaction — the shift omitted the bot's newest
        # activity; the passing +1 (12:31, rid 6) exists the whole
        # time and a SETTLED walk at t=15 reads it. When: wait polls
        # 20s. Then: exit 0 at 15s — the mutating walks raise
        # ReactionWalkExpired into the reading's UNREADABLE arm (both
        # probes read UNREADABLE; the state line prints once, on the
        # CHANGE — the round-2 rule; the six subprocess calls prove
        # both two-page walks ran), no findings transition fires, and
        # the settled walk's +1 follows the surviving EYES watermark
        # out; the pre-fix wait ran latest-wins over the inconsistent
        # walks, read NONE → NONE (the two-probe confirmation), and
        # returned WAIT FINDINGS at t=10 while the passing +1
        # existed.
        clock = FakeClock()
        eyes_walk = [bot_react("eyes", "2026-08-26T12:00:00Z", 5)]
        plus_walk = [bot_react("+1", "2026-08-26T12:31:00Z", 6)]
        shifting = [
            page(humans(100)),
            page([r(150, minute(98))] + humans(49, 201, 99)),
        ] * 2
        script = [page(eyes_walk)] + shifting + [page(plus_walk)]
        out = io.StringIO()
        # PR #49 round 25 fixture-seam maintenance (thread 3873970933):
        # the stable-head bounds ride a RoundBounds carrier whose
        # folded review evidence names the head (the stamp between the
        # surviving EYES 12:00 and the settled +1 12:31) — cold-start
        # completions require the evidence now; the tuple is unchanged.
        carried = pr_guard_reaction_probe.RoundBounds(
            (HEAD_OID, "2026-08-26T11:00:00Z", "", "")
        )
        carried.review_head = HEAD_OID
        carried.review_stamp = "2026-08-26T12:15:00Z"
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=lambda *a, **k: script.pop(0),
        ) as api_mock, mock.patch.object(
            pr_guard_reaction,
            "round_bounds",
            return_value=carried,
        ), mock.patch.object(
            pr_guard_reaction, "head_ref_oid", return_value=HEAD_OID
        ), mock.patch.object(
            pr_guard_reaction, "time", clock
        ), mock.patch.object(
            pr_guard_common, "time", clock
        ), redirect_stdout(out):
            code = pr_guard_reaction.wait_reaction(48, 20)
        self.assertEqual(code, 0)
        self.assertEqual(api_mock.call_count, 6)
        self.assertEqual(out.getvalue().count("BOT REACTION: UNREADABLE"), 1)
        self.assertNotIn("WAIT FINDINGS", out.getvalue())
        self.assertIn("WAIT DONE: THUMBS_UP at 15s", out.getvalue())


if __name__ == "__main__":
    unittest.main()
