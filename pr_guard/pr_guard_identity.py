"""The landing-identity gate for the guarded merge act (PR #45
rounds 3-8, terminally resolved round 17).

Split from pr_guard_merge.py BEFORE the round-3 fixes landed (the
family's split-FIRST rule at the 250 pure-LOC ceiling: merge stood
at 242 and thread 3835846318's evidence gate needs its own room).
Imports flow ONE way (merge -> identity -> common); nothing here
imports merge, completion, or revert.

Thread 3835846318 (P1, round 3) first widened the gate for the
ambiguous FAILED dispatch: a stale-OPEN pre-dispatch REST record on
an already-landed PR makes the merge command fail, and the
mismatch/DANGER cycle (with its AUTOMATIC REVERT) could otherwise
run against a historical merge this invocation never dispatched.

PR #45 ROUND 17 (thread 3836600782, P1) — the TERMINAL resolution.
Rounds 7-16 each tried a new client-side attribution signal for the
failed-dispatch path, and the reviewer's counter-example chain
demonstrated every one of them reproducible by a historical merge
hidden in GitHub's REST cache:

  - 3835944058: the open-sha EQUAL arm — a fresh landing can land
    REUSING the very synthetic test-merge object the OPEN record's
    merge_commit_sha names, and the reused object CARRIES ITS OLD
    test-merge creation date (%ct dates the commit OBJECT, not the
    landing EVENT), so neither the sha nor any committer date can
    arbitrate (round 5's margin upgrade, thread 3836003345's
    "failed-dispatch identity is fundamentally underdetermined"
    precedent, closed rounds 5-6's date arms);
  - 3835944061/3836043653: committer-date ordering — the dispatch
    instant is the LOCAL runner's time.time() while %ct is GitHub's
    commit clock, and the two diverge in BOTH directions, so no
    fixed margin ever separated fresh from pre-existing (round 7
    retired the clearly-after verdict, round 8 the clearly-before
    one);
  - 3836217633: the rc-0 IDEMPOTENT NO-OP dispatch — gh exits 0
    reporting "already merged" while GitHub accepted NO request
    from this invocation, so even rc 0 bounds nothing on that shape
    (the no-op signature is classified into the failed-dispatch
    class in pr_guard_merge);
  - 3836149500/3836217630/3836277960: the OBSERVED TRANSITION's
    paced OPEN baseline/credit pairs — a stale pre-dispatch OPEN
    record for an already-merged PR can serve EVERY read of the
    window (both paced reads, every settle/cancel/watch probe)
    before the cache flips to the historical MERGED, so the
    OPEN -> MERGED "flip" is eventual consistency, never proof of a
    merge event inside the watch;
  - 3836380780/3836380790: PENDING baselines and nested-watch
    evidence — widening WHICH reads arm/credit only widened which
    cached sequences the credit accepted;
  - 3836437093/3836437095/3836437098/3836437100: the coherent
    baseline/credit/monotonic-pacing state machine — sound pacing
    still proves nothing about the SERVER's state;
  - 3836501981/3836565818: same-clock updatedAt corroboration —
    comparing the two SERVER-authored stamps avoids the cross-clock
    flaw, but thread 3836600782 closed it too: an already-merged PR
    served from a stale OPEN snapshot for both paced reads and then
    refreshed to the historical MERGED snapshot satisfies
    "advancement between our reads" with two snapshots of the SAME
    historical timeline — ordered snapshots prove only that the
    cache refreshed, never WHEN the merge happened.

CONCLUSION (the round-6 precedent applied terminally): NO
client-side observation of GitHub's REST cache can soundly
attribute a landing to our dispatch on the failed-dispatch path.
The gate's failed-dispatch arm therefore no longer attempts fresh
attribution AT ALL — ANY merge observed after a failed dispatch
(however observed: completion poll, cancel, settle, watch, dequeue)
reports the ONE AMBIGUOUS manual banner (failed_dispatch_ambiguous_
banner below, citing the chain) and exits nonzero WITHOUT
auto-revert. The transition-evidence machinery (the baseline/
credit/updatedAt corroboration holder and its state machine,
pr_guard_transition, rounds 8-16) is DELETED; the committer-date
probe (read_committer_ts, rounds 3-8) is deleted with the date arms
it fed — every branch they served collapsed into the single
disposition.

What survives is exactly what is sound: the round-29/30 TRUSTED
ARMS (is_pre_existing_merge — an already-merged pre-dispatch state,
or an observed mergeCommit EQUAL to the merged-record snapshot's
sha; pre_existing_merge_banner) and the SUCCESSFUL-dispatch path,
where rc 0 itself bounds the landing to after-dispatch (a GENUINE
rc 0 — the no-op signature above is classified out — so the gate
returns None and the ordinary post-merge machinery runs). The
pre-existing check runs FIRST on every path, so a failed dispatch
reconciling into a provably-historical merge still gets the
PRE-EXISTING disposition rather than the ambiguous one.

Thread 3836043658 (PR #45 round 7, P1): every no-revert disposition
here returns the DISTINCT identity-gate code
(pr_guard_common.IDENTITY_GATE_EXIT), never a bare 1 — guarded_revert
completed reverts and revert failures share the integer channel
(0/1), and merge_guarded's final handling branches on the codes so a
gated exit is never reported as a completed revert.

Thread 3835877364 (PR #45 round 4): the SAME gate serves the
cancel/settlement entry points — revert_landed_during_cancel routes
every cancel/interrupt MERGED verdict through this gate (via the
`entry` label), so a historical merge that only becomes visible
during timeout cancellation or interrupt reconciliation is never
auto-reverted either — and under round 17 every failed-dispatch
landing on those paths is uniformly AMBIGUOUS too.
"""

from .pr_guard_common import IDENTITY_GATE_EXIT, is_pre_existing_merge
from .pr_guard_common import pre_existing_merge_banner


# Thread 3835846318 -> thread 3836600782: the gate itself. Returns
# None when the ordinary post-merge path must proceed — ONLY the
# successful dispatch's landing (a GENUINE rc 0 bounds it to
# after-dispatch; threads 3836217633's no-op dispatch is classified
# into the failed class before the gate is consulted) — and the
# identity-gate code (banner already printed, NO revert) when the
# landing is pre-existing (the round-29/30 trusted arms, sound on
# every path) or the dispatch FAILED (round 17: uniformly AMBIGUOUS,
# whatever the observation path — poll, cancel, settle, watch, or
# dequeue — and whatever shas/stamps/dates the window recorded; the
# rounds 7-16 attribution arms are retired, see the module
# docstring's chain). `open_sha` is the OPEN pre-dispatch record's
# merge_commit_sha — the PRE-DISPATCH capture (thread 3835944058),
# reported by the ambiguous banner when the landing equals it;
# `dispatch_ts` is the wall-clock dispatch instant, reported for the
# manual timeline check (attribution never branches on either).
# Thread 3835877364: `entry` labels the calling path for the banners
# — the reconcile arm ("failed-dispatch", the default) and the
# cancel/settlement arm name where the MERGED verdict came from.
def landing_identity_gate(
    pr: int,
    merge_sha: str,
    pre_merged: bool,
    pre_merge_sha: str,
    open_sha: str,
    dispatch_ts: float,
    dispatch_failed: bool,
    entry: str = "failed-dispatch",
) -> int | None:
    if is_pre_existing_merge(merge_sha, pre_merged, pre_merge_sha):
        if entry != "failed-dispatch":
            print(
                f"PRE-EXISTING MERGE GATE on the {entry} path "
                f"(thread 3835501549, widened by 3835877364): the MERGED "
                f"this path observed is reconciled against the "
                f"pre-dispatch identity BEFORE any landed-during-cancel "
                f"claim — the historical merge is never auto-reverted "
                f"by an invocation whose dispatch did not land it."
            )
        return pre_existing_merge_banner(
            pr, pre_merged, pre_merge_sha, merge_sha
        )
    if not dispatch_failed or not merge_sha:
        return None
    return failed_dispatch_ambiguous_banner(
        pr, merge_sha, open_sha, dispatch_ts, entry
    )


# Thread 3836600782 (PR #45 round 17, P1): the failed-dispatch
# path's ONE disposition. Rounds 7-16 each certified a fresh
# attribution signal and the reviewer's chain proved every one
# reproducible by a historical merge hidden in GitHub's REST cache
# (the module docstring lists the demonstration per thread id);
# thread 3836003345's round-6 verdict — failed-dispatch identity is
# fundamentally underdetermined — is therefore applied terminally:
# NO client-side observation can attribute the landing, so the
# banner reports the ambiguity, cites the chain, and demands the
# manual check. The landing is treated as potentially THIS
# invocation's fresh landing AND potentially pre-existing: NO
# mismatch/head assertions, NO quiet watch, NO automatic revert —
# only a human checking the PR's server-side merge event against
# the dispatch time may attribute it. The sha equality (when the
# landing reuses the OPEN record's synthetic object, thread
# 3835944058) is REPORTED for that check, never branched on.
def failed_dispatch_ambiguous_banner(
    pr: int,
    merge_sha: str,
    open_sha: str,
    dispatch_ts: float,
    entry: str,
) -> int:
    equality = (
        f" The landing sha also EQUALS the merge_commit_sha the OPEN "
        f"pre-dispatch record carried (thread 3835944058) — an "
        f"ACCEPTED-but-failed dispatch can land REUSING that very "
        f"synthetic object, which carries its OLD test-merge date, so "
        f"the equality narrows nothing either."
        if open_sha and merge_sha == open_sha
        else ""
    )
    print(
        f"AMBIGUOUS LANDING — MANUAL CHECK REQUIRED: the {entry} path "
        f"observed landing {merge_sha[:12]} on PR #{pr} after a "
        f"FAILED dispatch, and NO client-side observation can attribute "
        f"it to this invocation (thread 3836600782, PR #45 round 17: "
        f"the reviewer's rounds 7-17 counter-example chain proved every "
        f"attribution signal reproducible by a historical merge hidden "
        f"in GitHub's REST cache — open-sha reuse 3835944058, the "
        f"underdetermined precedent 3836003345, clock skew "
        f"3835944061/3836043653, the rc-0 no-op dispatch 3836217633, "
        f"cached OPEN baselines 3836149500/3836217630/3836277960, "
        f"PENDING/nested-watch evidence 3836380780/3836380790, the "
        f"baseline/credit state machine "
        f"3836437093/3836437095/3836437098/3836437100, same-clock "
        f"stamp corroboration 3836501981, cross-clock stamps "
        f"3836565818, and ordered cache snapshots 3836600782 itself — "
        f"two snapshots of the SAME historical timeline satisfy every "
        f"between-reads test). The transition/corroboration machinery "
        f"is RETIRED on this path; the landing is treated as "
        f"potentially THIS invocation's fresh landing AND potentially "
        f"pre-existing.{equality} NO automatic revert runs; manually "
        f"check the PR's server-side merge event/timeline against the "
        f"dispatch time {dispatch_ts:.0f}, survey the merge, and "
        f"revert via PR only if a human finds it unsafe. Exiting "
        f"nonzero."
    )
    # Thread 3836043658 (round 7): the identity-gate code, not a
    # bare 1 — merge_guarded branches on it (a completed revert is
    # 0, a failed one 1) and must never report this no-revert
    # disposition as a completed revert.
    return IDENTITY_GATE_EXIT
