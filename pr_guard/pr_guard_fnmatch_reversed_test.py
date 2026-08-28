"""pr_guard fnmatch reversed-range class tests (PR #45 round 2).

Thread 3835793219 (P2): round 1 compiled a REVERSED range (left >
right) to NOTHING — both endpoints dropped — but Ruby 3.4.4 dir.c's
bracket() compares the test char against EACH ENDPOINT LITERALLY
(memcmp(t1,s,r) / memcmp(t2,s,r2) in the range branch) BEFORE the
interval guards `c1 < left -> continue` / `c1 > right -> continue`,
which no char survives when left > right — so [m-0] matches exactly
'm' and '0', never the interval between. The drop made [!m-0] read
as [^/]ain, so the include `refs/heads/[!m-0]ain` was reported as
COVERING main while Ruby/GitHub — excluding 'm' — never applies
that ruleset to main: gate_covers could certify a merge without the
claimed server-side gate.

fnmatch_class now compiles a reversed range to its two endpoint
LITERALS, so the translator agrees with Ruby in both the positive
and negated direction.

No network: pure translation tests through github_fnmatch and
gate_covers.

Run: cd .omo/start-work && python3 -m unittest pr_guard_fnmatch_reversed_test -v
"""

import unittest

from . import pr_guard_fnmatch
from . import pr_guard_rulesets
from .pr_guard_rulesets_test import gate_ruleset


class ReversedRangeClassTests(unittest.TestCase):
    def test_reversed_range_matches_exactly_its_endpoints(self):
        # Given: Ruby 3.4.4 File.fnmatch(..., FNM_PATHNAME) treats
        # [m-0] as the two endpoint members 'm' and '0' (thread
        # 3835793219's citation: bracket()'s endpoint memcmps run
        # before the interval guards, and with left > right no char
        # survives the guards) — chars BETWEEN the endpoints ('5',
        # between '0' and 'm' codepoint-wise) and OUTSIDE them ('Z')
        # are never members; the round-1 drop matched nothing.
        # When: the translator judges reversed-range pairs, both
        # negation prefixes, and endpoint/between/outside chars.
        # Then: it agrees with Ruby — the positive class matches
        # exactly 'm' and '0'; the NEGATED class refuses exactly
        # 'm' and '0', admits the between/outside chars, and still
        # never matches a ref across '/'.
        for value, pattern in (
            ("refs/heads/main", "refs/heads/[m-0]ain"),
            ("refs/heads/0ain", "refs/heads/[m-0]ain"),
            ("refs/heads/Zain", "refs/heads/[!m-0]ain"),
            ("refs/heads/Zain", "refs/heads/[^m-0]ain"),
            ("refs/heads/5ain", "refs/heads/[!m-0]ain"),
            ("refs/heads/-ain", "refs/heads/[!m-0]ain"),
        ):
            self.assertTrue(
                pr_guard_fnmatch.github_fnmatch(value, pattern),
                (value, pattern),
            )
        for value, pattern in (
            ("refs/heads/main", "refs/heads/[!m-0]ain"),
            ("refs/heads/main", "refs/heads/[^m-0]ain"),
            ("refs/heads/0ain", "refs/heads/[!m-0]ain"),
            ("refs/heads/Zain", "refs/heads/[m-0]ain"),
            ("refs/heads/5ain", "refs/heads/[m-0]ain"),
            ("refs/heads/release/x", "refs/heads/[!m-0]*"),
        ):
            self.assertFalse(
                pr_guard_fnmatch.github_fnmatch(value, pattern),
                (value, pattern),
            )

    def test_reversed_range_negated_include_does_not_cover_main(self):
        # Given: an active equipped gate whose INCLUDE names
        # refs/heads/[!m-0]ain — Ruby/GitHub excludes the endpoints
        # 'm' and '0', so the ruleset NEVER applies to main; the
        # round-1 translator read the class as [^/]ain, MATCHED
        # main, and gate_covers certified the merge without the
        # claimed server-side gate (thread 3835793219's exact
        # shape).
        # When: coverage is checked for main and a sibling the class
        # admits.
        # Then: main is NOT covered; the sibling still is.
        gate = gate_ruleset(include=("refs/heads/[!m-0]ain",))
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([gate], "main", "main")
        )
        self.assertIs(
            pr_guard_rulesets.gate_covers([gate], "Zain", "main"), gate
        )

    def test_reversed_range_positive_include_covers_main(self):
        # Given: an active equipped gate whose INCLUDE names
        # refs/heads/[m-0]ain — 'm' is an endpoint member, so the
        # pattern MATCHES refs/heads/main and the ruleset applies;
        # the round-1 drop made the class never-match, so the guard
        # refused a gate GitHub does apply.
        # When: coverage is checked for main and a non-endpoint
        # sibling.
        # Then: main IS covered; the sibling is not.
        gate = gate_ruleset(include=("refs/heads/[m-0]ain",))
        self.assertIs(
            pr_guard_rulesets.gate_covers([gate], "main", "main"), gate
        )
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([gate], "dev", "main")
        )

    def test_reversed_range_exclusion_excludes_the_ref(self):
        # Given: an active equipped gate including ~ALL while its
        # exclude names refs/heads/[m-0]ain — the reversed-range
        # class MATCHES 'm' (an endpoint), so the exclusion fires
        # for main exactly as it does in Ruby/GitHub.
        # When: coverage is checked for main and a sibling.
        # Then: main is NOT covered (the exclusion matches it); the
        # sibling still is.
        gate = gate_ruleset(
            include=("~ALL",),
            exclude=("refs/heads/[m-0]ain",),
        )
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([gate], "main", "main")
        )
        self.assertIs(
            pr_guard_rulesets.gate_covers([gate], "dev", "main"), gate
        )


if __name__ == "__main__":
    unittest.main()
