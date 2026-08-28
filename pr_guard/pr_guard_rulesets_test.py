"""pr_guard ruleset-coverage tests.

Split from pr_guard_test.py at the 250 pure-LOC ceiling (PR #37, thread
3828495567). No network: gate_covers/fnmatch translation are pure.

Run: cd .omo/start-work && python3 -m unittest pr_guard_rulesets_test -v
"""

import unittest

from . import pr_guard_rulesets


def gate_ruleset(
    enforcement="active",
    include=("refs/heads/dev",),
    exclude=(),
    bypass_actors=(),
    current_user_can_bypass="never",
    target="branch",
):
    return {
        "name": "gate",
        "enforcement": enforcement,
        "bypass_actors": list(bypass_actors),
        "current_user_can_bypass": current_user_can_bypass,
        "target": target,
        "rules": [
            {
                "type": "pull_request",
                "parameters": {
                    "required_review_thread_resolution": True
                },
            }
        ],
        "conditions": {
            "ref_name": {"include": list(include), "exclude": list(exclude)}
        },
    }


class GateCoverageTests(unittest.TestCase):
    def test_active_gate_on_exact_ref_counts(self):
        # Given: an active thread-resolution ruleset on refs/heads/dev.
        # When: coverage is checked for dev.
        # Then: the ruleset is returned.
        gate = gate_ruleset()
        self.assertIs(
            pr_guard_rulesets.gate_covers([gate], "dev", "main"), gate
        )

    def test_disabled_or_unequipped_rulesets_never_count(self):
        # Given: a disabled-but-equipped ruleset and an active ruleset
        # WITHOUT the thread-resolution parameter.
        # When: coverage is checked.
        # Then: None — enforcement must be active AND the rule present.
        self.assertIsNone(
            pr_guard_rulesets.gate_covers(
                [gate_ruleset(enforcement="disabled")], "dev", "main"
            )
        )
        unequipped = gate_ruleset()
        unequipped["rules"] = [{"type": "pull_request", "parameters": {}}]
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([unequipped], "dev", "main")
        )

    def test_bypassable_rulesets_never_count(self):
        # Given: equipped active rulesets granting a bypass — an
        # always-bypass actor entry, a pull_request-bypass entry, and a
        # viewer who can always bypass (thread 3827635805).
        # When: coverage is checked.
        # Then: None in every shape — a bypassable gate is no gate.
        self.assertIsNone(
            pr_guard_rulesets.gate_covers(
                [
                    gate_ruleset(
                        bypass_actors=[
                            {
                                "actor_id": 1,
                                "actor_type": "RepositoryRole",
                                "bypass_mode": "always",
                            }
                        ]
                    )
                ],
                "dev",
                "main",
            )
        )
        self.assertIsNone(
            pr_guard_rulesets.gate_covers(
                [
                    gate_ruleset(
                        bypass_actors=[
                            {
                                "actor_id": 2,
                                "actor_type": "Team",
                                "bypass_mode": "pull_request",
                            }
                        ]
                    )
                ],
                "dev",
                "main",
            )
        )
        self.assertIsNone(
            pr_guard_rulesets.gate_covers(
                [gate_ruleset(current_user_can_bypass="always")],
                "dev",
                "main",
            )
        )

    def test_default_branch_token_and_globs_cover(self):
        # Given: one ruleset on ~DEFAULT_BRANCH, one pathname-glob
        # ruleset. When: coverage is checked for main and release/x.
        # Then: both match through their patterns, dev matches neither.
        default_gate = gate_ruleset(include=("~DEFAULT_BRANCH",))
        glob_gate = gate_ruleset(include=("refs/heads/release/**",))
        self.assertIs(
            pr_guard_rulesets.gate_covers([default_gate], "main", "main"),
            default_gate,
        )
        self.assertIs(
            pr_guard_rulesets.gate_covers([glob_gate], "release/x", "main"),
            glob_gate,
        )
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([default_gate], "dev", "main")
        )

    def test_star_and_terminal_double_star_do_not_cross_slashes(self):
        # Given: GitHub's PATHNAME fnmatch (thread 3827635802) — active
        # equipped rulesets including refs/heads/* and refs/heads/**.
        # When: coverage is checked for slash-bearing and slash-free
        # refs. Then: '*' matches 'feature' but NOT 'release/x', and a
        # TERMINAL '**' is likewise single-segment (thread 3828495569,
        # verified against Ruby File.fnmatch FNM_PATHNAME — only the
        # trailing '**/…' form is recursive).
        single = gate_ruleset(include=("refs/heads/*",))
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([single], "release/x", "main")
        )
        self.assertIs(
            pr_guard_rulesets.gate_covers([single], "feature", "main"),
            single,
        )
        terminal = gate_ruleset(include=("refs/heads/**",))
        self.assertIs(
            pr_guard_rulesets.gate_covers([terminal], "feature", "main"),
            terminal,
        )
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([terminal], "release/x", "main")
        )
        # The recursive form covers single AND nested segments.
        recursive = gate_ruleset(include=("refs/heads/**/*",))
        self.assertIs(
            pr_guard_rulesets.gate_covers([recursive], "release/x", "main"),
            recursive,
        )
        self.assertIs(
            pr_guard_rulesets.gate_covers([recursive], "feature", "main"),
            recursive,
        )

    def test_excluded_ref_never_counts_even_when_included(self):
        # Given: an active equipped ruleset whose include is the
        # all-branches wildcard pair ('**' + '**/*') while its exclude
        # names refs/heads/dev (thread 3827503026).
        # When: coverage is checked for dev.
        # Then: None — exclude wins, the ref is NOT protected.
        broad = gate_ruleset(
            include=("refs/heads/**", "refs/heads/**/*"),
            exclude=("refs/heads/dev",),
        )
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([broad], "dev", "main")
        )
        # And a sibling ref still matches through the include.
        self.assertIs(
            pr_guard_rulesets.gate_covers([broad], "feature/x", "main"),
            broad,
        )

    def test_negated_character_class_uses_fnmatch_semantics(self):
        # Given: GitHub patterns follow Ruby File.fnmatch, where [!m]
        # negates (thread 3828399592) — a naive passthrough reads
        # Python re's literal set {'!', 'm'} and would wrongly match
        # 'main'. When: coverage is checked for main/dev.
        # Then: the negated class excludes 'main' but admits 'dev'.
        negated = gate_ruleset(include=("refs/heads/[!m]*",))
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([negated], "main", "main")
        )
        self.assertIs(
            pr_guard_rulesets.gate_covers([negated], "dev", "main"), negated
        )
        # And '^' negates exactly like '!' (thread 3828643308 — Ruby
        # File.fnmatch accepts both prefixes; a literal caret needs a
        # backslash escape).
        caret = gate_ruleset(include=("refs/heads/[^a]*",))
        self.assertIs(
            pr_guard_rulesets.gate_covers([caret], "zb", "main"), caret
        )
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([caret], "ab", "main")
        )
        escaped = gate_ruleset(include=("refs/heads/[\\^a]*",))
        self.assertIs(
            pr_guard_rulesets.gate_covers([escaped], "^b", "main"), escaped
        )
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([escaped], "zb", "main")
        )

    def test_classes_never_match_path_separators(self):
        # Given: FNM_PATHNAME classes exclude '/' (thread 3828495572) —
        # the naive `[^m]` translation consumed the '/' and falsely
        # certified 'refs/heads/release[!m]*' as covering release/x.
        # When: coverage is checked for the nested ref.
        # Then: None — the class refuses the separator, so the pattern
        # dies at the '/', exactly like Ruby File.fnmatch.
        crossing = gate_ruleset(include=("refs/heads/release[!m]*",))
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([crossing], "release/x", "main")
        )
        # And a positive class whose RANGE contains '/' is guarded too.
        span = gate_ruleset(include=("refs/heads/release[ -~]*",))
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([span], "release/x", "main")
        )
        self.assertIs(
            pr_guard_rulesets.gate_covers([span], "releases", "main"), span
        )

    def test_escaped_bracket_stays_inside_the_class(self):
        # Given: an escaped ']' in a class (thread 3828735203) — the
        # naive find(']') split '[a\]b]' after the backslash, so the
        # trailing '?' was misread and 'refs/heads/[a\]b]?' matched
        # 'refs/heads/a' where Ruby File.fnmatch refuses (the class
        # consumes 'a', leaving nothing for the mandatory '?').
        # When: coverage is checked.
        # Then: the class is the set {a, ], b}; single-char 'a' is
        # refused and two-char 'ab' is admitted.
        escaped = gate_ruleset(include=("refs/heads/[a\\]b]?",))
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([escaped], "a", "main")
        )
        self.assertIs(
            pr_guard_rulesets.gate_covers([escaped], "ab", "main"), escaped
        )

    def test_leading_bracket_terminates_an_empty_class(self):
        # Given: 'refs/heads/[]a]' (thread 3828914090) — a ']' directly
        # after '[' TERMINATES an empty class under Ruby FNM_PATHNAME
        # (verified: the pattern matches neither 'a' nor ']').
        # When: coverage is checked. Then: the empty class never
        # matches, so the ruleset covers nothing.
        empty = gate_ruleset(include=("refs/heads/[]a]",))
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([empty], "a", "main")
        )
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([empty], "]", "main")
        )

    def test_all_token_covers_every_ref_in_both_directions(self):
        # Given: GitHub's '~ALL' every-ref token (thread 3828914098) —
        # one ruleset whose include is ~ALL, one whose include is ~ALL
        # but whose exclude is also ~ALL. When: coverage is checked.
        # Then: include ~ALL covers any ref; exclude ~ALL shields every
        # ref even when the include names it (exclude wins).
        include_all = gate_ruleset(include=("~ALL",))
        self.assertIs(
            pr_guard_rulesets.gate_covers([include_all], "anything/x", "main"),
            include_all,
        )
        exclude_all = gate_ruleset(include=("~ALL",), exclude=("~ALL",))
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([exclude_all], "dev", "main")
        )

    def test_harden_include_list_covers_protected_bases_only(self):
        # Given: harden's default include list (thread 3829356731 — the
        # old wildcard pair gated EVERY branch, making PR head refs
        # merge-only so authors could not push review fixes; the live
        # ruleset 21137845 was rescoped to exactly this list).
        # Thread 3832660865 (PR #40 round 4): 'refs/heads/release/**'
        # was REMOVED — it matched release branches USED AS PR HEADS
        # (merge commit 1e6b9a4 records PR #35 coming from
        # release/m6-to-main), so the pull_request rule made review-fix
        # pushes to a release PR head impossible.
        # When: the list is matched against the protected bases and
        # against PR-head branch shapes.
        # Then: main/dev are covered and NOTHING else is — release
        # heads (PR #35's own shape) stay directly pushable, so a
        # release PR head can receive review fixes.
        patterns = list(pr_guard_rulesets.PROTECTED_BASE_PATTERNS)
        self.assertEqual(patterns, ["refs/heads/main", "refs/heads/dev"])
        gate = gate_ruleset(include=patterns)
        for base in ("main", "dev"):
            self.assertIsNotNone(
                pr_guard_rulesets.gate_covers([gate], base, "main")
            )
        for head in (
            "release/m6-to-main",
            "release/1.2",
            "feature/x",
            "remediation/pr39-guard-fixes",
            "bugfix",
        ):
            self.assertIsNone(
                pr_guard_rulesets.gate_covers([gate], head, "main"),
                f"a PR head refs/heads/{head} must stay directly "
                f"pushable (thread 3832660865)",
            )
            for pattern in patterns:
                self.assertFalse(
                    pr_guard_rulesets.ref_matches(pattern, head, "main"),
                    f"{pattern} must not match PR head refs/heads/{head}",
                )

    def test_harden_ruleset_name_matches_the_live_rescoped_ruleset(self):
        # Given: the live ruleset 21137845 was renamed when it was
        # rescoped to main/dev (thread 3832660865). When: harden's
        # idempotence lookup name is computed. Then: it equals the
        # live name exactly, so a re-run finds and PATCHes the EXISTING
        # ruleset instead of POSTing a duplicate beside it.
        self.assertEqual(
            pr_guard_rulesets.GATE_RULESET_NAME,
            "pr-guard: required review thread resolution "
            "(protected bases)",
        )


if __name__ == "__main__":
    unittest.main()
