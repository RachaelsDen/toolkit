#!/usr/bin/env python3
"""pr_guard.py — atomic merge-time review-thread gate for RachaelsDen/UR-lorebook.

FAILURE MODE GUARDED (observed 2026-08-20 on PRs #32/#35): the review bot
(chatgpt-codex-connector) posted its final review rounds in the poll->merge
window and post-merge (#32 final round 01:59:57Z — the resolve loop saw 21
threads while the PR held 26, proving those rounds were never fetched; #35
final round 05:56:58Z, minutes after merge, during deploy). Both merges
proceeded blind over unanswered findings (13 threads, 3 P1) because thread
state was polled in a command SEPARATE from `gh pr merge`, and the resolve
loop resolved threads without verifying a human receipt. The M5 vault note
on PR #12 predicted this class: any non-atomic check->merge sequence leaves
a window the bot can win. This tool closes it.

IMPLEMENTATION SPLIT (PR #36 round 2, thread 3827503028 — the 250
pure-LOC ceiling): pr_guard_threads.py (GraphQL fetch + classification +
survey + resolve mutation), pr_guard_rulesets.py (REST + the server gate),
pr_guard_common.py (shared constants); this file is the CLI only.

THREAD CLASSIFICATION (every review thread, GraphQL, paginated first:100):
  resolved   isResolved — already closed.
  receipted  unresolved + LAST comment authored by a HUMAN (actor type
             User, outside the bot allowlist) — our fix/receipt reply is
             the final word on the thread.
  DANGER     unresolved + last comment NOT proven human: any bot (actor
             type Bot — Dependabot/Copilot/renamed apps fail closed even
             outside the allowlist, thread 3827503034), an allowlisted
             User-shaped bot, an organization/mannequin, or an unknown or
             deleted author. PR #36 round 1 (thread 3827397510):
             isOutdated NO LONGER softens this — the diff hunk moving
             does not prove the defect was fixed, so an outdated thread
             without a receipt is DANGER too (survey prints an
             [outdated] flag so a human can triage it).

Bot allowlist (belt for User-shaped bot accounts): chatgpt-codex-connector,
github-actions[bot], renovate[bot].

MODES
  survey <pr>
      Print each thread's classification (labelled by the thread's first
      comment databaseId — the numeric id used in plans and receipts) plus a
      summary count line. Always exits 0: it is a report, not a gate.
      PR #48 (vault note 'Unified Realms/Notes/Codex Review Bot Reaction
      Signal.md'): survey also prints the BOT REACTION line beside the
      summary — the review bot's PR reaction (THUMBS_UP = review complete;
      EYES = actively reviewing; none = not started/stale), the cheap
      wait signal. Informational ONLY and fail-open: thread state stays
      the merge authority.

  wait <pr> [--timeout-secs N]
      PR #48 (vault note 'Unified Realms/Notes/Codex Review Bot Reaction
      Signal.md', user-taught + API-verified 2026-08-26): the codex
      review bot (chatgpt-codex-connector[bot]) reacts ON the PR itself
      — THUMBS_UP = review COMPLETE + passed; EYES = review ACTIVELY in
      progress; none = not started/stale. The reaction is the DONE/
      ACTIVE signal: this mode polls ONLY that cheap single-endpoint
      read every 5s (be polite) until a terminal state or the timeout
      (default 600s; --timeout-secs overrides), printing each state
      change — REPLACING the orchestrator's blind sleep-poll loops.
      User-taught refinements #2 (vault note section 'User-taught
      refinements #2'): the bot REMOVES its EYES at round end — +1
      when it passed, NOTHING when it found feedback — so a
      transition from a verified EYES to a NONE that persists through
      the next probe is ALSO terminal: exit 3 (WAIT FINDINGS —
      survey the threads now: fix + receipt + re-wait). A cold NONE
      (no EYES variant ever observed) lasting >= 10s prints the
      '@codex review' trigger HINT exactly once (the bot may have
      failed to start; a HINT only — the tool never posts comments)
      and keeps polling. Exit codes: 0 = a THUMBS_UP the wait itself
      WATCHED the round reach (a +1 already present at start must
      first transition away — EYES, marker-driven stale, or none —
      and back, else timeout; thread 3867897766); 1 = timeout;
      2 = usage error (a failed read is never a done signal: it
      prints UNREADABLE and keeps polling under the deadline);
      3 = findings (EYES → NONE confirmed). PROTOCOL BOUNDARY: the
      reaction NEVER authorizes a merge by itself — thread state
      (survey/pre-merge) remains the merge authority, and the
      post-merge quiet-period watch still guards the landed tree.
      --accept-standing (user request 2026-08-28): the opt-in fast
      path for ALREADY-PASSED PRs — a standing DONE-classified
      THUMBS_UP exits 0 immediately (the default wait holds it to
      the full timeout: the round-5 rule refuses an unobserved +1,
      and the round-25 rule withholds when no folded review names
      the head — EVERY zero-findings pass). The explicit opt-in is
      the authority for the observation and review-evidence gates;
      the +1's own staleness CLASSIFICATION still applies (a +1
      predating the head push or the boundary markers reads
      THUMBS_UP_STALE and holds). Accepted risk: a standing pass
      may predate an unposted new round — thread state stays the
      merge authority.

  harden <pr>
      PR #36 round 1 (thread 3827397508): survey+merge is two processes —
      `&&` sequences them, it does not make them atomic, so the bot can
      still land a thread between the last GraphQL response and the merge
      request. harden closes that window SERVER-side: it ensures an ACTIVE
      repository ruleset whose pull_request rule requires review-thread
      resolution (required_review_thread_resolution). PR #39 (thread
      3829356731): the ruleset covers exactly the PROTECTED BASES —
      refs/heads/main, refs/heads/dev (mirroring live ruleset 21137845,
      rescoped by PR #40 thread 3832660865 after refs/heads/release/**
      matched release branches USED AS PR HEADS — PR #35 ran from
      release/m6-to-main — making review-fix pushes to them impossible)
      — because the old every-branch wildcards made PR head branches
      merge-only and authors could not push review fixes; a mid-flight
      retarget is caught by pre-merge/merge's base PINNING instead.
      Refuses bases outside the protected set. This also makes the
      protected bases merge-only-via-PR (the house git workflow).
      Idempotent; re-running on an already-hardened base is a no-op
      (a re-run PATCHes the ruleset by its lookup name).

  pre-merge <pr>
      The gate. Runs the survey (any DANGER thread => exit 1) AND verifies
      the harden ruleset is ACTIVE on the base branch, excluded refs
      notwithstanding (missing => exit 1, fail closed): the snapshot check
      and the server enforcement must compose — the snapshot catches
      unanswered findings early, the server gate owns the race window.
      PR #36 round 5 (thread 3827843314): the ruleset only requires
      resolution of threads that already EXIST, so a head swapped after
      the survey could merge unreviewed — pre-merge prints the surveyed
      head SHA and the merge MUST bind to it with gh's
      --match-head-commit (a late push aborts the merge instead).
      MUST be run ATOMICALLY in the SAME shell command as the merge:

          python3 -m pr_guard pre-merge <pr> \
              && gh pr merge <pr> --merge --match-head-commit <sha>

  resolve <pr>
      After receipts land: resolve ONLY receipted threads (unresolved
      whose last comment is human — outdated or not; thread 3827397510
      removed the old outdated-auto-resolve: outdated threads need
      receipts too). REFUSES (exit 1, resolves nothing) while any DANGER
      thread remains. PR #36 round 3 (thread 3827635810): each target is
      RE-FETCHED immediately before its mutation and the receipt must
      still be the last comment (a bot follow-up that landed after the
      survey aborts the whole pass), and a final audit re-surveys so
      anything that landed mid-pass surfaces as DANGER, never after the
      merge. PR #36 round 4 (thread 3827768016): the expected last
      comment id is preserved THROUGH the mutation and re-verified
      after it (the final audit alone cannot catch a follow-up landing
      inside the mutate window — resolved threads classify as resolved);
      on drift the thread is REOPENED so the server ruleset blocks the
      merge again. PR #49 round 11 (thread 3868979526, P2): the final
      audit survey runs BANNERLESS (reaction=False) — it is a
      decision-bearing snapshot (its DANGER check gates RESOLVE DONE),
      so the reaction banner's bounded informational read may never
      sit between it and the verdict; the OPENING survey keeps the
      human-facing banner.

  merge <pr> <head-sha> <base>
      Thread 3828735200: the guarded merge ACT. Re-verifies the PR is
      still at pre-merge's head+base, re-checks the ruleset gate, then
      re-surveys and dispatches `gh pr merge --merge
      --match-head-commit <head>` in the SAME process — the final
      thread fetch and the merge request are one act, closing the
      shell-sequencing window a bot follow-up on an already-resolved
      thread could win. pre-merge's CLEAN output names this command.
      PR #39 (thread 3829356723): one process is still not atomic — a
      bot reply landing on an already-RESOLVED thread between the final
      survey and the merge request passes both this act and the server
      ruleset — so after the merge the SAME invocation re-surveys, and
      any DANGER thread triggers an automatic revert (a revert PR via
      gh, since direct pushes to the protected bases are
      ruleset-blocked) and exits 1. The residual survey->merge window
      is narrowed and backstopped, not closed; only a server-side gate
      is truly atomic. PR #40 round 1: the merge request exiting 0 may
      only have enabled auto-merge/queued the PR, so the act POLLS
      `gh pr view --json state,mergeCommit,baseRefName` (30 x 10s)
      until state == MERGED before surveying (thread 3832321683 —
      timeout fails closed with the manual-revert warning); the poll
      also re-asserts baseRefName equals the verified base, because
      GitHub's merge API accepts no base lock and --match-head-commit
      pins only the head (thread 3832321698 — a retarget reverts on
      the landed base); and a post-merge survey that dies fails closed
      through the same revert path (thread 3832321706). PR #40 round
      2: a poll timeout first CANCELS the pending auto-merge/queue
      entry and verifies the cancel before failing closed (thread
      3832418151); the post-merge backstop is a QUIET-PERIOD WATCH —
      a re-survey every 60s for a bounded 15 minutes by default
      (`--quiet-secs <n>` overrides; 0 collapses it to the single
      PR #39 snapshot) with progress per cycle, reverting the moment
      any DANGER appears, and MERGED CLEAN only after the FULL window
      passes clean (thread 3832418158 — a bot round landing after the
      window is beyond any client-side gate; the server-side gap
      remains open). PR #40 round 3: the watch is DEADLINE-based —
      first survey immediate, a final survey ALWAYS at/after the
      deadline (a cycle-counted watch spans only cycles-1 sleeps;
      thread 3832522300); the poll-timeout cancel verifies BOTH the
      auto-merge and merge-queue contingencies (disable +
      autoMergeRequest null + OPEN, re-checked after a short delay —
      gh 2.97.0 exposes no queue field — reverting immediately if the
      merge landed during cancellation; thread 3832522306); and the
      merge-request-time headRefOid is captured BEFORE dispatch while
      the completion poll re-asserts the PR's FINAL head against the
      surveyed head once MERGED — a push while auto-merge was pending
      merged unsurveyed content and now reverts (thread 3832522310).
      PR #41: a FAILED merge command is an UNKNOWN outcome, not a
      proven refusal — the act reconciles with the same (shorter)
      completion poll and continues the ordinary post-merge path if
      the request had been accepted anyway, surfacing the original
      error only when nothing landed (thread 3833073949); the
      poll-timeout cancel settles the merge-queue contingency
      explicitly (GraphQL mergeQueueEntry probe + a bounded watch —
      gh 2.97.0 exposes no dequeue API, so a live entry is monitored
      and escalated to the manual instructions; thread 3833073940);
      and every gh pr command is pinned with -R RachaelsDen/UR-lorebook
      so a GH_REPO override cannot split the guard across two
      repositories (merge/harden warn loudly when it is set to
      something else; thread 3833073952). harden additionally
      MIGRATES the legacy '(all bases)'/'(dev)'-named rulesets by
      PATCH instead of POSTing a duplicate beside them (thread
      3833111358).

Exit codes: 0 ok/clean; 1 gate BLOCKED or resolve refusal; 2 usage/API error.
"""

import shlex
import sys

from .pr_guard_common import blocked_gh_host
from .pr_guard_merge import DEFAULT_QUIET_SECS, merge_guarded
from .pr_guard_reaction import DEFAULT_WAIT_TIMEOUT_SECS, wait_reaction
from .pr_guard_repo import configure, repo_flag_value
from .pr_guard_repo import parse_repo_slug, resolve_repo_target
from .pr_guard_rulesets import default_branch, fetch_gate_rulesets, gate_covers
from .pr_guard_rulesets import gh_rest_pr, harden
from .pr_guard_threads import (
    classify,
    refetch_thread,
    resolve_thread,
    survey,
    unresolve_thread,
)

USAGE = (
    "usage: pr_guard.py {survey|harden|pre-merge|resolve} <pr-number>\n"
    "       pr_guard.py merge <pr-number> <head-sha> <base-branch> "
    "[--quiet-secs <n>]\n"
    "       pr_guard.py wait <pr-number> [--timeout-secs <n>] "
    "[--accept-standing] — poll ONLY "
    "the review-bot reaction (THUMBS_UP = done, EYES = active, none =\n"
    "       not started / findings-after-EYES); exits 0 on a THUMBS_UP "
    "the wait WATCHED the round reach (a +1 already present at\n"
    "       start must first transition away — EYES, marker-driven "
    "stale, or none — and back, else timeout; thread 3867897766),\n"
    "       3 on EYES → NONE confirmed (review completed WITH "
    "findings — survey the threads: fix + receipt + re-wait), 1 on\n"
    "       timeout, 2 on usage. --accept-standing: the opt-in fast "
    "path for already-passed PRs — a standing DONE-classified\n"
    "       THUMBS_UP exits 0 immediately, bypassing the observation "
    "and review-evidence gates (the staleness classification\n"
    "       still applies); the accepted risk: a standing pass may "
    "predate an unposted new round — thread state stays the merge\n"
    "       authority. A cold NONE (no EYES variant ever "
    "observed) past 10s prints the '@codex review' trigger HINT\n"
    "       exactly once (the bot may have failed to start) and keeps "
    "polling. The reaction is the DONE/ACTIVE signal — thread\n"
    "       state stays the merge authority, and the post-merge "
    "quiet-period watch still guards the landed tree (the "
    "design-history note, 'User-taught refinements #2')\n"
    "       The optional global --repo OWNER/NAME precedes any mode: "
    "the target repository. Without it the PR_GUARD_REPO env var is\n"
    "       consulted, then the CWD's origin remote — and the tool "
    "refuses to run (exit 2) when none of the three resolves."
)


def pre_merge(pr: int) -> int:
    # Thread 3834400946 (PR #41 round 16): a foreign GH_HOST hard
    # blocks the gate — the surveys and the pinned merge command must
    # target github.com, not an identically named repository on a
    # GHE host.
    if blocked_gh_host():
        return 1
    # Thread 3828232326: the head (and base) are captured BEFORE the
    # survey and re-verified after — reading them only at the end
    # would print an UNSURVEYED SHA for --match-head-commit when a
    # push lands mid-survey (the ruleset only covers threads that
    # already exist).
    opening = gh_rest_pr(pr)
    surveyed_head = str(opening["head"]["sha"])
    surveyed_base = str(opening["base"]["ref"])
    threads = survey(pr)
    danger = [t for t in threads if t.classification == "DANGER"]
    if danger:
        print(f"BLOCKED: {len(danger)} unanswered finding(s) — DO NOT MERGE.")
        return 1
    # Thread 3827397508: the snapshot above cannot be atomic with the
    # merge — require the SERVER-side gate so the race window is closed
    # by GitHub itself, not by command sequencing.
    pr_data = gh_rest_pr(pr)
    base = str(pr_data["base"]["ref"])
    head = str(pr_data["head"]["sha"])
    if head != surveyed_head:
        print(
            f"BLOCKED: PR head moved during the survey "
            f"({surveyed_head[:12]} -> {head[:12]}) — the surveyed "
            f"threads belong to an older head. Re-run pre-merge."
        )
        return 1
    # Thread 3828399598: --match-head-commit binds only the HEAD — a
    # retargeted PR keeps its head while moving to an ungated base, so
    # the base is pinned to the surveyed one too.
    if base != surveyed_base:
        print(
            f"BLOCKED: PR was retargeted during the survey "
            f"({surveyed_base} -> {base}) — the ruleset was verified "
            f"for the OLD base. Re-run pre-merge."
        )
        return 1
    gate = gate_covers(fetch_gate_rulesets(), base, default_branch())
    if gate is None:
        print(
            f"BLOCKED: no ACTIVE branch-target review-thread-resolution "
            f"ruleset covers refs/heads/{base} — a tag/push-target "
            f"ruleset never counts (thread 3834666208), and the snapshot "
        f"alone leaves the poll->merge race open. Run: python3 "
        f"-m pr_guard harden {pr}"
        )
        return 1
    # Thread 3828399593: a bot follow-up on an ALREADY-RESOLVED thread
    # changes neither the head nor the ruleset's view (still resolved),
    # so the opening survey cannot see it — a final re-survey directly
    # before CLEAN catches it as DANGER (resolved threads whose last
    # word is untrusted classify DANGER). Residual window: between this
    # fetch and the merge command — pre-merge must run ATOMICALLY with
    # the merge (the documented && pattern).
    # Thread 3868158297 (PR #49 round 7, P1): the closing survey is
    # DECISION-BEARING — its list feeds the late-findings gate that
    # prints CLEAN — so it runs bannerless (reaction=False), the same
    # decision-surface rule as the guarded merge act and the quiet
    # watch (threads 3867757449/3867897759): the banner's bounded 15s
    # informational read between this snapshot and the go/no-go could
    # let a bot follow-up land on an already-resolved thread while the
    # gate consumed the stale clean list. The banner's home is the
    # human-facing informational surveys (the OPENING one above
    # included — its snapshot is re-verified by this fresh fetch).
    closing = survey(pr, reaction=False)
    late = [t for t in closing if t.classification == "DANGER"]
    if late:
        print(
            f"BLOCKED: {len(late)} finding(s) arrived during pre-merge "
            f"(resolved-thread follow-up?) — re-run after receipting."
        )
        return 1
    # Thread 3827843314: the ruleset only requires resolution of threads
    # that EXIST — a head swapped after this survey could merge before
    # the bot reviews the new commits. Thread 3828495560: gh binds only
    # the HEAD server-side. Thread 3828735200: the survey and the merge
    # must be one act — CLEAN names the guarded MERGE mode, which
    # re-runs this entire gate and dispatches the merge request in the
    # SAME process (thread 3828643312: the base rides as an argv
    # operand, never through shell interpolation).
    print(
        f"CLEAN: every unresolved thread carries a receipt AND ruleset "
        f"'{gate.get('name')}' (base {base}) blocks server-side if "
        f"anything lands before the merge. Merge ATOMICALLY with:\n"
        f"  python3 -m pr_guard merge {pr} {head} "
        f"{shlex.quote(base)}"
    )
    return 0


def resolve(pr: int) -> int:
    threads = survey(pr)
    danger = [t for t in threads if t.classification == "DANGER"]
    if danger:
        print(
            f"REFUSED: {len(danger)} DANGER thread(s) still lack receipts "
            f"({', '.join(t.label for t in danger)}). Post receipts first "
            "(pre-merge must report CLEAN); nothing was resolved."
        )
        return 1
    targets = [t for t in threads if t.classification == "receipted"]
    if not targets:
        print("NOTHING TO RESOLVE: no unresolved receipted threads.")
        return 0
    resolved = 0
    for thread in targets:
        # Thread 3827635810: a bot follow-up can land after the survey —
        # re-fetch the thread and verify the receipt is STILL the last
        # word immediately before mutating; any drift aborts the pass
        # (fail closed) instead of resolving an unanswered finding.
        fresh = refetch_thread(thread)
        if (
            fresh is None
            or fresh.is_resolved
            or fresh.last_id != thread.last_id
            or classify(fresh) != "receipted"
        ):
            print(
                f"DRIFT thread={thread.label}: last comment changed after "
                f"the survey (bot follow-up?) — STOPPING; re-run after "
                f"posting a fresh receipt. {resolved} thread(s) resolved "
                f"before the drift was detected."
            )
            return 1
        if not resolve_thread(thread):
            return 1
        # Thread 3827768016: the narrower window — a follow-up landing
        # between the pre-mutation check and the mutation itself. The
        # final survey audit cannot catch it (a resolved thread
        # classifies as resolved regardless of its last comment), so the
        # expected last comment id is preserved THROUGH the mutation and
        # re-verified after it; on drift the thread is REOPENED so the
        # server ruleset blocks the merge again.
        settled = refetch_thread(thread)
        if settled is None or settled.last_id != fresh.last_id:
            print(
                f"DRIFT thread={thread.label}: last comment changed DURING "
                f"resolution — reopening the thread (the merge gate blocks "
                f"until a fresh receipt lands)."
            )
            # Thread 3828232337: a discarded False here would let a
            # LATER pre-merge classify the still-resolved drifted
            # thread as safe. Require the reopen to take (one retry);
            # if the thread stays resolved, the bot follow-up as last
            # comment keeps it classified DANGER — the gate stays
            # blocked until it is manually reopened.
            if not unresolve_thread(thread) and not unresolve_thread(thread):
                print(
                    f"MERGE FORBIDDEN thread={thread.label}: reopen FAILED "
                    f"— the thread is still resolved with the bot follow-up "
                    f"as its last comment, so it classifies DANGER. "
                    f"Manually reopen it before any merge."
                )
            return 1
        resolved += 1
    # Final audit: anything that landed mid-pass must surface as DANGER
    # here rather than after the merge.
    # Thread 3868979526 (PR #49 round 11, P2): the audit survey is
    # DECISION-BEARING — its list gates the RESOLVE DONE verdict — so
    # it runs bannerless (reaction=False), the same decision-surface
    # rule as pre-merge's closing survey, the guarded merge act, and
    # the quiet watch (threads 3868158297/3867757449/3867897759): the
    # banner's bounded 15s informational read between this snapshot
    # and the go/no-go could let a bot follow-up land on an
    # already-resolved thread while the audit consumed the stale
    # clean list. The banner's home is the OPENING survey above
    # (human-facing; its snapshot is re-verified per target).
    audit = survey(pr, reaction=False)
    if any(t.classification == "DANGER" for t in audit):
        print(
            "AUDIT BLOCKED: new unanswered finding(s) arrived during the "
            "resolve pass — do NOT merge; re-run the loop."
        )
        return 1
    print(f"RESOLVE DONE: {resolved}/{len(targets)} thread(s)")
    return 0


def main(argv: list[str]) -> int:
    modes = {"survey", "harden", "pre-merge", "resolve", "merge", "wait"}
    # Toolkit extraction: the optional global --repo OWNER/NAME
    # strips BEFORE the subcommand (the trailing-flag precedent of
    # --quiet-secs/--timeout-secs) and CONFIGURES the target
    # immediately, so a direct main() caller passing it is honored.
    # Every other resolution source (the env var, the origin
    # remote, the refusal when nothing resolves) is run()'s job —
    # main() itself stays environment-free: the tests call it
    # directly, and dispatch must not depend on the ambient git
    # checkout.
    rest = argv
    repo_arg = repo_flag_value(argv)
    if repo_arg is not None:
        parsed = parse_repo_slug(repo_arg) if repo_arg else None
        if parsed is None:
            print(USAGE, file=sys.stderr)
            return 2
        configure(*parsed)
        rest = argv[:1] + argv[3:]
    # Thread 3832418158: merge's post-merge quiet period is bounded AND
    # overridable — 15 default minutes of progress-printed watching must
    # not make the guarded-merge workflow unusable (--quiet-secs 0
    # collapses the watch to the single PR #39 backstop snapshot).
    quiet_secs = DEFAULT_QUIET_SECS
    if rest[1:2] == ["merge"] and rest[-2:-1] == ["--quiet-secs"]:
        if not rest[-1].isdigit():
            print(USAGE, file=sys.stderr)
            return 2
        quiet_secs = int(rest[-1])
        rest = rest[:-2]
    # --accept-standing (user request 2026-08-28, no thread ID): the
    # wait-only valueless flag, stripped from ANY trailing position
    # BEFORE the --timeout-secs strip so both orders normalize —
    # `wait N --accept-standing --timeout-secs T` and `wait N
    # --timeout-secs T --accept-standing` both reach the {3,5}-token
    # shape check below. It never touches another mode's argv (an
    # --accept-standing under survey/merge stays an operand and the
    # shape check rejects it, exit 2).
    accept_standing = False
    if rest[1:2] == ["wait"] and "--accept-standing" in rest[3:]:
        accept_standing = True
        idx = rest.index("--accept-standing")
        rest = rest[:idx] + rest[idx + 1 :]
    # PR #48: wait's deadline rides the same trailing-flag strip as
    # merge's --quiet-secs (the merge precedent — a digit flag value
    # or it is a usage error before any dispatch).
    timeout_secs = DEFAULT_WAIT_TIMEOUT_SECS
    if rest[1:2] == ["wait"] and rest[-2:-1] == ["--timeout-secs"]:
        if not rest[-1].isdigit():
            print(USAGE, file=sys.stderr)
            return 2
        timeout_secs = int(rest[-1])
        rest = rest[:-2]
    if len(rest) not in {3, 5} or rest[1] not in modes or not rest[2].isdigit():
        print(USAGE, file=sys.stderr)
        return 2
    # Thread 3834666210 (PR #41 round 18): merge BINDS the head and
    # base it re-verifies — the truncated `merge <pr>` form used to
    # satisfy the {3,5} shape check, skip the merge_guarded branch,
    # and fall through to resolve(pr), mutating review-thread state
    # under a merge command name. merge demands exactly five argv
    # tokens (seven with --quiet-secs); every other mode exactly
    # three — anything else is a usage error BEFORE any dispatch.
    if (len(rest) == 5) != (rest[1] == "merge"):
        print(USAGE, file=sys.stderr)
        return 2
    pr = int(rest[2])
    if rest[1] == "merge":
        return merge_guarded(pr, rest[3], rest[4], quiet_secs)
    if rest[1] == "wait":
        # --accept-standing (user request 2026-08-28): the flagged
        # dispatch threads the opt-in through; the flagless call
        # keeps its historic two-arg shape so the argv-contract pins
        # (pr_guard_reaction_test) stand byte-identical — zero repins.
        if accept_standing:
            return wait_reaction(pr, timeout_secs, True)
        return wait_reaction(pr, timeout_secs)
    if rest[1] == "survey":
        survey(pr)
        return 0
    if rest[1] == "harden":
        return harden(pr)
    if rest[1] == "pre-merge":
        return pre_merge(pr)
    return resolve(pr)


# The process entry — the console script, `python -m pr_guard`, and
# the release zipapp all land here: resolve the repository target
# ONCE (the --repo flag, else PR_GUARD_REPO, else the CWD's origin
# remote) and refuse to run with the clean usage error (exit 2)
# when nothing resolves. main() stays the pure dispatcher the tests
# exercise directly; the environment-facing resolution lives only
# in this wrapper.
def run(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv
    owner, name = resolve_repo_target(repo_flag_value(argv))
    configure(owner, name)
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(run(sys.argv))
