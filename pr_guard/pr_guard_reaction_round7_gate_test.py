"""pr_guard reaction round-7 GATE tests (PR #49 threads 3868158297
P1 / 3868158304 P2).

Thread 3868158297 (P1): pre-merge's CLOSING survey is
decision-bearing — it runs bannerless (reaction=False), the same
decision-surface rule as the guarded merge act and the quiet watch;
the banner keeps its home in the human-facing surveys (pre-merge's
OPENING survey included).

Thread 3868158304 (P2): the request-events timeline is read
through a 50-event window with BACKWARDS pagination BEFORE the
codex filter — a current codex request can no longer vanish behind
later unrelated requests (the marker's disappearance used to
reclassify the unchanged old +1 from STALE to current and exit 0
early); a FAILED or deadline-expired walk reads the bounds
UNREADABLE (never a missing marker biasing a +1 toward done).

Split from pr_guard_reaction_round7_test at the 250 pure-LOC
ceiling (tests included) — the gate/survey discipline beside the
reaction-module semantics (the round-4 suite pair precedent).

No network: the pre-merge test mocks survey/gh_rest_pr/rulesets;
the window tests patch the probe module's subprocess seam
(round_bounds moved there at the round-7 split).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round7_gate_test -v
"""

import io
import json
import os
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import cli
from . import pr_guard_reaction
from . import pr_guard_reaction_probe
from .pr_guard_merge_fixtures import FakeClock, thread
from .pr_guard_rulesets_test import gate_ruleset

BOT = pr_guard_reaction.REACTION_BOT
PUSHED = "2026-08-26T11:00:00Z"
CODEX_REQUEST_AT = "2026-08-26T10:00:00Z"
# PR #49 round 8 repin (thread 3868443452): round_bounds grew a
# head-first headRefOid element — pull_payload's own headRefOid.
HEAD_OID = "8ed444e0d5b1ad3b3ff6c9d3e3b4a5c6d7e8f9a0"


def react(content, created="2026-08-26T12:00:00Z", rid=None):
    return {
        "content": content,
        "created_at": created,
        "id": rid,
        "user": {"login": BOT},
    }


class PreMergeClosingBannerlessTests(unittest.TestCase):
    def test_pre_merge_closing_survey_is_bannerless(self):
        # Given: the pre-merge gate over a clean resolved-thread
        # snapshot (head/base stable, ruleset covering dev). When:
        # pre_merge runs its two surveys. Then: the CLOSING survey —
        # the decision-bearing one whose late-findings check prints
        # CLEAN — passed reaction=False and dispatched NO banner read
        # (thread 3868158297: the banner's 15s informational read may
        # never sit between the final snapshot and the go/no-go); the
        # OPENING survey keeps the human-facing banner; exit 0 CLEAN.
        flags = []

        def fake_survey(pr, reaction=True):
            flags.append(reaction)
            return [thread("11", "resolved")]

        pr_read = {
            "head": {"sha": "8ed444e0d5b1ad3b3ff6c9d3e3b4a5c6d7e8f9a0"},
            "base": {"ref": "dev"},
        }
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"GH_HOST": ""}), mock.patch.object(
            cli, "survey", side_effect=fake_survey
        ), mock.patch.object(
            cli, "gh_rest_pr", return_value=pr_read
        ), mock.patch.object(
            cli, "fetch_gate_rulesets", return_value=[gate_ruleset()]
        ), mock.patch.object(
            cli, "default_branch", return_value="main"
        ), redirect_stdout(out):
            code = cli.pre_merge(39)
        self.assertEqual(code, 0)
        self.assertEqual(flags, [True, False])
        self.assertIn("CLEAN", out.getvalue())


def request_events(codex_at, humans):
    events = [{"createdAt": codex_at, "requestedReviewer": {"login": BOT}}]
    events += [human_event(minute) for minute in range(1, humans + 1)]
    return events


def human_event(minute):
    return {
        "createdAt": f"2026-08-26T13:{minute:02d}:00Z",
        "requestedReviewer": {"login": "octocat"},
    }


def human_events(count):
    return [human_event(minute) for minute in range(1, count + 1)]


def pull_payload(timeline_nodes, has_previous=False, cursor="c1"):
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "headRefOid": "8ed444e0d5b1ad3b3ff6c9d3e3b4a5c6d7e8f9a0",
                    # PR #49 round 28 fixture-seam maintenance (thread
                    # 3875089268): the bracket recheck now REQUIRES
                    # baseRefOid on every re-run page (the paginating
                    # probe's re-run must carry the base it certified).
                    "baseRefOid": "9ed444e0d5b1ad3b3ff6c9d3e3b4a5c6d7e8f9a0",
                    "headRef": {"target": {"pushedDate": PUSHED}},
                    "timelineItems": {
                        "pageInfo": {
                            "hasPreviousPage": has_previous,
                            "startCursor": cursor,
                        },
                        "nodes": timeline_nodes,
                    },
                    # PR #49 round 25 fixture-seam maintenance (thread
                    # 3873970927): the bracket RECHECK now REQUIRES a
                    # present, well-formed triggerComments connection
                    # on every re-run page (a re-run of our own
                    # assembled query always materializes the alias —
                    # absence is the partial-response class). The
                    # empty in-page window keeps the trigger walk at
                    # '' (no trigger, no pagination).
                    "triggerComments": {
                        "pageInfo": {"hasPreviousPage": False, "startCursor": None},
                        "nodes": [],
                    },
                    # PR #49 round 32 fixture-seam maintenance (thread
                    # 3876001004): the recheck likewise REQUIRES a
                    # present headTransition connection (an absent key
                    # is the partial class, never "provably no
                    # transition"); the empty node list keeps the
                    # pushedDate binding and the '' transition stamp.
                    "headTransition": {"nodes": []},
                    "latestReviews": {"nodes": []},
                    "reviewThreads": {"nodes": []},
                }
            }
        }
    }


class RequestEventWindowTests(unittest.TestCase):
    def probe(self, pages):
        """round_bounds against scripted graphql pages; (bounds, argvs)."""
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            walking = any(str(token).startswith("before=") for token in argv)
            page = pages[1] if walking else pages[0]
            if isinstance(page, subprocess.CompletedProcess):
                return page
            return subprocess.CompletedProcess(
                [], 0, stdout=json.dumps(page), stderr=""
            )

        with mock.patch.object(
            pr_guard_reaction_probe.subprocess, "run", side_effect=fake_run
        ), mock.patch.object(
            # Thread 3872980781 (round 22) fixture-seam maintenance,
            # FOLDED by thread 3873592857 (round 24): a paginating
            # probe re-RUNS the round query — the non-walking call
            # answers with pages[0] (the codex-free newest window the
            # recheck expects) — and the patched head seam is now the
            # NEVER-CALLED fold pin (the re-run's own headRefOid
            # replaced round 22's separate head read), keeping the
            # subprocess call counts these tests pin.
            pr_guard_reaction_probe, "head_ref_oid", return_value=HEAD_OID
        ):
            bounds = pr_guard_reaction.round_bounds(48)
        return bounds, calls

    def test_six_events_codex_oldest_found_single_page(self):
        # Given: the codex request is the OLDEST of SIX request events
        # — the exact shape GitHub's truncation evicted under the old
        # last:5 window (five later human requests push it out BEFORE
        # the client-side codex filter runs). When: the probe reads.
        # Then: the codex marker IS found in the one widened page —
        # ONE subprocess, no walk (thread 3868158304).
        bounds, calls = self.probe(
            [pull_payload(request_events(CODEX_REQUEST_AT, 5))]
        )
        self.assertEqual(
                bounds, (HEAD_OID, PUSHED, CODEX_REQUEST_AT, CODEX_REQUEST_AT)
            )
        self.assertEqual(len(calls), 1)

    def test_codex_beyond_fifty_found_by_backwards_walk(self):
        # Given: 55 request events — the codex request oldest, 54
        # later human requests — so even the widened window (the
        # newest 50) carries no codex event, and pageInfo says more
        # exist. When: the probe reads. Then: ONE backwards page
        # (before:<cursor>) is fetched and the codex marker is found
        # there — the server-side truncation can no longer hide a
        # current codex request behind unrelated requests (thread
        # 3868158304). (PR #49 round 24 fixture-seam maintenance,
        # thread 3873592857: the paginating probe now RE-RUNS the
        # round query — the non-walking call answers with pages[0],
        # the codex-free newest window the recheck expects, so the
        # count moves 2 -> 3 and the bounds/before-cursor assertions
        # are unchanged.)
        bounds, calls = self.probe(
            [
                pull_payload(human_events(50), has_previous=True),
                pull_payload(request_events(CODEX_REQUEST_AT, 4)),
            ]
        )
        self.assertEqual(
                bounds, (HEAD_OID, PUSHED, CODEX_REQUEST_AT, CODEX_REQUEST_AT)
            )
        self.assertEqual(len(calls), 3)
        self.assertTrue(
            any(str(token) == "before=c1" for token in calls[1]),
            calls[1],
        )

    def test_walk_failure_reads_unreadable_bounds(self):
        # Given: a codex-free newest 50 with earlier pages pending,
        # and the walk page FAILS (gh exits 1). When: the probe
        # reads. Then: ("", "") — an unreadable walk is never "no
        # codex request exists": a missing marker would bias the old
        # +1 toward done, the exact 3868158304 direction; unreadable
        # bounds read THUMBS_UP_UNVERIFIED instead.
        bounds, _ = self.probe(
            [
                pull_payload(human_events(50), has_previous=True),
                subprocess.CompletedProcess([], 1, stdout="", stderr="boom"),
            ]
        )
        self.assertEqual(bounds, ("", "", "", ""))

    def test_walk_failure_plus_one_reads_unreadable_probe(self):
        # Given: the bot's +1 (12:00, postdating the 11:00 push) read
        # against bounds whose request-event walk FAILED. When:
        # bot_review_reaction classifies. Then: the whole probe is
        # UNREADABLE — ReactionBracketUnreadable (the failed walk
        # reads the bounds ('', '') and either empty bracket endpoint
        # discards the probe; the wait retries next interval, the
        # banner fails open). (PR #49 round 13 repin, thread
        # 3869259808: the pre-round-13 reading was THUMBS_UP_UNVERIFIED
        # — a held state; the composed conservative arm of 3868158304
        # beside round 6's 3868047719 keeps its never-done direction
        # and tightens it to never-certified.)
        with mock.patch.object(
            pr_guard_reaction,
            "gh_reactions",
            return_value=[react("+1", created="2026-08-26T12:00:00Z", rid=1)],
        ), mock.patch.object(
            pr_guard_reaction_probe.subprocess,
            "run",
            side_effect=lambda argv, **kwargs: subprocess.CompletedProcess(
                [], 1, stdout="", stderr="boom"
            ),
        ):
            with self.assertRaises(pr_guard_reaction.ReactionBracketUnreadable):
                pr_guard_reaction.bot_review_reaction(48)

    def test_walk_expiry_mid_walk_reads_unreadable_bounds(self):
        # Given: a 0.05s probe budget; the newest-50 page is instant,
        # but the backwards walk page burns 1.0 fake second and still
        # carries no codex event with earlier pages pending. When:
        # the probe reads. Then: ("", "") — the EXPIRED walk is
        # unreadable, not markerless (a stopped-early walk must never
        # read as "no codex request exists", thread 3868158304).
        clock = FakeClock()
        page_one = pull_payload(human_events(50), has_previous=True)

        def fake_run(argv, **kwargs):
            if any(str(token).startswith("before=") for token in argv):
                clock.sleep(1.0)
                return subprocess.CompletedProcess(
                    [], 0,
                    stdout=json.dumps(
                        pull_payload(human_events(5), has_previous=True)
                    ),
                    stderr="",
                )
            return subprocess.CompletedProcess(
                [], 0, stdout=json.dumps(page_one), stderr=""
            )

        with mock.patch.object(
            pr_guard_reaction_probe.subprocess, "run", side_effect=fake_run
        ), mock.patch.object(pr_guard_reaction_probe, "time", clock):
            self.assertEqual(
                pr_guard_reaction_probe.round_bounds(48, timeout_secs=0.05),
                ("", "", "", ""),
            )

    def test_exhausted_walk_no_codex_leaves_head_binding(self):
        # Given: request events on both pages are ALL human, and the
        # walk exhausts the connection (no earlier pages). When: the
        # probe reads. Then: the marker is '' and the head push alone
        # binds, exactly the round-1 semantics a genuinely codex-free
        # history always had (3868158304 widens the window; it
        # invents no markers). (PR #49 round 24 fixture-seam
        # maintenance, thread 3873592857: the paginating probe now
        # RE-RUNS the round query — the third call answers with
        # pages[0]'s codex-free newest window, the unchanged picture
        # the recheck expects; the bounds assertion is unchanged.)
        bounds, calls = self.probe(
            [
                pull_payload(human_events(50), has_previous=True),
                pull_payload(human_events(5)),
            ]
        )
        self.assertEqual(bounds, (HEAD_OID, PUSHED, "", ""))
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
