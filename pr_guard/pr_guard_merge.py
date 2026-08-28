"""The guarded merge act for pr_guard.

Split from pr_guard.py at the 250 pure-LOC ceiling (PR #37, thread
3828735200): re-verifies pre-merge's binding then dispatches the merge
request in the SAME process as the final thread survey.

Thread 3829356723 (PR #39): one Python process does NOT make the
GraphQL survey and the `gh pr merge` request atomic — a bot reply
landing on an ALREADY-RESOLVED thread after survey(pr) returns but
before the merge request leaves passes BOTH this script (the survey
snapshot is already taken) and the server ruleset (resolved threads do
not block; --match-head-commit binds only the head SHA). The residual
race is narrowed to survey->merge and BACKSTOPPED: after the merge
completes this act re-surveys in the same invocation, and any DANGER
thread triggers an automatic revert — a revert PR opened via gh,
because direct pushes to the protected bases are themselves
ruleset-blocked (thread 3829356731) — and a nonzero exit. The only
truly atomic gate is server-side; this act minimizes the window and
repairs it.

PR #40 round 1:
- Thread 3832321683: `gh pr merge` exiting 0 may only have ENABLED
  auto-merge or queued the PR, so the backstop used to survey while
  the race window was still open and could print MERGED CLEAN before
  the merge landed. The act now waits for true completion — polling
  `gh pr view --json state,mergeCommit,baseRefName` (bounded
  MERGE_POLL_ATTEMPTS x MERGE_POLL_INTERVAL, progress each attempt)
  until state == MERGED, then runs the backstop survey; a timeout
  fails closed with the manual-revert warning and exit 1.
- Thread 3832321698: the verified base is NOT pinned server-side
  (GitHub's merge API accepts no base lock — --match-head-commit
  binds only the head), so a PR retargeted between the base check and
  the merge lands on an unprotected base with the command still
  succeeding. The completion poll therefore also re-reads baseRefName
  (printed every attempt) and asserts it STILL equals the verified
  base once MERGED; a mismatch goes straight to the revert path on
  the LANDED base. This closes the window to check->merge plus a
  post-merge destination assertion.
- Thread 3832321706: a post-merge survey that DIES (gh_graphql's die
  raises SystemExit) used to bypass the backstop entirely, leaving the
  merge unverified with no revert and no warning. The backstop is
  wrapped in try/except BaseException and fails closed through the
  SAME revert path; if the revert itself fails, the explicit
  manual-revert instructions name the merge SHA.

PR #40 round 2:
- Thread 3832418151: the completion poll timing out does NOT undo the
  `gh pr merge` request — it may persist as an enabled auto-merge or a
  merge-queue entry that lands AFTER this process exits, bypassing the
  destination assertion and the post-merge watch entirely. The timeout
  path now CANCELS the pending request and VERIFIES before failing
  closed (see pr_guard_revert).
- Thread 3832418158: one immediate post-merge survey can print MERGED
  CLEAN before the bot's final round lands (the documented production
  failure — rounds arrived minutes after merge). The backstop is now a
  QUIET-PERIOD WATCH, aborting to the revert path the MOMENT any
  DANGER appears; MERGED CLEAN prints only after the FULL window
  passes with zero DANGER. RESIDUAL TRUTH: a bot round arriving AFTER
  the quiet period is out of any client-side gate's reach — the
  mitigation is bounded monitoring plus the still-open server-side
  gap; only a server-side gate could close it.

PR #40 round 3 (the cancel/revert machinery now lives in
pr_guard_revert.py — the 250 pure-LOC ceiling again):
- Thread 3832522300: the quiet-period watch counted SURVEYS, not time
  — cycles surveys span only cycles-1 sleeps, so the default 900s
  window declared MERGED CLEAN at 840s and 1-119s windows returned
  almost immediately, recreating the tail race the watch exists to
  catch. The watch is now DEADLINE-based: deadline = monotonic() +
  quiet_secs; survey -> (DANGER reverts) -> sleep -> repeat while
  before the deadline, with one FINAL survey always run at/after it;
  a short remaining gap sleeps only the REMAINING time so the final
  survey lands at the deadline (quiet_secs=0 stays the documented
  single snapshot).
- Thread 3832522306: --disable-auto disables AUTO-MERGE only — a PR
  already in a MERGE QUEUE is a different pending state, and the
  installed gh 2.97.0's pr view --json exposes no queue-entry field,
  so autoMergeRequest == null does not prove it dequeued. The cancel
  path verifies BOTH contingencies and reverts immediately if the
  merge landed during cancellation (pr_guard_revert).
- Thread 3832522310: under pending auto-merge an author can push a NEW
  head after the merge request — the request then merges the new
  UNSURVEYED head and the completion poll (state/base/merge-sha only)
  accepted it, because --match-head-commit binds only at REQUEST
  time. The act now captures the merge-request-time headRefOid BEFORE
  dispatching (a head that moved during the closing survey BLOCKS
  instead of dispatching), and the completion poll verifies the PR's
  FINAL headRefOid equals the surveyed head — a mismatch means the
  landed content was never surveyed: revert path + exit 1. RESIDUAL
  TRUTH: a push to the head branch AFTER the merge also trips the
  final-head check — fail-closed by design (the revert PR opens; a
  human reconciles); the push-during-pending window is closed
  client-side only.

PR #41 (the completion/reconciliation machinery — the poll, the
cancel, and the queue settlement — now lives in
pr_guard_completion.py, thread 3833251667's round-6 split):
- Thread 3833073949: `gh pr merge` exiting nonzero does NOT prove the
  request wasn't accepted (the connection can die AFTER GitHub takes
  it), and the old immediate return skipped every poll, cancel,
  assertion, and watch — an accepted request could land later with NO
  backstop. A failed merge command is now an UNKNOWN outcome: the same
  completion poll runs (bounded, SHORTER — RECONCILE_POLL_ATTEMPTS),
  and a poll that observes MERGED continues the ORDINARY post-merge
  path (destination/head assertions + quiet watch + revert-on-danger);
  only a poll that settles OPEN/CLOSED (or a cancel that reverts a
  late landing) fails with the ORIGINAL error surfaced.
- Thread 3833073952: every `gh pr` command here is pinned with
  -R RachaelsDen/UR-lorebook (a GH_REPO override cannot aim the CLI
  half at another repository while the REST/GraphQL half surveys this
  one), and the act warns loudly at startup when GH_REPO names
  something else. The queue-aware cancel settlement lives in
  pr_guard_completion (threads 3833073940/3833251675).
- Thread 3833251667 (PR #41 round 6): the module had grown past the
  250 pure-LOC ceiling; the completion poll trio
  (wait_for_merge_completion / read_landed_state /
  completion_verdict) moved to pr_guard_completion with the cancel and
  queue-settlement machinery, leaving this module the dispatch act:
  binding re-verification, the merge request, the landed assertions,
  and the quiet-period watch.

PR #41 round 7:
- Thread 3833360219: the post-dispatch completion wait is wrapped in a
  reconciliation handler — an interrupt (KeyboardInterrupt or any
  exception) during the multi-minute wait runs the bounded
  cancel/reconciliation path BEFORE the original exception propagates,
  so a dispatched-but-pending merge request can never be left to land
  unbackstopped; a second interrupt during that cancellation prints
  the both-contingency manual instructions (PR number included) before
  the nonzero exit.
- Thread 3833360211: every guarded_revert call site passes its actual
  trigger (retargeted base / moved head / bot DANGER finding / failed
  survey; the merge-during-cancellation trigger is threaded from
  pr_guard_revert), and the revert PR title/body render it — see
  REVERT_TRIGGERS in pr_guard_revert.

PR #41 round 9:
- Thread 3833671126: the merge DISPATCH itself is inside the
  reconciliation envelope — an exception while `gh pr merge` is
  returning (Ctrl-C, a subprocess error) used to exit before any
  polling or cancellation, even though GitHub may already have
  accepted the request. The dispatch is now wrapped in
  try/except BaseException and treated as the SAME unknown outcome
  as a nonzero exit: the bounded reconcile poll runs (MERGED
  continues the ordinary post-merge path; anything else runs the
  cancel disposal), and the ORIGINAL exception is re-raised after
  the disposal so the act still exits nonzero.

PR #41 rounds 25-26 (threads 3835145981/3835290443): the PR commit
list and the BASE TIP are SNAPSHOTTED once, right before the merge
dispatch, and the frozen pair rides every revert path — a
post-merge push to the source branch moves refs/pull/<n>/head, and
the pre-revert base fetch moves `<remote>/<base>` to the landing
itself, so post-hoc re-reads describe post-merge state. The frozen
tip is the single-parent revert contract's comparison target; the
frozen list feeds the fail-closed banner's diagnostics only.

PR #45 round 17 (thread 3836600782, P1 — the TERMINAL resolution):
the failed-dispatch attribution is RETIRED. Rounds 8-16 threaded a
transition-evidence holder (baseline/credit pacing, then same-clock
updatedAt corroboration — pr_guard_transition) through every read
of the reconciliation window as the failed path's ONLY fresh
attribution; the reviewer's counter-example chain across rounds
7-17 proved every such client-side signal reproducible by a
historical merge hidden in GitHub's REST cache (open-sha reuse
3835944058; the underdetermined precedent 3836003345; clock skew
3835944061/3836043653; the rc-0 no-op dispatch 3836217633; cached
OPEN baselines 3836149500/3836217630/3836277960; PENDING/
nested-watch evidence 3836380780/3836380790; the baseline/credit
state machine 3836437093/3836437095/3836437098/3836437100; stamp
corroboration 3836501981; cross-clock stamps 3836565818; ordered
cache snapshots 3836600782 — two snapshots of the SAME historical
timeline satisfy every between-reads test). The holder, its state
machine module, the updatedAt read plumbing, and the committer-date
probe are DELETED; the identity gate's failed-dispatch arm is the
ONE AMBIGUOUS manual banner (NO automatic revert, nonzero exit) for
EVERY landing however observed. The SUCCESSFUL-dispatch path is
unchanged — a genuine rc 0 bounds the landing, and the pre-existing
trusted arms (rounds 29-30) still gate both paths first.
"""

import subprocess
import time
from .pr_guard_common import MERGE_POLL_ATTEMPTS, MERGE_POLL_INTERVAL
from .pr_guard_common import REPO_FLAG, blocked_gh_host, gh_env
from .pr_guard_common import warn_repo_override
from .pr_guard_common import reconciled_exit_summary, read_merge_request_head
from .pr_guard_completion import cancel_pending_merge, wait_for_merge_completion
from .pr_guard_identity import landing_identity_gate
from .pr_guard_plan import read_pr_commits, snapshot_base_tip
from .pr_guard_quiet import DEFAULT_QUIET_SECS, quiet_period_watch
from .pr_guard_revert import guarded_revert
from .pr_guard_rulesets import PROTECTED_BASE_PATTERNS, default_branch
from .pr_guard_rulesets import fetch_gate_rulesets, gate_covers, gh_rest_pr
from .pr_guard_rulesets import ref_matches
from .pr_guard_settle_banners import both_contingency_banner, merge_output_note
from .pr_guard_threads import survey

# Thread 3836217633 (PR #45 round 10, P1): the gh already-merged
# no-op signature — `gh pr merge` dispatched at an already-merged PR
# can exit 0 reporting the PR "was already merged" (the idempotent
# no-op success; gh prints the phrase to stdout or stderr). An rc-0
# dispatch whose captured output carries this signature (matched
# case-insensitively) is NOT a successful dispatch for attribution:
# GitHub accepted no request from THIS invocation, so the rc-0
# bounding ("any landing observed is bounded to after-dispatch") is
# false and the landing may be any historical merge the stale
# pre-dispatch OPEN record hid.
MERGE_NOOP_SIGNATURE = "already merged"

# Thread 3833073949 (PR #39): the reconcile poll after a FAILED merge
# command — the same completion machinery as the success path but a
# SHORTER bounded window (the request probably never landed, so the
# poll is a confirmation, not the primary wait). Thread 3836217633
# (round 10): the no-op-signature rc-0 dispatch reconciles with THIS
# budget too — nothing was dispatched, so the poll is a confirmation.
RECONCILE_POLL_ATTEMPTS = 10


# Thread 3828735200: the survey->merge sequence as separate shell
# commands leaves a window a bot follow-up on an ALREADY-RESOLVED
# thread can win (resolved threads never re-block server-side). This
# act re-runs the whole gate and dispatches the merge request in the
# SAME process, immediately after the final thread fetch — the closest
# attainable binding to GitHub's server-side head check. pre-merge's
# CLEAN output names THIS command; run it right after pre-merge.
def merge_guarded(
    pr: int, head: str, base: str, quiet_secs: int = DEFAULT_QUIET_SECS
) -> int:
    # Thread 3834400946 (PR #41 round 16): a GH_HOST naming a host
    # other than github.com is a HARD BLOCK — `-R RachaelsDen/
    # UR-lorebook` resolves against GH_HOST's host, so the act could
    # survey and merge an identically named repository there. Every
    # gh call below is additionally env-pinned to github.com.
    if blocked_gh_host():
        return 1
    # Thread 3833073952 (PR #41): the operator's environment cannot
    # redirect this act (every gh pr command is -R-pinned below), but a
    # GH_REPO naming another repository is reported loudly anyway.
    warn_repo_override()
    pr_data = gh_rest_pr(pr)
    if (
        str(pr_data["head"]["sha"]) != head
        or str(pr_data["base"]["ref"]) != base
    ):
        print(
            f"BLOCKED: PR head/base moved since pre-merge — re-run the "
            f"gate (expected {base}@{head[:12]})."
        )
        return 1
    # Thread 3835450367 (PR #41 round 29): the pre-dispatch merge
    # IDENTITY, snapshotted from the SAME REST read that validates
    # head/base. A stale re-run of this act against an ALREADY-MERGED
    # PR passes that validation (the fields never move post-merge),
    # the dispatch exits nonzero, and the reconcile poll then observed
    # the HISTORICAL MERGED state as though the failed dispatch had
    # just landed it — running the post-merge mismatch/DANGER cycle
    # (and the automatic revert) against a merge this invocation never
    # made. The snapshot is reconciled against the completion poll's
    # landing below: an EQUAL merge commit (or an already-merged
    # pre-dispatch state) is a PRE-EXISTING merge, not our landing.
    pre_merged = bool(pr_data.get("merged")) or (
        str(pr_data.get("state") or "").upper() == "MERGED"
    )
    # Thread 3835714800 (PR #43 round 2): the TRUSTED identity
    # snapshot (pre_merge_sha) still keys ONLY on the merged flags —
    # for an OPEN PR the REST merge_commit_sha can be GitHub's
    # synthetic TEST merge commit (the provisional merge built to
    # report mergeability), and the real dispatch can land REUSING
    # that very commit object; saving it unconditionally made
    # is_pre_existing_merge classify THIS invocation's fresh landing
    # as historical. Thread 3835846318 (PR #45 round 3): the OPEN
    # record's sha is nevertheless KEPT (open_merge_sha) as
    # AMBIGUITY EVIDENCE for a FAILED dispatch — the stale-OPEN
    # consistency window (record OPEN, PR already landed, merge
    # command failing "already merged") otherwise discards the only
    # pre-dispatch identity there is; the identity gate below
    # consults it ONLY when the dispatch failed, so an equal sha
    # after a SUCCESSFUL dispatch still runs the ordinary post-merge
    # path (the round-2 guarantee). Thread 3835944058 (PR #45 round
    # 5): this read is the sha's ONLY legitimate provenance — the
    # capture happens BEFORE the dispatch leaves, and the gate never
    # re-reads the record post-landing (the real landing can BE the
    # synthetic object, reachable and merge-shaped, so a later read
    # could not discriminate fresh from pre-existing anyway);
    # equality against THIS capture is AMBIGUITY evidence only and
    # NEVER resolves the verdict — not even by committer date
    # (thread 3836003345, round 6: a fresh landing REUSING the aged
    # synthetic object carries that object's OLD test-merge date, so
    # the date cannot discriminate the reuse); the identity gate
    # answers with the manual-check banner, never a pre-existing
    # claim off this sha alone.
    rest_sha = str(pr_data.get("merge_commit_sha") or "")
    pre_merge_sha = rest_sha if pre_merged else ""
    open_merge_sha = "" if pre_merged else rest_sha
    # Thread 3832660865 (PR #40 round 4): the guarded merge act runs on
    # the PROTECTED BASES only — the narrowed main/dev list. A release
    # branch must not slip through here as a base (the live ruleset no
    # longer gates it, so the gate_covers check below would refuse it
    # anyway — but with the misleading 're-run harden' remedy, which
    # harden itself would then reject); refuse it up front with the
    # accurate message, mirroring harden's own refusal.
    if not any(
        ref_matches(pattern, base, default_branch())
        for pattern in PROTECTED_BASE_PATTERNS
    ):
        print(
            f"BLOCKED: refs/heads/{base} is not a protected base "
            f"({', '.join(PROTECTED_BASE_PATTERNS)}) — the guarded merge "
            f"act runs only on the protected bases (thread 3832660865); "
            f"release/** heads must stay directly pushable."
        )
        return 1
    if gate_covers(fetch_gate_rulesets(), base, default_branch()) is None:
        print(
            "BLOCKED: no ACTIVE branch-target ruleset enforces "
            "review-thread resolution on the base — a tag/push-target "
            "ruleset never counts (thread 3834666208). Re-run harden."
        )
        return 1
    # Thread 3867757449 (PR #49 round 4, P1): the CLOSING survey is
    # the dispatch's gate — its snapshot feeds the DANGER check below
    # — so it runs WITHOUT the reaction banner: the banner's bounded
    # 15s informational read between the snapshot and the go/no-go
    # let a bot follow-up land on an already-resolved thread (the
    # ruleset cannot block a finding added to a resolved thread)
    # while the merge consumed the stale clean list. Thread 3867897759
    # (round 5, P1) brought the post-merge quiet watch into the same
    # bannerless camp (its cycles and final verdict gate too); the
    # banner's remaining home is the human-facing CLI surveys (plain
    # survey, harden, pre-merge, resolve), where it delays no
    # decision.
    closing = survey(pr, reaction=False)
    if any(t.classification == "DANGER" for t in closing):
        print("BLOCKED: finding(s) arrived since pre-merge — re-run the loop.")
        return 1
    # Thread 3832522310 (PR #40 round 3): capture the
    # merge-request-time headRefOid BEFORE dispatching —
    # --match-head-commit binds only at request time, so this is the
    # last moment the surveyed head is guaranteed current. A head that
    # moved during the closing survey BLOCKS here instead of merging
    # content the threads were never surveyed against.
    requested_head = read_merge_request_head(pr)
    if requested_head != head:
        print(
            f"BLOCKED: PR head moved during the closing survey "
            f"({head[:12]} -> {requested_head[:12] or 'unreadable'}) — the "
            f"surveyed threads belong to an older head; re-run the gate "
            f"(thread 3832522310)."
        )
        return 1
    # Thread 3835145981 (PR #41 round 25): the PR commit list is read
    # ONCE, HERE — beside the merge-request-time head, BEFORE the
    # dispatch — and the FROZEN snapshot is threaded through every
    # revert path below. A post-merge push to the source branch moves
    # refs/pull/<n>/head and GitHub reconnects the PR's commits, so a
    # post-merge re-read can describe the POST-MERGE branch while the
    # banner diagnostics want the landed truth. A failed read warns
    # and proceeds (read_pr_commits's own snapshot banners): the merge
    # gate does not depend on the list.
    frozen_commits = read_pr_commits(pr)
    # Thread 3835290443 (PR #41 round 26): the BASE TIP is frozen
    # HERE TOO — the pre-revert base fetch moves `<remote>/<base>` to
    # the landing itself (or beyond), so a single-parent revert
    # comparing the landing's parent against the CURRENT ref could
    # never match and the supposedly automated squash path always
    # fell through to the manual banner. The FROZEN tip is the
    # comparison target of pr_guard_plan's two-case contract; an
    # unavailable snapshot (snapshot_base_tip's own warning) degrades
    # every single-parent revert to fail-closed — never the merge.
    frozen_base_tip = snapshot_base_tip(pr, base)
    # Thread 3835846318 (PR #45 round 3): the WALL-CLOCK DISPATCH
    # TIMESTAMP, captured the moment `gh pr merge` is about to leave
    # — the ambiguous banner a FAILED dispatch reports cites it for
    # the manual timeline check (round 17: it REPORTS, never gates).
    dispatch_ts = time.time()
    print(
        f"MERGING pr={pr} at {head[:12]} — the survey->merge window is "
        f"still open (thread 3829356723); the post-merge re-survey below "
        f"backstops it with an automatic revert if a bot last word "
        f"slipped in. Only the server ruleset is truly atomic."
    )
    merge_rc = 0
    dispatch_failure: BaseException | None = None
    # Thread 3836217633 (PR #45 round 10, P1): the dispatch's
    # COMBINED OUTPUT — captured (not streamed) so the rc-0
    # already-merged no-op signature can be detected; the
    # classification banner below reports anything found.
    merge_output = ""
    try:
        merge_proc = subprocess.run(
            [
                "gh",
                "pr",
                "merge",
                str(pr),
                "--merge",
                "--match-head-commit",
                head,
            ]
            + REPO_FLAG,
            capture_output=True,
            text=True,
            env=gh_env(),
        )
        merge_rc = merge_proc.returncode
        merge_output = f"{merge_proc.stdout}\n{merge_proc.stderr}"
    except BaseException as exc:
        # Thread 3833671126 (PR #41 round 9): Ctrl-C or a subprocess
        # error while the dispatch is returning produced NO merge_rc,
        # so the old code exited BEFORE any polling or cancellation —
        # yet GitHub may already have accepted the request, and an
        # accepted auto-merge/queue entry could then land later with
        # no base/head assertions and no quiet watch. An exception
        # from the dispatch is therefore the SAME unknown outcome as
        # a nonzero exit: reconcile below (a poll that observes MERGED
        # continues the ordinary post-merge path; anything else runs
        # the cancel disposal), and only THEN re-raise the original
        # exception so the act still exits nonzero.
        dispatch_failure = exc
        merge_rc = 1
        print(
            f"MERGE DISPATCH RAISED ({type(exc).__name__}: {exc}) — the "
            f"exception proves NOTHING about whether GitHub accepted the "
            f"request (an interrupt or subprocess error can arrive AFTER "
            f"acceptance), so the outcome is UNKNOWN (thread 3833671126); "
            f"reconciling with a bounded completion poll — if it lands, "
            f"the full post-merge path (assertions + quiet watch + "
            f"revert-on-danger) still runs, and the ORIGINAL exception "
            f"is re-raised after the disposal."
        )
    # Thread 3833073949 (PR #41): a nonzero exit is an UNKNOWN outcome,
    # not a proven refusal — GitHub may already have accepted the
    # request when the connection died. Reconcile with the same
    # completion poll (bounded, SHORTER) before failing: a poll that
    # observes MERGED continues the ORDINARY post-merge path below, so
    # an accepted-but-errored request can never land unbackstopped.
    if merge_rc != 0 and dispatch_failure is None:
        print(
            f"MERGE COMMAND FAILED (gh exited {merge_rc}) — an exit code "
            f"proves NOTHING about whether GitHub accepted the request (a "
            f"lost connection after acceptance still exits nonzero), so "
            f"the outcome is UNKNOWN (thread 3833073949); reconciling with "
            f"a bounded {RECONCILE_POLL_ATTEMPTS * MERGE_POLL_INTERVAL:.0f}s "
            f"completion poll — if it lands, the full post-merge path "
            f"(assertions + quiet watch + revert-on-danger) still runs."
        )
    # Thread 3836217633 (PR #45 round 10, P1): an rc-0 dispatch whose
    # captured output carries the already-merged no-op signature is
    # NOT a successful dispatch for attribution — a stale-OPEN
    # pre-dispatch record on an already-merged PR makes `gh pr merge`
    # exit 0 with "was already merged" (the IDEMPOTENT no-op
    # success), and the rc-0 bounding is then false: GitHub accepted
    # no request from THIS invocation, so the merge predates the
    # dispatch and the post-merge machinery (mismatch/DANGER
    # handling, the automatic revert) must never run on it as ours.
    # The no-op dispatch joins the AMBIGUOUS class below (the
    # identity ladder decides); only a GENUINE rc 0 — no signature —
    # keeps the rc-0 bounding.
    dispatch_noop = (
        merge_rc == 0
        and dispatch_failure is None
        and MERGE_NOOP_SIGNATURE in merge_output.lower()
    )
    if dispatch_noop:
        print(
            f"MERGE COMMAND EXITED 0 WITHOUT DISPATCHING (thread "
            f"3836217633): gh reported PR #{pr} 'already merged' and "
            f"exited 0 — the IDEMPOTENT NO-OP SUCCESS. rc 0 here "
            f"proves NOTHING about who landed the merge (GitHub "
            f"accepted no request from THIS invocation; the landing "
            f"predates the dispatch), so the rc-0 attribution bounding "
            f"does NOT apply: the dispatch is treated as the "
            f"FAILED-dispatch class (ambiguous identity ladder below) "
            f"and the reconcile runs the SHORTER bounded "
            f"{RECONCILE_POLL_ATTEMPTS * MERGE_POLL_INTERVAL:.0f}s "
            f"poll — any landing it observes is gated before the "
            f"post-merge machinery."
        )
    # Thread 3835877364 (PR #45 round 4): the dispatch outcome flag —
    # a nonzero exit OR a raised dispatch is the AMBIGUOUS outcome
    # whose landings (reconcile, timeout-cancel, interrupt) all gate
    # through the widened pr_guard_identity evidence below. Thread
    # 3836217633 (round 10): the no-op-signature rc-0 dispatch joins
    # the class — its "success" is idempotent, not ours.
    dispatch_failed = (
        merge_rc != 0
        or dispatch_failure is not None
        or dispatch_noop
    )
    # Thread 3832321683: a zero exit may only have enabled auto-merge /
    # queued the PR — WAIT for true completion before surveying, so
    # MERGED CLEAN is never printed while the race window is open.
    # An int return means the timeout path already handled itself
    # (cancel converged, or the merge landed during cancellation and
    # the revert ran inside pr_guard_revert).
    # Thread 3833360219 (PR #41 round 7): this multi-minute wait is
    # ADVERTISED to the operator, so an interrupt here (Ctrl-C, or any
    # exception) must not exit while a dispatched merge request is
    # still pending — it could land later WITHOUT the destination/head
    # assertions or the quiet-period watch. The wait runs inside a
    # reconciliation handler: on ANY interruption the bounded cancel
    # path runs first (it itself reverts a merge that landed during
    # the cancellation, and prints its own disposition), and only then
    # does the original exception propagate (nonzero exit). A SECOND
    # interrupt arriving during that cancellation prints the
    # both-contingency manual instructions instead of dying silently.
    # Interruptions during the QUIET watch are already reconciled by
    # thread 3832321706's handler — the merge has landed by then, so
    # reverting IS the reconciliation.
    wait_attempts = (
        MERGE_POLL_ATTEMPTS
        if merge_rc == 0 and not dispatch_noop
        else RECONCILE_POLL_ATTEMPTS
    )
    # Thread 3836092104 (PR #45 round 8, P1) threaded a TRANSITION
    # EVIDENCE holder (baseline/credit, later same-clock
    # corroborated, pr_guard_transition) through the whole
    # reconciliation window as the failed path's fresh attribution;
    # thread 3836600782 (round 17, P1) RETIRED it — the reviewer's
    # chain proved every between-reads signal reproducible by
    # ordered cache snapshots of one historical timeline — and the
    # module was deleted. The failed path no longer observes for
    # attribution AT ALL: any landing it reconciles into reports the
    # uniform AMBIGUOUS banner at the gate below.
    try:
        settled_merge = wait_for_merge_completion(
            pr, base, head, attempts=wait_attempts,
            commits=frozen_commits, frozen_base_tip=frozen_base_tip,
            pre_merged=pre_merged, pre_merge_sha=pre_merge_sha,
            open_merge_sha=open_merge_sha, dispatch_ts=dispatch_ts,
            dispatch_failed=dispatch_failed,
        )
    except BaseException as exc:
        print(
            f"INTERRUPTED DURING THE COMPLETION WAIT "
            f"({type(exc).__name__}: {exc}) — the merge request is "
            f"already dispatched, so its outcome is UNKNOWN (thread "
            f"3833360219); running the bounded cancel path BEFORE "
            f"re-raising (a landing it observes reverts inside it, "
            f"and a converged cancel prints its own evidence)."
        )
        try:
            reconciled = cancel_pending_merge(
                pr, base, wait_attempts, frozen_commits,
                frozen_base_tip, pre_merged, pre_merge_sha,
                open_merge_sha, dispatch_ts, dispatch_failed,
            )
        except BaseException:
            print(
                "THE INTERRUPT ARRIVED DURING THE CANCELLATION TOO — "
                "the reconciliation is itself unfinished (thread "
                "3833360219); manual instructions:"
            )
            print(both_contingency_banner(pr, base, wait_attempts))
        else:
            if isinstance(reconciled, str):
                print(reconciled)
        raise
    if isinstance(settled_merge, str):
        print(settled_merge)
        if dispatch_failure is not None:
            # Thread 3833671126: the cancel disposal has printed its
            # own disposition — the original exception now propagates
            # so the act exits nonzero instead of returning cleanly.
            raise dispatch_failure
        if merge_rc != 0:
            print(
                f"ORIGINAL MERGE ERROR: gh pr merge exited {merge_rc} — "
                f"nothing landed (thread 3833073949)."
            )
            # Thread 3836323285 (PR #45 round 12, P2): emit the
            # captured dispatch diagnostics beside the failure
            # summary — the rc alone cannot say WHY gh failed.
            if note := merge_output_note(merge_output):
                print(note)
        return 1
    if isinstance(settled_merge, int):
        if dispatch_failure is not None:
            # Thread 3833671126: the reconcile observed the landing and
            # the revert already ran inside the cancellation — the
            # original exception still propagates (nonzero exit).
            raise dispatch_failure
        # Thread 3836043658 (PR #45 round 7, P1): the int is a
        # DISTINCT disposition — 0 the revert COMPLETED, 1 the revert
        # FAILED, 3 the identity gate exited WITHOUT reverting — and
        # the epilogue branches on the codes so each exit renders its
        # own truthful summary (round 6 treated every int as a
        # completed revert and claimed "the revert above already
        # undid it" over gated no-revert and failed-revert exits
        # alike). The act still exits nonzero for EVERY disposition:
        # 0 stays MERGED CLEAN's exclusive process meaning.
        reconciled_exit_summary(settled_merge, merge_rc)
        # Thread 3836323285 (PR #45 round 12, P2): the same captured
        # diagnostics beside the reconciliation epilogue's summary
        # (merge_rc != 0 only — a successful dispatch's quiet output
        # is not a failure diagnostic).
        if merge_rc and (note := merge_output_note(merge_output)):
            print(note)
        return 1
    merge_sha, landed_base, landed_head = settled_merge
    # Thread 3835450367 (PR #41 round 29): reconcile the landing
    # against the PRE-DISPATCH identity — a MERGED observation whose
    # mergeCommit is the pre-dispatch snapshot's own (or whose PR
    # was already merged before anything was dispatched) is a
    # PRE-EXISTING merge, NOT a landing of this invocation's dispatch:
    # no mismatch assertions, no quiet watch, and NEVER the automatic
    # revert (the historical merge is legitimate until a human surveys
    # it; comments or head movement after it are the operator's
    # post-merge check, not evidence against our dispatch). A NEW
    # mergeCommit on the SUCCESSFUL path is the ordinary path — rc 0
    # bounds the landing to after-dispatch. Thread 3836600782
    # (PR #45 round 17, P1): on the FAILED path the ordinary path no
    # longer exists — the rounds 7-16 attribution arms (open-sha
    # equality, committer dates, the observed transition and its
    # same-clock corroboration) are RETIRED, each proven reproducible
    # by a historical merge hidden in GitHub's REST cache (the
    # chain: 3835944058, 3836003345, 3835944061/3836043653,
    # 3836217633, 3836149500/3836217630/3836277960, 3836380780/
    # 3836380790, 3836437093-100, 3836501981/3836565818,
    # 3836600782), so EVERY failed-dispatch landing gets the ONE
    # AMBIGUOUS manual banner (NO automatic revert) at the gate
    # below. Thread 3835877364: the cancel/interrupt entry points
    # run this SAME gate via revert_landed_during_cancel.
    gated = landing_identity_gate(
        pr, merge_sha, pre_merged, pre_merge_sha, open_merge_sha,
        dispatch_ts, dispatch_failed,
    )
    if gated is not None:
        # Thread 3836043658 (round 7): the gate returns its DISTINCT
        # IDENTITY_GATE_EXIT disposition (banner already printed, no
        # revert ran); the act exits the family's uniform
        # attention-nonzero here.
        # Thread 3836788147 (PR #46, P2): the captured dispatch
        # diagnostics ride this exit too — it bypassed BOTH
        # note-printing summaries above, losing gh's actionable
        # stderr on the failed dispatch (merge_rc != 0 only — the
        # round-12 rationale: a successful dispatch's quiet output is
        # not a failure diagnostic).
        if merge_rc and (note := merge_output_note(merge_output)):
            print(note)
        return 1
    # Thread 3832321698: --match-head-commit pins only the head; the
    # base is re-asserted AFTER the merge (GitHub's merge API accepts
    # no base lock, so the check->merge window can only be closed by a
    # post-merge destination assertion) — a retarget reverts.
    if landed_base != base:
        print(
            f"POST-MERGE BASE MISMATCH: PR #{pr} landed on {landed_base}, "
            f"not the verified {base} — it was retargeted inside the "
            f"check->merge window and escaped the gate. REVERTING on the "
            f"landed base."
        )
        # Thread 3836043658 (round 7): `or 1` normalizes the completed
        # revert's 0 — the act exits nonzero for BOTH dispositions
        # (the open revert PR still needs a human merge).
        return guarded_revert(pr, landed_base, merge_sha, "retargeted_base", frozen_commits, frozen_base_tip) or 1
    # Thread 3832522310 (PR #40 round 3): the FINAL head is re-asserted
    # against the surveyed one — under pending auto-merge/queue an
    # author can push a NEW head after the request, and the request
    # then merges that unsurveyed head while the state/base/sha poll
    # alone would accept it (--match-head-commit bound only at request
    # time). A mismatch means the landed content was never surveyed.
    # A push AFTER the merge also trips this — fail-closed by design.
    if landed_head != head:
        print(
            f"POST-MERGE HEAD MISMATCH: PR #{pr} landed head "
            f"{landed_head[:12] or 'unknown'}, not the surveyed "
            f"{head[:12]} — the head moved after the merge request and "
            f"the request merged content that was never surveyed "
            f"(thread 3832522310). REVERTING on the landed base."
        )
        return guarded_revert(pr, landed_base, merge_sha, "moved_head", frozen_commits, frozen_base_tip) or 1
    # Thread 3829356723: the backstop — re-survey AFTER completion,
    # through the deadline-based QUIET-PERIOD WATCH (pr_guard_quiet
    # since the round-10 split: a bot last word that landed in the
    # survey->merge window classifies DANGER there — resolved or not
    # — and the watch reverts on it). Thread 3832321706: the survey
    # dying must not bypass the backstop — catch BaseException (incl.
    # gh_graphql's SystemExit) and fail closed through the revert too.
    # Thread 3832418158: the watch is a QUIET-PERIOD watch, never one
    # snapshot (the bot's final round can land minutes after the
    # merge); thread 3832522300: deadline-based with a FINAL survey
    # at/after it — the full discipline lives in pr_guard_quiet.
    try:
        return quiet_period_watch(
            pr, base, merge_sha, quiet_secs, frozen_commits,
            frozen_base_tip,
        )
    except BaseException as exc:
        print(
            f"POST-MERGE SURVEY FAILED ({type(exc).__name__}: {exc}) — the "
            f"merge landed UNVERIFIED; failing closed (thread 3832321706). "
            f"REVERTING."
        )
        return guarded_revert(pr, base, merge_sha, "survey_failed", frozen_commits, frozen_base_tip) or 1
