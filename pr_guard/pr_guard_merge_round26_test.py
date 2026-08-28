"""pr_guard merge-act round-26 tests (PR #41 round 26, thread
3835290443).

The P1: the round-25 single-parent contract compared the landing's
parent against `git rev-parse <remote>/<base>` read AFTER the
pre-revert base fetch — but that fetch is exactly what moves the ref
to `merge_sha` ITSELF (or a still-later base commit), so the
supposedly automated squash-revert path could NEVER match and always
fell through to the manual banner when a late DANGER finding or
post-merge mismatch triggered it. Round 26 freezes the base tip
PRE-DISPATCH (snapshot_base_tip, beside the frozen commit list of
thread 3835145981) and compares the landing's parent against THAT
immutable sha; the CURRENT ref survives only as a fail-closed-banner
diagnostic (landing-itself vs ADVANCED-past-the-frozen-tip).

These suites pin the three sides of the fix:
- the ORDINARY squash landing (parent == frozen tip, current ref ==
  the landing itself) is AUTOMATED again — the exact shape the P1
  proved dead under the round-25 comparison;
- a base that ADVANCED past the frozen tip (interleaved/foreign
  landings) fails closed with the parent-vs-frozen-tip numbers and
  the advancement note;
- an UNAVAILABLE snapshot fails closed even when parent == the
  CURRENT tip — the old round-25 comparison would have automated
  that shape, so the frozen snapshot is load-bearing, never
  decorative.

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act; a per-call counter fixture distinguishes the PRE-DISPATCH
tip read from the revert-time current-tip read (both are the same
argv, `git rev-parse --verify origin/dev` — only their ORDER
differs).

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round26_test -v
"""

import unittest

from .pr_guard_merge_fixtures import (
    BASE_TIP,
    FOREIGN_PARENT,
    GUARD_ID,
    GUARD_NO_SIGN,
    MERGE_SHA,
)
from .pr_guard_merge_harness import (
    HEAD,
    MERGE_ARGV,
    SNAPSHOT_ARGV,
    MergeHarness,
    merged,
    thread,
)

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000f00"
PR_COMMIT = "aaaa000000000000000000000000000000000011"
# The advancement shape: a base commit that is neither the frozen tip
# nor the landing itself — foreign/interleaved landings moved the ref
# past both.
ADVANCED_TIP = "3333000000000000000000000000000000000cc"
TIP_PROBE = ["git", "rev-parse", "--verify", "origin/dev"]


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


# Thread 3835290443: the two `<remote>/<base>` reads share one argv —
# the FIRST is merge_guarded's pre-dispatch snapshot, every later one
# the revert plan's current-tip probe. `reads` feeds them in order:
# reads[0] answers the snapshot, reads[1] (repeating) the probe.
def tip_reads(reads: list[tuple[int, str]]):
    calls = {"n": 0}

    def answer(argv, stdin):
        if argv[:4] == TIP_PROBE:
            idx = min(calls["n"], len(reads) - 1)
            calls["n"] += 1
            rc, sha = reads[idx]
            return (rc, sha + "\n" if rc == 0 and sha else "")
        return None

    return answer


class FrozenTipContractTests(unittest.TestCase):
    def test_squash_landing_matches_frozen_tip_not_the_moved_ref(self):
        # Given: the ORDINARY single-parent squash landing of the P1 —
        # at dispatch the base tip is BASE_TIP (the first read, the
        # FROZEN snapshot); after the merge the pre-revert base fetch
        # has moved origin/dev to MERGE_SHA ITSELF (the second read),
        # and the landing's parent is BASE_TIP. The round-25
        # comparison (parent == CURRENT tip) could never match here.
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires on that landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            pr_commits=[PR_COMMIT],
            git_answers=tip_reads(
                [(0, BASE_TIP), (0, MERGE_SHA)]
            ),
        )

        # Then: AUTOMATED — the plain revert of the landed commit runs
        # against the FROZEN tip (the moved ref is reported in the PR
        # body, never compared), the snapshot argvs precede the merge
        # dispatch, and the revert PR opens.
        self.assertEqual(code, 1)
        self.assertIn("REVERT PR OPENED", out)
        self.assertIn(
            f"git -C {RUNNER.revert_tmp} {GUARD_ID} {GUARD_NO_SIGN} revert --no-gpg-sign --no-edit {MERGE_SHA}",
            argvs,
        )
        self.assertNotIn("REVERT BLOCKED", out)
        snapshot_at = argvs.index(SNAPSHOT_ARGV)
        merge_at = argvs.index(MERGE_ARGV)
        self.assertLess(snapshot_at, merge_at)
        self.assertLess(argvs.index("git remote -v"), merge_at)
        self.assertLess(
            argvs.index("git fetch origin dev"), merge_at
        )
        self.assertLess(argvs.index(" ".join(TIP_PROBE)), merge_at)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(
            "SINGLE-PARENT landing whose parent IS the FROZEN", create
        )
        self.assertIn("PRE-DISPATCH base tip", create)
        self.assertIn("3835290443", create)
        self.assertIn(MERGE_SHA[:12], create)

    def test_base_advanced_past_frozen_tip_fails_closed(self):
        # Given: an advancement-interleaved landing — the frozen
        # pre-dispatch tip is BASE_TIP, but the landing's parent is a
        # FOREIGN commit (another entry landed between dispatch and
        # this PR) and the base has since advanced to ADVANCED_TIP.
        # Ambiguity by construction: the plain revert cannot be proven
        # to undo exactly this PR.
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires on that landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=[PR_COMMIT],
            git_answers=tip_reads(
                [(0, BASE_TIP), (0, ADVANCED_TIP)]
            ),
        )

        # Then: FAIL CLOSED — no revert argv, no revert PR, and the
        # banner reports the parent against the FROZEN tip (not the
        # moved ref) with the ADVANCEMENT note and the P1's citation.
        self.assertEqual(code, 1)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn(
            f"its parent probes as {FOREIGN_PARENT[:12]}", out
        )
        self.assertIn("FROZEN pre-dispatch base tip", out)
        self.assertIn(f"was {BASE_TIP[:12]}", out)
        self.assertIn("ADVANCED past the frozen tip", out)
        self.assertIn("3835290443", out)
        self.assertIn("MUST be reverted manually", out)

    def test_unavailable_snapshot_fails_closed_against_current_tip(self):
        # Given: the pre-dispatch snapshot probe FAILS (rc 1 — the
        # first read), leaving no frozen tip, while at revert time the
        # current ref reads BASE_TIP and the landing's parent IS
        # BASE_TIP. The RETIRED round-25 comparison (parent == current
        # tip) would have AUTOMATED this shape; the frozen snapshot is
        # load-bearing, so nothing can be proven and it fails closed.
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires with the snapshot
        # unreadable and the current tip equal to the parent.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            pr_commits=[PR_COMMIT],
            git_answers=tip_reads([(1, ""), (0, BASE_TIP)]),
        )

        # Then: the pre-dispatch warning names the degradation, the
        # banner reports the snapshot UNAVAILABLE, and no revert runs
        # — even though parent == the current tip.
        self.assertEqual(code, 1)
        self.assertIn("BASE-TIP SNAPSHOT UNAVAILABLE", out)
        self.assertIn("FAIL CLOSED", out)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn(
            "pre-dispatch base-tip snapshot is UNAVAILABLE", out
        )
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)


if __name__ == "__main__":
    unittest.main()
