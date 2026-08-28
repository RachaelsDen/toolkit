"""pr_guard merge-act round-48 tests (PR #46, thread 3836788147).

Thread 3836788147 (P2) — preserve gh diagnostics on identity-gated
landings: when `gh pr merge` exits nonzero but the reconciliation
poll IMMEDIATELY observes MERGED, dispatch_failed makes the identity
gate return its disposition and the gated exit returned BEFORE the
round-12 captured-output note ever printed — the actionable stderr
(a policy or transport error) was lost even though the string and
cancellation/int outcomes print it. The gated exit now emits the
labeled capture beside the banner (merge_rc != 0 only — the
round-12 rationale: a successful dispatch's quiet output is not a
failure diagnostic, and the rc-0 no-op signature is the
classification banner's own report, not a diagnostic).

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round48_test -v
"""

import unittest

from .pr_guard_merge_fixtures import HEAD
from .pr_guard_merge_harness import MergeHarness, merged, thread

RUNNER = MergeHarness()


def open_record(merge_commit_sha: str = ""):
    return {
        "head": {"sha": HEAD},
        "base": {"ref": "dev"},
        "state": "open",
        "merged": False,
        "merge_commit_sha": merge_commit_sha,
    }


class GatedExitDiagnosticsTests(unittest.TestCase):
    def test_immediate_failed_dispatch_landing_prints_the_capture(self):
        # Given: the merge command FAILED with a diagnostic on its
        # stderr (the fake dispatch's "boom") and the reconciliation
        # poll's FIRST read already observes the landing MERGED —
        # thread 3836788147's exact shape: the identity gate returns
        # the ambiguous disposition and the gated exit returned
        # before either round-12 summary path could print.
        surveys = iter([[thread("11", "resolved")]])

        # When: the act renders the identity-gate exit.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[merged()],
            merge_rc=1,
        )

        # Then: the ambiguous manual banner stands (no revert) and is
        # FOLLOWED by the labeled captured output — the operator sees
        # WHY gh pr merge failed on this exit path too, not just on
        # the nothing-landed and reconciliation-epilogue summaries.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("ORIGINAL MERGE ERROR", out)
        self.assertIn("MERGE COMMAND OUTPUT", out)
        self.assertIn("boom", out)
        self.assertLess(
            out.index("AMBIGUOUS LANDING"),
            out.index("MERGE COMMAND OUTPUT"),
        )

    def test_rc0_noop_gated_exit_prints_no_failure_capture(self):
        # Given: the dispatch exits 0 carrying gh's already-merged
        # no-op signature (thread 3836217633's idempotent no-op
        # class) and the reconcile's first read observes the landing
        # — the gate fires the same ambiguous disposition, but the
        # capture is NOT a failure diagnostic (rc 0; the signature is
        # the classification banner's own report).
        surveys = iter([[thread("11", "resolved")]])

        # When: the act renders the identity-gate exit for the rc-0
        # no-op dispatch.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[merged()],
            merge_noop=True,
        )

        # Then: the classification and ambiguous banners print, the
        # exit stays attention-nonzero, and NO merge-command-output
        # note renders — the round-12 rationale holds on this exit
        # too.
        self.assertEqual(code, 1)
        self.assertIn("MERGE COMMAND EXITED 0 WITHOUT DISPATCHING", out)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertNotIn("MERGE COMMAND OUTPUT", out)
        self.assertNotIn("git revert", " ".join(argvs))


if __name__ == "__main__":
    unittest.main()
