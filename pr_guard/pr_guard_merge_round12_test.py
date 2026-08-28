"""pr_guard merge-act round-12 tests (PR #41 round 12).

Thread 3833993101: when an earlier merge-queue entry ADVANCED the
base before this PR's squash, the round-11 fork-point rule read the
squash as a rebase range. Rounds 13-24 chased that shape through
counts, patch-ids, sequences, metadata, deltas, and markers; PR #41
round 25 (threads 3835145976/3835145981/3835175506/3835175508)
RETIRED the program — every signal fell to a reviewer counter-example
— and the advancement-interleaved squash now fails closed BY
CONTRACT (its parent is the foreign advancement head, not the
current base tip), with the fork/range numbers as banner
diagnostics only. The multi-commit-rebase suite here was DELETED as
redundant with round 11's fail-closed refit (the suite count drops
by design).

Thread 3833993106: the canonical-remote resolver requires the URL to
BE a GitHub URL — host literally github.com in the scp
(git@github.com:owner/repo) or https://github.com/owner/repo form. A
mirror host (git@mirror.example:...) or a local path that merely
ENDS in the slug is rejected, so the revert can never fetch/push
through a mirror while the pinned gh commands target github.com.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round12_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    FOREIGN_PARENT,
    HEAD,
    MERGE_SHA,
    MergeHarness,
    landing_probes,
    merged,
    thread,
)
from .pr_guard_remote import url_is_canonical

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"
RANGE_OLDEST = "bbbb000000000000000000000000000000000022"
RANGE_MIDDLE = "cccc000000000000000000000000000000000033"
RANGE_NEWEST = "dddd000000000000000000000000000000000044"
MIRROR_REMOTE_V = (
    "origin\tgit@mirror.example:RachaelsDen/UR-lorebook.git (fetch)\n"
    "origin\tgit@mirror.example:RachaelsDen/UR-lorebook.git (push)\n"
)


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class AdvancedBaseSquashTests(unittest.TestCase):
    def test_advanced_base_squash_fails_closed_by_contract(self):
        # Given: an earlier queue entry advanced the base BEFORE this
        # PR's three-commit squash — the landing's parent is the
        # FOREIGN advancement head, not the current base tip. The
        # rounds-11-to-24 classifier automated a one-commit revert
        # here (the fork counts exactly one commit); thread 3835175506
        # proved that whole program spoofable (a foreign cherry-pick
        # beside a marker-free custom-subject squash satisfies every
        # rule), so the round-25 contract fails this shape closed —
        # the advancement-interleaved anything class.
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires on the
        # advancement-interleaved squash.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=[RANGE_OLDEST, RANGE_MIDDLE, RANGE_NEWEST],
        )

        # Then: NO revert argv was dispatched and no revert PR opened
        # — the banner states the contract (neither automated shape),
        # carries the numbers a human needs (the parent beside the
        # base tip, the landed-range count past the fork, the frozen
        # commit count, marker presence), and cites the
        # counter-example chain.
        self.assertEqual(code, 1)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn("NEITHER", out)
        self.assertIn("counts 1 commit(s)", out)
        self.assertIn("FROZEN pre-dispatch commit snapshot counts 3 commit(s)", out)
        self.assertIn("NO trailing squash marker", out)
        self.assertIn("MUST be reverted manually", out)
        self.assertIn("3835175506", out)

    def test_erroring_list_probe_degrades_the_diagnostics_only(self):
        # Given: a fail-closed shape (parent is not the base tip)
        # whose landed-range LIST probe cannot answer (exit 128 — a
        # missing object or an unresolved rev). The old classifier
        # failed closed HERE on the unreadable probe; the round-25
        # contract fails closed on the SHAPE alone and reports the
        # unreadable list as a MISSING diagnostic, never as a
        # classification.
        surveys = iter([[thread("11", "resolved")]])

        # When: the fork probe resolves but the list probe exits
        # beyond a readable commit list.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=[RANGE_OLDEST, RANGE_MIDDLE, RANGE_NEWEST],
            git_answers=landing_probes(MERGE_SHA, list_rc=128),
        )

        # Then: the manual-revert banner fired on the contract and
        # reports the range count as UNAVAILABLE; NO revert argv was
        # dispatched, no revert PR opened.
        self.assertEqual(code, 1)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn("landed-range count is UNAVAILABLE", out)
        self.assertIn("MUST be reverted manually", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)


class GitHubHostTests(unittest.TestCase):
    def test_mirror_hosts_and_local_paths_are_not_canonical(self):
        # Given: URLs whose final two path segments ARE the slug but
        # whose host is a mirror, an alias, or nothing at all (a local
        # path) — the round-11 exact-PATH parser accepted every one of
        # them (thread 3833993106's exact finding).
        # Then: none is canonical — the host must be literally
        # github.com.
        self.assertFalse(
            url_is_canonical("git@mirror.example:RachaelsDen/UR-lorebook.git")
        )
        self.assertFalse(
            url_is_canonical("ssh://git@mirror.example/RachaelsDen/UR-lorebook.git")
        )
        self.assertFalse(
            url_is_canonical("https://mirror.example/RachaelsDen/UR-lorebook.git")
        )
        self.assertFalse(
            url_is_canonical("/srv/git/RachaelsDen/UR-lorebook")
        )
        self.assertFalse(
            url_is_canonical("../checkouts/RachaelsDen/UR-lorebook.git")
        )
        self.assertFalse(url_is_canonical("gh:RachaelsDen/UR-lorebook.git"))
        self.assertFalse(
            url_is_canonical("ssh://git@github.com:22/RachaelsDen/UR-lorebook.git")
        )
        self.assertFalse(
            url_is_canonical("http://github.com/RachaelsDen/UR-lorebook.git")
        )

    def test_github_urls_are_canonical(self):
        # Given: the canonical repository's GitHub URLs in every
        # accepted form (scp, https, ssh) — and the same host with a
        # different repository name.
        # Then: the GitHub forms qualify; the same-named repository on
        # github.com still does not.
        self.assertTrue(
            url_is_canonical("git@github.com:RachaelsDen/UR-lorebook.git")
        )
        self.assertTrue(
            url_is_canonical("git@github.com:RachaelsDen/UR-lorebook")
        )
        self.assertTrue(
            url_is_canonical("https://github.com/RachaelsDen/UR-lorebook.git")
        )
        self.assertTrue(
            url_is_canonical("https://github.com/RachaelsDen/UR-lorebook/")
        )
        self.assertTrue(
            url_is_canonical("ssh://git@github.com/RachaelsDen/UR-lorebook.git")
        )
        self.assertFalse(
            url_is_canonical("git@github.com:RachaelsDen/UR-lorebook-backup.git")
        )
        self.assertFalse(url_is_canonical("git@github.com:RachaelsDen"))

    def test_mirror_checkout_blocks_the_revert(self):
        # Given: the checkout's origin points at the MIRROR on both
        # endpoints — the path names the slug, the host does not name
        # github.com — so `git fetch`/`git push` through it would run
        # against the mirror while every pinned gh command targets
        # github.com.
        surveys = iter([[thread("11", "resolved")]])

        # When: the revert fires from the mirror checkout.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_v=MIRROR_REMOTE_V,
        )

        # Then: the hard block names the github.com host requirement
        # (with mirror/alias instructions) and NO git operation ever
        # touched the mirror.
        self.assertEqual(code, 1)
        self.assertIn("NO CANONICAL REMOTE", out)
        self.assertIn("literally github.com", out)
        self.assertIn("3833993106", out)
        joined = " ".join(argvs)
        self.assertNotIn("git remote add", joined)
        self.assertNotIn("git fetch", joined)
        self.assertNotIn("git push", joined)
        self.assertNotIn("git checkout", joined)
        self.assertNotIn("REVERT PR OPENED", out)


if __name__ == "__main__":
    unittest.main()
