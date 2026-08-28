"""GitHub's pathname-aware ruleset-pattern translation.

Split from pr_guard_rulesets.py at the 250 pure-LOC ceiling (PR #41
round 6, thread 3833251667's split family): the pure
pattern->regex translation block moved out so the ruleset module had
headroom for the all-legacy-migration harden fix (threads
3833144348/3833251666). Pure code, heavily unit-tested through
pr_guard_rulesets.gate_covers/ref_matches.

PR #41 round 18 (thread 3834666213's split headroom): ref_matches —
the pure include/exclude pattern->bool predicate gate_covers and
harden consume — moved here from pr_guard_rulesets so the ruleset
module had room for the paginated ruleset fetch without crossing the
ceiling; pr_guard_rulesets re-exports it, so every existing import
keeps resolving.

PR #43 round 1 (threads 3835653117/3835653120): outside a character
class a backslash now ESCAPES the next character (a trailing
backslash is end-of-pattern), and a bare-negation class [!]/[^]
compiles to any-one-char-except-'/' instead of a never-match — both
verified against Ruby 3.4.4 dir.c (fnmatch_helper's UNESCAPE/ISEND
and bracket()'s ok==not empty-body rule).

PR #43 round 2 (thread 3835714793): a '-' that STARTS a negated
class body is a LITERAL member in Ruby (bracket()'s not_first rule —
a range needs a preceding member), so folding the '/' exclusion in
BEFORE it turned that hyphen into a Python RANGE operator
([!-x] -> [^/-x] swallows every lowercase letter) and a ~ALL gate
with the exclusion `refs/heads/[!-x]ain` was certified over main
while Ruby's FNM_PATHNAME matches it. The '/' fold now lands AFTER a
leading hyphen: [^-/x] keeps both members literal.

PR #45 round 1 (thread 3835760159): the round-2 leading-hyphen arm
left SUBSEQUENT hyphens raw, so `refs/heads/[!-0--]ain` compiled to
`[^-/0--]` and Python re raised PatternError (bad character range
0--) — a configured include/exclusion CRASHED gate_covers instead of
evaluating. fnmatch_class now parses the body the way Ruby's
bracket() does — a '-' is a range OPERATOR only with a member on
BOTH sides (leading/trailing hyphens are literals) and every emitted
token is escaped for Python — so the pathological class compiles and
matches main exactly as Ruby 3.4.4's FNM_PATHNAME does.

PR #45 round 2 (thread 3835793219): round 1 DROPPED a reversed
range's both endpoints as never-matching — but Ruby 3.4.4 dir.c's
bracket() compares the test char against EACH ENDPOINT LITERALLY
(memcmp(t1,s)/memcmp(t2,s)) BEFORE the interval guards `c1 < left`
and `c1 > right`, which no char survives when left > right — so
[m-0] matches exactly 'm' and '0', never the interval between. A
reversed range now compiles to its two endpoint LITERALS, closing
the [!m-0]-shaped bypass: the include `refs/heads/[!m-0]ain` used to
translate to `[^/]ain`, matching (and certifying) main while
Ruby/GitHub excludes 'm' and never applies that ruleset to main.
"""

import re


# Thread 3827635802: GitHub ruleset patterns use PATHNAME-aware fnmatch
# — '*' does NOT cross '/', '?' matches one non-'/' char — while
# Python's fnmatch.fnmatch lets '*' span '/'.
# Thread 3828495569: '**' is recursive ONLY as a full segment in the
# trailing form '**/…' (verified against Ruby File.fnmatch with
# FNM_PATHNAME): a TERMINAL '**' stays within one segment, so
# 'refs/heads/**' does not cover 'refs/heads/release/x' — the
# recursive include is 'refs/heads/**/*' (or 'refs/heads/**/…').
def github_fnmatch(value: str, pattern: str) -> bool:
    return re.fullmatch(github_fnmatch_regex(pattern), value) is not None


def github_fnmatch_regex(pattern: str) -> str:
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if (
            char == "*"
            and pattern.startswith("**", i)
            and (i == 0 or pattern[i - 1] == "/")
        ):
            if i + 2 < len(pattern) and pattern[i + 2] == "/":
                # Recursive segment '**/' — zero or more whole segments.
                parts.append(r"(?:[^/]+/)*")
                i += 3
                continue
            # Terminal whole-segment '**' — one segment, like '*'.
            parts.append("[^/]*")
            i += 2
            continue
        if char == "*":
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        elif char == "\\" and i + 1 < len(pattern):
            # Thread 3835653117 (PR #43): outside a class the
            # backslash ESCAPES the next char — Ruby 3.4.4 dir.c's
            # fnmatch_helper reads every ordinary pattern char
            # through UNESCAPE(p), so `refs/heads/\main` matches
            # `refs/heads/main` and an exclusion `refs/heads/foo\*bar`
            # matches the literal `foo*bar` (the escaped star is NOT
            # a glob; an escaped `[` starts no class).
            parts.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        elif char == "\\":
            # Thread 3835653117: a TRAILING backslash is END-OF-
            # PATTERN (dir.c: ISEND fires after UNESCAPE advances
            # past it) — it matches nothing, so drop it
            # (`refs/heads/main\` behaves as `refs/heads/main`).
            i += 1
            continue
        elif char == "[":
            end = fnmatch_class_end(pattern, i)
            if end == -1:
                parts.append(re.escape(char))
            else:
                parts.append(fnmatch_class(pattern[i + 1 : end]))
                i = end
        else:
            parts.append(re.escape(char))
        i += 1
    return "".join(parts)


# Thread 3828735203: a naive find(']') terminates the class at an
# ESCAPED ']' (e.g. '[a\]b]' — Ruby File.fnmatch keeps scanning), so
# the body was mis-split and a gate could be certified for a ref
# GitHub does not cover. Scan honoring backslash escapes. A ']' right
# after '[' (or the '!'/'^' negation prefix) is NOT literal content in
# Ruby (thread 3828914090) — it terminates an empty class there, which
# fnmatch_class compiles to a never-match.
def fnmatch_class_end(pattern: str, start: int) -> int:
    i = start + 1
    if i < len(pattern) and pattern[i] in "!^":
        i += 1
    while i < len(pattern):
        if pattern[i] == "\\":
            i += 2
            continue
        if pattern[i] == "]":
            return i
        i += 1
    return -1


# Thread 3828399592: GitHub documents Ruby File.fnmatch semantics, where
# a class negates with a LEADING '!' — passed through unchanged, Python
# re reads '[!m]' as the literal set {'!', 'm'} and a 'main' gate would
# match where GitHub's does not. Thread 3828643308: Ruby accepts '^' as
# a negation prefix too (verified: File.fnmatch('refs/heads/[^m]*',
# 'refs/heads/main', FNM_PATHNAME) is false) — BOTH prefixes negate; a
# literal '!' or '^' must be backslash-escaped. Thread 3828914090: a
# ']' directly after '[' (or the negation prefix) TERMINATES an empty
# class — 'refs/heads/[]a]' matches neither 'a' nor ']' (verified
# against Ruby 3.4.4), so an empty class compiles to a never-match;
# thread 3835653120 (PR #43): the BARE-NEGATION body compiles to
# any-one-char-except-'/'. Backslash escapes the next char. Thread
# 3828495572: under FNM_PATHNAME a class NEVER matches '/' — a
# negated class folds '/' into the negated set, a positive class (whose
# set or RANGE may contain '/') takes a '(?![/])' lookahead guard.
# Thread 3835760159 (PR #45 round 1): the body is parsed with Ruby
# bracket()'s member rule — read ONE member (backslash escape
# honored), then a '-' is a RANGE OPERATOR only when a member FOLLOWS
# it (not the class-terminating ']', not end-of-body); every other
# hyphen (leading, trailing, doubled) is a LITERAL member, so no
# emitted '-' can pair in Python as an operator the pattern did not
# intend and the pathological [!-0--] shape compiles instead of
# raising re.PatternError. Thread 3835793219 (PR #45 round 2): a
# REVERSED range (left > right, e.g. m to 0) matches EXACTLY its two
# ENDPOINTS in Ruby 3.4.4 — dir.c's bracket() memcmps the test char
# against each endpoint literally BEFORE the interval guards, which
# no char survives when left > right — so it compiles to the two
# endpoint LITERALS, never dropped: the round-1 drop made [!m-0]
# over-broad ([^/]ain matched main) and certified gates Ruby/GitHub
# does not apply; the empty-memberset fallback below stays only as
# the fail-closed invariant (every parse path now emits a member).
def fnmatch_class(body: str) -> str:
    negated = body[:1] in {"!", "^"}
    if body == "":
        return r"(?!)"
    if negated and len(body) == 1:
        # Thread 3835653120 (PR #43): a bare-negation class [!]/[^]
        # matches ANY single char — Ruby 3.4.4 dir.c's bracket()
        # returns success when ok(0) != not(1) over an EMPTY body, so
        # `refs/heads/*[!]` matches `refs/heads/main`. Under
        # FNM_PATHNAME the class still never matches '/' (ISEND(s)
        # fires before bracket() is consulted) — hence [^/], the
        # empty-POSITIVE-class counterpart above stays never-match
        # (ok==not over an empty body).
        return r"[^/]"
    if negated:
        body = body[1:]
    members: list[str] = []
    i = 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            char = body[i + 1]
            i += 2
        else:
            char = body[i]
            i += 1
        if (
            i < len(body)
            and body[i] == "-"
            and i + 1 < len(body)
            and body[i + 1] != "]"
        ):
            j = i + 1
            if body[j] == "\\" and j + 1 < len(body):
                right = body[j + 1]
                j += 2
            else:
                right = body[j]
                j += 1
            if ord(char) <= ord(right):
                members.append(f"{re.escape(char)}-{re.escape(right)}")
            else:
                # Thread 3835793219: REVERSED range — Ruby matches the
                # two endpoints literally and nothing between.
                members.append(re.escape(char))
                members.append(re.escape(right))
            i = j
        else:
            members.append(re.escape(char))
    joined = "".join(members)
    if not joined:
        return r"[^/]" if negated else r"(?!)"
    if negated:
        return f"[^/{joined}]"
    return f"(?![/])[{joined}]"


# Moved from pr_guard_rulesets at the PR #41 round-18 split (thread
# 3834666213's headroom): the pure ref-pattern predicate every
# include/exclude decision funnels through — exact refs, GitHub's
# '~ALL' and '~DEFAULT_BRANCH' tokens, and fnmatch globs.
def ref_matches(pattern: str, ref: str, default: str) -> bool:
    if pattern == f"refs/heads/{ref}":
        return True
    # Thread 3828914098: '~ALL' is GitHub's every-ref token — it must
    # count in BOTH the exclude and the include direction (an exclude
    # of ~ALL shields every ref from the ruleset).
    if pattern == "~ALL":
        return True
    if pattern == "~DEFAULT_BRANCH" and ref == default:
        return True
    return github_fnmatch(f"refs/heads/{ref}", pattern)
