"""Wait-mode thread-authority checks.

No network: surveys use their real bannerless path over scripted thread
fetches, while the reaction wait is patched at the CLI boundary.
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from . import cli
from . import pr_guard_threads
from .pr_guard_classify import Thread
from .pr_guard_merge_fixtures import thread


def danger_thread() -> Thread:
    return Thread(
        node_id="PRRT_11",
        head_id=11,
        last_id=12,
        last_author="chatgpt-codex-connector",
        last_author_type="Bot",
        last_body="Unresolved finding.",
        is_resolved=False,
        is_outdated=False,
    )


class WaitThreadPreflightTests(unittest.TestCase):
    def test_preflight_danger_stops_before_any_reaction_probe(self):
        # Given: an unanswered bot finding already exists. When: wait
        # starts. Then: the bannerless survey prints it and exits 3
        # before the reaction poll begins.
        out = io.StringIO()
        reaction_probe = mock.Mock()
        with mock.patch.object(
            pr_guard_threads, "fetch_threads", return_value=([danger_thread()], [])
        ), mock.patch.object(
            pr_guard_threads, "reaction_banner"
        ) as banner, mock.patch.object(
            cli, "wait_reaction", side_effect=reaction_probe
        ), redirect_stdout(out):
            code = cli.main(["pr_guard.py", "wait", "48"])
        self.assertEqual(code, 3)
        reaction_probe.assert_not_called()
        banner.assert_not_called()
        self.assertIn("DANGER     thread=11", out.getvalue())
        self.assertIn(
            "WAIT FINDINGS (pre-existing): unresolved findings at wait start "
            "— the review already ran; threads are the authority",
            out.getvalue(),
        )

    def test_timeout_danger_overrides_reaction_timeout(self):
        # Given: a clean preflight and a DANGER finding in the timeout
        # snapshot. When: the reaction wait returns timeout. Then: the
        # final bannerless survey reports findings with exit 3.
        events = []

        def fetch_threads(pr):
            events.append("survey")
            return (
                ([thread("10", "resolved")], [])
                if len(events) == 1
                else ([danger_thread()], [])
            )

        def reaction_timeout(pr, timeout_secs):
            events.append("wait")
            return 1

        out = io.StringIO()
        with mock.patch.object(
            pr_guard_threads, "fetch_threads", side_effect=fetch_threads
        ), mock.patch.object(
            pr_guard_threads, "reaction_banner"
        ) as banner, mock.patch.object(
            cli, "wait_reaction", side_effect=reaction_timeout
        ), redirect_stdout(out):
            code = cli.main(["pr_guard.py", "wait", "48", "--timeout-secs", "10"])
        self.assertEqual(code, 3)
        self.assertEqual(events, ["survey", "wait", "survey"])
        banner.assert_not_called()
        self.assertIn("DANGER     thread=11", out.getvalue())
        self.assertIn(
            "WAIT FINDINGS (at timeout): findings appeared during the wait; "
            "the reaction could not be attributed — threads are the authority",
            out.getvalue(),
        )

    def test_clean_timeout_keeps_exit_one(self):
        # Given: clean preflight and timeout snapshots. When: the
        # reaction wait times out. Then: wait keeps its timeout exit 1.
        with mock.patch.object(
            pr_guard_threads, "fetch_threads", return_value=([thread("10", "resolved")], [])
        ), mock.patch.object(
            pr_guard_threads, "reaction_banner"
        ) as banner, mock.patch.object(
            cli, "wait_reaction", return_value=1
        ) as wait:
            code = cli.main(["pr_guard.py", "wait", "48"])
        self.assertEqual(code, 1)
        wait.assert_called_once_with(48, cli.DEFAULT_WAIT_TIMEOUT_SECS)
        banner.assert_not_called()

    def test_reaction_pass_does_not_run_the_timeout_survey(self):
        # Given: a clean preflight and a reaction-evidenced pass.
        # When: wait returns 0. Then: only the preflight survey runs;
        # no final authority read follows a reaction terminal result.
        with mock.patch.object(
            pr_guard_threads, "fetch_threads", return_value=([thread("10", "resolved")], [])
        ) as fetch, mock.patch.object(
            pr_guard_threads, "reaction_banner"
        ) as banner, mock.patch.object(
            cli, "wait_reaction", return_value=0
        ):
            code = cli.main(["pr_guard.py", "wait", "48"])
        self.assertEqual(code, 0)
        fetch.assert_called_once_with(48)
        banner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
