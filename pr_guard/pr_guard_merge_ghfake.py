"""The fake-gh half of the merge-act harness (PR #41 round 31).

Split from pr_guard_merge_harness.py at the 250 pure-LOC ceiling:
the harness stood at 265 pure LOC (over the ceiling since the
round-25 gitfake split's recount), so the `gh`-argv answering
branches of fake_run moved here as a factory — the exact precedent
of pr_guard_merge_gitfake (a PLAIN module; importing it adds nothing
to unittest discovery). The factory receives every fixture knob the
gh branches closed over; an UNMATCHED argv returns None exactly as
the old fall-through did (the runner's merge/create/rc_for tail then
governs). Like the gitfake, CompletedProcess objects are returned,
never run — no network.

Imports flow ONE way (harness -> ghfake -> fixtures/common).
"""

import json
import subprocess

from .pr_guard_common import CANCEL_FIELDS
from .pr_guard_dequeue import DEQUEUE_MUTATION
from .pr_guard_merge_fixtures import MERGE_SHA, PR_NODE_ID
from .pr_guard_merge_fixtures import commits_page


# The fake-gh branch of the harness's fake_run (round 31 split).
# Answers, in order: `gh pr view --json ...` (CANCEL_FIELDS from
# cancel_reads — the last provided read repeats forever so converged/
# MERGED tails need no padding; headRefOid from head_reads; the
# GraphQL node id for the dequeue mutation; otherwise poll_states or
# the merged() default), `gh api graphql` (the dequeue mutation FIRST
# from dequeue_next so an attempt never consumes a queue-entry
# reading, then the queue-entry fixture with "FAIL" driving the REST
# corroboration), the paginated PR commit-list REST read, and the
# plain `gh api` REST mergeable_state read. An exception item raises
# (the interrupt-during-subprocess fixture). Returns None for any
# non-gh argv.
def make_gh_fake(
    cancel_reads,
    head_reads,
    head_default,
    poll_states,
    merged_default,
    pr_commits,
    queue_entries,
    rest_states,
    dequeue_next,
):
    def handle(argv):
        if argv[:3] == ["gh", "pr", "view"]:
            fields = argv[argv.index("--json") + 1]
            if fields == CANCEL_FIELDS:
                # The last provided cancel read repeats forever,
                # so converged/MERGED tails need no padding.
                if cancel_reads is None:
                    state = {"autoMergeRequest": None, "state": "OPEN"}
                elif len(cancel_reads) > 1:
                    state = cancel_reads.pop(0)
                else:
                    state = cancel_reads[0]
            elif fields == "headRefOid":
                state = {
                    "headRefOid": (
                        head_reads.pop(0) if head_reads else head_default
                    )
                }
            elif fields == "id":
                # Thread 3834375737 (PR #41 round 15): the PR's
                # GraphQL node id for the dequeue mutation.
                state = {"id": PR_NODE_ID}
            elif poll_states:
                state = poll_states.pop(0)
            else:
                state = merged_default
            # Thread 3833360219 (PR #41 round 7): an exception
            # item simulates the interrupt arriving DURING the
            # subprocess call (the advertised multi-minute wait).
            if isinstance(state, BaseException):
                raise state
            return subprocess.CompletedProcess(
                argv, 0, stdout=json.dumps(state), stderr=""
            )
        if argv[:3] == ["gh", "api", "graphql"]:
            # Thread 3834375737 (PR #41 round 15): the dequeue
            # mutation is its OWN graphql call — answer it from
            # dequeue_next BEFORE the queue-entry fixture is
            # consulted, so a dequeue attempt never consumes a
            # probe reading.
            if f"query={DEQUEUE_MUTATION}" in argv:
                if (dequeue_rc_now := dequeue_next()) != 0:
                    return subprocess.CompletedProcess(
                        argv, dequeue_rc_now, stdout="",
                        stderr="dequeue refused",
                    )
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout=json.dumps(
                        {
                            "data": {
                                "dequeuePullRequest": {
                                    "clientMutationId": None
                                }
                            }
                        }
                    ),
                    stderr="",
                )
            if queue_entries is None:
                entry = None
            elif len(queue_entries) > 1:
                entry = queue_entries.pop(0)
            else:
                entry = queue_entries[0]
            if entry == "FAIL":
                return subprocess.CompletedProcess(
                    argv, 1, stdout="", stderr="probe unreadable"
                )
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {"mergeQueueEntry": entry}
                            }
                        }
                    }
                ),
                stderr="",
            )
        if argv[:2] == ["gh", "api"] and "/commits?" in argv[-1]:
            # Thread 3834883632 (PR #41 round 21): the PAGINATED
            # PR commit-list read (REST pulls/<n>/commits pages)
            # — served from pr_commits by the fixtures helper in
            # per_page=100 chunks.
            return subprocess.CompletedProcess(
                argv, 0,
                stdout=json.dumps(
                    commits_page(argv, pr_commits or [MERGE_SHA])
                ),
                stderr="",
            )
        if argv[:2] == ["gh", "api"]:
            if rest_states and len(rest_states) > 1:
                mergeable_state = rest_states.pop(0)
            else:
                mergeable_state = (
                    rest_states[0] if rest_states else "blocked"
                )
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps({"mergeable_state": mergeable_state}),
                stderr="",
            )
        return None

    return handle
