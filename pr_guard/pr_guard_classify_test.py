"""pr_guard classification tests.

Split from pr_guard_test.py at the 250 pure-LOC ceiling (PR #37, thread
3828495567); the classification seams moved to pr_guard_classify.py in
the same round. No network: classify is pure.

Run: cd .omo/start-work && python3 -m unittest pr_guard_classify_test -v
"""

import unittest

from . import pr_guard_threads


def make_thread(
    last_author,
    resolved=False,
    outdated=False,
    author_type="User",
    same=False,
):
    # Given-shaped helper: a thread whose varying fields are the last
    # comment's author login + actor type (plus the two server flags);
    # same=True models an unreplied finding (head == last).
    return pr_guard_threads.Thread(
        node_id="PRRT_test",
        head_id=3800000001,
        last_id=3800000001 if same else 3800000002,
        last_author=last_author,
        last_author_type=author_type,
        last_body="finding",
        is_resolved=resolved,
        is_outdated=outdated,
    )



class ClassifyTests(unittest.TestCase):
    def test_unreplied_human_finding_is_not_a_receipt(self):
        # Given: an unresolved thread a HUMAN opened that nobody replied
        # to — head and last are the SAME human comment (thread
        # 3827843271). When: classified.
        # Then: DANGER — the finding itself is not a receipt; only an
        # actual later human reply clears the thread.
        self.assertEqual(
            pr_guard_threads.classify(make_thread("RachaelsDen", same=True)),
            "DANGER",
        )

    def test_bot_last_comment_is_danger_even_when_outdated(self):
        # Given: an unresolved thread whose diff hunk went outdated with
        # the allowlisted bot's finding still the last word (thread
        # 3827397510). When: classified.
        # Then: DANGER — a moved hunk does not prove the defect was fixed.
        self.assertEqual(
            pr_guard_threads.classify(
                make_thread("chatgpt-codex-connector", outdated=True)
            ),
            "DANGER",
        )

    def test_human_receipt_beats_outdated_flag(self):
        # Given: an outdated thread whose last comment is our receipt.
        # When: classified. Then: receipted — receipts clear outdated too.
        self.assertEqual(
            pr_guard_threads.classify(
                make_thread("RachaelsDen", outdated=True)
            ),
            "receipted",
        )

    def test_unknown_or_deleted_author_fails_closed(self):
        # Given: an unresolved thread with no readable author/type.
        # When: classified. Then: DANGER — never silently safe.
        self.assertEqual(
            pr_guard_threads.classify(make_thread(None, author_type=None)),
            "DANGER",
        )

    def test_resolved_thread_classification(self):
        # Given: one already-resolved thread whose last comment is the
        # trusted human receipt, one resolved with the allowlisted bot's
        # follow-up as the last word, one resolved by its own trusted
        # author with no reply (head == last), one resolved with an
        # UNTRUSTED human's last word, and one unresolved thread whose
        # last comment is the allowlisted github-actions[bot].
        # When: classified.
        # Then: resolved / DANGER (thread 3828232337 — resolve state
        # alone is not a receipt; a bot holding the last word on a
        # resolved thread must keep blocking the gate) / resolved (the
        # trusted self-resolver IS the receipt) / DANGER (thread
        # 3828399604) / DANGER.
        self.assertEqual(
            pr_guard_threads.classify(make_thread("RachaelsDen", resolved=True)),
            "resolved",
        )
        self.assertEqual(
            pr_guard_threads.classify(
                make_thread("chatgpt-codex-connector", resolved=True)
            ),
            "DANGER",
        )
        self.assertEqual(
            pr_guard_threads.classify(
                make_thread("RachaelsDen", resolved=True, same=True)
            ),
            "resolved",
        )
        self.assertEqual(
            pr_guard_threads.classify(
                make_thread("some-outsider", resolved=True)
            ),
            "DANGER",
        )
        self.assertEqual(
            pr_guard_threads.classify(make_thread("github-actions[bot]")),
            "DANGER",
        )

    def test_untrusted_human_reply_is_not_a_receipt(self):
        # Given: an unresolved thread whose last comment is a human
        # OUTSIDE the trusted receipt accounts replying "this is still
        # broken" (thread 3828399604). When: classified.
        # Then: DANGER — a receipt is proof a FINDING was handled, so
        # only a trusted maintainer reply counts.
        self.assertEqual(
            pr_guard_threads.classify(make_thread("some-outsider")),
            "DANGER",
        )

    def test_resolved_with_unreadable_author_fails_closed(self):
        # Given: a resolved thread whose last comment author is unknown
        # or deleted (thread 3828232337 belt).
        # When: classified. Then: DANGER — never silently safe.
        self.assertEqual(
            pr_guard_threads.classify(
                make_thread(None, resolved=True, author_type=None)
            ),
            "DANGER",
        )

    def test_bot_actor_type_outside_the_allowlist_fails_closed(self):
        # Given: an unresolved thread whose last comment comes from a bot
        # NOT in the allowlist (Dependabot, Copilot, a renamed review
        # app) — actor type Bot (thread 3827503034).
        # When: classified.
        # Then: DANGER — the allowlist alone must never read a bot as a
        # human receipt.
        for login in ("dependabot[bot]", "copilot-pull-request-reviewer"):
            self.assertEqual(
                pr_guard_threads.classify(
                    make_thread(login, author_type="Bot")
                ),
                "DANGER",
                login,
            )

    def test_non_user_actor_types_are_not_receipts(self):
        # Given: Organization/Mannequin-typed last commenters.
        # When: classified. Then: DANGER — only a real User can receipt.
        self.assertEqual(
            pr_guard_threads.classify(
                make_thread("some-org", author_type="Organization")
            ),
            "DANGER",
        )
        self.assertEqual(
            pr_guard_threads.classify(
                make_thread("imported-user", author_type="Mannequin")
            ),
            "DANGER",
        )

    def test_user_shaped_allowlisted_bot_stays_danger(self):
        # Given: an allowlisted login carrying actor type User (a
        # bot operated through a user account — why BOT_AUTHORS stays).
        # When: classified. Then: DANGER.
        self.assertEqual(
            pr_guard_threads.classify(
                make_thread("chatgpt-codex-connector", author_type="User")
            ),
            "DANGER",
        )


if __name__ == "__main__":
    unittest.main()
