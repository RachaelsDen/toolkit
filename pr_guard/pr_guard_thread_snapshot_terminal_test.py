"""Terminal paginated snapshot regressions."""

import io
import unittest
from contextlib import redirect_stderr
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


def paginated_payload(first_body, visible_start, visible_end, held_start, held_end, has_next, has_previous, last_body="Fixed."):
    nodes = [issue_node(1, first_body)] + [
        issue_node(comment_id, "Fixed.") for comment_id in range(2, 102)
    ]
    nodes[-1] = issue_node(101, last_body)
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


def identity_read(first_body, first_tail_body, second_tail_body=None):
    second_tail_body = second_tail_body or first_tail_body
    return [
        paginated_payload(first_body, 0, 0, 0, 100, False, True, first_tail_body),
        paginated_payload(first_body, 0, 0, 100, 101, False, False, second_tail_body),
    ]


def paginated_attempt(first_body, tail_body="Fixed."):
    return [
        paginated_payload(first_body, 0, 0, 0, 0, False, False, tail_body),
        paginated_payload(first_body, 0, 100, 0, 0, True, False, tail_body),
        paginated_payload(first_body, 100, 101, 0, 0, False, False, tail_body),
        *identity_read(first_body, tail_body),
        *identity_read(first_body, tail_body),
    ]


def changing_fixed_point_attempt():
    return [
        *paginated_attempt("stable", "before")[:3],
        *identity_read("stable", "before"),
        *identity_read("stable", "after"),
        *identity_read("stable", "before"),
        *identity_read("stable", "after"),
    ]


class TerminalSnapshotTests(unittest.TestCase):
    def test_second_page_edit_retries_until_the_fixed_point_surfaces_it(self):
        # Given: the tail changes while the first complete identity read fetches page two.
        # When: its adjacent sibling differs. Then: the fixed point and snapshot both retry.
        responses = iter(
            paginated_attempt("stable", "before")[:3]
            + identity_read("stable", "before", "after")
            + identity_read("stable", "after")
            + identity_read("stable", "after")
            + paginated_attempt("stable", "after")
        )
        calls = []

        def fake_graphql(query, variables):
            calls.append((query, variables))
            return next(responses)

        with mock.patch.object(pr_guard_threads, "gh_graphql", side_effect=fake_graphql):
            _, comments = pr_guard_threads.fetch_threads(68)
        self.assertEqual(comments[-1].body, "after")
        self.assertEqual(len(calls), 16)

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

    def test_changing_fixed_point_fails_closed_after_snapshot_attempts_exhaust(self):
        # Given: every adjacent complete identity pair differs. When: fetched.
        # Then: the bounded snapshot retries fail closed instead of accepting a mixed walk.
        responses = iter(changing_fixed_point_attempt() * 3)
        calls = []
        error = io.StringIO()

        def fake_graphql(query, variables):
            calls.append((query, variables))
            return next(responses)

        with mock.patch.object(pr_guard_threads, "gh_graphql", side_effect=fake_graphql), redirect_stderr(error), self.assertRaises(SystemExit) as raised:
            pr_guard_threads.fetch_threads(68)
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("could not collect a stable snapshot", error.getvalue())
        self.assertEqual(len(calls), 33)


if __name__ == "__main__":
    unittest.main()
