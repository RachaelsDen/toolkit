"""pr_guard_suites_committed_test — the committed-suite guard.

PR #49 round 11 (thread 3868979520, P2 — the FOURTH occurrence of
the .omo gitignore add -f trap): the aggregate registered
pr_guard_reaction_round10_test while the module existed only in the
WORKING TREE (`.omo` is gitignored, so an ordinary `git add` never
staged it), and the documented aggregate command failed on the
clean checkout with ModuleNotFoundError while passing locally.

THE GUARD: every module referenced in the aggregate's _SUITES must
exist as a COMMITTED blob under the pr_guard package in HEAD — a
registered-but-uncommitted suite fails THIS test until `git add`
lands, so the class can never ship again. In a git-archive
extraction (no .git) the guard SKIPS: the archive's own aggregate
import is the stronger guard there (a missing module fails the load
itself), and committed-ness is meaningless without a repository;
an UNBORN HEAD (the extraction's pre-first-commit state) skips the
same way — nothing can be committed yet.

Run: cd .omo/start-work && python3 -m unittest pr_guard_suites_committed_test -v
"""

import os
import subprocess
import unittest

from . import pr_guard_test

SUITE_DIR = "pr_guard"


class SuitesCommittedTests(unittest.TestCase):
    def test_every_registered_suite_is_a_committed_blob(self):
        # Given: the aggregate's _SUITES registration (this guard
        # included — a working-tree-only guard would itself be the
        # trap it polices). When: HEAD's committed blobs under
        # .omo/start-work/ are listed. Then: EVERY registered module
        # is among them — nothing the aggregate imports may live
        # only in the working tree (thread 3868979520).
        here = os.path.dirname(os.path.abspath(__file__))
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=here,
            capture_output=True,
            text=True,
        )
        if root.returncode != 0:
            self.skipTest(
                "no git repository (archive checkout?) — the aggregate "
                f"import is the guard there: {root.stderr.strip()}"
            )
        # The toolkit extraction: before the FIRST commit exists an
        # unborn HEAD cannot list blobs — nothing can be committed
        # yet, so the aggregate import is the guard until history
        # lands (the archive-extraction precedent above).
        head = subprocess.run(
            ["git", "-C", root.stdout.strip(), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
        )
        if head.returncode != 0:
            self.skipTest(
                "unborn HEAD — no commit exists yet, so nothing can "
                "be a committed blob; the aggregate import is the "
                "guard until the first commit lands"
            )
        listing = subprocess.run(
            [
                "git", "-C", root.stdout.strip(),
                "ls-tree", "-r", "HEAD", "--", f"{SUITE_DIR}/",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(listing.returncode, 0, listing.stderr)
        committed = {
            line.split("\t", 1)[1]
            for line in listing.stdout.splitlines()
            if "\t" in line
        }
        missing = [
            name
            for name in pr_guard_test._SUITES
            if f"{SUITE_DIR}/{name}.py" not in committed
        ]
        self.assertEqual(
            missing,
            [],
            "registered in _SUITES but NOT committed — the .omo gitignore "
            "add -f trap (thread 3868979520); run: git add -f "
            + " ".join(f"{SUITE_DIR}/{name}.py" for name in missing),
        )


if __name__ == "__main__":
    unittest.main()
