"""pr_guard merge-act round-27 tests (PR #41 round 27, thread
3835345690).

The P2: the revert path's `git revert` — BOTH automated shapes — ran
without any author/committer identity. In an automation checkout
(CI runner, container, cron) with no user.name/user.email configured
locally or globally, git refuses to create the revert commit
("Author identity unknown"), so the promised automatic revert branch
and PR were never created and the unsafe merge stayed unreverted
with only the failure banner. Round 27 pins the FIXED guard identity
(user.name=pr-guard, user.email=pr-guard@users.noreply.github.com)
in the revert ARGV via pr_guard_common.with_guard_identity — argv
`-c` over GIT_AUTHOR_*/GIT_COMMITTER_* env because the family's
pinning style keeps safety-critical config visible in the recorded
argv and revert_failed's verbatim banner (a manual re-run of the
printed command keeps the identity), and argv flags cannot be
shadowed by an ambient env export. The two reverts are the path's
ONLY commit-creating git operations (fetch/worktree/probes/push
create none), so the identity rides exactly those two steps.

These suites pin the fix with LITERAL identity strings (independent
of the fixtures' GUARD_ID, so the values themselves are under test):
- BOTH revert shapes carry `-c user.name=pr-guard -c
  user.email=pr-guard@users.noreply.github.com` between the worktree
  `-C <tmp>` and the subcommand;
- the READ-ONLY probes of the same path carry NO identity (the
  pinning is scoped to commit-creating steps, never blanket);
- the failure banner prints the identity-carrying command verbatim —
  the documented manual re-run path keeps the identity.

Round 28 (thread 3835379480) extended the pinned argv with the
unsigned pinning (`-c commit.gpgsign=false` + the subcommand
`--no-gpg-sign`) — the literals below track the CURRENT argv shape
so a drift in either pinning fails here too.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round27_test -v
"""

import unittest

from .pr_guard_merge_fixtures import BASE_TIP, MERGE_SHA
from .pr_guard_merge_harness import (
    HEAD,
    MergeHarness,
    merged,
    thread,
)

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"
# The literal identity (thread 3835345690) — deliberately NOT the
# fixtures' GUARD_ID: these assertions must fail if the pinned values
# themselves ever drift, not just when the plumbing stops inserting
# them.
ID_FLAGS = (
    "-c user.name=pr-guard "
    "-c user.email=pr-guard@users.noreply.github.com "
    "-c commit.gpgsign=false"
)
TWO_PARENT_REVERT = (
    f"git -C {{tmp}} {ID_FLAGS} revert --no-gpg-sign "
    f"-m 1 --no-edit {MERGE_SHA}"
)
SINGLE_PARENT_REVERT = (
    f"git -C {{tmp}} {ID_FLAGS} revert --no-gpg-sign "
    f"--no-edit {MERGE_SHA}"
)


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class RevertIdentityTests(unittest.TestCase):
    def test_two_parent_revert_carries_the_guard_identity(self):
        # Given: a two-parent landing (the parent-count probe answers
        # rc 0) reverted after a post-merge head mismatch.
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires on that landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
        )

        # Then: the `-m 1` revert argv carries the LITERAL identity
        # flags between the worktree `-C <tmp>` and the subcommand,
        # and the revert PR opens.
        self.assertEqual(code, 1)
        self.assertIn(
            TWO_PARENT_REVERT.format(tmp=RUNNER.revert_tmp), argvs
        )
        self.assertIn("REVERT PR OPENED", out)

    def test_single_parent_revert_carries_the_guard_identity(self):
        # Given: the ordinary single-parent squash landing — the
        # parent IS the pre-dispatch base tip (the round-26 automated
        # shape; both the snapshot read and the plan's probes answer
        # BASE_TIP via the fixture defaults).
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires on that landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
        )

        # Then: the plain revert argv carries the same LITERAL
        # identity flags — the automation checkout has no configured
        # identity of its own, so without these flags git dies with
        # "Author identity unknown" before the revert commit exists.
        self.assertEqual(code, 1)
        self.assertIn(
            SINGLE_PARENT_REVERT.format(tmp=RUNNER.revert_tmp), argvs
        )
        self.assertIn("REVERT PR OPENED", out)

    def test_read_only_probes_carry_no_identity(self):
        # Given: the two-parent revert path — its rev-parse probes
        # (parent count, worktree head) create no commit, so the
        # identity pinning must scope to the REVERT alone, never
        # blanket the path's git argvs.
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
        )

        # Then: every OTHER git argv in the revert tail is
        # identity-free (fetch, worktree add, the probes, the push),
        # and exactly ONE argv carries the identity — the revert.
        carried = [a for a in argvs if "user.name=pr-guard" in a]
        self.assertEqual(
            carried,
            [TWO_PARENT_REVERT.format(tmp=RUNNER.revert_tmp)],
        )
        self.assertIn(f"git -C {RUNNER.revert_tmp} rev-parse HEAD", argvs)

    def test_failure_banner_prints_the_identity_carrying_command(self):
        # Given: a revert step that exits NONZERO (the automation
        # checkout's git refuses the commit) — the documented
        # argv-over-env rationale: revert_failed prints the failed
        # command VERBATIM, so the operator's manual re-run keeps the
        # fixed identity without rediscovering it.
        surveys = iter([[thread("11", "resolved")]])

        def rc_for(argv):
            return (
                1 if "user.name=pr-guard" in argv and "revert" in argv
                else 0
            )

        # When: the head-mismatch revert fires and the revert fails.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            rc_for=rc_for,
        )

        # Then: the banner names the exact identity-carrying command
        # (a copy-paste re-run works in the identity-less checkout).
        self.assertEqual(code, 1)
        self.assertIn("REVERT FAILED at `", out)
        self.assertIn("-c user.name=pr-guard", out)
        self.assertIn(
            "-c user.email=pr-guard@users.noreply.github.com", out
        )
        self.assertIn("MUST be reverted manually", out)


if __name__ == "__main__":
    unittest.main()
