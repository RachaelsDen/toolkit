"""pr_guard merge-act round-28 tests (PR #41 round 28, thread
3835379480).

The P2: the invoking checkout can carry `commit.gpgSign=true` (an
operator's signing policy) while the guard environment has NO usable
signing key — `git revert` INHERITS that config and dies building
the signature BEFORE the revert commit exists, so the promised
automatic revert branch and PR are never created (the same
never-created revert as the round-27 identity failure, one config
surface later). Round 28 pins the reverts UNSIGNED on BOTH flag
surfaces inside pr_guard_common.with_guard_identity — the reviewer
verified `git revert -h` exposes `--no-gpg-sign`, and the thread
also names the config override — so one helper change covers both
revert call sites (pr_guard_revert's `-m 1` shape and pr_guard_plan's
plain shape).

The chosen form, documented: `-c commit.gpgsign=false` joins the
identity prefix (the CONFIG surface — a `-c` override beats
inherited commit.gpgSign=true from ANY scope: local, global, or
system), and `--no-gpg-sign` is inserted immediately after the
subcommand (the COMMAND-LINE surface — explicit, config-independent,
and visible in revert_failed's verbatim banner so a manual re-run of
the printed command stays unsigned). Belt-and-braces across both
surfaces because they fail independently; the helper is the single
point both call sites already share.

These suites pin the fix with LITERAL no-sign strings (independent
of the fixtures' GUARD_NO_SIGN, so both surfaces are under test):
- BOTH revert shapes carry `-c commit.gpgsign=false` in the prefix
  and `--no-gpg-sign` right after `revert`;
- the READ-ONLY probes of the same path carry NO signing override
  (no commit is created, so ambient signing config cannot fail them
  — the pinning stays scoped to commit-creating steps, never
  blanket);
- the failure banner prints the unsigned command verbatim — the
  operator's manual re-run stays unsigned without rediscovering the
  flags.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round28_test -v
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
# The literal no-sign pinning (thread 3835379480) — deliberately NOT
# the fixtures' GUARD_NO_SIGN: these assertions must fail if either
# flag surface drifts, not just when the plumbing stops inserting it.
NO_SIGN_PREFIX = "-c commit.gpgsign=false"
NO_SIGN_FLAG = "revert --no-gpg-sign"
TWO_PARENT_REVERT = (
    f"git -C {{tmp}} -c user.name=pr-guard "
    f"-c user.email=pr-guard@users.noreply.github.com "
    f"{NO_SIGN_PREFIX} {NO_SIGN_FLAG} -m 1 --no-edit {MERGE_SHA}"
)
SINGLE_PARENT_REVERT = (
    f"git -C {{tmp}} -c user.name=pr-guard "
    f"-c user.email=pr-guard@users.noreply.github.com "
    f"{NO_SIGN_PREFIX} {NO_SIGN_FLAG} --no-edit {MERGE_SHA}"
)


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class RevertUnsignedTests(unittest.TestCase):
    def test_two_parent_revert_is_unsigned(self):
        # Given: a two-parent landing (the parent-count probe answers
        # rc 0) reverted after a post-merge head mismatch, from a
        # checkout whose commit.gpgSign=true has no usable key.
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires on that landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
        )

        # Then: the `-m 1` revert argv carries BOTH no-sign surfaces
        # — the config override in the -c prefix and the flag right
        # after the subcommand — and the revert PR opens.
        self.assertEqual(code, 1)
        self.assertIn(
            TWO_PARENT_REVERT.format(tmp=RUNNER.revert_tmp), argvs
        )
        self.assertIn("REVERT PR OPENED", out)

    def test_single_parent_revert_is_unsigned(self):
        # Given: the ordinary single-parent squash landing — the
        # parent IS the pre-dispatch base tip (the round-26 automated
        # shape; the fixture defaults answer BASE_TIP to both probe
        # reads).
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires on that landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
        )

        # Then: the plain revert argv carries the SAME both-surface
        # no-sign pinning — the plan's helper call is the single
        # point both shapes share, so neither can inherit the
        # operator's signing policy and die signature-less.
        self.assertEqual(code, 1)
        self.assertIn(
            SINGLE_PARENT_REVERT.format(tmp=RUNNER.revert_tmp), argvs
        )
        self.assertIn("REVERT PR OPENED", out)

    def test_read_only_probes_carry_no_signing_override(self):
        # Given: the two-parent revert path — its fetch, worktree
        # add, rev-parse probes, ls-remote, and push create NO
        # commit, so the unsigned pinning must scope to the REVERT
        # alone, never blanket the path's git argvs (a blanket
        # -c/--no-gpg-sign would misreport the ambient policy on
        # read-only steps).
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
        )

        # Then: exactly ONE argv carries each no-sign surface — the
        # revert — and every other git argv in the revert tail is
        # override-free.
        self.assertEqual(
            [a for a in argvs if NO_SIGN_PREFIX in a],
            [TWO_PARENT_REVERT.format(tmp=RUNNER.revert_tmp)],
        )
        self.assertEqual(
            [a for a in argvs if "--no-gpg-sign" in a],
            [TWO_PARENT_REVERT.format(tmp=RUNNER.revert_tmp)],
        )
        self.assertIn(f"git -C {RUNNER.revert_tmp} rev-parse HEAD", argvs)

    def test_failure_banner_prints_the_unsigned_command(self):
        # Given: a revert step that exits NONZERO — the documented
        # argv-over-env rationale: revert_failed prints the failed
        # command VERBATIM, so the operator's manual re-run keeps the
        # no-sign pinning without rediscovering it.
        surveys = iter([[thread("11", "resolved")]])

        def rc_for(argv):
            return (
                1 if "commit.gpgsign=false" in argv and "revert" in argv
                else 0
            )

        # When: the head-mismatch revert fires and the revert fails.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            rc_for=rc_for,
        )

        # Then: the banner names BOTH no-sign surfaces of the exact
        # failed command (a copy-paste re-run stays unsigned in the
        # signing-forcing checkout).
        self.assertEqual(code, 1)
        self.assertIn("REVERT FAILED at `", out)
        self.assertIn("-c commit.gpgsign=false", out)
        self.assertIn("revert --no-gpg-sign", out)
        self.assertIn("MUST be reverted manually", out)


if __name__ == "__main__":
    unittest.main()
