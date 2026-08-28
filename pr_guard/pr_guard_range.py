"""The single-parent landing probes and the FAIL-CLOSED banner.

THE ROUND-25 CONTRACT (threads 3835145976/3835145981/3835175506/
3835175508, PR #41): the landing-shape CLASSIFIER IS RETIRED. Rounds
9-24 each added a provenance signal — landed-range count (3834093635),
patch-id membership (3834210484), the empty-landing guard (3834375731),
complete maps (3834400951), direct diff-tree feeds (3834400957),
parent-chain contiguity (3834590322), the ordered patch-id sequence
(3834761209), author/subject correlation (3834819188), tree equality
(3834883628) then delta equality (3834934170), the contiguous-suffix
remainder (3834988955), and finally the squash MARKER (3835052616) —
and every one fell to a reviewer counter-example, because every one of
those signals is REPRODUCIBLE BY A FOREIGN LANDING:

- Thread 3835175506: an earlier queue entry's cherry-pick of patch X
  beside this PR's marker-free custom-subject squash of patch Y
  (`gh pr merge --subject` makes the subject user text) satisfies
  patch-id/order/metadata/delta rules AND the marker scans — the
  "rebase" range revert would undo the FOREIGN commit.
- Thread 3835175508: a rebase that drops already-upstream patches
  (`git rebase --empty=drop` / `--no-reapply-cherry-picks`) lands
  FEWER commits than the PR has, so even "the range is shorter than
  the PR" proved nothing — the shortened rebase read as a squash and
  the one-commit revert left the dropped-back commits on the base.
- Thread 3835145976: a rebase tip's ORIGINAL subject can itself end
  in "(#N)" — the marker is user-controlled commit text, not
  GitHub-owned landing metadata — collapsing the round-24
  discriminator's terminal rule.

Provenance is empirically UNCOMPUTABLE from local git data. The guard
therefore automates ONLY the two shapes whose revert is unambiguous by
CONSTRUCTION, never by classification (see pr_guard_plan and
pr_guard_revert): (a) the TWO-PARENT mergeCommit — `git revert -m 1`
reverts the merge's OWN diff, exactly the PR's net change; (b) the
SINGLE-PARENT landing whose PARENT IS THE PRE-DISPATCH base tip —
the FROZEN `<remote>/<base>` snapshot taken before the merge dispatch
(thread 3835290443, round 26: comparing against the CURRENT ref never
matched, because the pre-revert base fetch has already moved it to
the landing itself or beyond) — the one landed commit is exactly the
PR's delta over the base as it stood, so a plain `git revert` of it
undoes the whole PR. EVERYTHING ELSE — rebase landings,
advancement-interleaved landings, rewritten tips, shortened replays,
spoof-prone shapes — FAILS CLOSED to the manual banner below,
enriched with the diagnostic numbers the old classifier already
gathered (landed-range count past the fork, the PR's frozen
pre-dispatch commit count, marker presence) so a human can decide.
No heuristic classification remains; there is no spoofable surface
left to construct counter-examples against.

This module keeps the generic probes the contract still needs —
commit_available (object presence) and probe_sha (one probe whose
ANSWER is the stdout sha, thread 3833880596) — plus the banner. The
patch-id/sequence/metadata/delta plumbing (pr_guard_patch_id) and the
per-arm banners (pr_guard_range_banners) were DELETED at round 25
with the arms they served; the marker probes survive as diagnostics
only (pr_guard_marker).
"""

import subprocess

from .pr_guard_marker import marker_table


# One object-availability probe — `git rev-parse --verify <rev>` exits
# 0 only when the rev resolves in the local object database.
def commit_available(oid: str) -> bool:
    return (
        subprocess.run(
            ["git", "rev-parse", "--verify", oid], capture_output=True
        ).returncode
        == 0
    )


# Thread 3833880596 (PR #41 round 11): one probe whose ANSWER is the
# stdout sha, not just the exit code — `git rev-parse --verify <rev>`
# for the landing's parent and the base tip, `git merge-base <a> <b>`
# for the fork point. Empty stdout or a nonzero exit both read as "".
def probe_sha(argv: list[str]) -> str:
    proc = subprocess.run(argv, capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


# The LANDED-RANGE diagnostic (round 25): the count of commits past
# the fork point `git merge-base refs/pull/<n>/head <remote>/<base>`,
# listed by `git rev-list --no-merges <fork>..<merge_sha>` — the same
# numbers the retired classifier gathered (threads 3834093635/
# 3834210484), now purely INFORMATIONAL. The PR head ref is ensured
# first (probed, fetched WITH a refspec when missing — thread
# 3834093635's ensuring fetch, kept so the diagnostic works from a
# checkout that never pulled PR refs). Returns (fork, count); fork ""
# (and count -1) when the ref or the merge-base is unprobeable — the
# banner reports the degradation instead of a number it cannot prove.
def landed_range_diagnostic(
    pr: int, base: str, merge_sha: str, remote: str
) -> tuple[str, int]:
    head = f"refs/pull/{pr}/head"
    if not commit_available(head):
        subprocess.run(["git", "fetch", remote, f"+{head}:{head}"])
        if not commit_available(head):
            return "", -1
    fork = probe_sha(["git", "merge-base", head, f"{remote}/{base}"])
    if not fork:
        return "", -1
    listed = probe_sha(
        ["git", "rev-list", "--no-merges", f"{fork}..{merge_sha}"]
    )
    if not listed:
        return fork, -1
    return fork, len(listed.split())


# Thread 3835145976/3835175506/3835175508 (PR #41 round 25), re-aimed
# at the FROZEN tip by thread 3835290443 (round 26): THE fail-closed
# banner for every single-parent landing that is not the one
# unambiguous automated shape. `parent`/`tip` are the probed shas
# ("" = unreadable): the landing's parent, and the CURRENT
# `<remote>/<base>` ref as resolved AFTER the pre-revert base fetch —
# which is exactly why the ref can never be the comparison target (it
# resolves to the landing itself or beyond, thread 3835290443).
# `frozen_tip` is the PRE-DISPATCH base-tip snapshot (thread
# 3835290443: read once beside the frozen commit list of thread
# 3835145981; "" = the snapshot was unobtainable). `commits` is the
# PR's FROZEN pre-dispatch commit snapshot (None/[] = unobtainable).
# The banner states the contract, the numbers, and the manual
# obligation — nothing here classifies, so nothing here can be
# spoofed into an automated revert.
def single_parent_manual_banner(
    pr: int,
    base: str,
    merge_sha: str,
    remote: str,
    commits: list[str] | None,
    parent: str,
    tip: str,
    frozen_tip: str = "",
) -> None:
    parent_note = (
        f"its parent probes as {parent[:12]}"
        if parent
        else "its parent is UNREADABLE (root commit or missing object)"
    )
    frozen_note = (
        f"the FROZEN pre-dispatch base tip (thread 3835290443) was "
        f"{frozen_tip[:12]}"
        if frozen_tip
        else "the pre-dispatch base-tip snapshot is UNAVAILABLE "
        "(thread 3835290443: the tip is read once before the merge "
        "dispatch — no canonical remote, a failed fetch, or an "
        "unreadable probe left nothing to compare), so the automated "
        "shape cannot be proven and this fails closed"
    )
    if not tip:
        tip_note = (
            f"the current {remote}/{base} tip is UNREADABLE "
            "(the pre-revert base fetch failed to leave a resolvable "
            "ref)"
        )
    elif tip == frozen_tip and frozen_tip:
        tip_note = (
            f"the current {remote}/{base} tip still resolves to "
            f"{tip[:12]}, the frozen tip itself — nothing further "
            f"has landed on the base"
        )
    elif tip == merge_sha:
        tip_note = (
            f"the current {remote}/{base} tip resolves to "
            f"{tip[:12]} — the landing ITSELF (the ordinary "
            f"post-merge state; the pre-revert base fetch moved the "
            f"ref, which is why the comparison target is the frozen "
            f"tip, never the current ref — thread 3835290443)"
        )
    else:
        tip_note = (
            f"the current {remote}/{base} tip resolves to "
            f"{tip[:12]} — the base has ADVANCED past the frozen tip "
            f"(interleaved or foreign landings beside this one), and "
            f"advancement means ambiguity anyway: fail closed"
        )
    fork, count = landed_range_diagnostic(pr, base, merge_sha, remote)
    range_note = (
        f"the landed range past the fork point {fork[:12]} counts "
        f"{count} commit(s)"
        if count >= 0
        else "the landed-range count is UNAVAILABLE (the fork-point "
        "probe `git merge-base refs/pull/"
        f"{pr}/head {remote}/{base}` produced no usable answer)"
    )
    commits_note = (
        f"the PR's FROZEN pre-dispatch commit snapshot counts "
        f"{len(commits)} commit(s)"
        if commits
        else "the PR's pre-dispatch commit snapshot is UNAVAILABLE "
        "(the pre-dispatch read failed — thread 3835145981: the list "
        "is read once before the merge dispatch and never re-read "
        f"against a moved refs/pull/{pr}/head)"
    )
    markers = marker_table([merge_sha])
    marker_note = (
        "the landing tip's subject probe was UNREADABLE"
        if markers is None
        else (
            f"the landing tip's subject ends in the squash marker "
            f"\"(#{markers[merge_sha]})\""
            if merge_sha in markers
            else "the landing tip's subject carries NO trailing "
            "squash marker"
        )
    )
    print(
        f"REVERT BLOCKED: the landing {merge_sha[:12]} of PR #{pr} is "
        f"SINGLE-PARENT and {parent_note}, while {frozen_note} and "
        f"{tip_note} — the only two AUTOMATED revert shapes are the "
        f"TWO-PARENT mergeCommit (`git revert -m 1`) and the "
        f"single-parent landing whose parent IS the FROZEN "
        f"pre-dispatch base tip (the one commit is then exactly the "
        f"PR's delta over the base as it stood at dispatch, thread "
        f"3835290443); this landing is NEITHER. DIAGNOSTICS for the "
        f"manual "
        f"decision: {range_note}; {commits_note}; and {marker_note} — "
        f"a marker is USER-CONTROLLED commit text, not GitHub-owned "
        f"landing metadata (thread 3835145976), so it corroborates "
        f"nothing. The heuristic classifier that used to decide "
        f"squash-vs-rebase here was RETIRED because reviewer "
        f"counter-examples proved every provenance signal "
        f"reproducible by a foreign landing (threads "
        f"3835175506: a marker-free custom-subject squash beside a "
        f"foreign cherry-pick satisfies every patch-id/order/"
        f"metadata/delta rule; 3835175508: a rebase that drops "
        f"already-upstream patches lands FEWER commits than the PR "
        f"has; 3835145976: a rebase tip's original subject can itself "
        f"end in \"(#N)\") — so this shape fails closed BY CONTRACT, "
        f"never for lack of a heuristic; the merge MUST be reverted "
        f"manually on {base} (threads 3835145976/3835145981/"
        f"3835175506/3835175508)."
    )
