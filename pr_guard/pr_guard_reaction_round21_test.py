"""pr_guard reaction round-21 tests — the WAIT half (PR #49 thread
3872631145 P2: "Bind the findings exit to the current head").

The EYES -> NONE completion path bypassed head_bound entirely: after
an observed head A->B transition, A's still-running job can post its
EYES AFTER the transition floor (a verified ACTIVE reading — it
opens the none-arming gate and arms saw_verified_eyes), finish WITH
feedback, and remove the EYES; the confirming absent probes then
carried A's round's findings signal while the folded review evidence named
head A and B's round may not have started — the wait returned exit 3
on a round that never reviewed the head it would steer the
orchestrator to survey. The exit-3 gate now carries the SAME
post-transition evidence legs the THUMBS_UP exits have (rounds
17/18/20): review_head == observed_head AND review_stamp >
transition_floor (the +1-follows-stamp leg is MOOT — no +1 is
accepted on a findings exit). An unbound findings signal does NOT
exit: the wait keeps polling (the new head's round produces its own
signal); the confirming-absence + saw_verified_eyes machinery is
UNCHANGED — only the EXIT gate gained the check. [Round-23 repin,
thread 3873317562: the confirmation is the THIRD consecutive absent
probe (FINDINGS_GRACE_PROBES), so these fixtures carry one more
absent probe than round 21 shipped; the evidence legs are untouched.]

No network: the fixtures run REAL round_bounds over scripted
ROUND_QUERY pages (the round-18/19/20 shape) so the folded
review_head/review_stamp evidence rides the REAL probe through the
Reading attrs. FakeClock WALL_NOW 2023-11-14T22:13:20Z; the stamps
key INSIDE the wall window (the round-19 GOTCHA #2 rule — the t=5
move detection stamps the floor 22:13:25).

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round21_test -v
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

HEAD_A = "20ab97ffffffffffffffffffffffffffffffa"
HEAD_B = "20ab97ffffffffffffffffffffffffffffffb"

# The wall window (round-19 GOTCHA #2): probes land at 22:13:20
# (t=0), 22:13:25 (t=5 — the head-move detection stamps the
# transition floor 2023-11-14T22:13:25Z), 22:13:30 (t=10), 22:13:35
# (t=15).
PUSH = "2023-11-14T22:00:00Z"
STALE_STAMP = "2023-11-14T22:13:10Z"
A_JOB_STAMP = "2023-11-14T22:13:27Z"
B_JOB_STAMP = "2023-11-14T22:13:28Z"
# PR #49 round 26 (thread 3874405295) fixture-seam maintenance: the
# transition floor is the HEAD'S OWN BOUND now, and a mid-wait
# retarget onto an already-pushed commit is BY DEFINITION a force
# push (round 15, live-verified) — the coincidence fixture's HEAD_B
# pages carry the event so the pre-move review predates the EVENT
# bound (the no-event retarget the old pages staged is the unreal
# shape; the wall floor used to cover it).
RETARGET_EVENT = "2023-11-14T22:13:22Z"


def react(content, created, rid):
    return {"content": content, "created_at": created, "id": rid, "user": {"login": BOT}}


def gh_page(payload):
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(payload)
    )


def bot_node(oid, at):
    return {
        "author": {"login": pr_guard_reaction_probe.GRAPHQL_BOT_LOGIN},
        "commit": {"oid": oid},
        "submittedAt": at,
    }


def bounds_page(pushed, oid, review=None, force_push=None):
    """A well-formed ROUND_QUERY page; review/force_push None keep
    the key ABSENT (the round-18 legacy-minimal-payload rule)."""
    page = {
        "data": {
            "repository": {
                "pullRequest": {
                    "headRefOid": oid,
                    "headRef": {"target": {"pushedDate": pushed, "committedDate": pushed}},
                    "timelineItems": {
                        "pageInfo": {"hasPreviousPage": False, "startCursor": None},
                        "nodes": [],
                    },
                    "headTransition": {"nodes": []},
                    "latestReviews": {"nodes": []},
                    "reviewThreads": {"nodes": []},
                }
            }
        }
    }
    pr = page["data"]["repository"]["pullRequest"]
    if review is not None:
        pr["botReviews"] = {"nodes": [review]}
    if force_push is not None:
        pr["headTransition"] = {"nodes": [{"createdAt": force_push}]}
    return page


def run_wait_pages(reads, pages, heads, timeout_secs):
    """wait_reaction with REAL round_bounds over scripted ROUND_QUERY
    pages (the round-18/19/20 shape); heads scripts head_ref_oid per
    probe (a CHANGING oid stages the mid-wait head move)."""
    clock = FakeClock()
    items = iter(reads)
    script = iter(pages)
    head_reads = iter(heads)

    def fake_read(pr, timeout_secs=None):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    out = io.StringIO()
    with mock.patch.object(
        pr_guard_reaction, "gh_reactions", side_effect=fake_read
    ), mock.patch.object(
        pr_guard_reaction,
        "head_ref_oid",
        side_effect=lambda pr, timeout_secs=None: next(head_reads),
    ), mock.patch.object(
        pr_guard_reaction_probe.subprocess,
        "run",
        side_effect=lambda *a, **k: gh_page(next(script)),
    ), mock.patch.object(
        pr_guard_reaction, "time", clock
    ), mock.patch.object(
        pr_guard_common, "time", clock
    ), redirect_stdout(out):
        code = pr_guard_reaction.wait_reaction(48, timeout_secs)
    return code, out.getvalue()


class HeadBoundFindingsExitTests(unittest.TestCase):
    def test_old_head_findings_signal_cannot_exit(self):
        # Given: the thread-3872631145 race — the ref MOVES A->B at
        # t=5 (floor 22:13:25) while head A's review job is still
        # running; A's job posts its EYES at 22:13:26 (post-floor — a
        # verified ACTIVE reading that opens the gate and arms
        # saw_verified_eyes), finishes WITH feedback (its review of
        # A submitting at 22:13:27, post-floor), and removes the
        # EYES; B's round never starts. The t=10, t=15, and t=20
        # probes read the confirming absent triple — pre-fix the
        # wait returned exit 3 on A's round's signal with B reviewed
        # by nobody. When: wait polls 20s. Then: exit 1 — the
        # folded evidence
        # (review_head A != observed B) fails the findings exit's new
        # head leg, HOLDING FINDINGS prints with the thread id, and
        # the wait keeps polling to its timeout instead of claiming
        # findings (the pre-fix proof: exit 3 at the confirming
        # probe; the round-23 repin, thread 3873317562, moved the
        # confirmation to the third consecutive absent probe).
        code, out = run_wait_pages(
            [
                [],
                [react("eyes", "2023-11-14T22:13:26Z", 5)],
                [],
                [],
                [],
            ],
            [
                bounds_page(PUSH, HEAD_A, review=bot_node(HEAD_A, A_JOB_STAMP)),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_A, A_JOB_STAMP)),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_A, A_JOB_STAMP)),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_A, A_JOB_STAMP)),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_A, A_JOB_STAMP)),
            ],
            [HEAD_A, HEAD_B, HEAD_B, HEAD_B, HEAD_B],
            20,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING FINDINGS", out)
        self.assertIn("3872631145", out)
        self.assertNotIn("WAIT FINDINGS", out)
        self.assertIn("WAIT TIMEOUT: 20s elapsed", out)

    def test_new_head_findings_signal_still_exits(self):
        # Given: the NON-STRANDING survivor — the identical post-move
        # shape, but the folded evidence names the OBSERVED head and
        # submits after the floor (B's own findings round: review(B)
        # at 22:13:28 > 22:13:25), so the absent triple is genuinely
        # the current head's findings signal. When: wait polls 20s.
        # Then: exit 3 at 20s (the round-23 repin, thread 3873317562:
        # the third consecutive absent probe) with the WAIT FINDINGS
        # line — the
        # evidence bind withholds NOTHING a legitimate post-move
        # findings round reports (green on BOTH sides of the round-21
        # change: the pre-fix exit had no check to fail).
        code, out = run_wait_pages(
            [
                [],
                [react("eyes", "2023-11-14T22:13:26Z", 5)],
                [],
                [],
                [],
            ],
            [
                bounds_page(PUSH, HEAD_A, review=bot_node(HEAD_B, B_JOB_STAMP)),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_B, B_JOB_STAMP)),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_B, B_JOB_STAMP)),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_B, B_JOB_STAMP)),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_B, B_JOB_STAMP)),
            ],
            [HEAD_A, HEAD_B, HEAD_B, HEAD_B, HEAD_B],
            20,
        )
        self.assertEqual(code, 3)
        self.assertIn("WAIT FINDINGS: EYES → NONE at 20s", out)
        self.assertNotIn("HOLDING FINDINGS", out)

    def test_pre_floor_review_coincidence_cannot_exit(self):
        # Given: the stamp leg in isolation — the retarget-coincidence
        # twin of the THUMBS_UP guard (round 20): the ref moved A->B
        # onto an already-pushed commit a PRE-move bot review of B
        # names (oid B == observed head BY COINCIDENCE, submitted
        # 22:13:10 < the floor), and the post-floor EYES's
        # round ended without any newer bot review (its job cancelled
        # after the EYES removal). The head leg PASSES (B == B) but
        # the evidence predates the transition. When: wait polls 20s.
        # Then: exit 1 — the stamp leg withholds the findings exit
        # (the pre-fix proof: exit 3 at the confirming probe on the
        # oid alone; the round-23 repin, thread 3873317562, moved
        # the confirmation to the third consecutive absent probe).
        # [Round 26 fixture-seam maintenance, thread 3874405295: the
        # floor is the head's OWN bound now — max(B's 22:00
        # pushedDate, the force-push EVENT 22:13:22 the HEAD_B pages
        # carry; the stamp 22:13:10 predates the event) — the
        # wall-clock floor that used to reject it is gone.]
        code, out = run_wait_pages(
            [
                [],
                [react("eyes", "2023-11-14T22:13:26Z", 5)],
                [],
                [],
                [],
            ],
            [
                bounds_page(PUSH, HEAD_A, review=bot_node(HEAD_B, STALE_STAMP)),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_B, STALE_STAMP), force_push=RETARGET_EVENT),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_B, STALE_STAMP), force_push=RETARGET_EVENT),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_B, STALE_STAMP), force_push=RETARGET_EVENT),
                bounds_page(PUSH, HEAD_B, review=bot_node(HEAD_B, STALE_STAMP), force_push=RETARGET_EVENT),
            ],
            [HEAD_A, HEAD_B, HEAD_B, HEAD_B, HEAD_B],
            20,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOLDING FINDINGS", out)
        self.assertIn("3872631145", out)
        self.assertNotIn("WAIT FINDINGS", out)
        self.assertIn("WAIT TIMEOUT: 20s elapsed", out)


if __name__ == "__main__":
    unittest.main()
