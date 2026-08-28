"""pr_guard merge-act round-24 tests (PR #41 round 24, refit 25).

Thread 3835052616 made the SQUASH MARKER the terminal provenance
discriminator — GitHub's default squash subject ends " (#<N>)" —
and thread 3835052612 added the multi-rewrite position gate. PR #41
round 25 RETIRED both with the classifier: thread 3835145976 (this
round's P1) showed a rebase tip's ORIGINAL subject can itself end
in "(#N)" — an issue reference, or a subject amended after the PR
number became known — so the marker is USER-CONTROLLED COMMIT TEXT,
not GitHub-owned landing metadata, and can corroborate nothing. The
marker survives as ONE FAIL-CLOSED-BANNER DIAGNOSTIC: the banner
reports the landing tip's trailing marker to help the human decide,
and NO marker reading licenses or blocks anything. These suites pin
the diagnostic role (a marker-bearing tip beside a foreign parent
fails closed with the marker REPORTED), the spoof shape of thread
3835052616 failing closed BY CONTRACT, and the SHORTENED rebase of
thread 3835175508 failing closed (the round-24 shorter-range squash
fall-through is gone). The remaining marker/multi-rewrite suites
were DELETED with the arms (the suite count drops by design).

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act; landing_probes' commit_meta override serves the marker
subjects (the harness PR is #39, so this PR's own marker is
"(#39)" and "(#37)" is foreign).

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round24_test -v
"""

import unittest

from .pr_guard_merge_harness import (
    FOREIGN_PARENT,
    HEAD,
    MERGE_SHA,
    MergeHarness,
    landing_probes,
    merged,
    thread,
)

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000f00"
COMMIT_X = "bbbb0000000000000000000000000000000000aa"
COMMIT_Y = "cccc0000000000000000000000000000000000bb"
PATCH_X = "ppid0000x"
PATCH_Y = "ppid0000y"
PATCH_TIP = "ppid0000rewritten"
# Thread 3835052616: the spoof pair — the FOREIGN cherry-pick of X
# (exact patch-id/author/subject) beneath this PR's squash of Y
# (the PR title often IS Y's subject, so the squash carries it) —
# and the REBASED twin of X for the genuine shapes.
FOREIGN_DUP = "eeee0000000000000000000000000000000000d1"
REBASED_OLDEST = "eeee000000000000000000000000000000000b01"
# Thread 3835052612: an EARLIER commit also rewritten by conflict
# resolution — a NEW stable patch-id matching no PR commit, beside
# the rewritten tip.
PATCH_REWRITTEN_X = "ppid0000earlierrewrite"
REWRITTEN_X = "eeee0000000000000000000000000000000000c4"
DEFAULT_META = "Queue Bot <queue-bot@example.invalid>|queued change"
SQUASH_SUBJECT_Y = "Queue Bot <queue-bot@example.invalid>|Y (#39)"
FOREIGN_SUBJECT = "Queue Bot <queue-bot@example.invalid>|Z (#37)"


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class MarkerDiagnosticTests(unittest.TestCase):
    def test_marker_bearing_tip_beside_foreign_parent_fails_closed(self):
        # Given: a single-parent landing whose parent is NOT the
        # current base tip AND whose tip subject ends in this PR's
        # own marker "(#39)". The round-24 rules classified SQUASH on
        # the marker alone; thread 3835145976 proved a rebase tip's
        # ORIGINAL subject can itself end in "(#N)", so the round-25
        # contract fails the shape closed and merely REPORTS the
        # marker in the banner as a diagnostic.
        surveys = iter([[thread("11", "resolved")]])

        # When: the fail-closed banner runs its marker diagnostic
        # over the marker-bearing tip.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=[COMMIT_X, COMMIT_Y],
            git_answers=landing_probes(
                MERGE_SHA,
                commit_meta={MERGE_SHA: SQUASH_SUBJECT_Y},
            ),
        )

        # Then: NO revert argv was dispatched — the marker licensed
        # nothing — and the banner REPORTS the trailing marker beside
        # the explicit warning that a marker is user-controlled text.
        self.assertEqual(code, 1)
        self.assertIn(
            f"git log --no-walk --format=%H|%an <%ae>|%s {MERGE_SHA}",
            argvs,
        )
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn("ends in the squash marker \"(#39)\"", out)
        self.assertIn("USER-CONTROLLED commit text", out)
        self.assertIn("3835145976", out)
        self.assertIn("MUST be reverted manually", out)

    def test_marker_probe_unreadable_reports_the_degradation(self):
        # Given: the same fail-closed shape, but the `git log`
        # subject probe itself is UNREADABLE — the banner reports the
        # probe as unreadable, never as "no marker" (an unknown state
        # must not read as a clean one).
        surveys = iter([[thread("11", "resolved")]])

        # When: the marker diagnostic's probe exits nonzero.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=[COMMIT_X, COMMIT_Y],
            git_answers=landing_probes(MERGE_SHA, log_rc=1),
        )

        # Then: the banner still failed closed on the shape and
        # reports the subject probe as UNREADABLE.
        self.assertEqual(code, 1)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn("subject probe was UNREADABLE", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)


class MarkerSpoofRetirementTests(unittest.TestCase):
    def test_marker_tip_spoof_fails_closed_by_contract(self):
        # Given: thread 3835052616's exact spoof — this PR holds
        # [X, Y]; an earlier queue entry CHERRY-PICKED X and this PR
        # then landed as a SQUASH whose incremental diff IS Y's, with
        # GitHub's DEFAULT squash subject "Y (#39)" — every
        # count/membership/order/contiguity/author-subject/delta rule
        # holds and the tip carries the marker. The round-24 rules
        # classified SQUASH here and reverted the landing alone;
        # round 25 fails the shape closed (the parent is the FOREIGN
        # duplicate, not the base tip) because no signal — the marker
        # included — can prove which commits belong to this PR.
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires on the spoof landing.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=[COMMIT_X, COMMIT_Y],
            git_answers=landing_probes(
                MERGE_SHA,
                range_shas=[FOREIGN_DUP, MERGE_SHA],
                commit_meta={MERGE_SHA: SQUASH_SUBJECT_Y},
            ),
        )

        # Then: FAIL CLOSED — no revert argv (neither the one-commit
        # squash revert the marker used to license nor a range over
        # the foreign duplicate), the banner carries the numbers and
        # the REPORTED marker, and the counter-example chain is
        # cited.
        self.assertEqual(code, 1)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn("counts 2 commit(s)", out)
        self.assertIn("ends in the squash marker \"(#39)\"", out)
        self.assertIn("3835175506", out)
        self.assertIn("3835145976", out)

    def test_shortened_rebase_fails_closed_no_squash_fall_through(self):
        # Given: thread 3835175508's SHORTENED rebase — the queue
        # advancement already contained X+Y, so the rebase dropped
        # them (`git rebase --empty=drop` /
        # `--no-reapply-cherry-picks`) and landed only [Z, W'] for a
        # FOUR-commit PR: the range is SHORTER than the PR's commit
        # count, exactly the shape the round-24 squash fall-through
        # automated (fewer commits than the PR "can never be its
        # rebase replay"). It can — the dropped-back commits stay on
        # the base — so the fall-through is GONE and the shape fails
        # closed by contract.
        surveys = iter([[thread("11", "resolved")]]
        )
        commits = [
            COMMIT_X,
            COMMIT_Y,
            "dddd0000000000000000000000000000000000cc",
            "dddd0000000000000000000000000000000000dd",
        ]

        # When: the head-mismatch revert fires on the shortened
        # landing (parent is not the base tip; the range counts 2).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            parent_probe_rc=1,
            landing_parent=FOREIGN_PARENT,
            pr_commits=commits,
            git_answers=landing_probes(MERGE_SHA, landed=2),
        )

        # Then: FAIL CLOSED — never the one-commit squash revert the
        # shorter-range fall-through used to build; the banner
        # carries the shortened numbers (2 landed vs the frozen 4)
        # and cites 3835175508.
        self.assertEqual(code, 1)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertIn("REVERT BLOCKED", out)
        self.assertIn("counts 2 commit(s)", out)
        self.assertIn(
            "FROZEN pre-dispatch commit snapshot counts 4 commit(s)", out
        )
        self.assertIn("3835175508", out)
        self.assertIn("MUST be reverted manually", out)


if __name__ == "__main__":
    unittest.main()
