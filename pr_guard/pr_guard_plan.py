"""The pre-dispatch commit snapshot and the two-case single-parent
revert plan (PR #41 round 25).

THE CONTRACT (threads 3835145976/3835145981/3835175506/3835175508):
after seven rounds of provenance heuristics — each refuted by a
reviewer counter-example (see pr_guard_range's docstring for the
chain) — the classifier is DELETED. The single-parent revert path now
automates EXACTLY ONE shape: the landing whose PARENT IS THE
PRE-DISPATCH `<remote>/<base>` TIP — the tip snapshotted BEFORE the
merge dispatch (thread 3835290443, round 26) — where the one landed
commit is by construction exactly the PR's delta over the base as it
stood and a plain `git revert --no-edit <merge_sha>` undoes the entire
PR. Every other single-parent landing — rebase landings,
advancement-interleaved landings, rewritten tips, shortened replays
(thread 3835175508), marker-spoofable shapes (threads 3835145976/
3835175506) — fails closed to the manual-revert banner in
pr_guard_range, carrying diagnostics. The two-parent `git revert -m 1`
case lives in pr_guard_revert.

Thread 3835290443 (P1, round 26): the comparison target is the FROZEN
tip, never the current ref. The single-parent plan used to probe
`git rev-parse <remote>/<base>` AFTER the pre-revert base fetch — but
that fetch is exactly what moves the ref to `merge_sha` ITSELF (or a
still-later base commit), so `parent == tip` could never match for an
ordinary squash landing and the supposedly automated path ALWAYS fell
through to the manual banner. `snapshot_base_tip` reads the tip ONCE
pre-dispatch (beside the frozen commit list, thread 3835145981): fetch
the base through the CANONICAL remote, then rev-parse `<remote>/
<base>` — an immutable sha by the time any revert runs. A snapshot
that cannot be taken (no canonical remote, a failed fetch, an
unreadable probe) degrades like the commit snapshot: warn, proceed
with "", and every single-parent revert then fails closed (the
automated shape cannot be proven against a tip nobody froze).

Thread 3835145981 (P1, round 25): the PR commit list is read ONCE,
BEFORE the merge dispatch (merge_guarded snapshots it beside the
merge-request-time head) and the FROZEN list is threaded through
every revert path — a post-merge push to the source branch moves
refs/pull/<n>/head (and GitHub reconnects the PR's commit
association), so a post-merge re-read can describe the POST-MERGE
branch while the planner believed it held the landed commits. With
the classifier gone the snapshot feeds ONLY the fail-closed banner's
PR-commit-count diagnostic, but it must still be the PRE-DISPATCH
truth, and a failed read degrades diagnostics without blocking the
merge: the gate has never depended on the list.

read_pr_commits PAGINATES the REST commit endpoint (thread 3834883632,
round 21: the inspected gh GraphQL connection serves commits(first:
100) with no cursor loop, so `gh pr view --json commits` TRUNCATED a
>100-commit PR) and fails loud-but-nonblocking on the endpoint's
DOCUMENTED 250-commit cap (thread 3834934167, round 22: "Lists a
maximum of 250 commits for a pull request" — an at-cap list can never
prove itself complete, so the snapshot is discarded rather than
report an inexact count in the banner). The fetch-before-probe
obligation (thread 3833762316) and the landed-OID fetching (thread
3834761215) were DELETED with the arms that needed the objects: the
two-case plan probes only the landing's parent and the base tip
(post-merge, purely a banner diagnostic — the DECISION target is the
pre-dispatch snapshot below).

Thread 3835345690 (PR #41 round 27): the plan's plain `git revert
--no-edit` — one of the revert path's only two commit-creating git
operations — carries the FIXED guard identity
(pr_guard_common.with_guard_identity), because an automation checkout
without user.name/user.email makes the revert die with "Author
identity unknown" before the revert commit exists.

Thread 3835379480 (PR #41 round 28): with_guard_identity also pins
this revert UNSIGNED — `-c commit.gpgsign=false` plus the
subcommand `--no-gpg-sign` — because a checkout with
commit.gpgSign=true and no usable signing key fails the revert while
BUILDING THE SIGNATURE, before the commit exists.
"""

import json
import subprocess

from .pr_guard_common import (
    REPO_NAME,
    REPO_OWNER,
    gh_env,
    with_guard_identity,
)
from .pr_guard_range import probe_sha, single_parent_manual_banner
from .pr_guard_remote import canonical_remote

COMMITS_PAGE = 100
COMMITS_CAP = 250


# Thread 3833671111 (round 9) -> 3834883632 (round 21) -> 3835145981
# (round 25): the PR's own commit list, oldest-first, read ONCE
# pre-dispatch by merge_guarded and frozen for every later consumer
# (the fail-closed banner's commit-count diagnostic). Every page is
# consumed or the read warns and returns [] — any nonzero exit,
# unparseable body, non-list body, an entry without a sha, or a list
# filling to the endpoint's DOCUMENTED 250-commit cap (thread
# 3834934167: the last page of an exactly-250 PR is byte-identical to
# a longer PR's truncated one, so an at-cap list cannot prove itself
# complete and is discarded rather than misreport the count). A
# failed read NEVER blocks the merge (thread 3835145981: the gate
# does not depend on the list) — the warning names the degradation.
def read_pr_commits(pr: int) -> list[str]:
    oids: list[str] = []
    page = 1
    while True:
        proc = subprocess.run(
            [
                "gh", "api", "--method", "GET",
                f"repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr}"
                f"/commits?per_page={COMMITS_PAGE}&page={page}",
            ],
            capture_output=True,
            text=True,
            env=gh_env(),
        )
        try:
            entries = (
                json.loads(proc.stdout) if proc.returncode == 0 else None
            )
        except ValueError:
            entries = None
        if not isinstance(entries, list):
            snapshot_unreadable(pr, page)
            return []
        for entry in entries:
            oid = str(entry.get("sha") or "")
            if not oid:
                snapshot_unreadable(pr, page)
                return []
            oids.append(oid)
        if len(oids) >= COMMITS_CAP:
            print(
                f"PR COMMIT SNAPSHOT DISCARDED: PR #{pr}'s pre-dispatch "
                f"commit-list read (thread 3835145981: frozen before "
                f"the merge dispatch) reached the REST commits "
                f"endpoint's DOCUMENTED {COMMITS_CAP}-COMMIT CAP "
                f"(\"Lists a maximum of {COMMITS_CAP} commits for a "
                f"pull request\"), with the last page filling the list "
                f"to exactly {COMMITS_CAP}: a {COMMITS_CAP + 1}th commit "
                f"is UNREPRESENTABLE on this endpoint and an "
                f"exactly-{COMMITS_CAP} PR's page shape is "
                f"byte-identical to a longer PR's truncated one, so "
                f"the count cannot be proven exact (thread 3834934167). "
                f"The merge itself does NOT depend on the list, but a "
                f"later single-parent revert's fail-closed banner will "
                f"report the snapshot as UNAVAILABLE instead of "
                f"misreporting a truncated count."
            )
            return []
        if len(entries) < COMMITS_PAGE:
            return oids
        page += 1


# The pre-dispatch snapshot warning (round 25 rewording of the old
# REVERT BLOCKED banners, which made sense only post-merge): the read
# runs BEFORE the merge is dispatched, so a failure is a DIAGNOSTIC
# degradation, never a block.
def snapshot_unreadable(pr: int, page: int) -> list[str]:
    print(
        f"PR COMMIT SNAPSHOT UNREADABLE: PR #{pr}'s pre-dispatch "
        f"commit-list read (paginated REST, thread 3834883632; frozen "
        f"before the merge dispatch per thread 3835145981) failed on "
        f"page {page} — the merge itself does NOT depend on the list "
        f"and proceeds, but a later single-parent revert that fails "
        f"closed will report the PR-commit-count diagnostic as "
        f"UNAVAILABLE instead of re-reading the (mutable) PR."
    )
    return []


# Thread 3835290443 (PR #41 round 26): the pre-dispatch BASE-TIP
# snapshot — the twin of read_pr_commits's frozen commit list (thread
# 3835145981). Resolves the CANONICAL remote (the revert's own
# resolver, so snapshot and revert agree on the ref), fetches the base
# (repo-level: remote-tracking refs only, never the working tree),
# and rev-parses `<remote>/<base>` BEFORE the merge dispatch can move
# it. Returns "" on ANY failure — no canonical remote (its own banner
# has printed), a failed fetch, an unreadable probe — after warning
# that the degradation is DIAGNOSTIC-only for the merge (the gate
# never depended on git state) but LOAD-BEARING for a later
# single-parent revert: without a frozen tip nothing can prove the
# one automated shape, so every single-parent revert fails closed.
def snapshot_base_tip(pr: int, base: str) -> str:
    remote = canonical_remote()
    if remote:
        fetched = subprocess.run(
            ["git", "fetch", remote, base]
        ).returncode
        tip = (
            probe_sha(
                ["git", "rev-parse", "--verify", f"{remote}/{base}"]
            )
            if fetched == 0
            else ""
        )
        if tip:
            return tip
    ref = f"{remote}/{base}" if remote else f"a canonical remote/{base}"
    print(
        f"BASE-TIP SNAPSHOT UNAVAILABLE: PR #{pr}'s pre-dispatch "
        f"base-tip read (thread 3835290443: frozen before the merge "
        f"dispatch, beside the frozen commit list of thread "
        f"3835145981) could not resolve {ref} — the merge itself does "
        f"NOT depend on the tip and proceeds, but a later "
        f"single-parent revert cannot prove the one automated shape "
        f"(landing parent == frozen tip) and will FAIL CLOSED to the "
        f"manual banner."
    )
    return ""


# The round-25 two-case plan builder, re-aimed at the FROZEN tip by
# thread 3835290443 (round 26): the revert argv + PR-body note for a
# SINGLE-PARENT landing. Returns the plain-revert plan ONLY when the
# landing's parent IS the pre-dispatch base tip (`git rev-parse
# --verify <merge_sha>^` == the frozen `<remote>/<base>` snapshot
# taken beside the merge dispatch) — the one unambiguous
# single-parent shape (the landed commit is exactly the PR's delta
# over the base as it stood). The CURRENT tip is still probed (after
# the pre-revert base fetch, purely diagnostically — the fetched ref
# resolves to the landing itself or beyond, which is exactly WHY the
# decision target is the frozen snapshot). Everything else returns
# None after pr_guard_range's fail-closed banner (with diagnostics);
# the caller returns 1 without ever dispatching a doomed `git
# revert`. `commits` is the FROZEN pre-dispatch commit snapshot
# (thread 3835145981) — diagnostics only, never a license.
def single_parent_revert_plan(
    pr: int,
    base: str,
    merge_sha: str,
    remote: str,
    commits: list[str] | None = None,
    frozen_base_tip: str = "",
) -> tuple[list[str], str] | None:
    parent = probe_sha(
        ["git", "rev-parse", "--verify", f"{merge_sha}^"]
    )
    tip = probe_sha(
        ["git", "rev-parse", "--verify", f"{remote}/{base}"]
    )
    if parent and frozen_base_tip and parent == frozen_base_tip:
        return (
            # Threads 3835345690 (round 27) + 3835379480 (round 28):
            # the FIXED guard identity AND the unsigned pinning ride
            # the plan's revert argv — an automation checkout with no
            # user.name/user.email, or one with commit.gpgSign=true
            # and no usable signing key, dies BEFORE the revert
            # commit exists.
            with_guard_identity(
                ["git", "revert", "--no-edit", merge_sha]
            ),
            "a SINGLE-PARENT landing whose parent IS the FROZEN "
            f"PRE-DISPATCH base tip {frozen_base_tip[:12]} (thread "
            f"3835290443: snapshotted from {remote}/{base} before "
            f"the merge dispatch, beside the frozen commit list of "
            f"thread 3835145981 — the pre-revert base fetch has "
            f"already moved the ref to the landing itself or beyond, "
            f"so the CURRENT tip {tip[:12] or 'UNREADABLE'} can "
            f"never be the comparison target): the one landed commit "
            f"is exactly the PR's delta over the base as it stood at "
            f"dispatch, so one plain `git revert --no-edit` of the "
            f"landed commit undoes the entire PR — the ONE "
            f"unambiguous single-parent shape the round-25 contract "
            f"automates (threads 3833540921/3833671111); every other "
            f"single-parent shape fails closed to the manual banner "
            f"(threads 3835145976/3835145981/3835175506/3835175508: "
            f"reviewer counter-examples proved provenance "
            f"uncomputable from local git data, retiring the "
            f"round-9-to-24 classifier)",
        )
    single_parent_manual_banner(
        pr, base, merge_sha, remote, commits, parent, tip,
        frozen_base_tip,
    )
    return None
