"""pr_guard merge-act round-14 tests (PR #41 round 14).

Thread 3834210476: EVERY push URL of the canonical remote must be
canonical — `git remote -v` emits one (push) line per configured
pushurl and the round-13 resolver kept only the LAST, so a remote
holding a fork pushurl BESIDE the canonical one validated clean while
`git push` still tried the fork first. The resolver now requires
EVERY fetch and push URL (non-empty, all canonical), and repairing
the dedicated remote when it already exists REBUILDS it (remove +
add — `git remote set-url --push` replaces only the FIRST pushurl
and leaves strays, the exact bug); a failed rebuild is the hard
block.

Thread 3834210484's patch-id discriminator — and the whole
count/sequence/metadata/delta/marker chain it grew into through
round 24 — was RETIRED at round 25 (threads 3835145976/3835145981/
3835175506/3835175508): every provenance signal fell to a reviewer
counter-example, so the exotic spoof shapes those suites built now
FAIL CLOSED by contract (parent is not the base tip) and the
patch-id/delta plumbing never runs at all. The four PatchIdLanding
suites were collapsed into ONE retirement test asserting exactly
that; the rest were DELETED as redundant with the refit round-11/12
fail-closed suites (the suite count drops by design).

No network: the shared fake-gh/fake-clock harness drives the act;
landing_probes serves the diagnostic probes and remote_v the
multi-pushurl checkout shapes.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round14_test -v
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

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"
RANGE_OLDEST = "bbbb000000000000000000000000000000000022"
RANGE_MIDDLE = "cccc000000000000000000000000000000000033"
RANGE_NEWEST = "dddd000000000000000000000000000000000044"
FOREIGN_SHA = "eeee0000000000000000000000000000000000f1"
REBASED_FIRST = "eeee0000000000000000000000000000000000b1"
# Thread 3834761215 (round 19): the oldest sha rebase_probes
# synthesizes for the LANDED chain — distinct from REBASED_FIRST
# above (a hand-picked spoof sha), this one must match the
# generator's format exactly.
REBASED_OLDEST = "eeee000000000000000000000000000000000b01"
CANONICAL_URL = "git@github.com:RachaelsDen/UR-lorebook.git"
ORIGIN_TWO_PUSH_ONE_FORK = (
    "origin\tgit@github.com:RachaelsDen/UR-lorebook.git (fetch)\n"
    "origin\tgit@github.com:RachaelsDen/UR-lorebook.git (push)\n"
    "origin\tgit@github.com:contributor/UR-lorebook.git (push)\n"
)
ORIGIN_TWO_PUSH_BOTH_CANONICAL = (
    "origin\tgit@github.com:RachaelsDen/UR-lorebook.git (fetch)\n"
    "origin\tgit@github.com:RachaelsDen/UR-lorebook.git (push)\n"
    "origin\thttps://github.com/RachaelsDen/UR-lorebook.git (push)\n"
)
DEDICATED_STRAY_PUSHURL = (
    "origin\tgit@github.com:contributor/UR-lorebook.git (fetch)\n"
    "origin\tgit@github.com:contributor/UR-lorebook.git (push)\n"
    "pr-guard-canonical\tgit@github.com:RachaelsDen/UR-lorebook.git "
    "(fetch)\n"
    "pr-guard-canonical\tgit@github.com:RachaelsDen/UR-lorebook.git "
    "(push)\n"
    "pr-guard-canonical\tgit@mirror.example:RachaelsDen/UR-lorebook.git "
    "(push)\n"
)
PR_COMMITS = [RANGE_OLDEST, RANGE_MIDDLE, RANGE_NEWEST]


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class MultiPushUrlTests(unittest.TestCase):
    def test_origin_with_two_pushurls_one_fork_uses_dedicated(self):
        # Given: origin FETCHES and PUSHES the canonical repository
        # but carries a SECOND pushurl targeting the contributor's
        # fork (thread 3834210476's exact shape: the round-13 dict
        # kept only the LAST push line, and `git push origin` tries
        # every configured pushurl — the revert branch could land on
        # the fork).
        surveys = iter([[thread("11", "resolved")]])

        # When: the revert fires from the multi-pushurl checkout.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_v=ORIGIN_TWO_PUSH_ONE_FORK,
        )

        # Then: origin is rejected AS-IS, the dedicated remote is
        # installed at the canonical URL, and every git operation of
        # the revert goes through it — never origin.
        self.assertEqual(code, 1)
        self.assertIn(
            f"git remote add pr-guard-canonical {CANONICAL_URL}", argvs
        )
        tmp = RUNNER.revert_tmp
        self.assertIn("git fetch pr-guard-canonical dev", argvs)
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
        self.assertIn("3834210476", out)
        self.assertIn("REVERT PR OPENED", out)

    def test_origin_with_two_canonical_pushurls_is_used_directly(self):
        # Given: origin carries TWO pushurls but BOTH are canonical
        # GitHub URLs naming the repository (scp + https) — every
        # fetch and push URL qualifies, so the remote is safe as-is.
        surveys = iter([[thread("11", "resolved")]])

        # When: the revert fires from the all-canonical multi-pushurl
        # checkout.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_v=ORIGIN_TWO_PUSH_BOTH_CANONICAL,
        )

        # Then: origin is used DIRECTLY — no dedicated remote was
        # installed, no repair banner — and the revert PR opened.
        self.assertEqual(code, 1)
        tmp = RUNNER.revert_tmp
        self.assertIn("git fetch origin dev", argvs)
        self.assertIn(
            f"git worktree add --detach {tmp} origin/dev", argvs
        )
        self.assertIn(
            f"git -C {tmp} push origin "
            f"HEAD:refs/heads/revert/pr39-{MERGE_SHA[:7]}",
            argvs,
        )
        self.assertNotIn("git remote add", " ".join(argvs))
        self.assertNotIn("git remote remove", " ".join(argvs))
        self.assertNotIn("CANONICAL PUSH REPAIRED", out)
        self.assertIn("REVERT PR OPENED", out)

    def test_stray_dedicated_remote_pushurl_is_rebuilt(self):
        # Given: the dedicated pr-guard-canonical remote ALREADY
        # exists with a canonical fetch and push — plus a STRAY
        # mirror pushurl (thread 3834210476: `git remote set-url
        # --push` would replace only the FIRST pushurl and leave the
        # stray configured), and no other remote fetches canonically.
        surveys = iter([[thread("11", "resolved")]])
        rebuilt = {"removed": False}

        def rc_for(argv):
            if argv[:3] == ["git", "remote", "remove"]:
                rebuilt["removed"] = True
                return 0
            if argv[:3] == ["git", "remote", "add"]:
                return 0 if rebuilt["removed"] else 1
            return 0

        # When: the resolver repairs the mis-pointed dedicated remote
        # — the first add FAILS (it already exists), the remove+add
        # rebuild succeeds.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_v=DEDICATED_STRAY_PUSHURL,
            rc_for=rc_for,
        )

        # Then: the REBUILD argv ran (remove THEN add — no set-url,
        # which would leave the stray pushurl) and the rebuilt remote
        # carries every git operation of the revert.
        self.assertEqual(code, 1)
        self.assertIn("git remote remove pr-guard-canonical", argvs)
        self.assertIn(
            f"git remote add pr-guard-canonical {CANONICAL_URL}", argvs
        )
        self.assertLess(
            argvs.index("git remote remove pr-guard-canonical"),
            len(argvs)
            - 1
            - argvs[::-1].index(
                f"git remote add pr-guard-canonical {CANONICAL_URL}"
            ),
        )
        self.assertNotIn("git remote set-url", " ".join(argvs))
        tmp = RUNNER.revert_tmp
        self.assertIn("git fetch pr-guard-canonical dev", argvs)
        self.assertIn(
            f"git -C {tmp} push pr-guard-canonical "
            f"HEAD:refs/heads/revert/pr39-{MERGE_SHA[:7]}",
            argvs,
        )
        self.assertIn("CANONICAL PUSH REPAIRED", out)
        self.assertIn("3834210476", out)
        self.assertIn("REVERT PR OPENED", out)


class PatchIdRetirementTests(unittest.TestCase):
    def test_spoof_shape_fails_closed_with_no_provenance_pipes(self):
        # Given: the round-14to24 suites' SPOOF shape — a foreign
        # queue commit beside the landing, with every provenance
        # signal the old classifier consumed (patch-ids, order,
        # author/subject, deltas, markers) satisfiable by
        # construction — and a parent that is NOT the current base
        # tip. Threads 3835175506/3835175508/3835145976 proved every
        # one of those signals reproducible by a foreign landing, so
        # round 25 fails the shape closed BY CONTRACT and no
        # provenance pipe may even RUN.
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires on the spoof shape.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=PR_COMMITS,
            git_answers=landing_probes(
                MERGE_SHA,
                range_shas=[FOREIGN_SHA, MERGE_SHA],
                landed=2,
            ),
        )

        # Then: the fail-closed banner fired on the contract (neither
        # automated shape), NO patch-id/diff-tree/delta/metadata pipe
        # ran (the argv record holds only the two-case probes and the
        # fork/range DIAGNOSTICS), no revert argv was dispatched, and
        # no revert PR opened.
        self.assertEqual(code, 1)
        joined = " ".join(argvs)
        self.assertNotIn("git patch-id", joined)
        self.assertNotIn("git diff-tree", joined)
        self.assertNotIn("git rev-list --stdin", joined)
        self.assertNotIn("--is-ancestor", joined)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn("NEITHER", out)
        self.assertIn("counts 2 commit(s)", out)
        self.assertIn("MUST be reverted manually", out)
        self.assertIn("3835175506", out)
        self.assertNotIn("git revert", joined)
        self.assertNotIn("REVERT PR OPENED", out)


if __name__ == "__main__":
    unittest.main()
