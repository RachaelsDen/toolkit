"""pr_guard fnmatch subsequent-hyphen class tests (PR #45 round 1).

Thread 3835760159 (P2): a negated class whose body carries a hyphen
BEYOND the first member — `refs/heads/[!-0--]ain` — passed the
round-2 leading-hyphen arm but every LATER hyphen still landed raw in
the emission, so Python re paired `0--` as a range and raised
`re.PatternError: bad character range 0--` out of github_fnmatch: a
configured include/exclusion CRASHED gate_covers and aborted
harden/merge instead of evaluating the gate. Ruby 3.4.4's bracket()
parses the body member-by-member — a '-' is a range OPERATOR only
with a member on BOTH sides (the body `-0--` is the literal '-',
the reversed range 0-to-'-', then another literal '-'), so
FNM_PATHNAME matches `refs/heads/main` against
`refs/heads/[!-0--]ain` and the exclusion genuinely excludes it.

fnmatch_class parses the body that way (leading/trailing/doubled
hyphens are literals; every emitted token is escaped), so the
pathological shapes COMPILE and agree with Ruby instead of raising.
Round 2 (thread 3835793219) corrected this suite's endpoint rows:
the reversed range 0-to-'-' matches its two ENDPOINTS ('0' and '-'),
so [!-0--] excludes '-' AND '0', and the positive [0--] matches
exactly '0' and '-' — round 1 had pinned both as endpoint-blind.

No network: pure translation tests through github_fnmatch and
gate_covers.

Run: cd .omo/start-work && python3 -m unittest pr_guard_fnmatch_hyphen_test -v
"""

import unittest

from . import pr_guard_fnmatch
from . import pr_guard_rulesets
from .pr_guard_rulesets_test import gate_ruleset


class SubsequentHyphenClassTests(unittest.TestCase):
    def test_subsequent_hyphens_compile_and_match_ruby(self):
        # Given: Ruby 3.4.4 File.fnmatch(..., FNM_PATHNAME) matches
        # refs/heads/main against refs/heads/[!-0--]ain (thread
        # 3835760159's citation) — bracket() reads the body as
        # literal '-', then the reversed range 0-to-'-' (which
        # consumes BOTH trailing hyphens and contributes its two
        # endpoint members '0' and '-' per thread 3835793219), so
        # the negated class excludes '-' and '0' and matches m; the
        # round-2 emission [^-/0--] raised re.PatternError instead.
        # When: the translator judges the pathological pairs, both
        # negation prefixes, the trailing-hyphen body, and the
        # reversed-RANGE body ([!--z]: a real range '-', 'z',
        # negated — so main does NOT match it).
        # Then: no PatternError is raised, and it agrees with Ruby —
        # the negated classes exclude exactly '-' and '0' (and never
        # '/'), never crash, and the reversed-range positive class
        # [0--] matches exactly its endpoints '0' and '-'.
        for value, pattern in (
            ("refs/heads/main", "refs/heads/[!-0--]ain"),
            ("refs/heads/main", "refs/heads/[^-0--]ain"),
            ("refs/heads/main", "refs/heads/[!-x--]ain"),
            ("refs/heads/Zain", "refs/heads/[!--0]ain"),
            ("refs/heads/0ain", "refs/heads/[0--]ain"),
            ("refs/heads/-ain", "refs/heads/[0--]ain"),
        ):
            self.assertTrue(
                pr_guard_fnmatch.github_fnmatch(value, pattern),
                (value, pattern),
            )
        for value, pattern in (
            ("refs/heads/-ain", "refs/heads/[!-0--]ain"),
            ("refs/heads/0ain", "refs/heads/[!-0--]ain"),
            ("refs/heads/release/x", "refs/heads/[!-0--]*"),
            ("refs/heads/main", "refs/heads/[0--]ain"),
            ("refs/heads/Zain", "refs/heads/[0--]ain"),
            ("refs/heads/main", "refs/heads/[!--z]ain"),
        ):
            self.assertFalse(
                pr_guard_fnmatch.github_fnmatch(value, pattern),
                (value, pattern),
            )

    def test_ordinary_ranges_stay_ranges(self):
        # Given: the member-pair parser must not collapse the
        # ORDINARY forward ranges — `[a-z]`/`[--z]` (a hyphen-member
        # starting a range in Ruby: c1='-', operator '-', c2='z') —
        # into escaped literals, or a gate's `[a-z]ain` exclusion
        # would stop excluding the lowercase refs Ruby excludes.
        # When: the translator judges forward-range pairs.
        # Then: ranges still span their codepoint interval —
        # `[a-z]ain` matches main but not Main, and `[--z]ain`
        # (0x2D..0x7A) matches -ain, 0ain, Zain, .ain, and main
        # alike while a char outside the interval fails.
        for value, pattern in (
            ("refs/heads/main", "refs/heads/[a-z]ain"),
            ("refs/heads/-ain", "refs/heads/[--z]ain"),
            ("refs/heads/0ain", "refs/heads/[--z]ain"),
            ("refs/heads/Zain", "refs/heads/[--z]ain"),
            ("refs/heads/.ain", "refs/heads/[--z]ain"),
        ):
            self.assertTrue(
                pr_guard_fnmatch.github_fnmatch(value, pattern),
                (value, pattern),
            )
        for value, pattern in (
            ("refs/heads/Main", "refs/heads/[a-z]ain"),
            ("refs/heads/1ain", "refs/heads/[a-z]ain"),
            ("refs/heads/{ain", "refs/heads/[--z]ain"),
        ):
            self.assertFalse(
                pr_guard_fnmatch.github_fnmatch(value, pattern),
                (value, pattern),
            )

    def test_subsequent_hyphen_exclusion_excludes_the_ref(self):
        # Given: an active equipped gate including ~ALL while its
        # exclude names refs/heads/[!-0--]ain — GitHub's server-side
        # ruleset excludes main (thread 3835760159's exact shape: the
        # old translator RAISED re.PatternError from gate_covers, so
        # the harden/merge path aborted instead of evaluating the
        # gate at all).
        gate = gate_ruleset(
            include=("~ALL",),
            exclude=("refs/heads/[!-0--]ain",),
        )
        # When: coverage is checked for main and a sibling ref.
        # Then: the gate EVALUATES — main is NOT covered (the
        # exclusion matches it), and the sibling still is.
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([gate], "main", "main")
        )
        self.assertIs(
            pr_guard_rulesets.gate_covers([gate], "dev", "main"), gate
        )


if __name__ == "__main__":
    unittest.main()
