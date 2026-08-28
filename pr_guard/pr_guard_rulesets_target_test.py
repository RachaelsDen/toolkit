"""pr_guard harden ruleset-TARGET verification tests (PR #41 round
10, thread 3833762329).

Neither gate_covers nor the round-9 exact-scope check examined the
stored TARGET — a same-named ruleset stored with target 'tag' or
'push' passes every ref-condition and pull_request-rule check while
gating NOTHING about pull requests on branches (e.g. a manually
created same-named ruleset was selected, or a PATCH left the field
unchanged), so the DELETE loop would strip the real fallbacks under a
HARDENED claim. The pre-DELETE verification now asserts stored
target == 'branch'; a wrong target blocks the DELETEs with the stored
value printed. Split from pr_guard_rulesets_verify_test at the 250
pure-LOC ceiling. No network: the shared FakeRulesetStore from
pr_guard_rulesets_harden_test backs the gh_rest fake.

Run: cd .omo/start-work && python3 -m unittest pr_guard_rulesets_target_test -v
"""

import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_rulesets
from .pr_guard_rulesets_harden_test import (
    FakeRulesetStore,
    REPO_ROOT,
    WILDCARDS,
    detail,
)
from .pr_guard_rulesets_test import gate_ruleset
from .pr_guard_rulesets_verify_test import NoOpPatchStore

NEW_NAME = pr_guard_rulesets.GATE_RULESET_NAME
GATE_PREFIX = pr_guard_rulesets.GATE_RULE_PREFIX


class TargetVerificationTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def run_harden(self, store: FakeRulesetStore) -> tuple[int, str]:
        out = io.StringIO()
        with (
            mock.patch.object(
                pr_guard_rulesets, "gh_rest", side_effect=store.gh_rest
            ),
            redirect_stdout(out),
        ):
            code = pr_guard_rulesets.harden(39)
        return code, out.getvalue()

    def writes(self, store: FakeRulesetStore) -> dict[tuple[str, str], dict]:
        return {
            (method, path): body
            for method, path, body in store.calls
            if method in {"POST", "PATCH", "DELETE"}
        }

    def test_tag_target_blocks_the_deletes(self):
        # Given: a same-named MANUALLY created ruleset stored with
        # target='tag' (thread 3833762329) — its ref conditions and
        # pull_request rule have exactly the expected shape, but a
        # tag-target ruleset gates NOTHING about pull requests on
        # branches; a legacy '(all bases)' fallback sits beside it as
        # the only real branch gate.
        mistargeted = gate_ruleset(
            include=list(pr_guard_rulesets.PROTECTED_BASE_PATTERNS),
            target="tag",
        )
        mistargeted["id"] = 77
        mistargeted["name"] = NEW_NAME
        store = NoOpPatchStore(
            {
                77: mistargeted,
                21137845: detail(
                    21137845, f"{GATE_PREFIX} (all bases)", WILDCARDS
                ),
            }
        )

        # When: harden runs against the mis-targeted canonical.
        code, out = self.run_harden(store)

        # Then: BLOCKED printing the STORED target — NO DELETE fired
        # (only the transport no-op PATCH ran), so the legacy fallback
        # (the only gate that actually covers branch PRs) stays in
        # place while the canonical is repaired; no HARDENED claim.
        self.assertEqual(code, 1)
        self.assertEqual(
            list(self.writes(store)),
            [("PATCH", f"{REPO_ROOT}/rulesets/77")],
        )
        self.assertIn(21137845, store.rulesets)
        self.assertIn("stored TARGET is 'tag'", out)
        self.assertIn("not 'branch'", out)
        self.assertIn("gates NOTHING about pull requests on branches", out)
        self.assertIn("thread 3833762329", out)
        self.assertIn("LEFT IN PLACE", out)
        self.assertIn("DO NOT merge on this gate", out)
        self.assertNotIn("HARDENED", out)
        self.assertNotIn("DELETED redundant", out)

    def test_branch_target_still_proceeds_to_the_deletes(self):
        # Given: the stored canonical carries target='branch' with
        # the exact protected scope — the target invariant HOLDS, so
        # the DELETEs are licensed as before.
        store = FakeRulesetStore(
            {
                77: detail(
                    77, NEW_NAME,
                    list(pr_guard_rulesets.PROTECTED_BASE_PATTERNS),
                ),
                21137845: detail(
                    21137845, f"{GATE_PREFIX} (all bases)", WILDCARDS
                ),
            }
        )

        # When: harden runs.
        code, out = self.run_harden(store)

        # Then: the redundant is DELETEd and HARDENED verifies — the
        # new invariant only widens the check, it does not refuse the
        # healthy shape.
        self.assertEqual(code, 0)
        self.assertNotIn(21137845, store.rulesets)
        self.assertIn("DELETED redundant ruleset id 21137845", out)
        self.assertIn("HARDENED refs/heads/dev", out)


if __name__ == "__main__":
    unittest.main()
