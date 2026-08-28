"""Shared constants and the fatal-error helper for the pr_guard modules.

Split from pr_guard.py at the 250 pure-LOC ceiling (PR #36 round 2,
thread 3827503028).
"""

import json
import os
import subprocess
import sys
import time

REPO_OWNER = "RachaelsDen"
REPO_NAME = "UR-lorebook"
REPO_SLUG = f"{REPO_OWNER}/{REPO_NAME}"

# Thread 3833073952 (PR #41): every `gh pr ...` subprocess in the
# pr_guard family appends this flag, so a GH_REPO env override pointing
# at a fork/mirror/unrelated repository cannot redirect the CLI half of
# the gate while the REST/GraphQL half hardcodes this repository (a
# same-number/same-SHA PR in the other repo could otherwise be
# validated here but merged/reverted there). The `gh api` call sites
# need no pin: their REST paths are absolute (repos/{owner}/{repo}/…)
# and the GraphQL queries bind owner/name as variables, so GH_REPO
# cannot redirect them either way.
REPO_FLAG = ["-R", REPO_SLUG]

# Thread 3834400946 (PR #41 round 16): gh resolves `[HOST/]OWNER/REPO`
# against GH_HOST, so `-R RachaelsDen/UR-lorebook` under a GHE-naming
# GH_HOST targets THAT host's identically named repository — the gate
# could survey and merge there while the canonical-remote validation
# (github.com URLs only) keeps the revert on github.com. Every gh
# subprocess in the family therefore runs with GH_HOST forced to
# github.com via gh_env() (the explicit env beats the ambient var),
# and the interactive modes hard-block on a foreign host up front
# (blocked_gh_host).
GH_HOST_PIN = "github.com"


# Thread 3834400946: the env every gh subprocess runs under — a copy
# of the ambient environment with GH_HOST pinned to github.com, so an
# exported GHE host cannot redirect ANY gh call (pr view/merge/create
# and gh api alike — gh api reads GH_HOST too).
def gh_env() -> dict[str, str]:
    return {**os.environ, "GH_HOST": GH_HOST_PIN}


# Thread 3834400946: the startup check for merge/harden/pre-merge —
# an exported GH_HOST naming anything but github.com is a HARD BLOCK
# (an identically named repository on that host could be surveyed and
# merged while every revert push targets github.com); the operator
# must unset it or point gh at github.com. An unset or empty GH_HOST
# (and any capitalization of github.com) passes.
def blocked_gh_host() -> bool:
    host = os.environ.get("GH_HOST") or ""
    if not host or host.strip().lower() == GH_HOST_PIN:
        return False
    print(
        f"BLOCKED: GH_HOST={host.strip()} points gh at a host other "
        f"than {GH_HOST_PIN} (thread 3834400946) — '-R {REPO_SLUG}' "
        f"resolves against GH_HOST's host, so an identically named "
        f"repository there could be surveyed and merged here while "
        f"the revert path pushes to {GH_HOST_PIN} only. Unset GH_HOST "
        f"or point gh at {GH_HOST_PIN} (export GH_HOST={GH_HOST_PIN}), "
        f"then re-run."
    )
    return True


# Thread 3835345690 (PR #41 round 27): the fixed author/committer
# identity every COMMIT-CREATING git operation in the guard family
# runs under. An automation checkout (CI runner, container, cron) can
# carry NO user.name/user.email — local or global — and `git revert`
# then dies with "Author identity unknown" BEFORE building the revert
# commit, so the promised automatic revert branch and PR never appear.
# The survey of the revert path: the two `git revert` shapes are its
# ONLY commit-creating git operations (the base fetch, worktree add,
# rev-parse/ls-remote probes, and the push create no commits; gh pr
# merge runs server-side), so both are prefixed with this identity.
# ARGV `-c`, not GIT_AUTHOR_*/GIT_COMMITTER_* env: the family's
# pinning style puts safety-critical config where the recorded argv
# and revert_failed's verbatim banner show it (a manual re-run of the
# printed command keeps the identity), the tests assert the argv
# directly, and argv flags cannot be shadowed by an ambient
# GIT_AUTHOR_*/GIT_COMMITTER_* export the way env inheritance can.
GUARD_USER_NAME = "pr-guard"
GUARD_USER_EMAIL = "pr-guard@users.noreply.github.com"

# Thread 3835379480 (PR #41 round 28): the config half of the
# unsigned pinning — a signing-forcing checkout (commit.gpgSign=true
# in ANY config scope) with no usable signing key makes `git revert`
# die BUILDING THE SIGNATURE before the revert commit exists, the
# same never-created automatic revert as the round-27 identity
# failure. The reviewer-verified flag surface (`git revert -h`)
# rides the subcommand below; this constant keeps the config half
# importable beside the identity so the fixtures track one source of
# truth.
GUARD_GPGSIGN_FALSE = "commit.gpgsign=false"


# Threads 3835345690 (round 27) + 3835379480 (round 28): prefix a git
# step with the fixed guard identity AND the unsigned pinning —
# ["git", "revert", ...] becomes ["git", "-c", "user.name=pr-guard",
# "-c", "user.email=...", "-c", "commit.gpgsign=false", "revert",
# "--no-gpg-sign", ...] (global options precede the subcommand, so
# pr_guard_worktree.in_worktree's `-C <tmp>` insertion ahead of them
# stays valid git syntax). The no-sign pinning is BELT-AND-BRACES
# across BOTH flag surfaces because they fail independently: the
# `-c commit.gpgsign=false` overrides signing config inherited from
# ANY scope (local/global/system) for this one invocation, and the
# `--no-gpg-sign` right after the subcommand states the unsigned
# intent on the command line itself — visible in revert_failed's
# verbatim banner, so a manual re-run of the printed command stays
# unsigned too. Read-only probes take NO identity and NO override —
# no commit is created, so ambient signing config cannot fail them.
def with_guard_identity(step: list[str]) -> list[str]:
    return [
        "git",
        "-c",
        f"user.name={GUARD_USER_NAME}",
        "-c",
        f"user.email={GUARD_USER_EMAIL}",
        "-c",
        GUARD_GPGSIGN_FALSE,
        step[1],
        "--no-gpg-sign",
        *step[2:],
    ]


# Thread 3828399604: a receipt is proof a FINDING was handled — any
# outside User's follow-up ("this is still broken") must NOT count.
# Receipts are trusted only from the maintainer accounts listed here
# (the repository owner runs this gate and posts the fix receipts).
RECEIPT_AUTHORS = frozenset({REPO_OWNER})

# PR #40 round 3 (thread 3832522310): headRefOid rides the completion
# poll so the FINAL head is re-asserted against the surveyed one.
# Shared by pr_guard_merge (the poll) and pr_guard_revert (the
# landed-during-cancel fetch reads the SAME fields), so the list has
# exactly one home. Thread 3836501981 (PR #45 round 15, P1) added
# updatedAt to both lists for the transition corroboration; thread
# 3836600782 (round 17, P1) RETIRED it with the machinery — no
# consumer remains, so the lists carry exactly what their readers use.
MERGE_POLL_ATTEMPTS = 30
MERGE_POLL_INTERVAL = 10.0
POLL_FIELDS = "state,mergeCommit,baseRefName,headRefOid"
CANCEL_FIELDS = "autoMergeRequest,state"

# PR #41 round 8 (thread 3833540913): the cancel attempt budget and
# re-check delay moved here from pr_guard_completion when the queue
# settlement split into pr_guard_settle — the cancel loop (completion)
# and the converged-cancel banner (settle) both cite the re-check
# delay, and common is the constants home the family already shares.
CANCEL_ATTEMPTS = 3
CANCEL_RECHECK_SECS = 5.0

# PR #41 round 11: the settle-watch window constants moved here from
# pr_guard_settle (which stood at 247/250 pure LOC, HOT) so the
# terminal-banner builders could split into pr_guard_settle_banners
# WITHOUT an import cycle — settle's watch logic and the banners both
# render them, and common is already the shared constants home.
QUEUE_WATCH_ATTEMPTS = 6
QUEUE_WATCH_INTERVAL = 10.0
ABSENT_SETTLE_WINDOW_SECS = 60.0
ABSENT_SETTLE_INTERVAL = 5.0

# Thread 3834093639 (PR #41 round 13): the queue watch's window in
# SECONDS — attempts x interval stays the nominal definition (6 probes
# at a 10s cadence), but the watch itself is now DEADLINE-measured
# against this value, because a counted loop spans only attempts-1
# sleeps: with fast API reads the round-12 watch ended at ~50s while
# its banners claimed the full 60s window.
QUEUE_WATCH_WINDOW_SECS = QUEUE_WATCH_ATTEMPTS * QUEUE_WATCH_INTERVAL

# Thread 3835501550 (PR #41 round 30): the SHORTER re-settlement
# window entered when an EXPIRED settling watch saw the entry REAPPEAR
# and the round-29 re-probe then reads it ABSENT again — the entry may
# be mid-consumption (removed to merge right now), so one fresh bounded
# window watches for the MERGED flip instead of enforcing the spent
# outer deadline over a possibly-stale OPEN. It renders in the
# converged/terminal banners, so it lives in the constants home they
# already share.
ABSENT_RESETTLE_WINDOW_SECS = 30.0

# Thread 3835501550 (PR #41 round 30): the settling watch's SENTINEL
# return for "the entry REAPPEARED inside the window" — the watch's
# None meant "keep watching with QUEUED semantics", but round 30 must
# distinguish a REAPPEARANCE (which can earn ONE bounded re-settlement
# when the outer deadline is spent) from weaker-evidence Nones (which
# never do). It is identity-checked with `is`, never printed, and
# lives here because BOTH owners need it one-way: settle (the watch
# itself) and dequeue (the post-dequeue settling consumer) — a home in
# either would cycle the settle -> dequeue import.
REAPPEARED = object()

# Thread 3834590319 (PR #41 round 17): the bounded dequeue RETRY
# budget — the round-15 one-shot guard permanently suppressed every
# later dequeue attempt once any report existed, so a TRANSIENT
# mutation failure (or an entry automation re-enqueued during the
# settlement watch) rode out the whole window to the manual banner
# while still live. A probe that still reads QUEUED re-attempts the
# removal until this budget is spent; the terminal banner then reports
# the attempt count.
DEQUEUE_ATTEMPTS_MAX = 3

# Thread 3834666206 (PR #41 round 18): the landed-during-cancel revert
# re-reads the merge SHA with the SAME bounded pending semantics the
# completion poll applies to MERGED-with-empty-mergeCommit (thread
# 3834590326) — GitHub can report state=MERGED before the nullable
# mergeCommit is readable, and the old single read fell straight to the
# manual banner, leaving a landed merge without the automatic revert.
# Bounded re-reads at the cancel re-check cadence (CANCEL_RECHECK_SECS)
# — a persistently empty sha keeps the manual banner.
LANDED_SHA_RETRY_ATTEMPTS = 3


# Thread 3834093639 (PR #41 round 13): the shared form of the
# deadline-watch sleep discipline (the quiet watch's thread-3832522300
# and the settling watch's thread-3833540916 idiom, previously inline
# in each module): sleep at the probe cadence but never PAST the
# deadline — the final sleep is clamped to the REMAINING window so the
# probe after it lands at/after the deadline and the full window
# elapses even with instantaneous reads. Returns the seconds to sleep
# (never negative).
def deadline_clamped_sleep(deadline: float, interval: float) -> float:
    return max(0.0, min(interval, deadline - time.monotonic()))


def die(msg: str) -> None:
    print(f"pr_guard: {msg}", file=sys.stderr)
    raise SystemExit(2)


# Thread 3833073952 (PR #41): GH_REPO pointing at a fork/mirror/
# unrelated repo can no longer break the guard (every gh pr command is
# -R-pinned, every gh api path is absolute), but the operator should
# still KNOW their environment disagrees with the surveyed repository.
# The '[HOST/]OWNER/REPO' forms both count as matching.
def warn_repo_override() -> None:
    override = os.environ.get("GH_REPO")
    if override is None:
        return
    parts = override.strip().strip("/").split("/")
    if "/".join(parts[-2:] if len(parts) >= 2 else parts) == REPO_SLUG:
        return
    print(
        f"WARNING: GH_REPO={override} does not name {REPO_SLUG} (thread "
        f"3833073952) — every gh pr command in this act is pinned with "
        f"'-R {REPO_SLUG}' and every gh api path/query names the "
        f"repository explicitly, so the override cannot redirect the "
        f"guard; it is reported because the operator should confirm the "
        f"environment is the intended one."
    )


# Thread 3832522306 (PR #40 round 3): one cancel-verification read,
# moved HOME here from pr_guard_revert at PR #41 round 25 (its
# CANCEL_FIELDS/REPO_FLAG/gh_env dependencies all live here;
# completion, settle, and dequeue import it from this module — the
# one-way import chain kept revert free of back-imports). "OPEN"
# means the STRONG verdict — state=OPEN and no autoMergeRequest
# pending; "MERGED" the landed one; "PENDING" anything readable but
# not clean; "UNKNOWN" an unreadable/failed read. Nothing here can
# see a QUEUE entry — gh 2.97.0 has no field for it; only the
# delayed re-check or the GraphQL probe in pr_guard_completion can
# catch it merging. Thread 3836501981 (PR #45 round 15, P1) made
# this return (verdict, updatedAt) for the transition corroboration;
# thread 3836600782 (round 17, P1) retired that machinery, so the
# verdict is a plain string again.
def read_pending_state(pr: int) -> str:
    proc = subprocess.run(
        ["gh", "pr", "view", str(pr), "--json", CANCEL_FIELDS] + REPO_FLAG,
        capture_output=True,
        text=True,
        env=gh_env(),
    )
    if proc.returncode == 0:
        try:
            data = json.loads(proc.stdout)
            state = str(data.get("state") or "")
            if state == "MERGED":
                return "MERGED"
            if state == "OPEN" and not data.get("autoMergeRequest"):
                return "OPEN"
            return "PENDING"
        except ValueError:
            pass
    return "UNKNOWN"


# Thread 3832522310: the merge-request-time head capture, moved HOME
# here from pr_guard_merge at the PR #41 round-29 fixes (the
# read_pending_state precedent: its REPO_FLAG/gh_env dependencies all
# live here; merge imports it from this module, never the inverse).
# Returns "" on any read failure so the caller BLOCKS fail-closed (an
# unreadable head cannot be proven equal to the surveyed one).
def read_merge_request_head(pr: int) -> str:
    proc = subprocess.run(
        ["gh", "pr", "view", str(pr), "--json", "headRefOid"] + REPO_FLAG,
        capture_output=True,
        text=True,
        env=gh_env(),
    )
    if proc.returncode == 0:
        try:
            return str(json.loads(proc.stdout).get("headRefOid") or "")
        except ValueError:
            pass
    return ""


# Threads 3835450367 (round 29) + 3835501549 (round 30): the
# pre-existing-merge PREDICATE, extracted beside its banner at the
# round-30 fixes. Round 29 snapshotted the pre-dispatch merge identity
# in merge_guarded but reconciled it in ONE place (after the completion
# poll returns a landing); round 30 threads the same identity into
# every cancel/settle/interrupt MERGED verdict, so the decision itself
# — an already-merged pre-dispatch state, or an observed mergeCommit
# EQUAL to the snapshot's — must have exactly one home for both gates.
def is_pre_existing_merge(
    observed_sha: str, pre_merged: bool, pre_merge_sha: str
) -> bool:
    return pre_merged or bool(
        pre_merge_sha and observed_sha == pre_merge_sha
    )


# Thread 3836043658 (PR #45 round 7, P1): the guarded-merge act's
# distinct RESULT CODES. guarded_revert/revert_merged_pr return 0
# (REVERT_COMPLETED_EXIT) when the AUTOMATIC half of the revert
# COMPLETED — the revert PR is OPEN and must be merged by a human
# operator before the landing is actually undone (thread 3836217635,
# PR #45 round 10: the code names the automated half's completion,
# never the undo itself) — and 1 when the revert FAILED (the
# manual-revert banner stands); the landing identity gate (and every
# banner it prints) returns 3 (IDENTITY_GATE_EXIT) for its NO-REVERT
# dispositions — pre-existing or ambiguous, the manual-check banner
# already printed. The codes flow up through revert_landed_during_
# cancel -> cancel_pending_merge -> wait_for_merge_completion as
# ints, and merge_guarded's final handling branches on them so an
# identity-gate exit is never reported as a completed revert (round
# 6 returned 1 for BOTH and merge_guarded printed "the revert above
# already undid it" over a gated no-revert exit). The ACT's process
# exit stays nonzero for every disposition — 0 remains MERGED
# CLEAN's exclusive meaning; the codes distinguish dispositions at
# the internal boundary, where the conflation lived.
REVERT_COMPLETED_EXIT = 0
IDENTITY_GATE_EXIT = 3


# Thread 3835450367 (PR #41 round 29), shared at round 30 (thread
# 3835501549): the PRE-EXISTING MERGE banner — printed with NO revert
# path, identically on the reconciliation arm (merge_guarded, after
# the completion poll) and the cancel/settle/interrupt arms
# (revert_landed_during_cancel): the historical merge is legitimate
# until a human surveys it, so it is never auto-reverted by an
# invocation whose dispatch did not land it. Thread 3836043658
# (PR #45 round 7): the return value is the identity gate's
# NO-REVERT disposition code, not a bare 1 — see REVERT_COMPLETED_EXIT.
def pre_existing_merge_banner(
    pr: int, pre_merged: bool, pre_merge_sha: str, observed_sha: str
) -> int:
    identity = (
        "state=MERGED before the dispatch"
        if pre_merged
        else f"merge commit {pre_merge_sha[:12]}"
    )
    print(
        f"PRE-EXISTING MERGE: PR #{pr} was already merged before "
        f"this invocation (thread 3835450367) — the pre-dispatch "
        f"snapshot recorded {identity} and the observed landing "
        f"{observed_sha[:12] or 'unreadable'} is that same historical "
        f"merge, so nothing was dispatched by us; survey it as a "
        f"post-merge check or exit cleanly if it is the known merge. "
        f"No automatic revert runs (our dispatch did not land it); "
        f"exiting nonzero for the operator's survey."
    )
    return IDENTITY_GATE_EXIT


# Thread 3836043658 (PR #45 round 7, P1), copy corrected by thread
# 3836217635 (PR #45 round 10, P1): merge_guarded's
# reconciliation epilogue — the final handling of an int result from
# the completion wait BRANCHES on the distinct result codes so each
# exit renders its own truthful summary line: an identity-gate exit
# reports the manual banner WITHOUT claiming any revert PR exists, a
# completed revert reports the revert PR as OPEN AND REQUIRING THE
# OPERATOR'S MERGE (never as already undoing the landing — the
# automatic half only OPENED the PR; thread 3836217635: an operator
# following the old "already undid it" summary could leave the
# unsafe merge live, believing it reverted), and a failed revert
# reports that NOTHING was undone. The summary only renders when the
# merge command itself failed (merge_rc != 0) — the "ORIGINAL MERGE
# ERROR" framing names the failed dispatch whose accepted request
# landed during reconciliation (thread 3833073949).
def reconciled_exit_summary(disposition: int, merge_rc: int) -> None:
    if merge_rc == 0:
        return
    if disposition == IDENTITY_GATE_EXIT:
        print(
            f"ORIGINAL MERGE ERROR: gh pr merge exited {merge_rc}; the "
            f"landing observed during reconciliation was classified by "
            f"the IDENTITY GATE above (thread 3836043658) — NO automatic "
            f"revert ran and NO revert PR exists: the gate's manual-check "
            f"banner above stands as the operative instruction, and the "
            f"act exits nonzero for the operator's manual survey (never "
            f"a completed-revert claim over a gated exit)."
        )
        return
    if disposition == REVERT_COMPLETED_EXIT:
        # Thread 3836217635 (PR #45 round 10, P1): the completed
        # code means the AUTOMATIC half completed — the revert PR is
        # OPEN, and the landing is NOT undone until an operator
        # merges it. The old copy ("the revert above already undid
        # it") overclaimed an open PR as a done undo, so an operator
        # following the summary could leave the unsafe merge live.
        print(
            f"ORIGINAL MERGE ERROR: gh pr merge exited {merge_rc}; the "
            f"request HAD been accepted — it landed during "
            f"reconciliation and the automatic revert OPENED ITS PR "
            f"(threads 3833073949/3836217635): the REVERT PR IS OPEN "
            f"— ACTION REQUIRED: an OPERATOR must merge that revert "
            f"PR before the landing is undone (the unsafe merge "
            f"itself stays live on the base until then; the "
            f"automatic half alone only opened the PR, it did not "
            f"and cannot merge it — direct pushes are "
            f"ruleset-blocked)."
        )
        return
    print(
        f"ORIGINAL MERGE ERROR: gh pr merge exited {merge_rc}; the "
        f"AUTOMATIC REVERT FAILED — NOTHING was undone (thread "
        f"3836043658): the manual-revert instructions printed above "
        f"stand; the landing is NOT reverted until a human completes "
        f"them."
    )


# Thread 3834666206 (PR #41 round 18), moved HOME here from
# revert_landed_during_cancel at the round-30 fixes (thread
# 3835501549 — the read_pending_state precedent again: pr_guard_revert
# stood at 245/250 pure LOC and the round-30 identity gate lands in the
# same function). The bounded landed-sha re-read with the completion
# poll's thread-3834590326 pending semantics: GitHub can report
# state=MERGED before the nullable mergeCommit is readable, so the
# read RETRIES at the cancel recheck cadence before it is believed and
# only a persistently empty sha fails closed. Returns
# (merge_sha, landed_base), either "" when never readable.
def read_landed_merge_sha(pr: int) -> tuple[str, str]:
    merge_sha = landed_base = ""
    for attempt in range(1, LANDED_SHA_RETRY_ATTEMPTS + 1):
        proc = subprocess.run(
            ["gh", "pr", "view", str(pr), "--json", POLL_FIELDS] + REPO_FLAG,
            capture_output=True,
            text=True,
            env=gh_env(),
        )
        if proc.returncode == 0:
            try:
                data = json.loads(proc.stdout)
                landed_base = str(data.get("baseRefName") or "")
                merge_sha = str(
                    (data.get("mergeCommit") or {}).get("oid") or ""
                )
            except ValueError:
                pass
        if merge_sha:
            break
        print(
            f"MERGE COMMIT UNREADABLE: PR #{pr} reports MERGED with no "
            f"readable mergeCommit (thread 3834666206) — bounded re-read "
            f"{attempt}/{LANDED_SHA_RETRY_ATTEMPTS} at the cancel recheck "
            f"cadence; the sha normally populates within seconds (thread "
            f"3834590326's finding), and a persistently empty sha fails "
            f"closed to the manual banner."
        )
        if attempt < LANDED_SHA_RETRY_ATTEMPTS:
            time.sleep(CANCEL_RECHECK_SECS)
    return merge_sha, landed_base


# Thread 3833762320 (PR #41 round 10): one settling probe's
# autoMergeRequest read, moved HOME here from pr_guard_settle at the
# round-30 fixes (the same read-home precedent — settle needed the
# pure-LOC headroom for thread 3835501550's re-settlement, and the
# read's CANCEL_FIELDS/REPO_FLAG/gh_env dependencies all live here
# already). "MERGED" — the state flipped to landed; "AUTO" — state
# OPEN with a NON-NULL autoMergeRequest (someone re-enabled auto-merge
# after the initial disable); "OPEN" — open with auto-merge still gone
# (the clean evidence); "OTHER"/"UNKNOWN" — weaker or unreadable
# evidence the caller fails closed on, never converges. Thread
# 3836501981 (PR #45 round 15, P1) made this return (verdict,
# updatedAt) for the transition corroboration; thread 3836600782
# (round 17, P1) retired that machinery, so the verdict is a plain
# string again.
def read_auto_merge(pr: int) -> str:
    proc = subprocess.run(
        ["gh", "pr", "view", str(pr), "--json", CANCEL_FIELDS] + REPO_FLAG,
        capture_output=True,
        text=True,
        env=gh_env(),
    )
    if proc.returncode == 0:
        try:
            data = json.loads(proc.stdout)
            state = str(data.get("state") or "")
            if state == "MERGED":
                return "MERGED"
            if data.get("autoMergeRequest"):
                return "AUTO"
            if state == "OPEN":
                return "OPEN"
            return "OTHER"
        except ValueError:
            pass
    return "UNKNOWN"


# Thread 3832660859: one completion poll's read, shared by the bounded
# loop, the post-loop final check, AND the settling watch's per-probe
# state re-read (thread 3833251675, PR #41 round 6) — one POLL_FIELDS
# fetch with exactly one home, so every state read in the family reads
# the SAME fields. Its home moved settle -> common at the round-30
# fixes (thread 3835501549) with the other reads, because imports must
# flow one way and BOTH the completion poll and the settling watch
# consume it (completion -> settle -> revert -> common — neither may
# import the other for it). Returns (state, landed_base, merge_sha,
# landed_head) — anything unreadable stays "" so the verdict fails
# closed. Thread 3836501981 (PR #45 round 15, P1) added updatedAt to
# the return for the transition corroboration; thread 3836600782
# (PR #45 round 17, P1) retired that machinery and the field with it.
def read_landed_state(pr: int) -> tuple[str, str, str, str]:
    state = landed_base = merge_sha = landed_head = ""
    proc = subprocess.run(
        ["gh", "pr", "view", str(pr), "--json", POLL_FIELDS] + REPO_FLAG,
        capture_output=True,
        text=True,
        env=gh_env(),
    )
    if proc.returncode == 0:
        try:
            data = json.loads(proc.stdout)
            state = str(data.get("state") or "")
            landed_base = str(data.get("baseRefName") or "")
            landed_head = str(data.get("headRefOid") or "")
            merge_sha = str((data.get("mergeCommit") or {}).get("oid") or "")
        except ValueError:
            pass
    return state, landed_base, merge_sha, landed_head


# Thread 3836600782 (PR #45 round 17, P1): the transition arming/
# credit helper (pr_guard_transition.apply_transition_read, rounds
# 11-16, with its shared TransitionEvidence holder) is DELETED —
# the reviewer's rounds 7-17 counter-example chain proved no
# client-side observation of GitHub's REST cache can attribute a
# failed dispatch's landing, so the failed path no longer observes
# for attribution AT ALL (see pr_guard_identity's uniform AMBIGUOUS
# disposition).
