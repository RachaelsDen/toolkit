"""pr_guard fnmatch-translation tests (PR #43 rounds 1-2).

Thread 3835653117 (P2): outside a character class a backslash
ESCAPES the next character, and a TRAILING backslash is
end-of-pattern — Ruby 3.4.4's File.fnmatch (dir.c) reads every
ordinary pattern char through UNESCAPE(p) and treats the position
past a trailing backslash as ISEND, so `refs/heads/\\main` matches
`refs/heads/main`, `refs/heads/foo\\*bar` matches the literal
`foo*bar`, and `refs/heads/main\\` behaves as `refs/heads/main`. The
translator used to emit the backslash ITSELF as a literal, so with
an include of ~ALL the exclude `refs/heads/\\main` never matched and
gate_covers certified main as covered where GitHub's server-side
ruleset excludes it (the guarded merge proceeded without the claimed
gate).

Thread 3835653120 (P2): a bare-negation class matches ANY single
character — dir.c's bracket() succeeds when ok(0) != not(1) over an
EMPTY body, so Ruby 3.4.4 File.fnmatch(..., FNM_PATHNAME) matches
`refs/heads/main` against `refs/heads/*[!]` — while the empty
POSITIVE class stays a never-match (ok==not over an empty body,
thread 3828914090's verified `[]a]`). The class still never matches
'/' under FNM_PATHNAME (ISEND(s) fires before bracket()), and the
'^' prefix (thread 3828643308) behaves identically. The translator
compiled `[!]` to a never-match, so an exclude of `refs/heads/*[!]`
falsely certified refs Ruby's gate excludes.

Thread 3835714793 (P2, PR #43 round 2): a '-' that STARTS a negated
class body is a LITERAL member in Ruby — bracket() forms a range only
when the hyphen has a PRECEDING member (not_first) — so Ruby 3.4.4
FNM_PATHNAME matches `refs/heads/[!-x]ain` against `refs/heads/main`
while the translator's '/'-fold-first compiled it to `[^/-x]`, where
'-' became a RANGE operator ('/'..'x' swallowed every lowercase
letter) and the exclusion read as NOT covering main: with an include
of ~ALL the guarded merge certified the base without the claimed
server-side gate. The fold now lands AFTER the hyphen ([^-/x]).

No network: pure translation tests through github_fnmatch and
gate_covers.

Run: cd .omo/start-work && python3 -m unittest pr_guard_fnmatch_test -v
"""

import unittest

from . import pr_guard_fnmatch
from . import pr_guard_rulesets
from .pr_guard_rulesets_test import gate_ruleset


class OutsideClassEscapeTests(unittest.TestCase):
    def test_backslash_escapes_the_next_character(self):
        # Given: Ruby 3.4.4 File.fnmatch(..., FNM_PATHNAME) matches
        # refs/heads/\main against refs/heads/main (thread
        # 3835653117's citation) — dir.c consumes the backslash and
        # compares the next char literally (UNESCAPE).
        # When: the translator judges the same pairs.
        # Then: it agrees — escaped metachars are LITERALS, and an
        # escaped star/question/bracket does NOT glob or open a
        # class.
        for value, pattern in (
            ("refs/heads/main", "refs/heads/\\main"),
            ("refs/heads/foo*bar", "refs/heads/foo\\*bar"),
            ("refs/heads/dev?", "refs/heads/dev\\?"),
            ("refs/heads/[a]", "refs/heads/\\[a]"),
            ("refs/heads/ma\\in", "refs/heads/ma\\\\in"),
        ):
            self.assertTrue(
                pr_guard_fnmatch.github_fnmatch(value, pattern),
                (value, pattern),
            )
        for value, pattern in (
            ("refs/heads/foobar", "refs/heads/foo\\*bar"),
            ("refs/heads/fooXbar", "refs/heads/foo\\*bar"),
            ("refs/heads/devx", "refs/heads/dev\\?"),
            ("refs/heads/a", "refs/heads/\\[a]"),
        ):
            self.assertFalse(
                pr_guard_fnmatch.github_fnmatch(value, pattern),
                (value, pattern),
            )

    def test_trailing_backslash_is_end_of_pattern(self):
        # Given: dir.c's ISEND fires after UNESCAPE advances past a
        # backslash with nothing behind it — a TRAILING backslash
        # behaves as end-of-pattern and matches nothing itself.
        # When: the translator judges trailing-backslash patterns.
        # Then: `refs/heads/main\` == `refs/heads/main`, the glob's
        # trailing backslash still stops at the segment, and no
        # extra character is ever required.
        self.assertTrue(pr_guard_fnmatch.github_fnmatch(
            "refs/heads/main", "refs/heads/main\\"
        ))
        self.assertTrue(pr_guard_fnmatch.github_fnmatch(
            "refs/heads/feature", "refs/heads/*\\"
        ))
        self.assertFalse(pr_guard_fnmatch.github_fnmatch(
            "refs/heads/release/x", "refs/heads/*\\"
        ))

    def test_escaped_exclusion_still_excludes_the_ref(self):
        # Given: an active equipped gate including ~ALL while its
        # exclude names refs/heads/\main — GitHub's server-side
        # ruleset excludes main (thread 3835653117's exact bypass
        # shape: the old translator read the backslash literally, so
        # the exclusion never matched and the guarded merge
        # certified the base without the claimed server-side gate).
        gate = gate_ruleset(
            include=("~ALL",), exclude=("refs/heads/\\main",)
        )
        # When: coverage is checked for main and a sibling ref.
        # Then: main is NOT covered (the exclusion matches), and the
        # sibling still is.
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([gate], "main", "main")
        )
        self.assertIs(
            pr_guard_rulesets.gate_covers([gate], "dev", "main"), gate
        )


class BareNegationClassTests(unittest.TestCase):
    def test_bare_negation_class_matches_any_single_character(self):
        # Given: Ruby 3.4.4 File.fnmatch(..., FNM_PATHNAME) matches
        # refs/heads/main against refs/heads/*[!] (thread
        # 3835653120's citation) — bracket() succeeds over the empty
        # negated body, and the class still never matches '/'.
        # When: the translator judges bare-negation patterns.
        # Then: [!] (and the '^' form) match any one char except
        # '/', ']' included; the empty POSITIVE class stays
        # never-match (thread 3828914090).
        for value, pattern in (
            ("refs/heads/main", "refs/heads/*[!]"),
            ("refs/heads/]", "refs/heads/[!]"),
            ("refs/heads/n", "refs/heads/[!]"),
            ("refs/heads/main", "refs/heads/*[^]"),
        ):
            self.assertTrue(
                pr_guard_fnmatch.github_fnmatch(value, pattern),
                (value, pattern),
            )
        for value, pattern in (
            ("refs/heads/release/x", "refs/heads/*[!]"),
            ("refs/heads/feature/x", "refs/heads/**[!]"),
            ("refs/heads/a", "refs/heads/[]a]"),
            ("refs/heads/]", "refs/heads/[]a]"),
        ):
            self.assertFalse(
                pr_guard_fnmatch.github_fnmatch(value, pattern),
                (value, pattern),
            )

    def test_bare_negation_exclusion_still_excludes_the_ref(self):
        # Given: an active equipped gate including ~ALL while its
        # exclude names refs/heads/*[!] — GitHub's server-side
        # ruleset excludes every one-segment ref (thread
        # 3835653120's bypass shape: the old never-match translation
        # certified refs Ruby's gate excludes).
        gate = gate_ruleset(
            include=("~ALL",), exclude=("refs/heads/*[!]",)
        )
        # When: coverage is checked for a one-segment ref and a
        # nested one.
        # Then: the one-segment ref is NOT covered; the nested ref
        # (whose '/' the class refuses) still is.
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([gate], "main", "main")
        )
        self.assertIs(
            pr_guard_rulesets.gate_covers(
                [gate], "release/x", "main"
            ),
            gate,
        )


class LeadingHyphenNegatedClassTests(unittest.TestCase):
    def test_leading_hyphen_in_negated_class_is_literal(self):
        # Given: Ruby 3.4.4 File.fnmatch(..., FNM_PATHNAME) matches
        # refs/heads/[!-x]ain against refs/heads/main (thread
        # 3835714793's citation) — dir.c's bracket() takes a '-'
        # with NO preceding member (not_first) as an ordinary
        # literal, so the class excludes exactly '-' and 'x' (and
        # never '/' under FNM_PATHNAME); the old '/'-fold-first
        # compiled [^/-x], a RANGE from '/' to 'x' that swallowed
        # every lowercase letter and read the exclusion as not
        # covering main.
        # When: the translator judges the leading-hyphen pairs, both
        # negation prefixes, and the hyphen-only body.
        # Then: it agrees with Ruby — the hyphen is a member, never
        # a range operator, and '/' stays excluded.
        for value, pattern in (
            ("refs/heads/main", "refs/heads/[!-x]ain"),
            ("refs/heads/main", "refs/heads/[^-x]ain"),
            ("refs/heads/n", "refs/heads/[!-]"),
            ("refs/heads/x", "refs/heads/[!-]"),
        ):
            self.assertTrue(
                pr_guard_fnmatch.github_fnmatch(value, pattern),
                (value, pattern),
            )
        for value, pattern in (
            ("refs/heads/-ain", "refs/heads/[!-x]ain"),
            ("refs/heads/xain", "refs/heads/[!-x]ain"),
            ("refs/heads/-", "refs/heads/[!-]"),
            ("refs/heads/release/x", "refs/heads/[!-]*"),
        ):
            self.assertFalse(
                pr_guard_fnmatch.github_fnmatch(value, pattern),
                (value, pattern),
            )

    def test_leading_hyphen_exclusion_excludes_the_ref(self):
        # Given: an active equipped gate including ~ALL while its
        # exclude names refs/heads/[!-x]ain — GitHub's server-side
        # ruleset excludes main (thread 3835714793's exact bypass
        # shape: the old range-reading translator returned false, so
        # the guarded merge certified the base without the claimed
        # server-side gate).
        gate = gate_ruleset(
            include=("~ALL",), exclude=("refs/heads/[!-x]ain",)
        )
        # When: coverage is checked for main and a sibling ref.
        # Then: main is NOT covered (the exclusion matches it), and
        # the sibling still is.
        self.assertIsNone(
            pr_guard_rulesets.gate_covers([gate], "main", "main")
        )
        self.assertIs(
            pr_guard_rulesets.gate_covers([gate], "dev", "main"), gate
        )


if __name__ == "__main__":
    unittest.main()
