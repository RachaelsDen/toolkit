"""The revert half of the guarded merge act.

Split from pr_guard_merge.py at the 250 pure-LOC ceiling (PR #40
round 3): revert_merged_pr (thread 3829356731), its guarded wrapper
(thread 3832321706), the landed-during-cancel revert entry point, and
the cancel verification read (read_pending_state). PR #41 round 6
(thread 3833251667) moved the cancel/queue SETTLEMENT machinery into
pr_guard_completion, leaving this module the actual REVERTS plus the
cancel-state read they consume; imports flow one way (completion ->
settle -> revert -> range -> common).

PR #41 round 10: the single-parent range/commit analysis (read_pr_
commits, the availability probes, the fetch-before-fallback
obligation) moved to pr_guard_range.py at the 250 pure-LOC ceiling —
pr_guard_revert stood at 246/250 and every round-10 thread lands in
that half. See pr_guard_range's docstring for threads
3833671111/3833762316. PR #41 round 19 (threads 3834761209/3834761215)
moved the PLAN BUILDER itself on to pr_guard_plan.py when pr_guard_range
hit the ceiling again: the plan reverts the LANDED oid chain of a
classified rebase, never the PR's pre-rebase originals.

Thread 3833073952 (PR #41): every `gh pr` command here is pinned with
-R RachaelsDen/UR-lorebook so a GH_REPO override cannot aim the
revert plumbing at another repository.

Thread 3835145981 (PR #41 round 25): the PR's commit list is FROZEN
pre-dispatch (merge_guarded reads it beside the merge-request-time
head) and threaded DOWN through revert_landed_during_cancel ->
guarded_revert -> revert_merged_pr -> single_parent_revert_plan —
never re-read post-merge, where a push to the source branch has moved
refs/pull/<n>/head. With the round-25 classifier retirement (threads
3835145976/3835175506/3835175508 — see pr_guard_range) the snapshot
feeds ONLY the fail-closed banner's diagnostics; the two automated
shapes (two-parent `git revert -m 1`; single-parent parent==base-tip
plain revert) are decided by probes alone.

Thread 3833360211 (PR #41 round 7): guarded_revert is reached from
FIVE paths, and only ONE of them is "a post-merge survey found DANGER
threads" — every caller passes its trigger key and the revert PR
title/body render REVERT_TRIGGERS below; an unknown key fails closed
inside guarded_revert's BaseException handler.

Thread 3833540921 (PR #41 round 8): the revert no longer assumes the
landing is a two-parent merge commit — the landed commit's parent
count is probed after the fetch (`git rev-parse --verify <sha>^2`),
the argv carries `-m 1` only on the two-parent shape, and the revert
PR body documents which path ran (the single-parent shapes themselves
are planned by pr_guard_plan).

Thread 3833762325 (PR #41 round 10): every GIT operation here — the
base fetch, the revert-branch checkout, and the push — is pinned to
the CANONICAL remote resolved by pr_guard_remote.canonical_remote()
(scanning `git remote -v` for a URL naming RachaelsDen/UR-lorebook),
never the ambient origin: from a fork checkout the old argv fetched
the fork's base and pushed the revert branch to the fork while every
gh command targeted the canonical repository, so the pinned `gh pr
create` could not find the branch and the unsafe merge stayed
unreverted. A checkout with no canonical remote fails closed to the
manual-revert banner with setup instructions. PR #41 round 11
(threads 3833880596/3833880605): the resolver moved to
pr_guard_remote.py and now verifies BOTH the fetch and the push
endpoint (repairing a triangular pushurl through the dedicated
pr-guard-canonical remote), and the single-parent landing shape is
discriminated squash-vs-rebase by pr_guard_range's landed-range
COUNT instead of the PR's commit count. PR #41 round 13 (thread
3834093635): the round-12 parent-reachability probe read every
landed REBASE as a squash (the post-merge base fetch makes the whole
landed chain ancestors of <remote>/<base>), so the discriminator now
counts `git rev-list --count <fork>..<merge_sha>` against the fork
point `git merge-base refs/pull/<n>/head <remote>/<base>` — 1 is a
squash, the PR's own commit count is a rebase, anything else fails
closed — and the resolver's URLs must be GITHUB URLs — host
literally github.com — so a mirror or local path naming the slug
cannot carry the revert. PR #41 round 14 (threads 3834210476/
3834210484): the resolver validates EVERY fetch and push URL of a
remote (multi-URL endpoints; a stray pushurl beside the canonical
one is triangular, and a mis-pointed dedicated remote is REBUILT
with remove+add because set-url replaces only the first pushurl),
and the single-parent landing is classified by PATCH IDS, not
counts — a squash landing behind expected-1 foreign queue entries
no longer reads as a rebase.

PR #41 round 16 (threads 3834488871/3834400954): the revert branch
is built in a THROWAWAY WORKTREE (git worktree add --detach <tmp> at
the fetched base; every working-tree-mutating step runs git -C <tmp>
— the caller's checkout is never touched), and the push goes through
pr_guard_worktree.push_revert_branch, which REUSES a deterministic
branch whose remote head is already exactly this attempt's revert
commit or takes the first free -<k> suffix when a prior attempt's
pushed branch blocks the plain push. Every gh subprocess runs with
GH_HOST pinned to github.com (thread 3834400946). PR #41 round 20
(thread 3834819191): the worktree NEVER checks out the deterministic
branch name — the caller's checkout may still have it active, and
git refuses one branch in two worktrees — so the revert builds on
the DETACHED HEAD the worktree was created at and the push creates
the remote branch directly (HEAD:refs/heads/<name>, decided at PUSH
time inside push_revert_branch). PR #43 (thread 3835653121): the
reuse rule is widened — SHA equality first, then the revert's CONTENT
SIGNATURE (patch-id of the fetched branch tip vs the freshly-built
revert), so a retry's timestamp-fresh rebuild of the same reversed
merge reuses the pushed branch instead of minting another suffix.

Thread 3836043658 (PR #45 round 7, P1), copy sharpened by thread
3836217635 (PR #45 round 10, P1): the RESULT CONTRACT is distinct
per disposition — guarded_revert/revert_merged_pr return
REVERT_COMPLETED_EXIT (0) when the revert PR was opened, meaning the
AUTOMATIC half COMPLETED and nothing more: the revert PR is OPEN,
the landing is NOT undone, and a human operator MUST merge the
revert PR (thread 3836217635: no copy overclaims the open PR as a
done undo) — and 1 when the revert FAILED at any step (the
manual-revert banner above stands), while
revert_landed_during_cancel passes the identity gate's
IDENTITY_GATE_EXIT (3) through untouched for its no-revert
dispositions. merge_guarded's final handling branches on the codes
(see pr_guard_common.reconciled_exit_summary) so a gated exit is
never reported as a completed revert — round 6 returned 1 for BOTH
shapes and the epilogue printed "the revert above already undid it"
over a landing no revert had touched (a claim round 10 also removed
from the completed arm: an open PR is not an undo). The act's
process exit stays nonzero for every disposition (0 is MERGED
CLEAN's exclusive meaning); the codes distinguish dispositions at
this boundary.

Thread 3835345690 (PR #41 round 27): BOTH revert shapes — the
two-parent `git revert -m 1` here and pr_guard_plan's plain
single-parent revert — run with the FIXED guard identity
(user.name=pr-guard, user.email=pr-guard@users.noreply.github.com)
pinned in the argv via pr_guard_common.with_guard_identity: an
automation checkout with no configured identity makes `git revert`
die with "Author identity unknown" before the revert commit exists,
so the promised automatic revert branch and PR were never created.
They are the revert path's ONLY commit-creating git operations (the
fetch/worktree/probes/push create no commits), and the argv form —
not GIT_AUTHOR_*/GIT_COMMITTER_* env — keeps the identity visible in
revert_failed's verbatim banner (a manual re-run keeps it) and safe
from ambient env overrides.

Thread 3835379480 (PR #41 round 28): the same with_guard_identity
prefix also pins BOTH reverts UNSIGNED — `-c commit.gpgsign=false`
in the config half and `--no-gpg-sign` right after the subcommand —
because an invoking checkout with commit.gpgSign=true but no usable
signing key passes the flag down to `git revert`, which dies
building the signature BEFORE the revert commit exists (the same
never-created automatic revert, one config surface later). The
belt-and-braces pair covers both flag surfaces: the -c overrides
inherited signing config from any scope, the flag states the
unsigned intent on the command line the banner prints verbatim.

PR #41 round 25 (threads 3835145976/3835145981/3835175506/
3835175508), re-aimed by round 26 (thread 3835290443): the
single-parent classifier is RETIRED. The revert below automates
exactly TWO shapes — the two-parent mergeCommit (`git revert -m 1`)
and the single-parent landing whose parent IS the FROZEN PRE-DISPATCH
base tip (pr_guard_plan's two-case plan; the current `<remote>/<base>`
ref can never be the comparison target — the pre-revert base fetch
has already moved it to the landing itself or beyond) — and every
other single-parent landing fails closed to the manual-revert banner
with diagnostics. The frozen tip rides the same threading as the
frozen commit list below. The patch-id/sequence/
author-subject/delta/marker heuristic arms and their banners were
deleted with the classifier; every non-provenance safety rail above
(host pinning, repo pinning, canonical remote, worktree isolation,
branch reuse) stands.
"""

import shlex
import subprocess

from .pr_guard_common import REPO_FLAG
from .pr_guard_common import (
    IDENTITY_GATE_EXIT, REPO_SLUG, REVERT_COMPLETED_EXIT, gh_env,
    with_guard_identity,
)
from .pr_guard_common import LANDED_SHA_RETRY_ATTEMPTS
from .pr_guard_common import read_landed_merge_sha
from .pr_guard_identity import landing_identity_gate
from .pr_guard_plan import single_parent_revert_plan
from .pr_guard_remote import canonical_remote
from .pr_guard_worktree import in_worktree, new_revert_worktree
from .pr_guard_worktree import push_revert_branch, remove_revert_worktree

# Thread 3833360211 (PR #41 round 7): trigger key -> (title phrase,
# body sentence). The title/body are the durable record a reviewer
# acts on, so each of the five paths that reaches guarded_revert names
# WHY it fired instead of the historical always-DANGER copy.
REVERT_TRIGGERS = {
    "danger": (
        "bot finding after merge",
        "the post-merge re-survey found DANGER thread(s) — a bot last "
        "word landed in the survey->merge window (PR #39 thread "
        "3829356723)",
    ),
    "retargeted_base": (
        "landed on retargeted base",
        "the PR was retargeted inside the check->merge window and "
        "landed on a base other than the verified one (thread "
        "3832321698), escaping the gate",
    ),
    "moved_head": (
        "merged an unsurveyed head",
        "the head moved after the merge request and the request "
        "merged content the threads were never surveyed against "
        "(thread 3832522310)",
    ),
    "survey_failed": (
        "post-merge survey failed",
        "the post-merge quiet-period survey could not run to "
        "completion (thread 3832321706), so the landing is unverified",
    ),
    "landed_during_cancel": (
        "merge landed during cancellation",
        "the pending merge request landed while the poll/cancel was "
        "in flight (threads 3832522306/3833073949), bypassing the "
        "destination/head assertions and the quiet-period watch",
    ),
}


# Thread 3832522306: one cancel-verification read, moved HOME to
# pr_guard_common at round 25 (its CANCEL_FIELDS/REPO_FLAG/gh_env
# dependencies all live there; completion, settle, and dequeue import
# it from common now). "OPEN" means the STRONG verdict — state=OPEN
# and no autoMergeRequest pending; "MERGED" the landed one; "PENDING"
# anything readable but not clean; "UNKNOWN" an unreadable/failed
# read. Nothing here can see a QUEUE entry — gh 2.97.0 has no field
# for it; only the delayed re-check or the GraphQL probe in
# pr_guard_completion can catch it merging.


# Thread 3832522306: the cancel verification reporting MERGED means
# the merge landed while the poll/cancel was in flight — report it
# and go straight through the revert path (never "cancelled"). The
# landed metadata is read with the SAME poll fields (the bounded
# read_landed_merge_sha, thread 3834666206's retry semantics, moved
# home to pr_guard_common at round 30); a MERGED read whose
# mergeCommit has not populated yet is a bounded PENDING state, and
# only a persistently empty sha fails closed to the manual-revert
# banner.
# Thread 3835501549 (PR #41 round 30): round-29's pre-existing-merge
# identity check lived ONLY in merge_guarded's reconciliation (after
# the completion poll returns a landing) — a stale invocation on an
# already-merged PR whose completion reads stayed unreadable to the
# timeout, or an operator interrupt during the wait, sent the
# HISTORICAL MERGED observation through THIS function instead, and
# the automatic revert undid a merge this invocation never made
# before the late identity check ever ran. Every cancel/settle/
# interrupt MERGED verdict funnels through here, so the gate lives
# HERE. Thread 3835877364 (PR #45 round 4): the gate is the SHARED
# pr_guard_identity ladder, not just the round-29 trusted arms — a
# FAILED dispatch whose stale-OPEN record persists through the short
# reconcile poll (the historical merge becoming visible only during
# the timeout cancellation or interrupt settlement) still carries
# its identity evidence, so merge_guarded's late gate is never the
# only line of defense: the same evidence threaded down from the
# dispatch decides HERE, before any landed-during-cancel claim or
# revert. Thread 3836600782 (PR #45 round 17, P1): the
# transition_observed flag rounds 8-16 threaded here is RETIRED —
# no client-side observation can attribute a failed dispatch's
# landing (the reviewer's rounds 7-17 chain), so EVERY
# failed-dispatch MERGED verdict on these paths is uniformly
# AMBIGUOUS (manual banner, NO automatic revert); a SUCCESSFUL
# dispatch's landing still reverts (rc 0 bounds it).
def revert_landed_during_cancel(
    pr: int, base: str, commits: list[str] | None = None,
    frozen_base_tip: str = "",
    pre_merged: bool = False, pre_merge_sha: str = "",
    open_merge_sha: str = "", dispatch_ts: float = 0.0,
    dispatch_failed: bool = False,
) -> str | int:
    merge_sha, landed_base = read_landed_merge_sha(pr)
    gated = landing_identity_gate(
        pr, merge_sha, pre_merged, pre_merge_sha, open_merge_sha,
        dispatch_ts, dispatch_failed,
        entry="cancel/settlement",
    )
    if gated is not None:
        # Thread 3836043658 (PR #45 round 7): the gate's
        # IDENTITY_GATE_EXIT flows up UNTOUCHED — merge_guarded's
        # final handling branches on it (a completed revert is 0, a
        # failed one 1) so this no-revert disposition is never
        # reported as a completed revert.
        return gated
    print(
        f"THE MERGE LANDED DURING CANCELLATION: the cancel verification "
        f"reported state=MERGED — the request landed while the poll/cancel "
        f"was in flight (thread 3832522306). REVERTING on the landed base."
    )
    if not merge_sha:
        return (
            f"MERGE LANDED UNVERIFIED: PR #{pr} reports MERGED but exposes "
            f"no mergeCommit even after {LANDED_SHA_RETRY_ATTEMPTS} bounded "
            f"re-reads (thread 3834666206) — the merge MUST be reverted "
            f"manually on {landed_base or base} (direct pushes are "
            f"ruleset-blocked; revert via PR). DO NOT assume MERGED CLEAN."
        )
    return guarded_revert(
        pr, landed_base or base, merge_sha,
        "landed_during_cancel", commits, frozen_base_tip,
    )


# Thread 3832321706: the revert itself must never raise past the act —
# a gh/git call dying mid-revert would leave the same unverified merge
# with NO warning, so the failure prints the explicit manual-revert
# instructions naming the merge SHA. Thread 3833360211 (PR #41
# round 7): the trigger names WHY the revert fired; an unknown key raises
# KeyError HERE, which this same handler turns into the manual
# instructions — never a revert PR carrying a wrong reason.
# Thread 3836043658 (PR #45 round 7, P1): the RESULT CONTRACT —
# REVERT_COMPLETED_EXIT (0) when revert_merged_pr opened the revert
# PR (the AUTOMATIC half completed; the revert PR is OPEN and the
# landing is NOT undone until the operator merges it — thread
# 3836217635, PR #45 round 10), 1 when the revert failed or raised
# (the manual banner above stands). Callers keep the ACT's exit
# nonzero for both (the revert PR still needs a human merge; 0
# stays MERGED CLEAN's exclusive process meaning); the codes
# distinguish dispositions where the integer channel is shared with
# the identity gate's 3.
def guarded_revert(
    pr: int, base: str, merge_sha: str, trigger: str = "danger",
    commits: list[str] | None = None, frozen_base_tip: str = "",
) -> int:
    try:
        return revert_merged_pr(
            pr, base, merge_sha, trigger, commits, frozen_base_tip
        )
    except BaseException as exc:
        print(
            f"AUTOMATIC REVERT FAILED ({type(exc).__name__}: {exc}) — merge "
            f"{merge_sha[:12]} of PR #{pr} MUST be reverted MANUALLY on "
            f"{base} (direct pushes are ruleset-blocked; revert via PR)."
        )
        return 1


# The per-step failure banner shared by every revert step (thread
# 3829356731's manual-instructions shape): the failed command is
# printed verbatim so the operator can resume by hand.
def revert_failed(
    step: list[str], pr: int, base: str, merge_sha: str
) -> int:
    print(
        f"REVERT FAILED at `{' '.join(shlex.quote(p) for p in step)}` "
        f"— merge {merge_sha[:12]} of PR #{pr} MUST be reverted "
        f"manually on {base} (direct pushes are ruleset-blocked; "
        f"revert via PR)."
    )
    return 1


# Thread 3829356731: the protected bases are merge-only under the very
# ruleset this guard installs, so the revert cannot be `git revert &&
# git push` on the base — it lands on an UNPROTECTED revert branch and
# opens an immediate revert PR instead. Thread 3836043658 (PR #45
# round 7, P1): returns REVERT_COMPLETED_EXIT (0) once the revert PR
# is OPEN (the automatic half COMPLETED — thread 3836217635, PR #45
# round 10: the revert PR is OPEN and must be merged by the operator
# before the landing is actually undone; the completion names the
# automated half, never the undo itself) and 1 on every blocked/
# failed step (the manual-revert instructions above stand); the
# CALLER keeps the act's process exit nonzero either way, but the
# distinct codes let merge_guarded's final handling report the
# open-PR action-required truth without ever painting a gated or
# failed one with the same brush. Thread
# 3833360211 (PR #41 round 7): the PR title/body render the ACTUAL
# trigger (REVERT_TRIGGERS), not the historical always-DANGER copy.
def revert_merged_pr(
    pr: int, base: str, merge_sha: str, trigger: str = "danger",
    commits: list[str] | None = None, frozen_base_tip: str = "",
) -> int:
    if not merge_sha:
        print(
            f"REVERT BLOCKED: PR #{pr} exposes no merge SHA — the merge "
            f"MUST be reverted manually on {base}."
        )
        return 1
    # Thread 3833762325 (PR #41 round 10): resolve the CANONICAL
    # remote BEFORE any git step — every fetch/checkout/push below
    # runs against it, never the ambient origin (which may be a
    # fork). No canonical remote is a hard block with the setup
    # instructions; the merge is never left silently unreverted.
    remote = canonical_remote()
    if not remote:
        print(
            f"REVERT BLOCKED: merge {merge_sha[:12]} of PR #{pr} MUST be "
            f"reverted manually on {base} — run the revert from a "
            f"checkout with the canonical repository {REPO_SLUG} "
            f"configured as a git remote (git remote add upstream "
            f"https://github.com/{REPO_SLUG}.git), then re-run (thread "
            f"3833762325: the revert never fetches from or pushes to a "
            f"fork while the surveys target {REPO_SLUG})."
        )
        return 1
    title_why, body_why = REVERT_TRIGGERS[trigger]
    branch = f"revert/pr{pr}-{merge_sha[:7]}"
    # Thread 3834488871 (PR #41 round 16): every working-tree-mutating
    # operation of this revert runs in a THROWAWAY worktree — the
    # caller's staged/unstaged changes are never clobbered by the
    # checkout/revert, and the operator is never left switched onto
    # the revert branch. The base fetch runs FIRST (repo-level: it
    # updates remote-tracking refs only, never the caller's working
    # tree), then the worktree is created AT the fetched base and the
    # branch is built inside it. The plan-building probes in
    # pr_guard_plan stay in the caller checkout — every one of them
    # (rev-parse/merge-base/rev-list/diff-tree/patch-id/fetch) is
    # read-only or .git-only and touches no working tree.
    tmp = new_revert_worktree()

    def failed(step: list[str]) -> int:
        return revert_failed(step, pr, base, merge_sha)

    try:
        # Thread 3834819191 (PR #41 round 20): NO branch checkout —
        # the worktree stays DETACHED at the fetched base (worktree
        # add --detach put HEAD there), the revert builds on the
        # detached HEAD, and push_revert_branch lands it on the
        # remote directly as HEAD:refs/heads/<name>. The deterministic
        # name may be ACTIVE in the caller's checkout (an earlier
        # guard left the operator on that branch), and git refuses to
        # check one branch out in two worktrees — the old `checkout
        # -B` aborted the revert before any commit existed.
        for step in (
            ["git", "fetch", remote, base],
            ["git", "worktree", "add", "--detach", tmp, f"{remote}/{base}"],
        ):
            if subprocess.run(step).returncode != 0:
                return failed(step)
        # Thread 3833540921 (PR #41 round 8): a merge queue configured
        # for squash or rebase lands the PR as a SINGLE-parent commit,
        # so the unconditional `git revert -m 1` fails outright on a
        # squash (-m requires a merge commit) or reverses only the
        # final rebased commit instead of the landing. The landed
        # shape is PROBED after the fetch has put the commit in the
        # local object database: `git rev-parse --verify <sha>^2`
        # exits 0 only when the second parent exists, i.e. a genuine
        # two-parent merge commit.
        two_parent = (
            subprocess.run(
                in_worktree(
                    tmp, ["git", "rev-parse", "--verify", f"{merge_sha}^2"]
                ),
                capture_output=True,
            ).returncode
            == 0
        )
        if two_parent:
            # Threads 3835345690 (round 27) + 3835379480 (round 28):
            # the revert carries the FIXED guard identity AND the
            # unsigned pinning — an automation checkout with no
            # user.name/user.email makes bare `git revert` die with
            # "Author identity unknown", and one with
            # commit.gpgSign=true but no usable signing key dies
            # building the signature — both BEFORE any commit exists.
            revert_step = with_guard_identity(
                ["git", "revert", "-m", "1", "--no-edit", merge_sha]
            )
            shape_note = (
                "a TWO-PARENT merge commit, reverted with "
                "`git revert -m 1 --no-edit` against the mainline parent"
            )
        else:
            # Thread 3833540921 (round 8) + the round-25 contract
            # (threads 3835145976/3835145981/3835175506/3835175508):
            # the single-parent side automates ONLY the landing whose
            # parent IS the current base tip (pr_guard_plan's two-case
            # plan); every other single-parent shape fails closed to
            # the manual banner with the frozen-snapshot diagnostics —
            # None is that banner already printed.
            planned = single_parent_revert_plan(
                pr, base, merge_sha, remote, commits, frozen_base_tip,
            )
            if planned is None:
                return 1
            revert_step, shape_note = planned
        # Thread 3834488871: the revert itself runs INSIDE the worktree.
        revert_step = in_worktree(tmp, revert_step)
        if subprocess.run(revert_step).returncode != 0:
            return failed(revert_step)
        # Thread 3834400954 (PR #41 round 16): read the revert commit
        # this attempt built, then let the reuse/suffix logic decide
        # how it lands on the remote (a prior attempt's pushed branch
        # must never block the retry with a non-fast-forward push).
        head_probe = in_worktree(tmp, ["git", "rev-parse", "HEAD"])
        local_head = probe_worktree_head(head_probe)
        if not local_head:
            return failed(head_probe)
        pushed = push_revert_branch(
            tmp, remote, branch, local_head, failed
        )
        if pushed is None:
            return 1
        created = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--base",
                base,
                "--head",
                pushed,
                "--title",
                f"Revert PR #{pr}: {title_why}",
                "--body",
                (
                    f"Automated revert of merge {merge_sha} (PR #{pr}): "
                    f"{body_why} (thread 3833360211: this names the actual "
                    f"trigger '{trigger}' that reached the revert path). "
                    f"Landed-commit shape (thread 3833540921; the round-25 "
                    f"contract, threads 3835145976/3835145981/3835175506/"
                    f"3835175508 — only the unambiguous landings are "
                    f"automated, everything else fails closed): "
                    f"{shape_note} (the parent count was probed with `git "
                    f"rev-parse --verify {merge_sha}^2` before the revert, "
                    f"and every git operation ran against the canonical "
                    f"remote '{remote}' — thread 3833762325). The revert "
                    f"branch refs/heads/{pushed} was built on a DETACHED HEAD "
                    f"in an ISOLATED temporary worktree (threads 3834488871/"
                    f"3834819191: the caller's checkout is never touched and "
                    f"no LOCAL branch exists to conflict with a name active "
                    f"there) and landed on {remote} by pushing HEAD "
                    f"straight to the ref (sha/content-signature "
                    f"reuse/suffix, threads 3834400954/3835653121). "
                    f"MERGE THIS REVERT IMMEDIATELY, then re-run the review "
                    f"loop."
                ),
            ]
            + REPO_FLAG,
            capture_output=True,
            text=True,
            env=gh_env(),
        )
    finally:
        remove_revert_worktree(tmp)
    if created.returncode != 0:
        print(
            f"REVERT PR FAILED: the revert commit IS pushed on {pushed} "
            f"— open the PR manually (gh pr create exited "
            f"{created.returncode}: {created.stderr.strip()}). Merge "
            f"{merge_sha[:12]} MUST still be reverted."
        )
        return 1
    print(
        f"*** REVERT PR OPENED: {created.stdout.strip()} ***\n"
        f"*** MERGE IT NOW to undo PR #{pr} ({merge_sha[:12]}) on "
        f"{base}. ***"
    )
    return REVERT_COMPLETED_EXIT


# Thread 3834400954: the revert commit this attempt built, read from
# the worktree HEAD — "" on an unreadable probe so the caller fails
# closed (an unknown commit cannot be reuse-checked against remote).
def probe_worktree_head(argv: list[str]) -> str:
    proc = subprocess.run(argv, capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""
