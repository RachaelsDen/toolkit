"""The stored-ruleset verification findings for harden's pre-DELETE
gate (PR #41 round 31).

Split from pr_guard_rulesets.py at the 250 pure-LOC ceiling: the
ruleset module stood at 257 pure LOC, and the findings builder for
harden's post-write verification (threads 3833360207/3833540908/
3833671117/3833762329/3834590324 — the checks that must pass BEFORE
any redundant fallback ruleset is DELETEd) is a PURE dict-read
predicate with no gh surface, so it moved to this leaf sibling.
harden computes the stored values and the gate_covers-based
`uncovered` list (gate_covers stays in pr_guard_rulesets — the merge
act and pre-merge import it from there), passes them in, and fails
closed on any non-empty findings list.

Imports flow ONE way (rulesets -> rulesets_verify -> rules_payload).
"""

from .pr_guard_rules_payload import stored_payload_findings


# Threads 3833540908/3833671117/3833762329/3834590324 (carried from
# pr_guard_rulesets.harden): the pre-DELETE verification findings.
# `uncovered` (computed by the caller through gate_covers) names
# protected bases the stored canonical does NOT cover; the checks
# here add the stored TARGET ('branch' only — a tag/push-target
# ruleset gates nothing about pull requests), the exact-scope rule
# (includes == PROTECTED_BASE_PATTERNS as set equality, excludes
# empty — coverage alone blesses an OVER-BROAD canonical), and the
# stored RULE PAYLOAD (exactly one pull_request rule with exactly
# GATE_RULE's parameters — the single source the write sends and
# this comparison checks). Any finding blocks the fallback DELETEs
# with the discrepancy printed and every legacy gate left in place.
def stored_scope_findings(
    stored: dict,
    uncovered: list[str],
    stored_includes: list[str],
    stored_excludes: list[str],
    stored_target: str,
    protected_patterns: tuple[str, ...],
) -> list[str]:
    offenders = sorted(set(stored_includes) - set(protected_patterns))
    stray_excludes = sorted(stored_excludes)
    wrong_target = stored_target != "branch"
    payload = stored_payload_findings(stored)
    if not (uncovered or offenders or stray_excludes or wrong_target):
        return list(payload) if payload else []
    findings = [f"refs/heads/{name} is NOT covered" for name in uncovered]
    if wrong_target:
        # Thread 3833762329: ref conditions say nothing about the
        # ruleset's TARGET — a same-named ruleset with target
        # 'tag'/'push' passes every include/exclude check while
        # gating NOTHING about pull requests on branches, and the
        # DELETEs would strip the real fallbacks.
        findings.append(
            f"the stored TARGET is {stored_target!r}, not 'branch' — "
            f"a ruleset targeting tags or pushes gates NOTHING "
            f"about pull requests on branches (thread 3833762329)"
        )
    if offenders:
        findings.append(
            f"include patterns OUTSIDE the protected bases survived "
            f"the write: {offenders} — an OVER-BROAD gate (thread "
            f"3833671117: coverage checks pass because the wildcards "
            f"match the protected refs too, but every OTHER ref those "
            f"patterns match stays merge-only and PR-head review-fix "
            f"pushes are rejected)"
        )
    if stray_excludes:
        findings.append(
            f"a non-empty exclude list survived the write: "
            f"{stray_excludes} (thread 3833671117: the canonical "
            f"gate must exclude nothing)"
        )
    findings.extend(payload)
    return findings
