"""Terminal paginated snapshot regressions."""

import unittest
from unittest import mock

from . import pr_guard_threads

TIMESTAMP = "2026-09-20T10:00:00Z"


def issue_node(comment_id, body):
    return {
        "databaseId": comment_id,
        "author": {"login": "RachaelsDen", "__typename": "User"},
        "body": body,
        "createdAt": TIMESTAMP,
        "updatedAt": TIMESTAMP,
    }


def paginated_payload(first_body, visible_start, visible_end, held_start, held_end, has_next, has_previous):
    nodes = [issue_node(1, first_body)] + [
        issue_node(comment_id, "Fixed.") for comment_id in range(2, 102)
    ]
    root = {
        "updatedAt": TIMESTAMP,
        "reviewThreads": {
            "totalCount": 0,
            "pageInfo": {"endCursor": None, "hasNextPage": False},
            "nodes": [],
        },
        "comments": {
            "totalCount": len(nodes),
            "pageInfo": {"endCursor": None, "hasNextPage": has_next},
            "nodes": nodes[visible_start:visible_end],
        },
        "lastThread": {"nodes": []},
        "lastComment": {"nodes": nodes[-1:]},
        "heldThreads": {
            "pageInfo": {"startCursor": None, "hasPreviousPage": False},
            "nodes": [],
        },
        "heldComments": {
            "pageInfo": {
                "startCursor": "comment-page" if has_previous else None,
                "hasPreviousPage": has_previous,
            },
            "nodes": nodes[held_start:held_end],
        },
    }
    return {"repository": {"pullRequest": root}}


def paginated_attempt(first_body):
    return [
        paginated_payload(first_body, 0, 0, 0, 0, False, False),
        paginated_payload(first_body, 0, 100, 0, 0, True, False),
        paginated_payload(first_body, 100, 101, 0, 0, False, False),
        paginated_payload(first_body, 0, 0, 0, 100, False, True),
        paginated_payload(first_body, 0, 0, 100, 101, False, False),
        paginated_payload(first_body, 0, 0, 0, 100, False, True),
        paginated_payload(first_body, 0, 0, 100, 101, False, False),
    ]


class TerminalSnapshotTests(unittest.TestCase):
    def test_non_tail_same_second_edit_between_terminal_reads_retries(self):
        # Given: a two-page validation whose non-tail node changes only in body.
        # When: the terminal reread observes the same-second edit. Then: retry returns it.
        responses = iter(
            paginated_attempt("before")[:5]
            + paginated_attempt("after")[5:]
            + paginated_attempt("after")
        )
        calls = []

        def fake_graphql(query, variables):
            calls.append((query, variables))
            return next(responses)

        with mock.patch.object(pr_guard_threads, "gh_graphql", side_effect=fake_graphql):
            _, comments = pr_guard_threads.fetch_threads(68)
        self.assertEqual(comments[0].body, "after")
        self.assertEqual(len(calls), 14)

    def test_adjacent_paginated_terminal_reads_that_agree_accept(self):
        # Given: an unchanged two-page validation. When: both terminal reads agree.
        # Then: the snapshot accepts without a retry.
        responses = iter(paginated_attempt("stable"))
        calls = []

        def fake_graphql(query, variables):
            calls.append((query, variables))
            return next(responses)

        with mock.patch.object(pr_guard_threads, "gh_graphql", side_effect=fake_graphql):
            _, comments = pr_guard_threads.fetch_threads(68)
        self.assertEqual(len(comments), 101)
        self.assertEqual(len(calls), 7)


if __name__ == "__main__":
    unittest.main()
