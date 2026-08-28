"""The temporary-worktree mechanics and branch-reuse push for the
revert path.

Split from pr_guard_revert.py at the PR #41 round-16 fixes: revert
stood near the 250 pure-LOC ceiling and BOTH round-16 revert findings
land in its git mechanics — thread 3834488871 (isolate the revert
from the caller's worktree) and thread 3834400954 (reuse or uniquify
an already-pushed revert branch). Imports flow ONE way (revert ->
worktree; subprocess/tempfile/shutil only below).

Thread 3834488871 (PR #41 round 16): the revert used to run
`git checkout -B` / `git revert` / `git push` directly in the
INVOKING checkout — staged or conflicting unstaged changes aborted
the revert before a PR could open, and even a clean run left the
operator switched onto the generated revert branch. Every
working-tree-mutating git operation now runs inside a THROWAWAY
worktree (`git worktree add --detach <tmp>`, `git -C <tmp> ...`,
`git worktree remove --force`): the caller's checkout is never
touched, and the revert branch is created in the temporary worktree.

Thread 3834400954 (PR #41 round 16): the revert branch name is
DETERMINISTIC (revert/pr<N>-<sha7>), so a prior run whose push
succeeded but whose `gh pr create` failed transiently leaves the
remote branch behind, and the rerun's fresh revert commit makes the
plain push non-fast-forward — the retry could never reach PR
creation. Before pushing, `git ls-remote` decides: a remote head
IDENTICAL to this attempt's revert commit means the pushed branch is
already exactly right (skip the push, open the PR against it); a
DIFFERENT head gets a uniqueness suffix (-2, -3, ... first free).

Thread 3834819191 (PR #41 round 20): the worktree NEVER checks out
the deterministic branch name. The invoking checkout may still HAVE
it active (an earlier guard left the operator on that branch), and
git refuses to check a branch out in two worktrees at once — the
`checkout -B` aborted the automatic revert before any commit
existed. The worktree stays DETACHED (worktree add --detach already
put HEAD at the fetched base), the revert builds on the detached
HEAD, and the push creates the remote branch directly from it:
`git push <remote> HEAD:refs/heads/<name>` — no local branch is
created anywhere, so a caller-active name can never block the build
and the remote name is decided at PUSH time. The round-17 local
namespace scan (thread 3834590328) left with the rename it guarded:
a refspec push never touches local refs, so local residue cannot
block a suffix either.

Thread 3835653121 (PR #43): reuse also matches by CONTENT
SIGNATURE. A retry REBUILDS the revert with a fresh committer
timestamp, so its sha differs from the pushed branch's even though
both reverse the same merge — the sha-equality reuse check could
never recognize it and every retry minted another -2, -3, ... toward
the 50-name budget. Each candidate is now checked by sha equality
FIRST, then by `git patch-id --stable` of the fetched branch tip's
first-parent diff against the freshly-built local revert's — the
same reversed patch is reusable regardless of sha.

Thread 3835714798 (PR #43 round 2): the content-signature arm also
proves ANCESTRY. patch-id compares only the tip's first-parent diff,
not the branch history, so a collaborator could precreate the
deterministic name as `unrelated changes + a matching revert`; the
patch-id arm alone reused that branch and the urgent PR carried the
foreign history. A candidate is reusable only when its tip's PARENT
is the SAME base this attempt's revert was built on (rev-parse
FETCH_HEAD^ == the local revert's parent) — a mismatch (or any
unreadable stage) takes the suffix path instead.

Thread 3835760162 (PR #45 round 1): the ancestry arm additionally
rejects MERGE tips. `FETCH_HEAD^` is parent ONE (gitrevisions: `^`
alone = first parent), so a merge commit whose first parent IS the
local base still passed the probe while its SECOND parent carried
the foreign history — a candidate with the expected base as parent
one, foreign commits through parent two, and a matching first-parent
patch-id was reused. Reuse now also requires the fetched tip to be a
SINGLE-PARENT commit; a merge tip takes the suffix path like any
other unproven candidate.

Thread 3835846317 (PR #45 round 3): the merge-tip probe FAILS
CLOSED. `rev-parse` exits NONZERO for the missing second parent AND
for every transient git failure alike, so round 1's boolean rc==0
test could not tell a PROVEN single-parent tip from an UNREADABLE
one — a probe that errored read "not a merge", reuse proceeded to
the ancestry check, and a transiently-unreadable candidate that was
in fact a merge could carry its foreign second-parent history into
the urgent PR. The probe is now a TRI-STATE: rc 0 = the second
parent resolved (a merge); rc 128 WITH git's missing-parent stderr
signature = PROVEN single-parent; anything else (wrong rc, a
transient failure's stderr) = UNREADABLE. Only the PROVEN
single-parent tip is reusable — a merge or an unreadable probe both
take the suffix path.

Thread 3835877368 (P2, PR #45 round 4): the stderr signature was a
LOCALE API. Under a non-English LC_MESSAGES git localizes the
rev-parse fatal, so a normal single-parent candidate failed the
signature match and every candidate read UNREADABLE — reuse never
fired and each timestamp-changing retry minted another suffix
toward the 50-name budget. The probe now runs `git rev-parse
--verify --quiet FETCH_HEAD^2` and discriminates by EXIT CODE
ALONE, documented against real git (verified on git 2.55): plain
`--verify` on a missing revision prints the LOCALIZED "fatal:
Needed a single revision" and exits 128, while `--quiet` SUPPRESSES
the diagnostic entirely and exits exactly 1 — there is no stderr
left to localize, and locale cannot move an exit code. rc 0 = a
merge; rc 1 = PROVEN single parent; anything else (128 fatals,
transient failures) = UNREADABLE. The subprocess env pins
LC_ALL=C as belt-and-braces so any future diagnostic-bearing
variant of the probe stays English.
"""

import os
import shutil
import subprocess
import tempfile

# Thread 3834400954: the suffix probe budget — a remote that keeps
# answering occupied names for dozens of candidates is pathological
# (or the probe is broken); fail closed instead of looping forever.
SUFFIX_ATTEMPTS_MAX = 50

# Thread 3835877368 (PR #45 round 4): the single stable locale the
# parent-count probe runs under — exit codes are locale-independent
# (the discrimination below), but pinning LC_ALL keeps any stderr a
# future probe variant emits in the English shape the banners quote.
PROBE_LOCALE = "C"


# Thread 3834488871: one scratch directory for the throwaway worktree
# (mkdtemp yields an EMPTY directory, which `git worktree add`
# accepts; the real cleanup is worktree remove + rmtree below).
def new_revert_worktree() -> str:
    return tempfile.mkdtemp(prefix="pr-guard-revert-")


# Thread 3834488871: re-aim any planned git step at the worktree —
# ["git", "revert", ...] becomes ["git", "-C", <tmp>, "revert", ...],
# so the caller's checkout is never mutated.
def in_worktree(tmp: str, step: list[str]) -> list[str]:
    return ["git", "-C", tmp, *step[1:]]


# Thread 3834488871: drop the worktree after the revert attempt —
# `git worktree remove --force` (the revert leaves the tree dirty,
# and a FAILED attempt must not strand it either), then rmtree any
# remains. Best-effort: cleanup failures never mask the revert's own
# disposition (the admin data is pruned by git itself over time).
def remove_revert_worktree(tmp: str) -> None:
    subprocess.run(["git", "worktree", "remove", "--force", tmp])
    shutil.rmtree(tmp, ignore_errors=True)


# Thread 3834400954: the remote head of refs/heads/<branch>, "" when
# the branch does not exist, None when ls-remote itself is unreadable
# (the caller fails closed — an unknown remote state must never read
# as "branch free, push away").
def remote_branch_head(remote: str, branch: str) -> str | None:
    ref = f"refs/heads/{branch}"
    proc = subprocess.run(
        ["git", "ls-remote", remote, ref],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1] == ref:
            return fields[0]
    return ""


# Thread 3835653121 (PR #43): the CONTENT SIGNATURE of a commit —
# `git patch-id --stable` over its first-parent diff. patch-id hashes
# the patch TEXT (paths + hunks) and ignores commit metadata
# entirely, so a retry's timestamp-fresh rebuild of the same reversed
# merge yields the SAME id as the pushed original. "" on any
# unreadable stage so the caller fails closed (no signature, no
# reuse).
def commit_patch_id(tmp: str, revision: str) -> str:
    diff = subprocess.run(
        in_worktree(tmp, ["git", "diff", f"{revision}^", revision]),
        capture_output=True,
        text=True,
    )
    if diff.returncode != 0:
        return ""
    pid = subprocess.run(
        in_worktree(tmp, ["git", "patch-id", "--stable"]),
        input=diff.stdout,
        capture_output=True,
        text=True,
    )
    if pid.returncode != 0 or not pid.stdout.strip():
        return ""
    return pid.stdout.strip().split(" ", 1)[0]


# Thread 3835653121: fetch the remote candidate's TIP and sign it the
# same way — the refspec has no destination, so it writes FETCH_HEAD
# only (no remote-tracking ref, no working-tree touch in the caller's
# checkout). "" on a failed fetch/probe reads as "unknown signature"
# — never reusable.
def remote_patch_id(tmp: str, remote: str, branch: str) -> str:
    fetch = in_worktree(
        tmp, ["git", "fetch", remote, f"refs/heads/{branch}"]
    )
    if subprocess.run(fetch, capture_output=True).returncode != 0:
        return ""
    return commit_patch_id(tmp, "FETCH_HEAD")


# Thread 3835714798 (PR #43 round 2): one in-worktree rev-parse — ""
# on any unreadable probe so every caller fails closed. Serves the
# LOCAL revert's parent (HEAD^: the fetched base the worktree built
# the revert on) and, right after remote_patch_id's fetch, the remote
# candidate's tip parent (FETCH_HEAD^ — no intervening fetch runs
# inside branch_carries_revert, so FETCH_HEAD is still the fetched
# candidate).
def worktree_rev_parse(tmp: str, revision: str) -> str:
    proc = subprocess.run(
        in_worktree(tmp, ["git", "rev-parse", revision]),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


# Thread 3835653121: does the remote branch at `head` carry THIS
# attempt's revert? SHA equality FIRST (a prior attempt pushed the
# identical commit), then the content signature — the fetched tip's
# patch-id equals the freshly-built local revert's. Thread 3835714798
# (PR #43 round 2): the signature arm ADDITIONALLY proves ANCESTRY —
# patch-id sees only the tip's first-parent diff, so a branch whose
# tip reverses the same merge but whose PARENT carries unrelated
# commits also matches by signature alone; reuse additionally requires
# the fetched tip's parent (FETCH_HEAD^) to BE the local revert's
# parent (the base the revert was built on), and an unreadable parent
# probe reads as a mismatch (fail closed — never reuse). Thread
# 3835760162 (PR #45 round 1): `FETCH_HEAD^` names parent ONE only,
# so a MERGE tip with the base as first parent and foreign history on
# the second still passed; a fetched tip that is not PROVEN
# single-parent (fetch_head_single_parent) is therefore NOT reusable
# — the suffix path, never the urgent PR over foreign history. Thread
# 3835846317 (PR #45 round 3): "not proven" includes the UNREADABLE
# probe. Thread 3835877368 (PR #45 round 4): the proof is rc-ONLY
# (see fetch_head_single_parent) — locale can no longer turn every
# candidate unreadable.
def branch_carries_revert(
    tmp: str, remote: str, branch: str, head: str, local_head: str,
    local_patch_id: str, local_base: str,
) -> bool:
    if head == local_head:
        return True
    if not local_patch_id or not local_base:
        return False
    if remote_patch_id(tmp, remote, branch) != local_patch_id:
        return False
    if fetch_head_single_parent(tmp) is not True:
        return False
    return worktree_rev_parse(tmp, "FETCH_HEAD^") == local_base


# Thread 3835760162 (PR #45 round 1), reworked by thread 3835846317
# (PR #45 round 3) and thread 3835877368 (PR #45 round 4): the
# fetched candidate tip's SINGLE-PARENT probe —
# `git rev-parse --verify --quiet FETCH_HEAD^2`. rc 0 means the
# second parent RESOLVED (a merge tip). rc 1 is the only LEGITIMATE
# failure — the quiet form of --verify exits EXACTLY 1 for a
# revision that cannot resolve (verified on git 2.55: plain
# --verify prints the LOCALIZED "fatal: Needed a single revision"
# at exit 128, --quiet prints NOTHING and exits 1), so the commit
# provably has no parent two with NO stderr to localize. Every
# other shape — a 128 fatal, a transient git failure — returns None
# (UNREADABLE), and the caller fails closed: an unproven tip is
# never reused no matter how well it signatures. The env pins
# LC_ALL=C (PROBE_LOCALE) belt-and-braces.
def fetch_head_single_parent(tmp: str) -> bool | None:
    proc = subprocess.run(
        in_worktree(
            tmp,
            ["git", "rev-parse", "--verify", "--quiet", "FETCH_HEAD^2"],
        ),
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": PROBE_LOCALE},
    )
    if proc.returncode == 0:
        return False
    if proc.returncode == 1:
        return True
    return None


# Thread 3834400954, reworked by thread 3834819191 (round 20), widened
# by thread 3835653121 (PR #43): land this attempt's DETACHED-HEAD
# revert commit on the remote — reuse the deterministic branch when
# its remote head is EXACTLY this commit or CARRIES this revert's
# content (patch-id over the fetched tip), otherwise push
# `HEAD:refs/heads/<name>` directly (no local branch is created in
# the worktree, so a branch name ACTIVE in the caller's checkout can
# never block the build, and a first free -<k> suffix sidesteps a
# prior attempt's different head) — and return the branch name the PR
# must be opened against. Returns None after the caller's failure
# banner (fail(step)) when any probe or push fails.
def push_revert_branch(
    tmp: str,
    remote: str,
    branch: str,
    local_head: str,
    fail,
) -> str | None:
    probe = ["git", "ls-remote", remote, f"refs/heads/{branch}"]
    head = remote_branch_head(remote, branch)
    if head is None:
        fail(probe)
        return None
    if head == local_head:
        print(
            f"REVERT BRANCH REUSED: refs/heads/{branch} on {remote} "
            f"already carries exactly this revert commit "
            f"({local_head[:12]}) — skipping the push (thread "
            f"3834400954) and opening the PR against the existing "
            f"branch."
        )
        return branch
    if not head:
        step = [
            "git", "-C", tmp, "push", remote,
            f"HEAD:refs/heads/{branch}",
        ]
        if subprocess.run(step).returncode != 0:
            fail(step)
            return None
        return branch
    # Thread 3835653121: the deterministic name is occupied by a
    # DIFFERENT commit — sign this attempt's revert once and read its
    # PARENT (the base the worktree built it on), then let the
    # sha-then-patch-id-plus-ancestry rule judge every occupied
    # candidate (thread 3835714798).
    local_pid = commit_patch_id(tmp, "HEAD")
    local_base = worktree_rev_parse(tmp, "HEAD^")
    if branch_carries_revert(
        tmp, remote, branch, head, local_head, local_pid, local_base
    ):
        print(
            f"REVERT BRANCH REUSED: refs/heads/{branch} on {remote} "
            f"carries this attempt's revert CONTENT — patch-id "
            f"{local_pid[:12]} matches over the different commit "
            f"{head[:12]}, the tip's parent IS the base this "
            f"revert was built on, and the tip is PROVEN "
            f"SINGLE-PARENT (threads 3835653121 + 3835714798 + "
            f"3835760162 + 3835846317 + 3835877368) — skipping the push and "
            f"opening the PR against the existing branch."
        )
        return branch
    for k in range(2, 2 + SUFFIX_ATTEMPTS_MAX):
        candidate = f"{branch}-{k}"
        probe_k = ["git", "ls-remote", remote, f"refs/heads/{candidate}"]
        head_k = remote_branch_head(remote, candidate)
        if head_k is None:
            fail(probe_k)
            return None
        if head_k == local_head:
            # Thread 3835587498 (PR #41 round 31): an earlier retry
            # already pushed THIS exact revert to the suffix and then
            # failed before the PR was created — the same match rule
            # as the deterministic name REUSES it (skip the push, open
            # the PR against the existing branch) instead of treating
            # the exact branch as an ordinary collision, minting
            # further suffixes, and eventually exhausting the 50-name
            # budget while a perfectly reusable branch sits remote.
            print(
                f"REVERT BRANCH REUSED: refs/heads/{candidate} on "
                f"{remote} already carries exactly this revert commit "
                f"({local_head[:12]}) — an earlier attempt pushed this "
                f"identical revert to the suffix without completing "
                f"the PR (thread 3835587498) — skipping the push and "
                f"opening the PR against the existing branch."
            )
            return candidate
        if head_k and branch_carries_revert(
            tmp, remote, candidate, head_k, local_head, local_pid,
            local_base,
        ):
            print(
                f"REVERT BRANCH REUSED: refs/heads/{candidate} on "
                f"{remote} carries this attempt's revert CONTENT — "
                f"patch-id {local_pid[:12]} matches over the "
                f"different commit {head_k[:12]}, the tip's "
                f"parent IS the base this revert was built on, and "
                f"the tip is PROVEN SINGLE-PARENT (an earlier retry "
                f"REBUILT the same reversed merge under a new "
                f"timestamp and pushed it here without completing "
                f"the PR; threads "
                f"3835653121/3835714798/3835760162/3835846317/3835877368) — "
                f"skipping the push and opening the PR against the "
                f"existing branch."
            )
            return candidate
        if head_k:
            continue
        print(
            f"REVERT BRANCH SUFFIXED: refs/heads/{branch} exists on "
            f"{remote} at a DIFFERENT commit ({head[:12]}) — a prior "
            f"attempt's pushed revert (thread 3834400954), a "
            f"same-content tip over FOREIGN ancestry (thread "
            f"3835714798), a MERGE tip whose second parent carries "
            f"foreign history (thread 3835760162), or a merge-tip "
            f"probe that could not PROVE a single parent — rc 1 of "
            f"`rev-parse --verify --quiet FETCH_HEAD^2` is the only "
            f"legitimate failure, by EXIT CODE alone (threads "
            f"3835846317/3835877368) — none is this attempt's "
            f"revert — so this attempt pushes its detached-HEAD "
            f"revert commit DIRECTLY as refs/heads/{candidate} "
            f"(thread 3834819191: no local branch is created, so a "
            f"name active in the caller's worktree can never block "
            f"the push)."
        )
        push = [
            "git", "-C", tmp, "push", remote,
            f"HEAD:refs/heads/{candidate}",
        ]
        if subprocess.run(push).returncode != 0:
            fail(push)
            return None
        return candidate
    print(
        f"REVERT BLOCKED: no free uniqueness suffix for refs/heads/"
        f"{branch} on {remote} within {SUFFIX_ATTEMPTS_MAX} attempts "
        f"(thread 3834400954) — the revert commit IS built locally in "
        f"the temporary worktree; push it and open the PR manually."
    )
    return None
