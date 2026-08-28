"""The GraphQL merge-queue entry surface: probe, dequeue, and the
round-15 dequeue SETTLEMENT flow.

Split from pr_guard_settle.py at the PR #41 round-15 fixes (thread
3834375737): settle stood at 265 pure LOC (HOT) with the round-15
dequeue changes in, so the whole GraphQL queue-entry surface moved
here — the entry PROBE (QUEUE_ENTRY_QUERY / read_queue_contingency,
thread 3833073940's original probe) beside the REMOVAL it always
lacked, plus attempt_queue_dequeue (the attempt -> re-verify ->
settling-watch flow). Thread 3833073940's premise — "gh and the
GitHub REST/GraphQL surface expose NO client-side dequeue operation"
— was WRONG, and the round-14 watch acted on it: a QUEUED entry was
only WATCHED for 60s before the manual instructions returned, so the
entry could still merge after the guard exited, bypassing every
assertion and the quiet-period survey. The reviewer-cited mutation
exists — verified against the LIVE GitHub schema (GraphQL __type
introspection at the round-15 fixes): DequeuePullRequestInput carries
clientMutationId: String and id: ID! (the pull request's NODE id),
the payload exposes clientMutationId and mergeQueueEntry, and the
speculative MergeQueueInput { pullRequestId, action: MERGE|REMOVE }
does NOT exist — dequeuePullRequest is the actual shape. `gh api
graphql -f query=... -f id=<node id>` invokes it.

Imports flow ONE way (settle -> dequeue -> revert -> common);
subprocess only below. Like the family's every gh call, the PR view
is -R-pinned so a GH_REPO override cannot aim the dequeue at another
repository's PR (the GraphQL query itself binds the node id GitHub
issued). The settling watch is INJECTED into attempt_queue_dequeue as
a callable precisely to keep that order — settle imports this module,
never the inverse.
"""

import json
import subprocess

from .pr_guard_common import REAPPEARED, REPO_FLAG
from .pr_guard_common import REPO_NAME, REPO_OWNER, gh_env
from .pr_guard_common import read_pending_state
from .pr_guard_revert import revert_landed_during_cancel

# Thread 3833073940 (PR #41, moved home at round 15): the queue-entry
# probe query — only gh 2.97.0's `pr view --json` lacks the field; the
# raw GraphQL API has it.
QUEUE_ENTRY_QUERY = (
    "query($owner: String!, $name: String!, $number: Int!) {"
    "repository(owner: $owner, name: $name) {"
    "pullRequest(number: $number) { mergeQueueEntry { state } } } }"
)

# Thread 3834375737 (PR #41 round 15): the dequeue mutation, in the
# shape the live schema introspection reported. The payload's
# clientMutationId selection is the minimal valid set — the removal is
# VERIFIED separately by the caller's own queue-entry probe, the same
# read the watch already trusts, rather than by trusting the mutation's
# response alone.
DEQUEUE_MUTATION = (
    "mutation($id: ID!) { dequeuePullRequest(input: {id: $id}) "
    "{ clientMutationId } }"
)


# Thread 3834375737: the PR's GraphQL NODE id, fetched through the
# existing pinned PR view (`gh pr view --json id`) — the mutation takes
# the node id, not the number, and the -R pin keeps the id (and the
# dequeue) aimed at this repository even under a GH_REPO override
# (thread 3833073952). Returns "" on any unreadable read so the caller
# fails closed into the bounded watch.
def read_pr_node_id(pr: int) -> str:
    proc = subprocess.run(
        ["gh", "pr", "view", str(pr), "--json", "id"] + REPO_FLAG,
        capture_output=True,
        text=True,
        env=gh_env(),
    )
    if proc.returncode == 0:
        try:
            return str(json.loads(proc.stdout).get("id") or "")
        except ValueError:
            pass
    return ""


# Thread 3834375737 (PR #41 round 15): remove the PR's live merge-queue
# entry through the dequeuePullRequest mutation. Returns True only when
# the mutation was dispatched AND GitHub accepted it (exit 0 and a
# parseable data.dequeuePullRequest payload); every failure mode — no
# node id, a nonzero exit, an unparseable response — prints its own
# DEQUEUE diagnostic and returns False, so the caller keeps the
# bounded-watch fallback (thread 3833073940's monitoring) and documents
# the attempt in the terminal banner instead of silently leaving the
# live entry in place.
def dequeue_queue_entry(pr: int) -> bool:
    node_id = read_pr_node_id(pr)
    if not node_id:
        print(
            f"DEQUEUE UNAVAILABLE: `gh pr view {pr} --json id` produced "
            f"no node id for the dequeuePullRequest mutation (thread "
            f"3834375737) — the entry cannot be removed programmatically "
            f"from here; falling back to the bounded watch."
        )
        return False
    proc = subprocess.run(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={DEQUEUE_MUTATION}",
            "-f",
            f"id={node_id}",
        ],
        capture_output=True,
        text=True,
        env=gh_env(),
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or "no diagnostic"
        print(
            f"DEQUEUE FAILED: the dequeuePullRequest mutation for PR "
            f"#{pr} exited {proc.returncode} ({detail}, thread "
            f"3834375737); falling back to the bounded watch."
        )
        return False
    try:
        json.loads(proc.stdout)["data"]["dequeuePullRequest"]
    except (KeyError, TypeError, ValueError):
        print(
            f"DEQUEUE FAILED: the dequeuePullRequest mutation for PR "
            f"#{pr} returned an unparseable payload (thread 3834375737); "
            f"falling back to the bounded watch."
        )
        return False
    return True


# Thread 3833073940 (moved home at round 15): one queue-entry probe.
# "QUEUED" — the GraphQL mergeQueueEntry is present (the definitive
# read; only gh 2.97.0's pr view --json lacks the field, the raw API
# has it). "ABSENT" — the probe is readable and the entry is null.
# "AMBIGUOUS" — the GraphQL probe itself failed (field/schema/auth);
# the REST record is read for corroboration, mergeable_state 'blocked'
# being CONSISTENT with a queued entry (and with ordinary unmet
# requirements), so ambiguity fails closed — never a clean absence
# claim on weaker evidence.
def read_queue_contingency(pr: int) -> str:
    proc = subprocess.run(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={QUEUE_ENTRY_QUERY}",
            "-F",
            f"owner={REPO_OWNER}",
            "-F",
            f"name={REPO_NAME}",
            "-F",
            f"number={pr}",
        ],
        capture_output=True,
        text=True,
        env=gh_env(),
    )
    if proc.returncode == 0:
        try:
            node = json.loads(proc.stdout)["data"]["repository"]["pullRequest"]
            return "QUEUED" if node.get("mergeQueueEntry") else "ABSENT"
        except (KeyError, TypeError, ValueError):
            pass
    mergeable_state = ""
    proc = subprocess.run(
        ["gh", "api", f"repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr}"],
        capture_output=True,
        text=True,
        env=gh_env(),
    )
    if proc.returncode == 0:
        try:
            mergeable_state = str(
                json.loads(proc.stdout).get("mergeable_state") or ""
            )
        except ValueError:
            pass
    print(
        f"QUEUE PROBE GraphQL unreadable — REST mergeable_state="
        f"{mergeable_state or 'unreadable'} (thread 3833073940: 'blocked' "
        f"is consistent with a queued entry; neither value proves "
        f"absence) — treating the queue contingency as AMBIGUOUS."
    )
    return "AMBIGUOUS"


# Thread 3834375737 (PR #41 round 15): one dequeue SETTLEMENT attempt
# — attempt the mutation, then RE-VERIFY the removal with the probe
# (never the mutation's response alone): a state re-read of MERGED
# goes straight through the revert path; ABSENT + OPEN enters the
# settling window (injected as `settle_watch` to keep imports one
# way); anything else becomes the REPORT the queue watch and its
# terminal banner document. Returns (terminal result or None to keep
# watching, report clause). Thread 3834988957 (round 23): disable_rc
# (the cancel loop's observed --disable-auto exit code) rides along
# to the settling watch so the converged banner reports the ACTUAL
# rc on the queued path instead of implying success. Thread
# 3835501549 (round 30): the pre-dispatch merge identity rides the
# same path so the MERGED verdict observed after a dequeue is gated
# through the pre-existing check before any revert. Thread 3835501550
# (round 30): the settle watch's REAPPEARED sentinel maps to the
# keep-watching report (the removal genuinely happened, but the entry
# re-entered the window live) — never a terminal verdict.
# Thread 3835587500 (round 31): a plain-None settle watch return gets
# its own AMBIGUOUS-settlement report clause — the sentinel and the
# weaker-evidence None are DIFFERENT facts, and the report/banner must
# not claim a reappearance only the sentinel proves. Thread
# 3836600782 (PR #45 round 17, P1): the transition-evidence holder
# rounds 8-16 threaded through this flow is RETIRED (no client-side
# observation can attribute a failed dispatch's landing — the
# reviewer's rounds 7-17 chain); a MERGED verdict after a dequeue is
# uniformly AMBIGUOUS on the failed path, never attributed.
def attempt_queue_dequeue(
    pr: int,
    base: str,
    attempts: int,
    probe: int,
    settle_watch,
    disable_rc: int | None = None,
    commits: list[str] | None = None,
    frozen_base_tip: str = "",
    pre_merged: bool = False,
    pre_merge_sha: str = "",
    open_merge_sha: str = "",
    dispatch_ts: float = 0.0,
    dispatch_failed: bool = False,
) -> tuple[str | int | None, str]:
    if not dequeue_queue_entry(pr):
        return None, (
            f"was attempted at queue-watch probe {probe} and FAILED — "
            f"the DEQUEUE diagnostics above name the failure (thread "
            f"3834375737)"
        )
    state = read_pending_state(pr)
    if state == "MERGED":
        return (
            revert_landed_during_cancel(
                pr, base, commits, frozen_base_tip,
                pre_merged, pre_merge_sha,
                open_merge_sha, dispatch_ts, dispatch_failed,
            ),
            "",
        )
    if read_queue_contingency(pr) == "ABSENT" and state == "OPEN":
        print(
            f"QUEUE ENTRY DEQUEUED: the dequeuePullRequest mutation "
            f"removed the live entry (queue-watch probe {probe}, thread "
            f"3834375737) and the re-probe reads ABSENT with the PR "
            f"still OPEN — verifying the removal through the settling "
            f"window before any converged claim."
        )
        settled = settle_watch(
            pr,
            base,
            attempts,
            probe,
            (
                f"the live entry was REMOVED by the "
                f"dequeuePullRequest mutation at queue-watch probe "
                f"{probe} (thread 3834375737) and "
            ),
            disable_rc,
            commits,
            frozen_base_tip,
            pre_merged=pre_merged,
            pre_merge_sha=pre_merge_sha,
            open_merge_sha=open_merge_sha,
            dispatch_ts=dispatch_ts,
            dispatch_failed=dispatch_failed,
        )
        if settled is not None and settled is not REAPPEARED:
            return settled, ""
        if settled is REAPPEARED:
            return None, (
                f"SUCCEEDED at queue-watch probe {probe} and the entry read "
                f"ABSENT, but it REAPPEARED inside the settling window "
                f"(thread 3834375737)"
            )
        # Thread 3835587500 (PR #41 round 31): plain None is the
        # AMBIGUOUS-settlement outcome — the dequeue mutation
        # SUCCEEDED and the entry read ABSENT, but the injected watch
        # returned on WEAKER EVIDENCE (a subsequent state, queue, or
        # auto-merge probe unreadable or non-OPEN), which proves
        # neither convergence nor reappearance. Only the REAPPEARED
        # sentinel above proves the re-enqueue event; the old form
        # collapsed this case into the REAPPEARED clause and fed
        # operators false evidence of a competing re-enqueue through
        # the progress and terminal cancellation banners.
        return None, (
            f"SUCCEEDED at queue-watch probe {probe} and the entry read "
            f"ABSENT, but the settlement watch ended AMBIGUOUS — a later "
            f"state, queue, or auto-merge probe was weaker or unreadable, "
            f"so neither convergence nor reappearance is proven (threads "
            f"3834375737/3835587500)"
        )
    return None, (
        f"SUCCEEDED at queue-watch probe {probe} but the entry did NOT "
        f"read ABSENT on the re-probe (thread 3834375737)"
    )
