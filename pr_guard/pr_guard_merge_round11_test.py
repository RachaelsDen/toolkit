"""pr_guard merge-act round-11 tests (PR #41 round 11, refit 25).

Thread 3833880596: a multi-commit PR squashed by the queue lands ONE
commit while the PR's commit list still counts many — the round-9/10
commit-COUNT branch built a range revert of the ORIGINAL PR commits
instead of reverting merge_sha. Rounds 11-24 answered with a chain of
landing-shape discriminators (count, patch-ids, sequence, metadata,
deltas, markers); PR #41 round 25 (threads 3835145976/3835145981/
3835175506/3835175508) RETIRED the whole program — every signal fell
to a reviewer counter-example — and these suites now drive the
CONTRACT: the single-parent revert is automated only when the
landing's parent IS the current <remote>/<base> tip (harness defaults
landing_parent == base_tip); a multi-commit rebase-shaped landing
fails closed to the manual banner WITH the fork/range/count
diagnostics (served by landing_probes), never an automated range
revert.

Thread 3833880605: the canonical-remote resolver verifies BOTH the
fetch and the push URL against the EXACT repository path — a
triangular remote (canonical fetch, fork pushurl) is repaired by
installing the dedicated pr-guard-canonical remote at the canonical
fetch URL (both directions); a repair that fails blocks the revert,
and a similarly named repository (UR-lorebook-backup) is not
canonical at all.

No network: the shared fake-gh/fake-clock harness drives the act;
landing_probes serves the discriminator probe ANSWERS and remote_v
the triangular/backup checkout shapes.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round11_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    FORK_SHA,
    FOREIGN_PARENT,
    GUARD_ID,
    GUARD_NO_SIGN,
    HEAD,
    MERGE_SHA,
    MergeHarness,
    landing_probes,
    merged,
    thread,
)

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"
RANGE_OLDEST = "bbbb000000000000000000000000000000000022"
RANGE_MIDDLE = "cccc000000000000000000000000000000000033"
RANGE_NEWEST = "dddd000000000000000000000000000000000044"
TRIANGULAR_REMOTE_V = (
    "origin\tgit@github.com:RachaelsDen/UR-lorebook.git (fetch)\n"
    "origin\tgit@github.com:contributor/UR-lorebook.git (push)\n"
)
BACKUP_REMOTE_V = (
    "origin\tgit@github.com:RachaelsDen/UR-lorebook-backup.git "
    "(fetch)\n"
    "origin\tgit@github.com:RachaelsDen/UR-lorebook-backup.git (push)\n"
)
CANONICAL_URL = "git@github.com:RachaelsDen/UR-lorebook.git"


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class TwoCaseContractTests(unittest.TestCase):
    def test_squash_of_three_reverts_the_landing_once(self):
        # Given: the merge queue SQUASHED a THREE-commit PR — the PR's
        # frozen pre-dispatch snapshot counts three (thread 3833880596's
        # finding: the count-based branch used to build a range revert
        # of the original pre-squash commits) while the landing sits
        # DIRECTLY on the current base tip (parent == tip, the harness
        # defaults) — the round-25 contract's one automated
        # single-parent shape.
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires on that landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            pr_commits=[RANGE_OLDEST, RANGE_MIDDLE, RANGE_NEWEST],
        )

        # Then: ONE plain `git revert --no-edit` of the LANDED commit
        # — never a range of the original pre-squash OIDs — decided by
        # the parent/base-tip probes ALONE (no fork, range, patch-id,
        # or marker probe licenses anything any more), with the PR
        # body documenting the unambiguous-shape contract.
        self.assertEqual(code, 1)
        self.assertIn(f"git -C {RUNNER.revert_tmp} {GUARD_ID} {GUARD_NO_SIGN} revert --no-gpg-sign --no-edit {MERGE_SHA}", argvs)
        self.assertNotIn("^..", " ".join(argvs))
        self.assertNotIn(RANGE_OLDEST, " ".join(argvs[-4:]))
        self.assertNotIn("git merge-base", " ".join(argvs))
        self.assertNotIn("git rev-list", " ".join(argvs))
        self.assertNotIn("git patch-id --stable", " ".join(argvs))
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn("SINGLE-PARENT landing whose parent IS the FROZEN", create)
        self.assertIn("3835145976", create)
        self.assertIn("REVERT PR OPENED", out)

    def test_rebase_of_three_fails_closed_by_contract(self):
        # Given: the same three-commit single-parent landing, but the
        # landed range counts THREE commits past the fork point — the
        # queue REBASED the PR (thread 3833671111's finding stands:
        # reverting only the tip would leave the earlier PR commits)
        # — so the landing's parent is the second rebased PR commit,
        # NOT the base tip. Rounds 11-24 automated a RANGE revert
        # here; thread 3835175506's counter-example (a foreign
        # cherry-pick beside a marker-free custom-subject squash
        # satisfying every provenance rule) retired that classifier,
        # so the shape now fails closed BY CONTRACT.
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires on the rebase-shaped
        # landing whose parent is not the base tip.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=[RANGE_OLDEST, RANGE_MIDDLE, RANGE_NEWEST],
            git_answers=landing_probes(MERGE_SHA, landed=3),
        )

        # Then: the DIAGNOSTIC probes ran (the fork-point merge-base
        # and the landed-range list feed the banner, they license
        # nothing), NO revert argv was dispatched, and the banner
        # names the contract, the numbers, and the counter-example
        # chain.
        self.assertEqual(code, 1)
        self.assertIn(
            f"git rev-list --no-merges {FORK_SHA}..{MERGE_SHA}", argvs
        )
        self.assertNotIn("git patch-id --stable", " ".join(argvs))
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn("NEITHER", out)
        self.assertIn("counts 3 commit(s)", out)
        self.assertIn("FROZEN pre-dispatch commit snapshot counts 3 commit(s)", out)
        self.assertIn("MUST be reverted manually", out)
        self.assertIn("3835175506", out)
        self.assertNotIn("REVERT PR OPENED", out)

    def test_unreadable_fork_degrades_only_the_diagnostics(self):
        # Given: a single-parent landing whose parent is NOT the base
        # tip (fail-closed by contract) AND a fork-point probe that
        # cannot answer — the merge-base exits nonzero, so the
        # landed-range count cannot be formed. The round-13 classifier
        # failed closed HERE; the round-25 banner fails closed on the
        # SHAPE alone and reports the fork degradation as a missing
        # diagnostic, never as a classification.
        surveys = iter([[thread("11", "resolved")]])

        # When: the revert fires with only the fork-point probe
        # failing beside the non-tip parent.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=[RANGE_OLDEST, RANGE_MIDDLE, RANGE_NEWEST],
            git_answers=landing_probes(MERGE_SHA, fork_rc=128),
        )

        # Then: the manual-revert banner still fired on the contract
        # (parent is not the tip) and reports the range count as
        # UNAVAILABLE; NO revert argv was dispatched, no revert PR
        # opened.
        self.assertEqual(code, 1)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn("landed-range count is UNAVAILABLE", out)
        self.assertIn("MUST be reverted manually", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)


class TriangularRemoteTests(unittest.TestCase):
    def test_triangular_remote_installs_dedicated_canonical(self):
        # Given: the ordinary fork-contribution checkout — origin
        # FETCHES the canonical repository but its PUSH URL targets
        # the contributor's fork (thread 3833880605: the round-10
        # resolver selected origin by its fetch line alone, and
        # `git push origin` follows the pushurl to the fork).
        surveys = iter([[thread("11", "resolved")]])

        # When: the revert fires from the triangular checkout.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_v=TRIANGULAR_REMOTE_V,
        )

        # Then: the dedicated pr-guard-canonical remote was INSTALLED
        # at the canonical fetch URL and carries EVERY git operation
        # of the revert — the base fetch, the worktree build, and the
        # push — never the triangular origin, and the repair is
        # reported.
        self.assertEqual(code, 1)
        self.assertIn(
            f"git remote add pr-guard-canonical {CANONICAL_URL}", argvs
        )
        self.assertIn("git fetch pr-guard-canonical dev", argvs)
        tmp = RUNNER.revert_tmp
        self.assertIn(
            f"git worktree add --detach {tmp} pr-guard-canonical/dev",
            argvs,
        )
        self.assertNotIn("git checkout -B", " ".join(argvs))
        self.assertIn(
            f"git -C {tmp} push pr-guard-canonical "
            f"HEAD:refs/heads/revert/pr39-{MERGE_SHA[:7]}",
            argvs,
        )
        self.assertNotIn("git push -u origin", " ".join(argvs))
        self.assertNotIn("git fetch origin", " ".join(argvs))
        self.assertIn("CANONICAL PUSH REPAIRED", out)
        self.assertIn("3833880605", out)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn("canonical remote 'pr-guard-canonical'", create)
        self.assertIn("REVERT PR OPENED", out)

    def test_triangular_remote_repair_failure_blocks(self):
        # Given: the same triangular checkout, but the environment
        # refuses remote mutation — the first `git remote add` AND the
        # remove+add rebuild both fail, so no safe push destination
        # exists (thread 3834210476: the rebuild replaced the old
        # set-url repair, which left stray pushurls configured).
        surveys = iter([[thread("11", "resolved")]])

        # When: every remote-mutation argv exits nonzero.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_v=TRIANGULAR_REMOTE_V,
            rc_for=lambda argv: (
                1
                if argv[:3] in (
                    ["git", "remote", "add"],
                    ["git", "remote", "remove"],
                )
                else 0
            ),
        )

        # Then: the hard block names the pushurl trap and the manual
        # obligation — NO fetch, checkout, push, or revert ever ran
        # against the fork's push destination, and no set-url repair
        # was attempted (it would leave stray pushurls).
        self.assertEqual(code, 1)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn("PUSH URL", out)
        self.assertIn("3833880605", out)
        self.assertIn("3834210476", out)
        self.assertNotIn("git remote set-url", " ".join(argvs))
        self.assertIn("MUST be reverted manually", out)
        joined = " ".join(argvs)
        self.assertNotIn("git fetch", joined)
        self.assertNotIn("git push", joined)
        self.assertNotIn("git checkout", joined)
        self.assertNotIn("git revert", joined)
        self.assertNotIn("REVERT PR OPENED", out)

    def test_backup_named_repo_is_not_canonical(self):
        # Given: the checkout's origin points at the similarly named
        # RachaelsDen/UR-lorebook-BACKUP repository on both endpoints
        # — the round-10 substring test accepted it as canonical.
        surveys = iter([[thread("11", "resolved")]])

        # When: the revert fires from the backup checkout.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_v=BACKUP_REMOTE_V,
        )

        # Then: the hard block requires the EXACT repository — no
        # dedicated remote was added for the backup (it does not even
        # fetch canonically) and no git operation ran.
        self.assertEqual(code, 1)
        self.assertIn("NO CANONICAL REMOTE", out)
        self.assertIn("3833880605", out)
        joined = " ".join(argvs)
        self.assertNotIn("git remote add", joined)
        self.assertNotIn("git fetch", joined)
        self.assertNotIn("git push", joined)
        self.assertNotIn("REVERT PR OPENED", out)


if __name__ == "__main__":
    unittest.main()
