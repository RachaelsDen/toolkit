"""pr_guard merge-act round-16 tests (PR #41 round 16).

Thread 3834400946: GH_HOST pinning — a GH_HOST naming a host other
than github.com makes `-R RachaelsDen/UR-lorebook` resolve against
THAT host, so an identically named repository there could be
surveyed and merged while the canonical-remote validation keeps the
revert on github.com. merge/harden/pre-merge hard-block a foreign
host up front, and EVERY gh subprocess carries GH_HOST=github.com in
its explicit env (the override beats the ambient variable).

Threads 3834400957/3834400951 (the patch-id map plumbing and the
complete-map rule) were RETIRED at round 25 (threads 3835145976/
3835145981/3835175506/3835175508) with the classifier they served —
the DirectDiffTree and IncompleteMapSquash suites were DELETED with
the arms (the suite count drops by design; the refit round-14 suite
asserts the pipes never run at all).

Thread 3834400954: the deterministic revert branch is REUSED when
its remote head is exactly this attempt's revert commit, or pushed
under the first free -<k> suffix when a prior attempt's branch
blocks the plain push as non-fast-forward.

Thread 3834488871: the revert branch is built in a THROWAWAY
WORKTREE — worktree add/remove in the argv sequence, every
working-tree-mutating step prefixed `git -C <tmp>`, and no bare
caller-tree checkout/revert/push at all.

No network: the shared fake-gh/fake-clock harness drives the act;
remote_heads serves the ls-remote reuse probe and gh_host injects
GH_HOST for the block tests.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round16_test -v
"""

import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import cli
from . import pr_guard_common
from . import pr_guard_rulesets
from .pr_guard_common import gh_env
from .pr_guard_merge_harness import (
    GUARD_ID,
    GUARD_NO_SIGN,
    HEAD,
    MERGE_SHA,
    REVERT_HEAD,
    MergeHarness,
    merged,
    thread,
)

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"
RANGE_OLDEST = "bbbb000000000000000000000000000000000022"
RANGE_MIDDLE = "cccc000000000000000000000000000000000033"
RANGE_NEWEST = "dddd000000000000000000000000000000000044"
FOREIGN_EMPTY = "eeee0000000000000000000000000000000000f1"
BRANCH = f"revert/pr39-{MERGE_SHA[:7]}"
PR_COMMITS = [RANGE_OLDEST, RANGE_MIDDLE, RANGE_NEWEST]


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


def clean_surveys(count: int = 1):
    return iter([[thread("11", "resolved")] for _ in range(count)])


class GhHostPinTests(unittest.TestCase):
    def test_foreign_gh_host_blocks_the_merge_act_up_front(self):
        # Given: the operator's environment exports GH_HOST naming a
        # GHE host — `-R RachaelsDen/UR-lorebook` would resolve
        # against that host's identically named repository (thread
        # 3834400946's exact finding).
        # When: the guarded merge act starts.
        code, out, argvs, events = RUNNER.run_guarded(
            clean_surveys(),
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            gh_host="ghe.example.com",
        )

        # Then: HARD BLOCK before ANY gh/git dispatch or survey — the
        # banner names the host, the remedy, and the thread; nothing
        # merged, nothing surveyed.
        self.assertEqual(code, 1)
        self.assertIn("BLOCKED: GH_HOST=ghe.example.com", out)
        self.assertIn("3834400946", out)
        self.assertIn("Unset GH_HOST", out)
        self.assertEqual(argvs, [])
        self.assertNotIn("MERGED CLEAN", out)

    def test_github_com_host_and_unset_host_do_not_block(self):
        # Given: GH_HOST set to exactly the pinned host (any
        # capitalization) or left unset — the environment agrees with
        # the repository's home.
        # When: the guarded merge act runs to a clean landing.
        for host in (None, "github.com", "GitHub.com"):
            code, out, argvs, events = RUNNER.run_guarded(
                clean_surveys(2),
                pinned(),
                poll_states=[merged()],
                gh_host=host,
            )
            # Then: no block banner — the ordinary clean path ran.
            self.assertEqual(code, 0)
            self.assertNotIn("BLOCKED: GH_HOST", out)
            self.assertIn("MERGED CLEAN", out)

    def test_every_dispatched_gh_command_pins_the_host_env(self):
        # Given: a run that dispatches the full gh surface — the
        # headRefOid view, the merge command, the completion polls,
        # and (on a landing head mismatch) the revert PR create.
        # When: the act runs under an ambient GH_HOST naming the
        # canonical host (allowed) and hits the revert path.
        code, out, argvs, events = RUNNER.run_guarded(
            clean_surveys(),
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            gh_host="github.com",
        )

        # Then: EVERY recorded gh subprocess env carries
        # GH_HOST=github.com — the explicit pin, not the ambient var.
        self.assertEqual(code, 1)
        self.assertIn("REVERT PR OPENED", out)
        self.assertGreater(len(RUNNER.gh_envs), 3)
        for env in RUNNER.gh_envs:
            self.assertIsInstance(env, dict)
            self.assertEqual(env.get("GH_HOST"), "github.com")

    def test_gh_env_unit_overrides_a_foreign_ambient_host(self):
        # Given: a foreign GH_HOST exported in the ambient
        # environment.
        with mock.patch.dict(
            os.environ, {"GH_HOST": "ghe.example.com"}
        ):
            # Then: the subprocess env builder OVERRIDES it to the
            # pinned host and preserves the rest of the environment,
            # while the startup check flags the foreign host.
            env = gh_env()
            self.assertEqual(env["GH_HOST"], "github.com")
            self.assertEqual(env.get("PATH"), os.environ.get("PATH"))
            captured = io.StringIO()
            with redirect_stdout(captured):
                self.assertTrue(pr_guard_common.blocked_gh_host())
            self.assertIn("GH_HOST=ghe.example.com", captured.getvalue())

    def test_blocked_gh_host_passes_when_empty_or_canonical(self):
        # Given: GH_HOST empty or the canonical host in any
        # capitalization — the environment agrees with the repo.
        for host, blocked in (
            ("", False),
            ("github.com", False),
            ("GitHub.com", False),
            ("ghe.example.com", True),
        ):
            with mock.patch.dict(os.environ, {"GH_HOST": host}):
                captured = io.StringIO()
                with redirect_stdout(captured):
                    self.assertEqual(
                        pr_guard_common.blocked_gh_host(), blocked, host
                    )

    def test_pre_merge_blocks_on_foreign_gh_host(self):
        # Given: the same foreign host with the pre-merge gate about
        # to run its surveys.
        with mock.patch.dict(
            os.environ, {"GH_HOST": "ghe.example.com"}
        ), mock.patch.object(
            cli, "gh_rest_pr"
        ) as read, mock.patch.object(cli, "survey") as survey:
            # When: pre-merge starts.
            captured = io.StringIO()
            with redirect_stdout(captured):
                code = cli.pre_merge(39)
            self.assertIn("BLOCKED: GH_HOST=ghe.example.com", captured.getvalue())

        # Then: hard block before any read or survey.
        self.assertEqual(code, 1)
        read.assert_not_called()
        survey.assert_not_called()

    def test_harden_blocks_on_foreign_gh_host(self):
        # Given: the same foreign host with harden about to write
        # the ruleset.
        with mock.patch.dict(
            os.environ, {"GH_HOST": "ghe.example.com"}
        ), mock.patch.object(
            pr_guard_rulesets.subprocess, "run"
        ) as run:
            # When: harden starts.
            captured = io.StringIO()
            with redirect_stdout(captured):
                code = pr_guard_rulesets.harden(39)
            self.assertIn("BLOCKED: GH_HOST=ghe.example.com", captured.getvalue())

        # Then: hard block before any gh api call — the ruleset
        # cannot be written to a foreign host's repository.
        self.assertEqual(code, 1)
        run.assert_not_called()


class BranchReuseTests(unittest.TestCase):
    def test_matching_remote_branch_head_is_reused_without_push(self):
        # Given: a PRIOR attempt already pushed this deterministic
        # branch carrying EXACTLY this attempt's revert commit (the
        # push succeeded, the `gh pr create` failed transiently —
        # thread 3834400954's exact scenario).
        surveys = iter([[thread("11", "resolved")]])

        # When: the rerun rebuilds the same revert commit and the
        # ls-remote probe reports the identical remote head.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_heads={BRANCH: REVERT_HEAD},
        )

        # Then: the push is SKIPPED (no new non-fast-forward attempt)
        # and the PR opens straight against the EXISTING branch.
        self.assertEqual(code, 1)
        self.assertIn("REVERT BRANCH REUSED", out)
        self.assertIn(f"git ls-remote origin refs/heads/{BRANCH}", argvs)
        self.assertNotIn("git push", " ".join(argvs))
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(f"--head {BRANCH}", create)
        self.assertIn("REVERT PR OPENED", out)

    def test_conflicting_remote_branch_gets_a_uniqueness_suffix(self):
        # Given: the prior attempt's pushed branch carries a
        # DIFFERENT commit (the base moved between attempts), so the
        # plain push would be rejected as non-fast-forward.
        surveys = iter([[thread("11", "resolved")]])

        # When: ls-remote reports the conflicting head and the -2
        # candidate is free.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_heads={
                BRANCH: "dead0000000000000000000000000000000000ff"
            },
        )

        # Then: the first free suffix gets the DETACHED-HEAD commit
        # pushed straight to it (thread 3834819191: the push refspec
        # creates the remote branch with NO local rename); the PR
        # opens against it.
        self.assertEqual(code, 1)
        self.assertIn("REVERT BRANCH SUFFIXED", out)
        tmp = RUNNER.revert_tmp
        self.assertIn(f"git ls-remote origin refs/heads/{BRANCH}", argvs)
        self.assertIn(
            f"git ls-remote origin refs/heads/{BRANCH}-2", argvs
        )
        self.assertNotIn("git branch -m", " ".join(argvs))
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(f"--head {BRANCH}-2", create)
        self.assertIn("REVERT PR OPENED", out)


class WorktreeIsolationTests(unittest.TestCase):
    def test_revert_builds_the_branch_in_a_temporary_worktree(self):
        # Given: the invoking checkout may hold staged or unstaged
        # changes — thread 3834488871's exact finding: the old
        # `git checkout -B` / `git revert` ran directly in that tree,
        # clobbering it or aborting, and even a clean run left the
        # operator switched onto the revert branch.
        surveys = iter([[thread("11", "resolved")]])

        # When: the revert fires.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
        )

        # Then: the worktree is created at the fetched base and
        # REMOVED after the PR create, and every working-tree-mutating
        # step (revert/push) runs `git -C <tmp>` inside it — NO bare
        # caller-tree mutation argv exists, NO branch is ever checked
        # out (thread 3834819191: the worktree stays detached so a
        # caller-active branch name can never block it), and the PR
        # body documents the isolation.
        self.assertEqual(code, 1)
        tmp = RUNNER.revert_tmp
        self.assertIn(f"git worktree add --detach {tmp} origin/dev", argvs)
        self.assertIn(f"git worktree remove --force {tmp}", argvs)
        for mutating in ("git checkout", "git revert", "git push"):
            self.assertFalse(
                any(a.startswith(mutating) for a in argvs),
                mutating,
            )
        self.assertNotIn("checkout -B", " ".join(argvs))
        self.assertNotIn("git branch ", " ".join(argvs))
        self.assertIn(
            f"git -C {tmp} rev-parse --verify {MERGE_SHA}^2", argvs
        )
        self.assertIn(
            f"git -C {tmp} {GUARD_ID} {GUARD_NO_SIGN} revert --no-gpg-sign -m 1 --no-edit {MERGE_SHA}", argvs
        )
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn("ISOLATED temporary worktree", create)
        self.assertIn("3834488871", create)
        self.assertIn("REVERT PR OPENED", out)


if __name__ == "__main__":
    unittest.main()
