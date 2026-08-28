"""pr_guard revert-trigger copy tests (PR #41 round 7, thread
3833360211).

guarded_revert is reached from FIVE paths, and the old revert PR
title/body always claimed a DANGER-thread survey finding plus a
survey->merge race — false for every path except the quiet-watch
DANGER one. Each caller now passes its trigger key, and the PR the
reviewer actually sees renders THIS path's reason. No network: the
scenarios ride the shared fake-gh harness; the copy is asserted on
the full `gh pr create` argv (revert_create_argv).

Run: cd .omo/start-work && python3 -m unittest pr_guard_revert_trigger_test -v
"""

import unittest

from . import pr_guard_revert
from .pr_guard_merge_harness import (
    HEAD,
    MERGE_SHA,
    MergeHarness,
    merged,
    pending,
    thread,
)

RUNNER = MergeHarness()
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


class TriggerCopyTests(unittest.TestCase):
    def test_retargeted_base_trigger_renders_its_own_copy(self):
        # Given: the PR was retargeted inside the check->merge window
        # and the completion poll reports MERGED on an UNPROTECTED base
        # (thread 3832321698) — no survey finding exists.
        surveys = iter([[thread("11", "resolved")]])

        # When: the base-mismatch revert fires.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), poll_states=[merged(base="feature/x")]
        )

        # Then: the revert PR title names the RETARGETED base (not a
        # DANGER finding), the body explains the escaped-destination
        # race with its thread, and the historical always-DANGER copy
        # is absent.
        self.assertEqual(code, 1)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn("--base feature/x", create)
        self.assertIn(
            "Revert PR #39: landed on retargeted base", create
        )
        self.assertIn(
            "landed on a base other than the verified one", create
        )
        self.assertIn("thread 3832321698", create)
        self.assertNotIn("DANGER thread", create)
        self.assertNotIn("unanswered review finding", create)

    def test_moved_head_trigger_renders_its_own_copy(self):
        # Given: the request merged a head that moved after the merge
        # request was dispatched (thread 3832522310) — unsurveyed
        # content, but no DANGER thread and no retarget.
        surveys = iter([[thread("11", "resolved")]])

        # When: the head-mismatch revert fires on the verified base.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), poll_states=[merged(head=PUSHED_HEAD)]
        )

        # Then: the title names the UNSURVEYED HEAD.
        self.assertEqual(code, 1)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn("--base dev", create)
        self.assertIn(
            "Revert PR #39: merged an unsurveyed head", create
        )
        self.assertIn("never surveyed against", create)
        self.assertIn("thread 3832522310", create)
        self.assertNotIn("DANGER thread", create)

    def test_danger_trigger_keeps_the_survey_finding_copy(self):
        # Given: a bot last word survived into the post-merge
        # quiet-period watch (thread 3829356723) — the ONE path the
        # historical copy was true for.
        surveys = iter(
            [[thread("11", "resolved")], [thread("11", "DANGER")]]
        )

        # When: the quiet-watch revert fires.
        code, out, argvs, events = RUNNER.run_guarded(surveys, pinned())

        # Then: the title names the bot finding after merge, and the
        # body keeps the survey->merge race explanation.
        self.assertEqual(code, 1)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(
            "Revert PR #39: bot finding after merge", create
        )
        self.assertIn("found DANGER thread(s)", create)
        self.assertIn("thread 3829356723", create)

    def test_survey_failed_trigger_renders_its_own_copy(self):
        # Given: the merge landed cleanly but the backstop survey DIED
        # (thread 3832321706) — an unverified landing, not a finding.
        surveys = iter([[thread("11", "resolved")], SystemExit(2)])

        # When: the fail-closed revert fires.
        code, out, argvs, events = RUNNER.run_guarded(surveys, pinned())

        # Then: the title names the FAILED SURVEY.
        self.assertEqual(code, 1)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(
            "Revert PR #39: post-merge survey failed", create
        )
        self.assertIn("could not run to completion", create)
        self.assertIn("thread 3832321706", create)
        self.assertNotIn("found DANGER thread", create)

    def test_landed_during_cancel_trigger_renders_its_own_copy(self):
        # Given: the pending request landed while the poll/cancel was
        # in flight (threads 3832522306/3833251675/3833360201) — the
        # queue entry went ABSENT and the settling window caught the
        # MERGED flip.
        surveys = iter([[thread("11", "resolved")]])

        # When: the landed-during-cancel revert fires.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys, pinned(), poll_states=[pending()] * 32 + [merged()]
        )

        # Then: the title names the merge landing DURING CANCELLATION.
        self.assertEqual(code, 1)
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(
            "Revert PR #39: merge landed during cancellation", create
        )
        self.assertIn("landed while the poll/cancel was in flight", create)
        self.assertIn("3833073949", create)
        self.assertNotIn("found DANGER thread", create)

    def test_trigger_map_pins_the_five_paths(self):
        # Given/When: the trigger mapping is read. Then: exactly the
        # five paths that reach guarded_revert carry distinct title
        # phrases (thread 3833360211) — no path silently shares
        # another's reason.
        self.assertEqual(
            set(pr_guard_revert.REVERT_TRIGGERS),
            {
                "danger",
                "retargeted_base",
                "moved_head",
                "survey_failed",
                "landed_during_cancel",
            },
        )
        titles = [
            phrase for phrase, _ in pr_guard_revert.REVERT_TRIGGERS.values()
        ]
        self.assertEqual(len(titles), len(set(titles)))


if __name__ == "__main__":
    unittest.main()
