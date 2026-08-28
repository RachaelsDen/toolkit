"""pr_guard harden verify-before-delete tests (PR #41 round 7, thread
3833360207).

A canonical PATCH can succeed at the transport level and still leave
the stored ruleset bypassable, inactive, or mis-scoped — the exact
cases the post-write GET exists to detect. The old order DELETEd
every redundant legacy gate before that verification, so the later
BLOCKED left the repository with NO working gate. The verification
now runs FIRST: a broken canonical fails hard with the discrepancy
printed and every fallback retained; the DELETEs proceed only after a
healthy canonical verifies. No network: the shared FakeRulesetStore
from .pr_guard_rulesets_harden_test backs the gh_rest fake.

Thread 3833671117 (PR #41 round 9): coverage alone would BLESS an
OVER-BROAD canonical — a transport-successful PATCH can leave the
stored includes as the legacy WILDCARD pair, which covers main AND
dev (so the coverage checks pass and `uncovered` stays empty) while
the DELETE loop removes every fallback and the wildcard gate stays
the ONLY gate: release/feature/remediation heads remain merge-only
and PR-head review-fix pushes are rejected. The stored scope must be
EXACTLY the intended configuration — include list equal to
PROTECTED_BASE_PATTERNS, exclude list empty — or the DELETEs are
blocked with the offending patterns named. Thread 3833762329's
TARGET invariant lives in pr_guard_rulesets_target_test (PR #41
round 10 split of this file at the 250 pure-LOC ceiling).

Run: cd .omo/start-work && python3 -m unittest pr_guard_rulesets_verify_test -v
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

NEW_NAME = pr_guard_rulesets.GATE_RULESET_NAME
GATE_PREFIX = pr_guard_rulesets.GATE_RULE_PREFIX


class NoOpPatchStore(FakeRulesetStore):
    # Thread 3833360207's failure shape: the PATCH is accepted at the
    # transport level (recorded, exits 0) but the STORED ruleset is
    # unchanged — still mis-scoped for the base — so only the
    # post-write GET detects it.
    def gh_rest(self, method, path, body=None):
        if method == "PATCH":
            self.calls.append((method, path, body))
            return self.rulesets[int(path.rsplit("/", 1)[-1])]
        return super().gh_rest(method, path, body)


class VerifyBeforeDeleteTests(unittest.TestCase):
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

    def test_broken_canonical_keeps_the_legacy_fallbacks(self):
        # Given: the canonical new-name ruleset sits beside a legacy
        # '(all bases)' wildcard one, and the PATCH is a transport
        # no-op — the stored canonical stays MIS-SCOPED (include only
        # refs/heads/main while harden runs against dev).
        store = NoOpPatchStore(
            {
                77: detail(77, NEW_NAME, ["refs/heads/main"]),
                21137845: detail(
                    21137845, f"{GATE_PREFIX} (all bases)", WILDCARDS
                ),
            }
        )

        # When: harden runs against the duplicated-but-broken repo.
        code, out = self.run_harden(store)

        # Then: BLOCKED with the DISCREPANCY printed (enforcement,
        # bypass actors, include/exclude, the uncovered ref) — and NO
        # DELETE ever fired: the legacy fallback stays in the store,
        # so the broken canonical is never the only gate; no HARDENED
        # claim.
        self.assertEqual(code, 1)
        writes = self.writes(store)
        self.assertEqual(
            list(writes), [("PATCH", f"{REPO_ROOT}/rulesets/77")]
        )
        self.assertIn(21137845, store.rulesets)
        self.assertIn("did not verify after the write", out)
        self.assertIn("discrepancy:", out)
        self.assertIn("enforcement=", out)
        self.assertIn("bypass_actors=", out)
        self.assertIn("refs/heads/dev is NOT covered", out)
        self.assertIn("LEFT IN PLACE", out)
        self.assertIn("thread 3833360207", out)
        self.assertIn("DO NOT merge on this gate", out)
        self.assertNotIn("HARDENED", out)
        self.assertNotIn("DELETED redundant", out)

    def test_inactive_stored_canonical_also_keeps_the_fallbacks(self):
        # Given: the stored canonical came back DISABLED (the second
        # broken shape the finding names — inactive) even though the
        # PATCH body requested active.
        broken = gate_ruleset(include=list(
            pr_guard_rulesets.PROTECTED_BASE_PATTERNS
        ))
        broken["id"] = 77
        broken["name"] = NEW_NAME
        broken["enforcement"] = "disabled"
        store = NoOpPatchStore(
            {
                77: broken,
                21137845: detail(
                    21137845, f"{GATE_PREFIX} (all bases)", WILDCARDS
                ),
            }
        )

        # When: harden runs.
        code, out = self.run_harden(store)

        # Then: same fail-hard shape — discrepancy printed (naming
        # enforcement='disabled'), no DELETE, fallback retained.
        self.assertEqual(code, 1)
        self.assertEqual(
            list(self.writes(store)),
            [("PATCH", f"{REPO_ROOT}/rulesets/77")],
        )
        self.assertIn(21137845, store.rulesets)
        self.assertIn("enforcement='disabled'", out)
        self.assertIn("LEFT IN PLACE", out)
        self.assertNotIn("HARDENED", out)

    def test_canonical_covering_only_the_hardened_base_blocks_deletes(self):
        # Given: the transport-successful PATCH leaves the stored
        # canonical covering ONLY the base being hardened (dev) while a
        # legacy '(main)' fallback still gates main (thread 3833540908,
        # PR #41 round 8) — the OLD single-base verification PASSED
        # here, and the DELETE loop then removed the '(main)' fallback,
        # leaving main exposed under a HARDENED claim.
        store = NoOpPatchStore(
            {
                77: detail(77, NEW_NAME, ["refs/heads/dev"]),
                21137845: detail(
                    21137845, f"{GATE_PREFIX} (main)", ["refs/heads/main"]
                ),
            }
        )

        # When: harden runs against the dev-based PR.
        code, out = self.run_harden(store)

        # Then: BLOCKED naming the OTHER protected base (main) as the
        # uncovered one — NO DELETE fired, so the '(main)' fallback
        # stays in the store covering main while the canonical is
        # repaired; no HARDENED claim, no redundant removal.
        self.assertEqual(code, 1)
        writes = self.writes(store)
        self.assertEqual(list(writes), [("PATCH", f"{REPO_ROOT}/rulesets/77")])
        self.assertIn(21137845, store.rulesets)
        self.assertIn("refs/heads/main is NOT covered", out)
        self.assertIn("thread 3833540908", out)
        self.assertIn("EVERY protected base", out)
        self.assertIn("LEFT IN PLACE", out)
        self.assertNotIn("HARDENED", out)
        self.assertNotIn("DELETED redundant", out)

    def test_healthy_canonical_verifies_before_the_deletes(self):
        # Given: the ordinary duplicated repo — canonical new-name
        # ruleset beside a legacy wildcard, and a PATCH that STORES.
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

        # Then: PATCH first, then the verifying GET of the CANONICAL
        # (a detail GET strictly between the PATCH and the DELETE —
        # the pre-delete verification of thread 3833360207, widened to
        # EVERY protected base by thread 3833540908: a canonical
        # covering both main and dev is what licenses the DELETE),
        # then the DELETE, and HARDENED — exactly one gate survives.
        self.assertEqual(code, 0)
        seq = [(method, path) for method, path, _ in store.calls]
        patch_at = seq.index(("PATCH", f"{REPO_ROOT}/rulesets/77"))
        delete_at = seq.index(("DELETE", f"{REPO_ROOT}/rulesets/21137845"))
        verify_gets = [
            i
            for i, entry in enumerate(seq)
            if entry == ("GET", f"{REPO_ROOT}/rulesets/77")
            and patch_at < i < delete_at
        ]
        self.assertTrue(verify_gets)
        self.assertNotIn(21137845, store.rulesets)
        self.assertIn("DELETED redundant ruleset id 21137845", out)
        self.assertIn("HARDENED refs/heads/dev", out)


class ExactScopeTests(unittest.TestCase):
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

    def test_wildcard_survivor_blocks_the_deletes(self):
        # Given: the PATCH is a transport no-op and the stored
        # canonical's includes are still the legacy WILDCARD pair
        # (thread 3833671117) — the wildcards COVER main and dev, so
        # the round-8 coverage checks passed and `uncovered` stays
        # empty; a legacy '(all bases)' fallback sits beside it.
        store = NoOpPatchStore(
            {
                77: detail(77, NEW_NAME, WILDCARDS),
                21137845: detail(
                    21137845, f"{GATE_PREFIX} (all bases)", WILDCARDS
                ),
            }
        )

        # When: harden runs against the over-broad-but-covering repo.
        code, out = self.run_harden(store)

        # Then: BLOCKED naming the OFFENDING patterns themselves (set
        # equality with the protected bases failed) — NO DELETE fired,
        # so the legacy fallback stays beside the over-broad canonical
        # (deleting it would leave the wildcard the ONLY gate, keeping
        # every release/feature/remediation head merge-only); no
        # HARDENED claim.
        self.assertEqual(code, 1)
        writes = self.writes(store)
        self.assertEqual(list(writes), [("PATCH", f"{REPO_ROOT}/rulesets/77")])
        self.assertIn(21137845, store.rulesets)
        for pattern in WILDCARDS:
            self.assertIn(pattern, out)
        self.assertIn("OUTSIDE the protected bases", out)
        self.assertIn("thread 3833671117", out)
        self.assertIn("LEFT IN PLACE", out)
        self.assertIn("DO NOT merge on this gate", out)
        self.assertNotIn("HARDENED", out)
        self.assertNotIn("DELETED redundant", out)

    def test_stray_exclude_list_blocks_the_deletes(self):
        # Given: the stored includes are exactly the protected bases,
        # but a stale EXCLUDE of an unprotected ref survived the
        # transport-successful PATCH — coverage is unaffected (the
        # exclude shields no protected ref), so only the exact-scope
        # comparison catches it (thread 3833671117).
        stray = gate_ruleset(
            include=list(pr_guard_rulesets.PROTECTED_BASE_PATTERNS),
            exclude=["refs/heads/feature/x"],
        )
        stray["id"] = 77
        stray["name"] = NEW_NAME
        store = NoOpPatchStore(
            {
                77: stray,
                21137845: detail(
                    21137845, f"{GATE_PREFIX} (all bases)", WILDCARDS
                ),
            }
        )

        # When: harden runs.
        code, out = self.run_harden(store)

        # Then: BLOCKED naming the non-empty exclude list — no DELETE,
        # fallback retained, no HARDENED claim.
        self.assertEqual(code, 1)
        self.assertEqual(
            list(self.writes(store)),
            [("PATCH", f"{REPO_ROOT}/rulesets/77")],
        )
        self.assertIn(21137845, store.rulesets)
        self.assertIn("non-empty exclude list survived the write", out)
        self.assertIn("refs/heads/feature/x", out)
        self.assertIn("thread 3833671117", out)
        self.assertNotIn("HARDENED", out)
        self.assertNotIn("DELETED redundant", out)


if __name__ == "__main__":
    unittest.main()
