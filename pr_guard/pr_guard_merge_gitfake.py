"""The fake-git half of the merge-act harness (PR #41 round 25).

Split from pr_guard_merge_harness.py at the 250 pure-LOC ceiling:
the harness stood at 249/250 (HOT since the round-11 fixtures split)
and the round-25 two-case contract added the fake's answers for the
PARENT/BASE-TIP probes and the fork/range/marker DIAGNOSTIC probes
(threads 3835145976/3835145981/3835175506/3835175508), so the whole
`git`-argv branch of fake_run moved here verbatim as a factory — the
fixtures precedent (a PLAIN module; importing it adds nothing to
unittest discovery). The factory receives every fixture knob the git
branch closed over; `state["tmp"]` carries the captured worktree path
back to the runner (worktree add records it), and an UNMATCHED argv
returns None exactly as the old fall-through did (the caller's
rc_for tail then governs).

Imports flow ONE way (harness -> gitfake -> fixtures); subprocess
objects are returned, never run — no network.
"""

import subprocess

from .pr_guard_merge_fixtures import BASE_TIP, FORK_SHA, MERGE_SHA
from .pr_guard_merge_fixtures import WALL_NOW

# The canonical remote NAMES the resolver may answer for — the
# base-tip probe reads `<remote>/<base>` for whichever canonical
# remote the checkout resolved (origin, an upstream, or the dedicated
# pr-guard-canonical the triangular repair installs).
CANONICAL_REMOTE_NAMES = ("origin", "upstream", "pr-guard-canonical")


# The fake-git branch of the harness's fake_run (round 25 split).
# `git_answers` (a test's landing_probes fixture) is consulted FIRST;
# then the built-in handlers: worktree add (records the tmp path into
# state), remote -v (the checkout shape), rev-parse (HEAD -> the
# fixture's revert head; `--verify` probes answer their rc via
# rev_rc_for / parent_probe_rc / range_probe_rc with STDOUT shas for
# the round-25 parent (`<merge_sha>^` -> landing_parent) and base-tip
# (`<remote>/<base>` -> base_tip) probes), ls-remote (remote_heads),
# the fail-closed banner's DIAGNOSTIC probes (merge-base -> the
# well-known fork, rev-list of the fork..landing range -> one commit,
# and the marker subject probe -> a marker-free default subject).
# Returns a CompletedProcess for a MATCHED argv, None to fall through
# to the runner's rc_for tail.
def make_git_fake(
    git_answers,
    base: str,
    landing_parent: str,
    base_tip: str,
    parent_probe_rc: int,
    range_probe_rc: int,
    rev_rc_for,
    remote_v: str,
    revert_head: str,
    remote_heads,
    state: dict,
):
    def handle(argv, stdin):
        if git_answers is not None:
            answered = git_answers(argv, stdin)
            if answered is not None:
                # Thread 3835846317 (PR #45 round 3): a 3-tuple answer
                # carries its own STDERR — the transient-failure
                # fixtures must serve probe failures whose rc alone
                # cannot tell "missing parent" from "git broke".
                stderr = answered[2] if len(answered) > 2 else ""
                return subprocess.CompletedProcess(
                    argv, answered[0], stdout=answered[1], stderr=stderr
                )
        # Thread 3834488871 (PR #41 round 16): the revert's git steps
        # run as `git -C <tmp> ...` — normalize the prefix away so the
        # round-8/10 rev-parse fixtures keep matching on the
        # subcommand.
        g = ["git", *argv[3:]] if argv[1:2] == ["-C"] else argv
        if g[:3] == ["git", "worktree", "add"]:
            state["tmp"] = argv[argv.index("--detach") + 1]
        if g[:3] == ["git", "remote", "-v"]:
            # Thread 3833880605 (PR #41 round 11): match the LISTING
            # argv exactly — `git remote add` / `git remote set-url`
            # must fall through so repair-success/repair-failure
            # fixtures can drive them via the runner's rc_for.
            return subprocess.CompletedProcess(
                argv, 0, stdout=remote_v, stderr=""
            )
        if g[:2] == ["git", "rev-parse"]:
            if g[2:3] == ["HEAD"]:
                # Thread 3834400954: the revert commit this attempt
                # built, per the fixture.
                return subprocess.CompletedProcess(
                    argv, 0, stdout=revert_head, stderr=""
                )
            if g[2:3] in (["HEAD^"], ["FETCH_HEAD^"]):
                # Thread 3835714798 (PR #43 round 2): the ANCESTRY
                # probes of the patch-id reuse — the local revert's
                # PARENT (HEAD^: the worktree sits on the fetched
                # base, whose tip the base-tip fixture answers) and
                # the fetched remote candidate's tip PARENT
                # (FETCH_HEAD^, right after remote_patch_id's fetch).
                # The DEFAULT parent equals the base tip: the
                # ordinary reusable shape (an earlier retry built the
                # same revert on the same base); a FOREIGN-ancestry
                # fixture overrides via git_answers (consulted
                # first), and an unreadable override fails closed in
                # the implementation.
                return subprocess.CompletedProcess(
                    argv, 0, stdout=base_tip + "\n", stderr=""
                )
            if g[2:] == ["--verify", "--quiet", "FETCH_HEAD^2"]:
                # Thread 3835760162 (PR #45 round 1) + threads
                # 3835846317/3835877368 (rounds 3-4): the reuse
                # candidate's MERGE-TIP probe — the DEFAULT is REAL
                # git's single-parent failure shape under the
                # rc-only rule (the QUIET --verify form exits
                # EXACTLY 1 for the missing second parent, printing
                # nothing — verified on git 2.55 — so locale can
                # never move the classification); a merge-tip
                # fixture overrides via git_answers (consulted
                # first) with rc 0 + a sha.
                return subprocess.CompletedProcess(
                    argv, 1, stdout="", stderr=""
                )
            # Thread 3833540921 (parent-count `^2`) vs the round-25
            # two-case contract (thread 3835145981): the PARENT probe
            # (`<merge_sha>^` answers landing_parent) and BASE-TIP
            # probe (`<remote>/<base>` answers base_tip) — the
            # contract's defaults are EQUAL (the automated shape).
            # Plain OIDs / the PR head ref answer rc 0 by default
            # (objects present); only a rev_rc_for fixture makes them
            # missing.
            rev = g[3]
            stdout = ""
            if rev == f"{MERGE_SHA}^":
                stdout = landing_parent + "\n"
            elif (
                "/" in rev
                and rev.endswith(f"/{base}")
                and rev.partition("/")[0] in CANONICAL_REMOTE_NAMES
            ):
                stdout = base_tip + "\n"
            if rev_rc_for is not None:
                rc = rev_rc_for(rev)
            else:
                rc = parent_probe_rc if rev.endswith("^2") else (
                    range_probe_rc if rev.endswith("^") else 0
                )
            return subprocess.CompletedProcess(
                argv, rc, stdout=stdout, stderr=""
            )
        if g[:2] == ["git", "merge-base"] and g[2:4] == [
            "refs/pull/39/head",
            f"origin/{base}",
        ]:
            # Round 25: the fail-closed banner's fork-point DIAGNOSTIC
            # (the PR ref "exists" per the plain-rev default, so no
            # ensuring fetch fires in the default shape).
            return subprocess.CompletedProcess(
                argv, 0, stdout=FORK_SHA + "\n", stderr=""
            )
        if g[:3] == ["git", "rev-list", "--no-merges"] and g[3:4] == [
            f"{FORK_SHA}..{MERGE_SHA}"
        ]:
            # Round 25: the banner's range-count diagnostic — the
            # default landing is ONE commit past the fork.
            return subprocess.CompletedProcess(
                argv, 0, stdout=MERGE_SHA + "\n", stderr=""
            )
        if g[:2] == ["git", "log"] and "--format=%ct" in g:
            # Thread 3835846318 (PR #45 round 3): the landing
            # identity gate's committer-date read — the DEFAULT is a
            # FRESH landing (ct just AFTER the fake wall clock's
            # dispatch time), the ordinary outcome every earlier
            # failed-dispatch fixture assumed when its reconcile poll
            # observed MERGED; the round-35 suites override the date
            # via git_answers for the pre-existing/ambiguous shapes.
            return subprocess.CompletedProcess(
                argv, 0, stdout=f"{int(WALL_NOW) + 60}\n", stderr=""
            )
        if g[:2] == ["git", "log"] and "--no-walk" in g:
            # Round 25: the banner's MARKER diagnostic — the default
            # subject carries NO trailing "(#N)".
            fmt = next(a for a in g if a.startswith("--format="))
            named = g[g.index(fmt) + 1:]
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout="".join(
                    f"{sha}|Queue Bot "
                    "<queue-bot@example.invalid>|queued change\n"
                    for sha in named
                ),
                stderr="",
            )
        if g[:2] == ["git", "ls-remote"]:
            # Thread 3834400954: the remote branch head probe —
            # absent branches (the default) answer "".
            head = (remote_heads or {}).get(
                g[3].removeprefix("refs/heads/"), ""
            )
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=f"{head}\t{g[3]}\n" if head else "",
                stderr="",
            )
        return None

    return handle
