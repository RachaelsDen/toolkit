"""Repository-ruleset server gate for pr_guard.

Split from pr_guard.py at the 250 pure-LOC ceiling (PR #36 round 2,
thread 3827503028): REST helpers, the review-thread-resolution ruleset
match (harden/verification), and the harden mode itself (thread
3827397508's server-side enforcement — see pr_guard.py's docstring).
PR #41 round 6 moved the pure pattern->regex translation block into
pr_guard_fnmatch (thread 3833251667's split family) so harden had
headroom for the every-match migration (threads 3833144348/
3833251666). PR #41 round 7 (thread 3833360207) reordered the
migration tail: the canonical ruleset is GET-verified BEFORE any
redundant is DELETEd, so a transport-successful PATCH that stored a
bypassable/inactive/mis-scoped ruleset fails hard with the fallbacks
retained instead of leaving the broken canonical as the only gate.
PR #41 round 8 (thread 3833540908) widened that verification to EVERY
protected base in PROTECTED_BASE_PATTERNS, not just the base being
hardened — a canonical covering only dev passed the single-base check
during a dev harden, the DELETE loop then removed the '(main)'
fallback, and main sat ungated under a HARDENED claim; any uncovered
base now blocks the DELETEs with the gap named. PR #41 round 9
(thread 3833671117) tightened it to EXACT scope: positive coverage
alone blesses an OVER-BROAD canonical — a transport-successful PATCH
whose stored includes are still the legacy wildcards covers main AND
dev, so coverage checks pass while the DELETEs would remove every
fallback and leave the wildcard as the only gate (release/feature/
remediation heads merge-only, review-fix pushes rejected). The stored
include list must equal PROTECTED_BASE_PATTERNS exactly and the
exclude list must be empty; offending patterns block the DELETEs.
PR #41 round 10 (thread 3833762329) added the TARGET invariant the
exact-scope check still omitted: a same-named ruleset stored with
target 'tag' or 'push' passes every ref-condition and pull_request-
rule check while gating NOTHING about branch pull requests, so the
pre-DELETE verification now also asserts stored target == 'branch';
a wrong target blocks the DELETEs with the stored value printed.
PR #41 round 17 (thread 3834590324) added the stored RULE PAYLOAD
verification: exactly one pull_request rule carrying exactly the
parameters dict the guard installs (pr_guard_rules_payload is the
single source for the write AND the comparison) — a stale
approving-count, an extra rule, or a dismiss-stale flag surviving a
transport-successful PATCH blocks the DELETEs with the diff printed.
"""

import json
import subprocess

from .pr_guard_common import REPO_NAME, REPO_OWNER, blocked_gh_host, die
from .pr_guard_common import gh_env, warn_repo_override
from .pr_guard_fnmatch import ref_matches
from .pr_guard_rules_payload import GATE_RULE
from .pr_guard_rulesets_verify import stored_scope_findings

GATE_RULE_PREFIX = "pr-guard: required review thread resolution"

# Thread 3832660865 (PR #40 round 4): harden's idempotence lookup name.
# The live ruleset 21137845 was renamed to exactly this when it was
# rescoped, so a re-run finds it by name and PATCHes (rescopes) the
# EXISTING ruleset instead of POSTing a duplicate beside it.
GATE_RULESET_NAME = f"{GATE_RULE_PREFIX} (protected bases)"

# Thread 3833111358 (PR #41): every name the gate ruleset carried
# before the rescope — the PR #36 round-1 form parameterized by the
# hardened base ("(dev)"/"(main)"), and the PR #37-#39 "(all bases)"
# wildcard era. A repository hardened by those versions still has the
# OLD-named ruleset ACTIVE: looking up only the new name misses it,
# POSTs a second ruleset beside it, and GitHub then applies BOTH (the
# legacy wildcard keeps blocking pushes to release and other PR-head
# branches). Threads 3833144348/3833251666 (PR #41 round 6): the
# lookup returns EVERY ruleset matching ANY known name — a duplicate
# (new name AND legacy alias both active, e.g. left behind by an
# older harden run) means selecting ONE match leaves the other
# applying beside it, and GitHub enforces both. harden PATCHes the
# CANONICAL match to the desired config and DELETEs every redundant
# other, so exactly one gate ruleset survives under exactly the
# intended name and scope.
LEGACY_GATE_RULESET_NAMES = (
    f"{GATE_RULE_PREFIX} (all bases)",
    f"{GATE_RULE_PREFIX} (dev)",
    f"{GATE_RULE_PREFIX} (main)",
)

# Thread 3829356731 (PR #39): the old wildcard pair ('refs/heads/**' +
# 'refs/heads/**/*') gated EVERY branch — including PR head refs, whose
# direct pushes the pull_request rule then rejects, so authors could
# not push review fixes and the ordinary PR workflow recursed into
# itself. The gate covers exactly the PROTECTED BASES (mirroring live
# ruleset 21137845, rescoped at the repo level); head branches stay
# directly pushable, and a mid-flight retarget (thread 3828495560) is
# caught by the pre-merge/merge base pinning PLUS the merge act's
# post-merge destination assertion (PR #40 thread 3832321698: GitHub's
# merge API accepts no base lock, so --match-head-commit cannot pin
# the base server-side — merge re-reads baseRefName once state==MERGED
# and reverts on a mismatch).
# Thread 3832660865 (PR #40 round 4): 'refs/heads/release/**' is
# REMOVED — that pattern also matches release branches USED AS PR
# HEADS, and this repository does exactly that (merge commit 1e6b9a4
# records PR #35 coming from 'release/m6-to-main'), so the ruleset's
# pull_request rule made review-fix pushes to a release PR head
# impossible — the same head-usage collision as thread 3829356731,
# just narrower. The live ruleset 21137845 was already rescoped to
# main/dev only; this list now mirrors it. A release branch used as a
# BASE is simply not gated: merges into it are not guarded, by the
# same trade-off (protecting it would block every release-shaped PR
# head's fixes). Extend this list only when the repo grows a base that
# is NEVER used as a PR head.
PROTECTED_BASE_PATTERNS = (
    "refs/heads/main",
    "refs/heads/dev",
)


def gh_rest(method: str, path: str, body: dict | None = None) -> dict:
    cmd = ["gh", "api", "--method", method, path]
    stdin = None
    if body is not None:
        cmd += ["--input", "-"]
        stdin = json.dumps(body)
    proc = subprocess.run(
        cmd, input=stdin, capture_output=True, text=True, env=gh_env()
    )
    if proc.returncode != 0:
        die(
            f"gh api {method} {path} exited {proc.returncode}: "
            f"{proc.stderr.strip()}"
        )
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def gh_rest_pr(pr: int) -> dict:
    """The PR record (base ref + head SHA) for the pre-merge gate."""
    return gh_rest("GET", f"repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr}")


def pr_base_ref(pr: int) -> str:
    return str(gh_rest_pr(pr)["base"]["ref"])


def default_branch() -> str:
    return str(
        gh_rest("GET", f"repos/{REPO_OWNER}/{REPO_NAME}")["default_branch"]
    )


def fetch_gate_rulesets() -> list[dict]:
    # The list view truncates rules/conditions — fetch each detail.
    # Thread 3834666213 (PR #41 round 18): the list view ALSO paginates
    # — a repository with more than 100 rulesets served only the first
    # per_page=100 page, truncating the legacy-migration match set (a
    # legacy wildcard gate on a LATER page stayed invisible while the
    # visible redundants were DELETEd and HARDENED printed, and the
    # hidden gate kept blocking review-fix pushes). Follow the REST
    # page cursor until a short page and flatten EVERY page before any
    # canonical selection or redundant deletion.
    listed: list[dict] = []
    page = 1
    while True:
        entries = gh_rest(
            "GET",
            f"repos/{REPO_OWNER}/{REPO_NAME}/rulesets?per_page=100&page={page}",
        )
        listed.extend(entries)
        if len(entries) < 100:
            break
        page += 1
    return [
        gh_rest(
            "GET", f"repos/{REPO_OWNER}/{REPO_NAME}/rulesets/{entry['id']}"
        )
        for entry in listed
    ]


def gate_covers(rulesets: list[dict], ref: str, default: str) -> dict | None:
    """First ACTIVE ruleset enforcing thread resolution on ref, else None.

    Pure matching (unit-tested in pr_guard_test.py): exact
    refs/heads/<ref> patterns, the ~DEFAULT_BRANCH token, and
    GitHub-pathname fnmatch patterns (thread 3827635802) all count; a
    matching EXCLUDE never counts (thread 3827503026 — include patterns
    are only consulted after the ref is proven not excluded); disabled
    rulesets, rulesets without the required_review_thread_resolution
    parameter, and rulesets granting ANY bypass never do (thread
    3827635805 — a bypassable gate is no gate: an 'always' or
    'pull_request' bypass entry, or a viewer-merge bypass, means the
    merger can skip thread resolution entirely, so fail closed). Non-
    branch-target rulesets never count either (thread 3834666208 — a
    tag/push-target ruleset gates nothing about PR merges).
    """
    for ruleset in rulesets:
        if ruleset.get("enforcement") != "active":
            continue
        # Thread 3834666208 (PR #41 round 18): the shared coverage
        # predicate requires a BRANCH-target ruleset — an active tag-
        # or push-target ruleset whose ref conditions match and whose
        # pull_request rule carries required_review_thread_resolution
        # gates NOTHING about PR merges (thread 3833762329 verified the
        # target only during harden; pre_merge and the merge act call
        # this predicate directly). Non-branch matches are ignored, so
        # a base whose ONLY match is non-branch reads gate-missing.
        if ruleset.get("target") != "branch":
            continue
        gated = any(
            rule.get("type") == "pull_request"
            and (rule.get("parameters") or {}).get(
                "required_review_thread_resolution"
            )
            is True
            for rule in (ruleset.get("rules") or [])
        )
        if not gated:
            continue
        if ruleset.get("bypass_actors"):
            continue
        if ruleset.get("current_user_can_bypass") in {
            "always",
            "pull_request",
        }:
            continue
        conditions = (ruleset.get("conditions") or {}).get("ref_name") or {}
        if any(
            ref_matches(pattern, ref, default)
            for pattern in conditions.get("exclude") or []
        ):
            continue
        if any(
            ref_matches(pattern, ref, default)
            for pattern in conditions.get("include") or []
        ):
            return ruleset
    return None


def harden(pr: int) -> int:
    # Thread 3834400946 (PR #41 round 16): a foreign GH_HOST hard
    # blocks harden too — gh api resolves against GH_HOST, so the
    # ruleset could be written to an identically named repository on
    # another host (every gh_rest call is env-pinned regardless).
    if blocked_gh_host():
        return 1
    # Thread 3833073952 (PR #41): harden's gh api paths are absolute
    # (GH_REPO-immune), but an override naming another repository is
    # still reported loudly so the operator can confirm it.
    warn_repo_override()
    base = pr_base_ref(pr)
    ref = f"refs/heads/{base}"
    # Thread 3829356731: harden only ever gates the protected bases —
    # writing the ruleset for any other base would (after the rescope)
    # fail the post-write verification anyway; refuse up front with the
    # actionable message instead of the generic repair banner.
    if not any(
        ref_matches(pattern, base, default_branch())
        for pattern in PROTECTED_BASE_PATTERNS
    ):
        print(
            f"BLOCKED: refs/heads/{base} is not a protected base "
            f"({', '.join(PROTECTED_BASE_PATTERNS)}) — harden gates "
            f"exactly the protected bases (thread 3829356731); PR head "
            f"branches must stay directly pushable."
        )
        return 1
    name = GATE_RULESET_NAME
    # Thread 3833111358: the lookup matches the new name OR any
    # historical alias — a repo configured by the parent version
    # still runs the '(all bases)' wildcard, and missing it would POST
    # a second ruleset while the legacy one keeps applying beside it.
    # Threads 3833144348/3833251666: EVERY match is collected; the
    # canonical one (a new-name match if any exists, else the first
    # legacy) takes the PATCH, and every OTHER match is DELETEd below.
    matches = [
        ruleset
        for ruleset in fetch_gate_rulesets()
        if ruleset.get("name") == name
        or ruleset.get("name") in LEGACY_GATE_RULESET_NAMES
    ]
    canonical = next(
        (
            ruleset
            for ruleset in matches
            if ruleset.get("name") == name
        ),
        matches[0] if matches else None,
    )
    if canonical is not None and canonical.get("name") != name:
        print(
            f"MIGRATING legacy ruleset id {canonical.get('id')} "
            f"'{canonical.get('name')}' -> '{name}' with the narrowed "
            f"protected-bases patterns (thread 3833111358): one PATCH "
            f"renames and rescopes it — no POST, so no duplicate "
            f"ruleset ever applies beside the migrated one."
        )
    body = {
        "name": name,
        "target": "branch",
        "enforcement": "active",
        # Thread 3829356731 (PR #39): the include list is the protected
        # bases ONLY (PROTECTED_BASE_PATTERNS) — the previous
        # every-branch wildcards ('**' + '**/*', threads 3828495560/
        # 3828495569) made PR head refs merge-only and unpushable. A
        # mid-flight retarget is caught because pre-merge/merge PIN
        # the base they verified and the merge act RE-ASSERTS the
        # destination after state==MERGED (PR #40 thread 3832321698 —
        # a mismatch reverts on the landed base); re-running harden on
        # the rescoped live ruleset (21137845) is an idempotent no-op.
        "conditions": {
            "ref_name": {
                "include": list(PROTECTED_BASE_PATTERNS),
                "exclude": [],
            }
        },
        # Thread 3834590324 (PR #41 round 17): the rule payload lives
        # in pr_guard_rules_payload as the SINGLE SOURCE the write
        # sends and the pre-DELETE verification compares the STORED
        # ruleset against (full-neutral parameters except the
        # thread-resolution flag; the API rejects a partial object).
        "rules": [GATE_RULE],
        # Thread 3828232340: PATCH PRESERVES omitted fields — a repair
        # of an existing bypassable gate must clear its bypass actors
        # explicitly, or "HARDENED" prints while the bypass survives.
        "bypass_actors": [],
    }
    if canonical is None:
        ruleset_id = gh_rest(
            "POST", f"repos/{REPO_OWNER}/{REPO_NAME}/rulesets", body
        ).get("id")
    else:
        gh_rest(
            "PATCH",
            f"repos/{REPO_OWNER}/{REPO_NAME}/rulesets/{canonical['id']}",
            body,
        )
        ruleset_id = canonical.get("id")
    # Thread 3828232340: never trust the write's echo — re-read the
    # stored ruleset and verify it actually covers the ref with no
    # bypass. Thread 3833360207 (PR #41 round 7): the verification
    # runs BEFORE any redundant is DELETEd — a PATCH can succeed at the
    # transport level and still leave the stored ruleset
    # bypassable, inactive, or mis-scoped (the exact cases this GET
    # detects), and deleting the legacy gates first would leave that
    # broken canonical as the ONLY gate. Verification failure fails
    # hard with the discrepancy printed and leaves every fallback in
    # place. Thread 3833540908 (PR #41 round 8): the verification must
    # cover EVERY protected base, not just the one being hardened — a
    # canonical left covering only dev passed the single-base check
    # while hardening a dev PR, the DELETE loop then removed the
    # '(main)' fallback, and main sat ungated under a HARDENED claim.
    # PROTECTED_BASE_PATTERNS holds literal refs today, so the base
    # name is the pattern minus refs/heads/; any uncovered base blocks
    # the DELETEs with the gap named.
    # Thread 3833671117 (PR #41 round 9): coverage alone still blesses
    # an OVER-BROAD canonical — a transport-successful PATCH can leave
    # the stored includes as the legacy WILDCARD pair, which covers
    # main and dev (so `uncovered` stays empty) while the DELETE loop
    # would remove every fallback and leave the wildcard the ONLY
    # gate: release/*, feature/*, remediation/* heads stay merge-only
    # and review-fix pushes are rejected. The stored scope must be
    # EXACTLY the intended configuration — the include list in SET
    # EQUALITY with PROTECTED_BASE_PATTERNS (any pattern outside the
    # protected set matches refs the gate must not touch) and the
    # exclude list EMPTY; a mismatch blocks the DELETEs with the
    # offending patterns printed.
    stored = gh_rest(
        "GET", f"repos/{REPO_OWNER}/{REPO_NAME}/rulesets/{ruleset_id}"
    )
    default = default_branch()
    stored_target = str(stored.get("target") or "")
    uncovered = [
        pattern.removeprefix("refs/heads/")
        for pattern in PROTECTED_BASE_PATTERNS
        if gate_covers(
            [stored], pattern.removeprefix("refs/heads/"), default
        )
        is None
    ]
    ref_name = (stored.get("conditions") or {}).get("ref_name") or {}
    stored_includes = list(ref_name.get("include") or [])
    stored_excludes = list(ref_name.get("exclude") or [])
    # PR #41 round 31 (the family's split-FIRST rule at the 250
    # pure-LOC ceiling): the findings builder for the pre-DELETE
    # verification lives in pr_guard_rulesets_verify (this module
    # stood at 257/250); `uncovered` is computed HERE because
    # gate_covers must stay in this module beside the coverage
    # predicate the merge act imports.
    findings = stored_scope_findings(
        stored, uncovered, stored_includes, stored_excludes,
        stored_target, PROTECTED_BASE_PATTERNS,
    )
    if findings:
        print(
            f"BLOCKED: canonical ruleset id {ruleset_id} did not verify "
            f"after the write — discrepancy: enforcement="
            f"{stored.get('enforcement')!r}, bypass_actors="
            f"{stored.get('bypass_actors') or []}, target="
            f"{stored_target!r}, include={stored_includes!r}, "
            f"exclude={stored_excludes!r}; "
            + "; ".join(findings)
            + f" (thread 3833540908: the pre-DELETE verification covers "
            f"EVERY protected base ({', '.join(PROTECTED_BASE_PATTERNS)}), "
            f"not just the refs/heads/{base} being hardened — deleting "
            f"the fallbacks with a base uncovered would leave that base "
            f"with NO gate); every redundant legacy gate was LEFT IN "
            f"PLACE (thread 3833360207: deleting them now would leave "
            f"this broken canonical as the only gate); repair it "
            f"manually in the repo settings and re-run harden. DO NOT "
            f"merge on this gate."
        )
        return 1
    # Threads 3833144348/3833251666: the PATCH rescopes only the
    # canonical ruleset — every OTHER match keeps applying beside it
    # (GitHub enforces BOTH), so the redundants are DELETEd only AFTER
    # the canonical VERIFIED above (never before: a failure between
    # the PATCH and the DELETEs leaves a working gate, not none).
    for redundant in matches:
        if redundant is canonical:
            continue
        print(
            f"DELETED redundant ruleset id {redundant.get('id')} "
            f"'{redundant.get('name')}' (threads 3833144348/"
            f"3833251666): it matched a known gate name beside the "
            f"canonical ruleset {ruleset_id}, and GitHub applies "
            f"BOTH — exactly one gate ruleset survives this run."
        )
        gh_rest(
            "DELETE",
            f"repos/{REPO_OWNER}/{REPO_NAME}/rulesets/{redundant['id']}",
        )
    print(
        f"HARDENED {ref}: ruleset id {ruleset_id} verified ACTIVE, "
        f"covering the ref, no bypass actors — GitHub now refuses every "
        f"merge (or direct push) while a review thread is unresolved."
    )
    return 0
