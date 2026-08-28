"""pr_guard merge-act round-18 tests (PR #41 round 18).

Thread 3834666206: cancellation observing state=MERGED before GitHub
populated the nullable mergeCommit fell INSTANTLY to the manual-revert
banner — the landed merge lost the automatic revert even though the
completion poll had just gained pending semantics for the exact same
transient state (thread 3834590326). The landed read in
revert_landed_during_cancel is now a bounded retry at the cancel
recheck cadence; a persistently empty sha keeps the manual banner.

Thread 3834666208: gate_covers never checked the ruleset TARGET — an
active tag/push-target ruleset whose ref conditions match and whose
pull_request rule carries required_review_thread_resolution satisfied
the merge-mode gate while gating nothing about PR merges. The shared
coverage predicate now requires target == 'branch', so a base whose
ONLY match is non-branch reads gate-missing.

Thread 3834666210: `pr_guard.py merge <pr>` without head/base
validated through the {3,5} shape check and fell through to
resolve(pr), mutating review-thread state under a merge command name.
merge now demands exactly five argv tokens (seven with --quiet-secs)
— anything else is a usage error (exit 2) BEFORE any dispatch.

Thread 3834666213: fetch_gate_rulesets returned only the first
per_page=100 page, truncating the legacy-migration match set. The
fetch now follows the REST page cursor until a short page; a legacy
gate on page two is migrated, not missed.

No network: threads 3834666206/3834666208 ride the shared
fake-gh/fake-git harness (the landed-sha retry sleeps moved home to
pr_guard_common at round 30, so the harness's global fake clock
covers them — no separate revert clock anymore), 3834666210 patches
the CLI entry points, 3834666213 rides the paginated FakeRulesetStore.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round18_test -v
"""

import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from . import cli
from . import pr_guard_merge_harness
from . import pr_guard_rulesets
from .pr_guard_merge import DEFAULT_QUIET_SECS
from .pr_guard_merge_fixtures import HEAD
from .pr_guard_merge_harness import MERGE_ARGV, POLL_ARGV, MergeHarness
from .pr_guard_merge_harness import merged, pending, thread
from .pr_guard_merge_harness import gate_ruleset as branch_gate
from .pr_guard_rulesets_harden_test import (
    FakeRulesetStore,
    REPO_ROOT,
    WILDCARDS,
    detail,
)

RUNNER = MergeHarness()


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


def clean_surveys(count: int = 1):
    return iter([[thread("11", "resolved")] for _ in range(count)])


def merged_no_sha(base: str = "dev", head: str = HEAD) -> dict:
    return {"state": "MERGED", "mergeCommit": None,
            "baseRefName": base, "headRefOid": head}


MERGED_CANCEL_READ = {"autoMergeRequest": None, "state": "MERGED"}


class CancelShaRetryTests(unittest.TestCase):
    def test_sha_populating_on_retry_still_reverts(self):
        # Given: the SUCCESSFUL dispatch's completion poll timed out
        # still-pending and the cancel path (thread 3836600782, round
        # 17: only the successful path's landing may still revert —
        # a failed dispatch's is uniformly AMBIGUOUS) then observes
        # MERGED while the mergeCommit has not populated yet (thread
        # 3834666206's exact finding: the old SINGLE read fell
        # straight to the manual banner, leaving the landed merge
        # without the automatic revert) — the sha populates on the
        # re-read.
        # When: the cancel verification observes the landing and the
        # landed read retries at the cancel recheck cadence (empty,
        # then populated). Thread 3835501549 (round 30): the retry
        # sleeps ride the HARNESS clock now (read_landed_merge_sha
        # moved home to pr_guard_common).
        code, out, argvs, events = RUNNER.run_guarded(
            clean_surveys(1),
            pinned(),
            poll_states=[pending()] * 31
            + [merged_no_sha(), merged()],
            cancel_reads=[MERGED_CANCEL_READ],
        )

        # Then: the empty read printed the bounded progress line and
        # RETRIED (one 5s recheck sleep), the populated sha went
        # through the ORDINARY revert path — the revert PR carries the
        # landed-during-cancel trigger — and never the manual banner.
        self.assertEqual(code, 1)
        self.assertIn("THE MERGE LANDED DURING CANCELLATION", out)
        self.assertIn("MERGE COMMIT UNREADABLE", out)
        self.assertIn("bounded re-read 1/3", out)
        self.assertIn("3834666206", out)
        self.assertIn("REVERT PR OPENED", out)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn("merge landed during cancellation", create)
        self.assertNotIn("MERGE LANDED UNVERIFIED", out)
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("AMBIGUOUS LANDING", out)
        self.assertEqual(argvs.count(POLL_ARGV), 33)
        self.assertEqual(RUNNER.clock.slept, [10.0] * 30 + [5.0])

    def test_persistently_empty_sha_keeps_the_manual_banner(self):
        # Given: the mergeCommit stays unreadable across the ENTIRE
        # bounded retry budget — the read can never ground a revert.
        # When: all three landed reads report MERGED with an empty
        # mergeCommit.
        code, out, argvs, events = RUNNER.run_guarded(
            clean_surveys(1),
            pinned(),
            poll_states=[pending()] * 11 + [merged_no_sha()] * 3,
            merge_rc=1,
            cancel_reads=[MERGED_CANCEL_READ],
        )

        # Then: the manual banner names the bounded budget, no revert
        # plumbing ran (no revert PR, no gh pr create), and both
        # recheck sleeps elapsed before failing closed.
        self.assertEqual(code, 1)
        self.assertIn("MERGE LANDED UNVERIFIED", out)
        self.assertIn("even after 3 bounded re-reads", out)
        self.assertIn("3834666206", out)
        self.assertIn("MUST be reverted manually", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertEqual(argvs.count(POLL_ARGV), 14)
        self.assertEqual(RUNNER.clock.slept, [10.0] * 10 + [5.0, 5.0])


class BranchTargetGateTests(unittest.TestCase):
    def test_non_branch_target_never_counts_as_coverage(self):
        # Given: active equipped rulesets whose TARGET is tag or push
        # (thread 3834666208 — ref conditions and the pull_request rule
        # have exactly the expected shape, but a non-branch ruleset
        # gates NOTHING about pull requests on branches), beside an
        # ordinary branch-target one.
        # When/Then: the shared predicate ignores the non-branch
        # matches and returns the branch-target ruleset — a base whose
        # only match is non-branch reads gate-missing.
        self.assertIsNone(
            pr_guard_rulesets.gate_covers(
                [branch_gate(target="tag")], "dev", "main"
            )
        )
        self.assertIsNone(
            pr_guard_rulesets.gate_covers(
                [branch_gate(target="push")], "dev", "main"
            )
        )
        gate = branch_gate()
        self.assertIs(
            pr_guard_rulesets.gate_covers([gate], "dev", "main"), gate
        )

    def test_merge_mode_blocks_on_a_tag_target_only_gate(self):
        # Given: the ONLY gate ruleset on the base carries target='tag'
        # — the merge-mode gate check must not dispatch under it.
        # When: the guarded merge act runs.
        code, out, argvs, events = self._run_with_tag_gate()

        # Then: BLOCKED as gate-missing naming the branch-target
        # requirement — the merge request was NEVER dispatched.
        self.assertEqual(code, 1)
        self.assertIn("BLOCKED: no ACTIVE branch-target ruleset", out)
        self.assertIn("3834666208", out)
        self.assertIn("Re-run harden", out)
        self.assertNotIn(MERGE_ARGV, argvs)

    def _run_with_tag_gate(self):
        # The harness builds its fetch_gate_rulesets fake from this
        # module-level builder — patch it so the patched gate list
        # carries the tag-target ruleset.
        with mock.patch.object(
            pr_guard_merge_harness,
            "gate_ruleset",
            return_value=branch_gate(target="tag"),
        ):
            return RUNNER.run_guarded(clean_surveys(0), pinned())

    def test_branch_target_gate_dispatches_the_merge(self):
        # Given: the ordinary branch-target gate — the widened
        # predicate must not refuse the healthy shape.
        # When: the guarded merge act runs to a clean landing.
        code, out, argvs, events = RUNNER.run_guarded(
            clean_surveys(2), pinned(), poll_states=[merged()]
        )

        # Then: the merge request dispatched and the act ran its full
        # post-merge path to MERGED CLEAN.
        self.assertEqual(code, 0)
        self.assertIn(MERGE_ARGV, argvs)
        self.assertIn("MERGED CLEAN", out)


class MergeArityTests(unittest.TestCase):
    MODES = ("merge_guarded", "resolve", "pre_merge", "harden", "survey")

    def run_main(self, argv):
        err = io.StringIO()
        run = mock.Mock()
        fakes = {
            name: mock.Mock(name=name, return_value=0)
            for name in self.MODES
        }
        with mock.patch("subprocess.run", run):
            with mock.patch.multiple(
                cli, **{name: fakes[name] for name in self.MODES}
            ):
                with redirect_stderr(err):
                    code = cli.main(argv)
        return code, err.getvalue(), fakes, run

    def test_truncated_merge_is_a_usage_error_before_any_dispatch(self):
        # Given: the operator truncated the merge command copied from
        # pre-merge (thread 3834666210's exact shape — the old {3,5}
        # check accepted it and fell through to resolve(pr), mutating
        # review-thread state under a merge command name).
        # When: the CLI runs the three-token merge form.
        code, err, fakes, run = self.run_main(
            ["pr_guard.py", "merge", "39"]
        )

        # Then: usage error exit 2, USAGE on stderr, and ZERO
        # dispatch — no mode entry point and no subprocess at all.
        self.assertEqual(code, 2)
        self.assertIn("usage: pr_guard.py", err)
        for name in self.MODES:
            fakes[name].assert_not_called()
        run.assert_not_called()

    def test_quiet_secs_truncated_merge_is_a_usage_error(self):
        # Given: the truncated merge with its optional flag — the
        # strip leaves three tokens, which merge must still refuse.
        code, err, fakes, run = self.run_main(
            ["pr_guard.py", "merge", "39", "--quiet-secs", "30"]
        )

        # Then: usage error, zero dispatch.
        self.assertEqual(code, 2)
        self.assertIn("usage: pr_guard.py", err)
        for name in self.MODES:
            fakes[name].assert_not_called()
        run.assert_not_called()

    def test_non_merge_five_token_form_is_a_usage_error(self):
        # Given: a five-token NON-merge invocation (the old late
        # len==5 guard's shape — now refused by the same arity rule).
        code, err, fakes, run = self.run_main(
            ["pr_guard.py", "survey", "39", "stray", "tokens"]
        )

        # Then: usage error, zero dispatch.
        self.assertEqual(code, 2)
        self.assertIn("usage: pr_guard.py", err)
        for name in self.MODES:
            fakes[name].assert_not_called()

    def test_full_merge_form_dispatches_bound(self):
        # Given: the complete merge command pre-merge's CLEAN output
        # names. When: the CLI runs it (both quiet-secs shapes).
        code, err, fakes, run = self.run_main(
            ["pr_guard.py", "merge", "39", HEAD, "dev"]
        )
        quiet_code, _, quiet_fakes, _ = self.run_main(
            ["pr_guard.py", "merge", "39", HEAD, "dev", "--quiet-secs", "0"]
        )

        # Then: merge_guarded is dispatched EXACTLY bound (pr, head,
        # base, quiet secs — default 900, override 0) and nothing else
        # runs; resolve is never reached.
        self.assertEqual(code, 0)
        self.assertEqual(quiet_code, 0)
        fakes["merge_guarded"].assert_called_once_with(
            39, HEAD, "dev", DEFAULT_QUIET_SECS
        )
        quiet_fakes["merge_guarded"].assert_called_once_with(
            39, HEAD, "dev", 0
        )
        for fakes_ in (fakes, quiet_fakes):
            for name in self.MODES:
                if name != "merge_guarded":
                    fakes_[name].assert_not_called()


class RulesetPaginationTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_two_page_store_migrates_the_page_two_legacy_gate(self):
        # Given: 100 filler rulesets fill list page one; the legacy
        # '(all bases)' wildcard gate sits ALONE on page two (thread
        # 3834666213's exact shape — the round-17 fetch read only page
        # one, saw no gate-name match, and the hidden wildcard kept
        # blocking review-fix pushes beside the POSTed canonical).
        store = FakeRulesetStore(
            {
                rid: detail(rid, f"filler-{rid}", ["refs/heads/main"])
                for rid in range(1, 101)
            }
        )
        store.rulesets[21137845] = detail(
            21137845,
            f"{pr_guard_rulesets.GATE_RULE_PREFIX} (all bases)",
            WILDCARDS,
        )

        # When: harden runs against the two-page repository.
        out = io.StringIO()
        with (
            mock.patch.object(
                pr_guard_rulesets, "gh_rest", side_effect=store.gh_rest
            ),
            redirect_stdout(out),
        ):
            code = pr_guard_rulesets.harden(39)

        # Then: BOTH list pages were consumed (page=1 AND page=2 GETs,
        # never a page=3 — the short page stops the cursor), the
        # page-two legacy gate is the MIGRATED canonical (one PATCH to
        # its id, no POST), and HARDENED verifies over the flattened
        # set.
        self.assertEqual(code, 0)
        gets = [path for method, path, _ in store.calls if method == "GET"]
        self.assertIn(f"{REPO_ROOT}/rulesets?per_page=100&page=1", gets)
        self.assertIn(f"{REPO_ROOT}/rulesets?per_page=100&page=2", gets)
        self.assertFalse(any("page=3" in path for path in gets))
        writes = {
            (method, path): body
            for method, path, body in store.calls
            if method in {"POST", "PATCH", "DELETE"}
        }
        self.assertEqual(
            list(writes), [("PATCH", f"{REPO_ROOT}/rulesets/21137845")]
        )
        self.assertIn("MIGRATING legacy ruleset id 21137845", out.getvalue())
        self.assertIn("HARDENED refs/heads/dev", out.getvalue())


if __name__ == "__main__":
    unittest.main()
