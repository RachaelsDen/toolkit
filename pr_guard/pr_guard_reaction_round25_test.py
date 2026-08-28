"""pr_guard reaction round-25 walk + probe tests (PR #49 threads
3873970919 P2 / 3873970927 P1 — the per-page walk revalidation and
the strict rerun connections).

Thread 3873970919 (P2, walk): round 24's page-1 stability recheck
only detects mutations in the FIRST offset window. With more than
200 reactions, deleting an item from page 2's range AFTER page 2 is
fetched but BEFORE page 3 is fetched shifts page 3 and silently
SKIPS its former first reaction — page 1 remains byte-identical
(and `_page_shift_reason` still cannot detect a pure deletion), so
the pre-fix recheck passed and the flattened walk crowned the wrong
latest bot reaction. If the skipped reaction is the bot's current
EYES while an older +1 remains visible, the mixed snapshot can let
an armed waiter report WAIT DONE during an active review. Round 25
generalizes the recheck to EVERY FULL PAGE the walk fetched
(1..last-full — each full page's window can shift a later page's
offset; the short final page shifts nothing past it): after the
walk completes, each full page is re-read and its newest item's
identity (`created_at|id`) required unchanged, all riding the
walk's EXISTING deadline. Drift, a failed re-read, or an expired
deadline raises ReactionWalkExpired (unreadable probe, retry).

Thread 3873970927 (P1, probe): when a boundary lookup paginates,
the round-24 bracket RE-RUN is supposed to prove that no newer
manual-trigger comment arrived during the walk — but an OMITTED
`triggerComments` field was accepted as "unchanged", so a
successful-but-partial/malformed re-run certified the preceding
round's boundary while a trigger had arrived, and the waiter kept
the old boundary and could accept the old round's terminal +1
before the requested review started. The recheck parse is now
STRICT: this is a re-run of OUR OWN assembled query (a success
response always materializes every requested alias), so an absent
or null connection means the partial/malformed class — unreadable
bounds, retry next interval. The INITIAL query's legacy-absent-key
tolerance stays (the minimal-payload fixtures' no-trigger read);
the asymmetry is pinned by a survivor.

No network: the walk tests patch the subprocess seam (the round-24
walk fixture shape — ids ride the REST wire vocabulary); the probe
tests run REAL round_bounds over scripted ROUND_QUERY + walk pages
(the round-24 probe-suite shape). The WAIT-level harm of thread
3873970919 (the EYES-skip replacement exit) lives in the sibling
pr_guard_reaction_round25_wait_test with the thread-3873970933
wait-side fixtures.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round25_test -v
"""

import json
import subprocess as sp
import unittest
from unittest import mock

from . import pr_guard_reaction
from . import pr_guard_reaction_probe
from . import pr_guard_reaction_walk
from .pr_guard_merge_fixtures import FakeClock

BOT = pr_guard_reaction.REACTION_BOT
HEAD_OID = "c05572ba62bcbcfe54177ea0ff99c8007e4fde"


def r(nid, at, login="human"):
    return {"content": "heart", "created_at": at, "id": nid, "user": {"login": login}}


def bot_react(content, at, rid):
    return {"content": content, "created_at": at, "id": rid, "user": {"login": BOT}}


def page(items):
    return sp.CompletedProcess([], 0, stdout=json.dumps(items), stderr="")


def fail_page():
    return sp.CompletedProcess([], 1, stdout="", stderr="gh: error")


def minute(i):
    """An ascending created_at for fixture index i (10:00 + i minutes)."""
    return f"2026-08-26T{10 + i // 60:02d}:{i % 60:02d}:00Z"


def humans(count, start_id=1, start_i=0):
    return [r(start_id + i, minute(start_i + i)) for i in range(count)]


class PerPageRevalidationTests(unittest.TestCase):
    def test_page_two_deletion_shift_rejected_by_page_two_reread(self):
        # Given: the thread-3873970919 residue — a THREE-page walk
        # (page 1 ids 1-100, page 2 ids 101-200, both full; page 3
        # short); between the page-2 and page-3 requests the reaction
        # id 150 is DELETED from page 2's range, so page 3 returns old
        # ids 202-211 and SKIPS its former first item (old id 201)
        # with NO duplicate, order inversion, or id regression for
        # the page-pair signatures to see — and PAGE 1 IS IDENTICAL
        # (the deletion is outside its window), so round 24's page-1
        # re-read passes too: only the PAGE-2 re-read catches it (the
        # deletion slid old id 201 into page 2's window, so the
        # re-read's newest item is old id 201, not the original 200).
        # When: gh_reactions walks. Then: ReactionWalkExpired raises —
        # the mixed 211-item walk is UNREADABLE, never a latest-wins
        # input; the pre-fix walk flattened the shifted snapshot and
        # returned it (the pre-fix proof: no raise).
        p1 = humans(100)
        p2 = humans(100, 101, 100)
        p3 = humans(10, 202, 201)
        p2_after = humans(100, 102, 101)
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[
                page(p1),
                page(p2),
                page(p3),
                page(list(p1)),
                page(p2_after),
            ],
        ):
            with self.assertRaises(pr_guard_reaction.ReactionWalkExpired):
                pr_guard_reaction.gh_reactions(48)

    def test_every_full_page_reread_after_multipage_walk(self):
        # Given: the survivor — a clean FOUR-page walk (THREE full
        # pages of 100, then a short 20): every full page's window can
        # shift a later page's offset, so pages 1..3 are EACH re-read
        # and all come back identical. When: gh_reactions walks.
        # Then: 320 combined over EIGHT subprocess calls (4 walk
        # pages + 3 per-page re-reads + the round-33 TERMINAL
        # short-page re-read, thread 3876172349 — the appended
        # identical p4 answers it, so the count pin moves 7 -> 8);
        # the pre-fix walk spent FIVE calls on the same readable
        # result (only page 1 re-read — the pre-fix proof: 5 != 7).
        p1, p2, p3 = humans(100), humans(100, 101, 100), humans(100, 201, 200)
        p4 = humans(20, 301, 300)
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[
                page(p1), page(p2), page(p3), page(p4),
                page(list(p1)), page(list(p2)), page(list(p3)), page(list(p4)),
            ],
        ) as fake:
            combined = pr_guard_reaction.gh_reactions(48)
        self.assertEqual(len(combined), 320)
        self.assertEqual(fake.call_count, 8)

    def test_short_final_page_never_reread(self):
        # Given: a three-page walk with TWO full pages (100 + 100 +
        # a short 50) — the SHORT final page shifts nothing past it,
        # so only pages 1 and 2 are re-read by the full-page loop.
        # When: gh_reactions walks. Then: 250 combined over SIX
        # subprocess calls — PR #49 ROUND 33 (thread 3876172349)
        # SUPERSEDES this pin's five-call expectation: the terminal
        # SHORT page is now revalidated TOO (after the full-page
        # rechecks, its LENGTH and newest identity both required
        # unchanged — a deletion on it shrinks the length without
        # moving the identity, and the bot's latest +1 lived exactly
        # there), so the SIXTH call re-reads page 3 (the call-count
        # 5 -> 6 and the last-call argv pin page=2 -> page=3 are the
        # repin; the flattening assertion is unchanged).
        p1, p2, p3 = humans(100), humans(100, 101, 100), humans(50, 201, 200)
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[
                page(p1), page(p2), page(p3), page(list(p1)), page(list(p2)), page(list(p3)),
            ],
        ) as fake:
            combined = pr_guard_reaction.gh_reactions(48)
        self.assertEqual(len(combined), 250)
        self.assertEqual(fake.call_count, 6)
        self.assertTrue(fake.call_args.args[0][-1].endswith("page=3"))

    def test_failed_page_two_reread_reads_unreadable(self):
        # Given: a three-page walk whose PAGE-2 RE-READ FAILS (gh
        # exits nonzero — a transient API failure: a re-read that
        # cannot run validates nothing). When: gh_reactions walks.
        # Then: ReactionWalkExpired raises — page 2's window is
        # UNVALIDATED, so the walk is UNREADABLE (retry next
        # interval), never a latest-wins input trusted on an unproven
        # window; the pre-fix walk never re-read page 2 and returned
        # the readable list (the pre-fix proof: no raise).
        with mock.patch.object(
            pr_guard_reaction.subprocess,
            "run",
            side_effect=[
                page(humans(100)),
                page(humans(100, 101, 100)),
                page(humans(10, 201, 200)),
                page(humans(100)),
                fail_page(),
            ],
        ):
            with self.assertRaises(pr_guard_reaction.ReactionWalkExpired):
                pr_guard_reaction.gh_reactions(48)

    def test_expired_deadline_before_page_two_reread_reads_unreadable(self):
        # Given: a three-page walk under a 2s budget whose PAGE-1
        # RE-READ (the FOURTH call) burns 5 FAKE seconds — page 1's
        # own recheck completes (the identity compared BEFORE the
        # burn is visible to the deadline check), and the deadline
        # expires exactly before the PAGE-2 recheck could run (every
        # recheck rides the walk's EXISTING deadline, never a fresh
        # grant). When: gh_reactions walks. Then: ReactionWalkExpired
        # raises at the page-2 recheck over FOUR subprocess calls —
        # an expired deadline cannot validate page 2's window either;
        # the pre-fix walk re-read page 1 only and returned the
        # readable list over FOUR calls with no raise (the pre-fix
        # proof).
        clock = FakeClock()
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(argv[-1])
            if len(calls) == 4:
                clock.sleep(5.0)
            items = (
                humans(100) if argv[-1].endswith("page=1")
                else humans(100, 101, 100) if argv[-1].endswith("page=2")
                else humans(10, 201, 200)
            )
            return page(items)

        with mock.patch.object(
            pr_guard_reaction_walk.subprocess, "run", side_effect=fake_run
        ) as fake, mock.patch.object(
            pr_guard_reaction_walk, "time", clock
        ):
            with self.assertRaises(pr_guard_reaction.ReactionWalkExpired):
                pr_guard_reaction_walk.gh_reactions(48, timeout_secs=2.0)
        self.assertEqual(fake.call_count, 4)


BOT_LOGIN = pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN
HEAD_A = "c05572000000000000000000000000000000a"
PUSH = "2026-11-14T22:00:00Z"
REQ_AT = "2026-11-14T22:10:00Z"
TRG_AT = "2026-11-14T22:09:00Z"
EMPTY = ("", "", "", "")


def gh_page(pr_node, rc=0):
    return sp.CompletedProcess(
        args=[],
        returncode=rc,
        stdout=json.dumps({"data": {"repository": {"pullRequest": pr_node}}}),
    )


def human_request(created, minute_id):
    return {"createdAt": created, "id": minute_id, "requestedReviewer": {"login": "octocat"}}


def req_node(created, nid, login=BOT_LOGIN):
    return {"createdAt": created, "id": nid, "requestedReviewer": {"login": login}}


def trg_node(created, nid):
    return {"createdAt": created, "id": nid, "body": "@codex review"}


def round_page(paginating="request", head=HEAD_A, request=(), trigger=None):
    """A well-formed ROUND_QUERY page. paginating names the ONE kind
    whose newest-50 window is marker-FREE with earlier pages pending
    (that walk walks back — the post-query window opens); "none" puts
    the request ON page one (no walk, no recheck). request/trigger
    seed the newest windows directly (the re-run pages). trigger
    OMITTED keeps the triggerComments key ABSENT (thread 3873970927's
    exact partial-response shape)."""
    pr = {
        "headRefOid": head,
        # PR #49 round 28 fixture-seam maintenance (thread
        # 3875089268): every re-run page now carries baseRefOid (the
        # strict recheck validates the base beside the head); the
        # bare-oid shape keeps base_bound '' (no floor effect).
        "baseRefOid": "9ed444e0d5b1ad3b3ff6c9d3e3b4a5c6d7e8f9a0",
        "headRef": {"target": {"pushedDate": PUSH, "committedDate": PUSH}},
        "timelineItems": {
            "pageInfo": {
                "hasPreviousPage": paginating == "request",
                "startCursor": "c1" if paginating == "request" else None,
            },
            "nodes": list(request)
            or [human_request(f"2026-11-14T22:0{i}:00Z", f"H_{i}") for i in (1, 2, 3)],
        },
        "headTransition": {"nodes": []},
        "latestReviews": {"nodes": []},
        "reviewThreads": {"nodes": []},
    }
    if trigger is not None:
        pr["triggerComments"] = {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": list(trigger),
        }
    return pr


def walk_page(request=()):
    """A REQUEST_WALK_QUERY answering page carrying the boundary the
    newest-50 window evicted; no earlier pages."""
    return {
        "timelineItems": {
            "pageInfo": {"hasPreviousPage": False, "startCursor": None},
            "nodes": list(request),
        }
    }


def run_bounds(pages):
    script = iter(pages)
    with mock.patch.object(
        pr_guard_reaction_probe.subprocess,
        "run",
        side_effect=lambda *a, **k: gh_page(next(script)),
    ), mock.patch.object(pr_guard_reaction_probe, "head_ref_oid", return_value=HEAD_A):
        return pr_guard_reaction_probe.round_bounds(48, timeout_secs=None)


class StrictRerunConnectionTests(unittest.TestCase):
    def test_absent_trigger_rerun_discards_probe(self):
        # Given: the thread-3873970927 race — the newest-50 request
        # window is codex-FREE with earlier pages pending, so the
        # walk fetches RA_9 (22:10) backwards AFTER ROUND_QUERY
        # captured the newest page; DURING the continuation a NEW
        # manual-trigger comment TC_10 (22:12) lands at the timeline's
        # top — and the bracket RE-RUN comes back a SUCCESSFUL but
        # PARTIAL response whose triggerComments field is OMITTED
        # entirely (the request picture itself is unchanged: the
        # re-run's codex-free window matches the walked-back RA_9, so
        # ONLY the trigger field decides). When: round_bounds parses.
        # Then: ('', '', '', '') — the re-run of OUR OWN assembled
        # query must carry a present, well-formed connection (a
        # success response always materializes the alias), so the
        # omission is the partial/malformed class: unreadable bounds,
        # retry next interval — the NEXT probe's own newest window
        # sees the trigger; the pre-fix recheck accepted the omitted
        # key as "unchanged" and returned the readable OLD-round
        # bounds (the pre-fix proof: a readable 4-tuple, not EMPTY).
        bounds = run_bounds(
            [
                round_page(paginating="request"),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                round_page(paginating="request"),
            ]
        )
        self.assertEqual(bounds, EMPTY)

    def test_null_trigger_rerun_discards_probe(self):
        # Given: the present-but-NULL twin — the re-run's
        # triggerComments reads null inside an otherwise-successful
        # response. When: round_bounds parses. Then: ('', '', '',
        # '') — the null connection was ALREADY the round-15
        # partial-error class (green on BOTH sides; the strict
        # round-25 parse keeps it).
        script = iter(
            [
                gh_page(round_page(paginating="request")),
                gh_page(walk_page(request=[req_node(REQ_AT, "RA_9")])),
                gh_page(
                    {
                        "headRefOid": HEAD_A,
                        "headRef": {"target": {"pushedDate": PUSH}},
                        "timelineItems": {"pageInfo": {"hasPreviousPage": False}, "nodes": []},
                        "triggerComments": None,
                        "latestReviews": {"nodes": []},
                        "reviewThreads": {"nodes": []},
                    }
                ),
            ]
        )
        with mock.patch.object(
            pr_guard_reaction_probe.subprocess,
            "run",
            side_effect=lambda *a, **k: next(script),
        ), mock.patch.object(pr_guard_reaction_probe, "head_ref_oid", return_value=HEAD_A):
            self.assertEqual(
                pr_guard_reaction_probe.round_bounds(48, timeout_secs=None), EMPTY
            )

    def test_initial_absent_trigger_stays_tolerated(self):
        # Given: the ASYMMETRY survivor — the INITIAL query's page
        # carries NO triggerComments key (the legacy minimal-payload
        # fixture shape: an absent alias reads no-trigger, and the
        # request window itself carries RA_9 so NOTHING paginates —
        # no re-run, no recheck). When: round_bounds parses the ONE
        # page. Then: the fully readable bounds with the request
        # identity third and an empty trigger — the initial parse
        # stays fixture-tolerant while the RERUN parse is strict
        # (thread 3873970927's documented asymmetry); green on BOTH
        # sides.
        bounds = run_bounds([round_page(paginating="none", request=[req_node(REQ_AT, "RA_9")])])
        self.assertEqual(bounds, (HEAD_A, PUSH, f"{REQ_AT}|RA_9", REQ_AT))

    def test_strict_rerun_with_well_formed_trigger_passes(self):
        # Given: the survivor — the paginating request walk (RA_9
        # walked back below the newest window) whose re-run page
        # carries a WELL-FORMED triggerComments connection (a
        # human comment, no trigger) beside the codex-free request
        # window and the unchanged head. When: round_bounds parses.
        # Then: the fully readable bounds — the strict recheck
        # accepts a present, well-formed connection whose visible
        # trigger identities match the walk's report (none); a
        # legitimate paginating probe never fails (green on BOTH
        # sides: the pre-fix recheck skipped the absent key and
        # passed the same picture).
        bounds = run_bounds(
            [
                round_page(paginating="request"),
                walk_page(request=[req_node(REQ_AT, "RA_9")]),
                round_page(
                    paginating="request",
                    trigger=[{"createdAt": "2026-11-14T22:01:00Z", "id": "C_1", "body": "looks fine"}],
                ),
            ]
        )
        self.assertEqual(bounds, (HEAD_A, PUSH, f"{REQ_AT}|RA_9", REQ_AT))


if __name__ == "__main__":
    unittest.main()
