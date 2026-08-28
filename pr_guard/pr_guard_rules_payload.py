"""The exact gate-rule payload and its pre-DELETE verification.

Split from pr_guard_rulesets.py at the PR #41 round-17 fixes (thread
3834590324): rulesets stood at the 250 pure-LOC ceiling and the
round-17 payload verification lands entirely in harden's write+verify
half, so the intended RULE SHAPE moved here — both the payload the
guard WRITES (GATE_RULE, the full-neutral parameters object the
ruleset API demands) and the comparison against what a post-PATCH GET
actually STORED (stored_payload_findings). Imports flow ONE way
(rulesets -> rules_payload; no imports below — a leaf beside
pr_guard_fnmatch).

Thread 3834590322's sibling finding, thread 3834590324 (PR #41 round
17): the pre-DELETE verification asserted target/ref scope but never
the stored RULE LIST or its parameters — a transport-successful PATCH
could leave `required_approving_review_count` nonzero, an EXTRA rule
beside the gate, or `dismiss_stale_reviews_on_push` true, and the
redundant fallbacks were then DELETEd with `HARDENED` printed while
the surviving canonical ruleset unexpectedly BLOCKED merges the
neutral rule would allow. The stored shape must be EXACTLY one
pull_request rule carrying EXACTLY the parameters dict the guard
installs; any difference blocks the DELETEs with the diff printed.
"""

# Thread 3834590324: the ONE pull_request rule the guard installs —
# the full-neutral parameters object except the thread-resolution
# flag (the ruleset API rejects a PARTIAL parameters object, 422
# "data matches no possible input"). This is the single source the
# write uses AND the verification compares against, so the intended
# payload can never drift between the two halves.
GATE_RULE_PARAMETERS = {
    "dismiss_stale_reviews_on_push": False,
    "require_code_owner_review": False,
    "require_last_push_approval": False,
    "required_approving_review_count": 0,
    "required_review_thread_resolution": True,
}

GATE_RULE = {"type": "pull_request", "parameters": GATE_RULE_PARAMETERS}


# Thread 3834590324: the stored ruleset's RULE LIST + parameters vs
# the exact intended shape. Returns [] when the stored payload is
# exactly right, else human-readable findings that harden appends to
# its BLOCKED banner (no fallback DELETE may run on a mismatch — the
# surviving canonical must not block merges the neutral rule allows).
def stored_payload_findings(stored: dict) -> list[str]:
    rules = list(stored.get("rules") or [])
    pull_rules = [r for r in rules if r.get("type") == "pull_request"]
    if len(rules) != 1 or len(pull_rules) != 1:
        return [
            f"the stored RULE LIST holds {len(rules)} rule(s) "
            f"({len(pull_rules)} of them pull_request) beside the "
            f"intended EXACTLY ONE pull_request rule (thread "
            f"3834590324: an extra surviving rule can block merges "
            f"the neutral gate would allow)"
        ]
    params = dict(pull_rules[0].get("parameters") or {})
    stale = sorted(
        key
        for key, want in GATE_RULE_PARAMETERS.items()
        if params.get(key) != want
    )
    extra = sorted(set(params) - set(GATE_RULE_PARAMETERS))
    if not stale and not extra:
        return []
    diff = "; ".join(
        [
            f"{key}: stored {params.get(key)!r}, intended "
            f"{GATE_RULE_PARAMETERS[key]!r}"
            for key in stale
        ]
        + [
            f"{key}: stored {params[key]!r}, intended <absent>"
            for key in extra
        ]
    )
    return [
        f"the stored pull_request rule's parameters differ from the "
        f"intended payload — {diff} (thread 3834590324: a stale "
        f"parameter surviving a transport-successful PATCH can block "
        f"merges the neutral rule would allow, and the DELETEs would "
        f"have removed every fallback beside it)"
    ]
