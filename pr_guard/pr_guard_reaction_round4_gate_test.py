"""pr_guard reaction round-4 GATE tests (PR #49, thread 3867757449).

Thread 3867757449 (P1): the informational banner never sits between
a gate survey's thread snapshot and its dispatch decision — survey()
keeps the banner AFTER the summary by default (human-facing
informational contexts) while the guarded merge's CLOSING survey
passes reaction=False and dispatches no reaction read at all.
Round 5 (thread 3867897759, P1) brought the post-merge quiet watch
into the bannerless camp as well — its cycles and final verdict are
gate decisions (the round-5 suite covers the multi-cycle shape).

Split from pr_guard_reaction_round4_test at the 250 pure-LOC
ceiling (tests included) — the gate/survey discipline beside the
reaction-module semantics.

No network: fetch_threads and the banner are patched at their seams
inside pr_guard_threads; the merge act runs on the shared fake-gh/
fake-git/fake-clock harness.

Run: cd .omo/start-work && python3 -m unittest pr_guard_reaction_round4_gate_test -v
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_threads
from .pr_guard_merge_fixtures import thread
from .pr_guard_merge_harness import MergeHarness, merged

RUNNER = MergeHarness()


class ClosingSurveyTests(unittest.TestCase):
    def survey_run(self, reaction_flag):
        calls = []
        out = io.StringIO()

        def fake_banner(pr, labels=None):
            calls.append(pr)
            print("BOT REACTION: THUMBS_UP (fake) — threads are the authority")
            return "THUMBS_UP"

        with mock.patch.object(
            pr_guard_threads,
            "fetch_threads",
            return_value=[thread("3867757439", "resolved")],
        ), mock.patch.object(
            pr_guard_threads, "reaction_banner", side_effect=fake_banner
        ), redirect_stdout(out):
            threads = pr_guard_threads.survey(48, reaction=reaction_flag)
        return threads, calls, out.getvalue()

    def test_closing_survey_dispatches_no_reaction_read(self):
        # Given: a gate survey (the guarded merge's closing shape)
        # over one resolved thread. When: survey runs with
        # reaction=False. Then: the SUMMARY prints with NO BOT
        # REACTION line and the banner read NEVER DISPATCHES — the
        # informational read cannot stall between the snapshot and
        # the go/no-go (thread 3867757449).
        threads, calls, text = self.survey_run(False)
        self.assertEqual(len(threads), 1)
        self.assertEqual(calls, [])
        self.assertIn("SUMMARY pr=48 total=1", text)
        self.assertNotIn("BOT REACTION", text)

    def test_informational_survey_keeps_the_banner_after_the_summary(self):
        # Given: a human-facing informational survey (the plain CLI
        # survey mode) over the same thread. When: survey runs with
        # the default flag. Then: the banner STILL prints — AFTER the
        # SUMMARY, its useful place — and the thread list returns.
        threads, calls, text = self.survey_run(True)
        self.assertEqual(calls, [48])
        self.assertIn("SUMMARY pr=48 total=1", text)
        self.assertIn("BOT REACTION", text)
        self.assertLess(text.index("SUMMARY pr=48"), text.index("BOT REACTION"))

    def test_merge_closing_survey_passes_the_flag(self):
        # Given: a guarded merge act over a clean resolved-thread
        # snapshot. When: the act runs its surveys. Then: the FIRST —
        # the dispatch-gating closing survey — is bannerless
        # (reaction=False) and so is EVERY post-merge QUIET-WATCH
        # survey (thread 3867897759, round 5: each cycle's DANGER
        # check and the final MERGED CLEAN verdict are gate decisions
        # — the banner lives only in the human-facing CLI surveys):
        # absent between snapshot and go/no-go throughout the act.
        RUNNER.run_guarded(
            iter([[thread("11", "resolved")]]),
            iter(
                [
                    {
                        "head": {"sha": "b979176095b9dd6b6f8e989ed460feab9ce0abc4"},
                        "base": {"ref": "dev"},
                        "state": "open",
                        "merged": False,
                        "merge_commit_sha": "",
                    }
                ]
            ),
            poll_states=[merged()],
        )
        self.assertEqual(RUNNER.survey_reactions, [False, False])


if __name__ == "__main__":
    unittest.main()
