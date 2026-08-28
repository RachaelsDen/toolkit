"""pr_guard harden stored-rule PAYLOAD verification tests (PR #41
round 17, thread 3834590324).

The pre-DELETE verification asserted target and ref scope but never
the stored RULE LIST or its parameters — a transport-successful PATCH
could leave `required_approving_review_count` nonzero, an EXTRA rule
beside the gate, or `dismiss_stale_reviews_on_push` true, and the
redundant fallbacks were then DELETEd with `HARDENED` printed while
the surviving canonical ruleset unexpectedly BLOCKED merges the
neutral rule would allow. The stored shape must be EXACTLY one
pull_request rule carrying EXACTLY the parameters dict the guard
installs (pr_guard_rules_payload.GATE_RULE_PARAMETERS — the single
source the write sends and the verification compares). No network:
the shared FakeRulesetStore from pr_guard_rulesets_harden_test backs
the gh_rest fake.

Run: cd .omo/start-work && python3 -m unittest pr_guard_rulesets_payload_test -v
"""

import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_rulesets
from .pr_guard_rules_payload import GATE_RULE, GATE_RULE_PARAMETERS
from .pr_guard_rulesets_harden_test import (
    FakeRulesetStore,
    REPO_ROOT,
    WILDCARDS,
    detail,
)
from .pr_guard_rulesets_test import gate_ruleset

NEW_NAME = pr_guard_rulesets.GATE_RULESET_NAME
GATE_PREFIX = pr_guard_rulesets.GATE_RULE_PREFIX


class NoOpPatchStore(FakeRulesetStore):
    # Thread 3834590324's failure shape: the PATCH is accepted at the
    # transport level (recorded, exits 0) but the STORED ruleset is
    # unchanged — scope and target are already exactly right, so ONLY
    # the payload comparison can catch what survived.
    def gh_rest(self, method, path, body=None):
        if method == "PATCH":
            self.calls.append((method, path, body))
            return self.rulesets[int(path.rsplit("/", 1)[-1])]
        return super().gh_rest(method, path, body)


def payload_detail(rules: list[dict]) -> dict:
    record = gate_ruleset(
        include=list(pr_guard_rulesets.PROTECTED_BASE_PATTERNS)
    )
    record["id"] = 77
    record["name"] = NEW_NAME
    record["rules"] = rules
    return record


class StoredPayloadVerifyTests(unittest.TestCase):
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

    def test_stale_approving_count_blocks_the_deletes(self):
        # Given: the transport-successful PATCH leaves the stored
        # canonical EXACTLY scoped (both protected bases, no excludes,
        # target branch, active, no bypass) — every earlier check
        # passes — but its pull_request rule carries a STALE
        # `required_approving_review_count` of 2 (thread 3834590324's
        # exact finding: the surviving canonical would block merges
        # the neutral rule allows, and the DELETEs would have removed
        # every fallback beside it).
        stale = dict(GATE_RULE_PARAMETERS)
        stale["required_approving_review_count"] = 2
        store = NoOpPatchStore(
            {
                77: payload_detail([{"type": "pull_request",
                                     "parameters": stale}]),
                21137845: detail(
                    21137845, f"{GATE_PREFIX} (all bases)", WILDCARDS
                ),
            }
        )

        # When: harden runs against the payload-stale canonical.
        code, out = self.run_harden(store)

        # Then: BLOCKED with the parameter DIFF printed (stored 2 vs
        # intended 0) — NO DELETE fired, the legacy fallback stays in
        # the store, no HARDENED claim.
        self.assertEqual(code, 1)
        writes = self.writes(store)
        self.assertEqual(
            list(writes), [("PATCH", f"{REPO_ROOT}/rulesets/77")]
        )
        self.assertIn(21137845, store.rulesets)
        self.assertIn("parameters differ from the intended payload", out)
        self.assertIn("required_approving_review_count", out)
        self.assertIn("stored 2, intended 0", out)
        self.assertIn("thread 3834590324", out)
        self.assertIn("LEFT IN PLACE", out)
        self.assertNotIn("HARDENED", out)
        self.assertNotIn("DELETED redundant", out)

    def test_extra_rule_beside_the_gate_blocks_the_deletes(self):
        # Given: the stored canonical's pull_request rule is EXACTLY
        # the intended payload, but an EXTRA rule survived the PATCH
        # beside it (a stale required-linear-history rule, say) — the
        # round-16 verification compared nothing about the rule list,
        # so the DELETEs would strip the fallbacks beside a canonical
        # that keeps enforcing the extra rule.
        store = NoOpPatchStore(
            {
                77: payload_detail(
                    [GATE_RULE,
                     {"type": "required_linear_history",
                      "parameters": {}}]
                ),
                21137845: detail(
                    21137845, f"{GATE_PREFIX} (all bases)", WILDCARDS
                ),
            }
        )

        # When: harden runs against the extra-rule canonical.
        code, out = self.run_harden(store)

        # Then: BLOCKED naming the RULE LIST shape (two rules, one of
        # them pull_request, beside the intended EXACTLY ONE) — no
        # DELETE, fallback retained, no HARDENED claim.
        self.assertEqual(code, 1)
        self.assertEqual(
            list(self.writes(store)),
            [("PATCH", f"{REPO_ROOT}/rulesets/77")],
        )
        self.assertIn(21137845, store.rulesets)
        self.assertIn("RULE LIST holds 2 rule(s)", out)
        self.assertIn("EXACTLY ONE pull_request rule", out)
        self.assertIn("thread 3834590324", out)
        self.assertIn("LEFT IN PLACE", out)
        self.assertNotIn("HARDENED", out)
        self.assertNotIn("DELETED redundant", out)

    def test_exact_payload_licenses_the_deletes(self):
        # Given: the stored canonical's rule list and parameters are
        # EXACTLY what the guard installs (even though the PATCH was a
        # transport no-op — the stored shape was already right), with
        # a redundant legacy fallback beside it.
        store = NoOpPatchStore(
            {
                77: payload_detail([GATE_RULE]),
                21137845: detail(
                    21137845, f"{GATE_PREFIX} (all bases)", WILDCARDS
                ),
            }
        )

        # When: harden runs.
        code, out = self.run_harden(store)

        # Then: the payload check passes and the DELETEs PROCEED —
        # exactly one gate ruleset survives and HARDENED verifies (the
        # payload comparison blocks ONLY a real difference).
        self.assertEqual(code, 0)
        self.assertNotIn(21137845, store.rulesets)
        self.assertIn("DELETED redundant ruleset id 21137845", out)
        self.assertIn("HARDENED refs/heads/dev", out)
        self.assertNotIn("parameters differ", out)
        self.assertNotIn("RULE LIST holds", out)


if __name__ == "__main__":
    unittest.main()
