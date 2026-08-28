"""pr_guard harden migration tests (PR #41, threads 3833111358 +
3833144348/3833251666).

A repository configured by the parent version still runs the
OLD-named gate ruleset ('(all bases)', or the round-1 '(dev)'/
'(main)' base-parameterized form); looking up only the new
'(protected bases)' name misses it, POSTs a second ruleset beside it,
and GitHub then applies BOTH — the legacy wildcard keeps blocking
pushes to release and other PR-head branches. The harden lookup
matches every historical alias and MIGRATES the found ruleset (one
PATCH renames AND rescopes it; no POST). Threads 3833144348/
3833251666 (round 6): when SEVERAL rulesets match (new name AND
legacy aliases — e.g. a duplicate an older harden run created), the
canonical one takes the PATCH and every redundant other is DELETEd,
because GitHub enforces BOTH otherwise. No network: gh_rest is faked
with a mutable ruleset store, so the PATCH/DELETE effect on the
stored detail is asserted directly.

Run: cd .omo/start-work && python3 -m unittest pr_guard_rulesets_harden_test -v
"""

import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_rulesets
from .pr_guard_common import REPO_NAME, REPO_OWNER
from .pr_guard_rulesets_test import gate_ruleset

REPO_ROOT = f"repos/{REPO_OWNER}/{REPO_NAME}"
NEW_NAME = pr_guard_rulesets.GATE_RULESET_NAME
WILDCARDS = ["refs/heads/**", "refs/heads/**/*"]


def detail(ruleset_id: int, name: str, include: list[str]) -> dict:
    record = gate_ruleset(include=include)
    record["id"] = ruleset_id
    record["name"] = name
    return record


class FakeRulesetStore:
    """A mutable id->detail store behind a fake gh_rest: POST mints a
    new id, PATCH updates the stored detail, DELETE removes it, GET
    returns it — so the post-write verification re-reads what the
    write actually left."""

    def __init__(self, rulesets: dict[int, dict]):
        self.rulesets = rulesets
        self.calls: list[tuple[str, str, dict | None]] = []

    def gh_rest(self, method: str, path: str, body: dict | None = None):
        self.calls.append((method, path, body))
        if path.endswith("/pulls/39"):
            return {"base": {"ref": "dev"}}
        if path == REPO_ROOT:
            return {"default_branch": "main"}
        if "/rulesets?" in path:
            # Thread 3834666213: the list endpoint serves per_page=100
            # slices by ?page=N like the REST shape — a store bigger
            # than one page exercises the fetch's cursor follow.
            ids = list(self.rulesets)
            page = int(path.rsplit("page=", 1)[-1])
            return [
                {"id": rid} for rid in ids[(page - 1) * 100 : page * 100]
            ]
        if method == "POST" and path.endswith("/rulesets"):
            new_id = 900 + len(self.rulesets)
            stored = dict(body or {})
            stored["id"] = new_id
            self.rulesets[new_id] = stored
            return {"id": new_id}
        ruleset_id = int(path.rsplit("/", 1)[-1])
        if method == "DELETE":
            del self.rulesets[ruleset_id]
            return {}
        if method == "PATCH":
            self.rulesets[ruleset_id].update(body or {})
            return self.rulesets[ruleset_id]
        assert method == "GET", (method, path)
        return self.rulesets[ruleset_id]


class HardenMigrationTests(unittest.TestCase):
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

    def test_legacy_all_bases_ruleset_is_migrated_not_duplicated(self):
        # Given: the live ruleset still carries the parent version's
        # '(all bases)' name over the old wildcard pair (thread
        # 3833111358) — the new-name-only lookup would miss it.
        store = FakeRulesetStore(
            {21137845: detail(21137845, f"{pr_guard_rulesets.GATE_RULE_PREFIX} (all bases)", WILDCARDS)}
        )

        # When: harden runs against that repository.
        code, out = self.run_harden(store)

        # Then: ONE PATCH to the EXISTING id carrying the new name and
        # the narrowed protected-bases patterns — NO POST, so no
        # duplicate ruleset applies beside the migrated one — the
        # migration is announced, the stored detail is renamed and
        # rescoped, and HARDENED verifies.
        self.assertEqual(code, 0)
        writes = self.writes(store)
        self.assertEqual(list(writes), [("PATCH", f"{REPO_ROOT}/rulesets/21137845")])
        body = writes[("PATCH", f"{REPO_ROOT}/rulesets/21137845")]
        self.assertEqual(body["name"], NEW_NAME)
        self.assertEqual(
            body["conditions"]["ref_name"]["include"],
            ["refs/heads/main", "refs/heads/dev"],
        )
        self.assertEqual(store.rulesets[21137845]["name"], NEW_NAME)
        self.assertIn("MIGRATING legacy ruleset id 21137845", out)
        self.assertIn("resolution (all bases)'", out)
        self.assertIn("no POST, so no duplicate", out)
        self.assertIn("HARDENED refs/heads/dev", out)

    def test_legacy_dev_ruleset_is_migrated_not_duplicated(self):
        # Given: the round-1 base-parameterized name '(dev)' (thread
        # 3833111358's alias list — the PR #36 era hardened per base).
        store = FakeRulesetStore(
            {123: detail(123, f"{pr_guard_rulesets.GATE_RULE_PREFIX} (dev)", ["refs/heads/dev"])}
        )

        # When: harden runs.
        code, out = self.run_harden(store)

        # Then: PATCH of ruleset 123 to the new name/patterns, no POST.
        self.assertEqual(code, 0)
        writes = self.writes(store)
        self.assertEqual(list(writes), [("PATCH", f"{REPO_ROOT}/rulesets/123")])
        self.assertEqual(writes[("PATCH", f"{REPO_ROOT}/rulesets/123")]["name"], NEW_NAME)
        self.assertIn("MIGRATING legacy ruleset id 123", out)
        self.assertIn("resolution (dev)'", out)
        self.assertIn("HARDENED", out)

    def test_no_existing_ruleset_posts_the_new_one(self):
        # Given: a repository with NO gate ruleset at all.
        store = FakeRulesetStore({})

        # When: harden runs.
        code, out = self.run_harden(store)

        # Then: ONE POST carrying the new name and narrowed patterns,
        # no PATCH, no migration note — the ordinary first-harden path.
        self.assertEqual(code, 0)
        writes = self.writes(store)
        self.assertEqual(list(writes), [("POST", f"{REPO_ROOT}/rulesets")])
        body = writes[("POST", f"{REPO_ROOT}/rulesets")]
        self.assertEqual(body["name"], NEW_NAME)
        self.assertEqual(
            body["conditions"]["ref_name"]["include"],
            ["refs/heads/main", "refs/heads/dev"],
        )
        self.assertNotIn("MIGRATING", out)
        self.assertIn("HARDENED", out)

    def test_new_named_ruleset_still_patches_in_place(self):
        # Given: the current-name ruleset already exists (the ordinary
        # idempotent re-run, thread 3832660865).
        store = FakeRulesetStore(
            {77: detail(77, NEW_NAME, list(pr_guard_rulesets.PROTECTED_BASE_PATTERNS))}
        )

        # When: harden runs.
        code, out = self.run_harden(store)

        # Then: PATCH of the existing id, no POST, no migration note.
        self.assertEqual(code, 0)
        writes = self.writes(store)
        self.assertEqual(list(writes), [("PATCH", f"{REPO_ROOT}/rulesets/77")])
        self.assertNotIn("MIGRATING", out)
        self.assertIn("HARDENED", out)

    def test_legacy_alias_list_pins_the_history(self):
        # Given/When: the alias list is read. Then: it names exactly
        # the historical forms — '(all bases)' (PR #37-#39) and the
        # round-1 '(dev)'/'(main)' base-parameterized names.
        self.assertEqual(
            pr_guard_rulesets.LEGACY_GATE_RULESET_NAMES,
            (
                "pr-guard: required review thread resolution (all bases)",
                "pr-guard: required review thread resolution (dev)",
                "pr-guard: required review thread resolution (main)",
            ),
        )

    def test_new_and_legacy_rulesets_patch_one_delete_the_other(self):
        # Given: BOTH the new-name ruleset AND a legacy '(all bases)'
        # wildcard ruleset are active (threads 3833144348/3833251666 —
        # e.g. an older harden run POSTed the narrow one beside the
        # legacy one); GitHub applies BOTH, so leaving the legacy one
        # keeps blocking every PR-head push.
        store = FakeRulesetStore(
            {
                21137845: detail(
                    21137845,
                    f"{pr_guard_rulesets.GATE_RULE_PREFIX} (all bases)",
                    WILDCARDS,
                ),
                77: detail(
                    77, NEW_NAME,
                    list(pr_guard_rulesets.PROTECTED_BASE_PATTERNS),
                ),
            }
        )

        # When: harden runs against the duplicated repository.
        code, out = self.run_harden(store)

        # Then: the CANONICAL new-name ruleset takes the ONE PATCH
        # (even though the legacy one is listed first) and the legacy
        # ruleset is DELETEd — never a POST, and exactly one gate
        # ruleset survives in the store.
        self.assertEqual(code, 0)
        writes = self.writes(store)
        self.assertEqual(
            list(writes),
            [
                ("PATCH", f"{REPO_ROOT}/rulesets/77"),
                ("DELETE", f"{REPO_ROOT}/rulesets/21137845"),
            ],
        )
        self.assertEqual(
            writes[("PATCH", f"{REPO_ROOT}/rulesets/77")]["name"], NEW_NAME
        )
        self.assertEqual(
            writes[("PATCH", f"{REPO_ROOT}/rulesets/77")]["conditions"][
                "ref_name"
            ]["include"],
            ["refs/heads/main", "refs/heads/dev"],
        )
        self.assertNotIn(21137845, store.rulesets)
        self.assertIn("DELETED redundant ruleset id 21137845", out)
        self.assertIn("GitHub applies BOTH", out)
        self.assertIn("exactly one gate ruleset survives", out)
        self.assertIn("HARDENED", out)

    def test_two_legacy_rulesets_patch_one_delete_the_other(self):
        # Given: TWO legacy-named rulesets are active (a '(dev)' one
        # from the round-1 era beside an '(all bases)' wildcard from
        # the PR #37-#39 era — threads 3833144348/3833251666).
        store = FakeRulesetStore(
            {
                123: detail(
                    123,
                    f"{pr_guard_rulesets.GATE_RULE_PREFIX} (dev)",
                    ["refs/heads/dev"],
                ),
                456: detail(
                    456,
                    f"{pr_guard_rulesets.GATE_RULE_PREFIX} (all bases)",
                    WILDCARDS,
                ),
            }
        )

        # When: harden runs.
        code, out = self.run_harden(store)

        # Then: the first legacy match is MIGRATED (PATCHed to the new
        # name + narrowed patterns) and the second is DELETEd — one
        # PATCH, one DELETE, no POST, one survivor.
        self.assertEqual(code, 0)
        writes = self.writes(store)
        self.assertEqual(
            list(writes),
            [
                ("PATCH", f"{REPO_ROOT}/rulesets/123"),
                ("DELETE", f"{REPO_ROOT}/rulesets/456"),
            ],
        )
        self.assertEqual(store.rulesets[123]["name"], NEW_NAME)
        self.assertEqual(
            store.rulesets[123]["conditions"]["ref_name"]["include"],
            ["refs/heads/main", "refs/heads/dev"],
        )
        self.assertNotIn(456, store.rulesets)
        self.assertIn("MIGRATING legacy ruleset id 123", out)
        self.assertIn("DELETED redundant ruleset id 456", out)
        self.assertIn("HARDENED", out)

    def test_foreign_gh_repo_env_warns_loudly_in_harden(self):
        # Given: GH_REPO names an unrelated repository (thread
        # 3833073952) — harden's gh api paths are absolute and cannot
        # be redirected, but the operator must know.
        store = FakeRulesetStore({})
        out = io.StringIO()
        with (
            mock.patch.object(
                pr_guard_rulesets, "gh_rest", side_effect=store.gh_rest
            ),
            mock.patch.dict(os.environ, {"GH_REPO": "somebody/other-repo"}),
            redirect_stdout(out),
        ):
            code = pr_guard_rulesets.harden(39)

        # Then: the loud warning prints and harden still completes.
        self.assertEqual(code, 0)
        self.assertIn("WARNING: GH_REPO=somebody/other-repo", out.getvalue())
        self.assertIn("thread 3833073952", out.getvalue())
        self.assertIn("HARDENED", out.getvalue())


if __name__ == "__main__":
    unittest.main()
