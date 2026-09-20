"""Body-identity snapshot regressions."""

from __future__ import annotations

import unittest
from hashlib import sha256
from unittest import mock

from . import pr_guard_threads
from .pr_guard_thread_snapshot import (
    IDENTITY_QUERY,
    comment_identity,
    thread_identity,
)

TIMESTAMP = "2026-09-20T10:00:00Z"


def comment_node(body: str) -> dict:
    return {
        "databaseId": 12,
        "author": {"login": "chatgpt-codex-connector", "__typename": "Bot"},
        "body": body,
        "createdAt": TIMESTAMP,
        "updatedAt": TIMESTAMP,
    }


def thread_node(body: str) -> dict:
    return {
        "id": "thread",
        "isResolved": False,
        "isOutdated": False,
        "head": {"nodes": [{"databaseId": 10}]},
        "last": {
            "nodes": [
                {
                    "databaseId": 11,
                    "updatedAt": TIMESTAMP,
                    "author": {
                        "login": "chatgpt-codex-connector",
                        "__typename": "Bot",
                    },
                    "body": body,
                }
            ]
        },
    }


def snapshot_response(thread_body: str = "Initial thread", comment_body: str = "P1 Badge") -> dict:
    thread = thread_node(thread_body)
    issue_comment = comment_node(comment_body)
    root = {
        "updatedAt": TIMESTAMP,
        "reviewThreads": {
            "totalCount": 1,
            "pageInfo": {"endCursor": None, "hasNextPage": False},
            "nodes": [thread],
        },
        "comments": {
            "totalCount": 1,
            "pageInfo": {"endCursor": None, "hasNextPage": False},
            "nodes": [issue_comment],
        },
        "lastThread": {"nodes": [thread]},
        "lastComment": {"nodes": [issue_comment]},
        "heldThreads": {
            "pageInfo": {"startCursor": None, "hasPreviousPage": False},
            "nodes": [thread],
        },
        "heldComments": {
            "pageInfo": {"startCursor": None, "hasPreviousPage": False},
            "nodes": [issue_comment],
        },
    }
    return {"repository": {"pullRequest": root}}


class BodyIdentityTests(unittest.TestCase):
    def test_comment_identity_hashes_body_without_retaining_it(self) -> None:
        # Given: a long body. When: its held-node identity is built.
        # Then: the identity retains only its fixed-size SHA-256 digest.
        body = "finding-body-" * 100
        identity = comment_identity(comment_node(body))
        self.assertEqual(identity, (12, TIMESTAMP, sha256(body.encode()).hexdigest()))
        self.assertNotIn(body, identity)

    def test_thread_identity_hashes_last_body_without_retaining_it(self) -> None:
        # Given: a long last review-thread body. When: its identity is built.
        # Then: classification fields remain and the body is bounded by a digest.
        body = "thread-body-" * 100
        identity = thread_identity(thread_node(body))
        self.assertEqual(identity[-1], sha256(body.encode()).hexdigest())
        self.assertNotIn(body, identity)

    def test_same_second_held_comment_body_edit_retries_snapshot(self) -> None:
        # Given: only a held issue-comment body changes in the same timestamp second.
        # When: revalidated. Then: the complete snapshot retries and returns that body.
        calls: list[tuple[str, dict]] = []
        responses = iter(
            [
                snapshot_response(comment_body="P1 Badge: before"),
                snapshot_response(comment_body="P1 Badge: before"),
                snapshot_response(comment_body="P1 Badge: after"),
                snapshot_response(comment_body="P1 Badge: after"),
                snapshot_response(comment_body="P1 Badge: after"),
                snapshot_response(comment_body="P1 Badge: after"),
            ]
        )

        def fake_graphql(query: str, variables: dict) -> dict:
            calls.append((query, variables))
            return next(responses)

        with mock.patch.object(pr_guard_threads, "gh_graphql", side_effect=fake_graphql):
            _, comments = pr_guard_threads.fetch_threads(68)
        self.assertEqual(comments[0].body, "P1 Badge: after")
        self.assertEqual(len(calls), 6)

    def test_same_second_held_thread_body_edit_retries_snapshot(self) -> None:
        # Given: only a held review-thread body changes in the same timestamp second.
        # When: revalidated. Then: the complete snapshot retries and returns that body.
        calls: list[tuple[str, dict]] = []
        responses = iter(
            [
                snapshot_response(thread_body="before"),
                snapshot_response(thread_body="before"),
                snapshot_response(thread_body="after"),
                snapshot_response(thread_body="after"),
                snapshot_response(thread_body="after"),
                snapshot_response(thread_body="after"),
            ]
        )

        def fake_graphql(query: str, variables: dict) -> dict:
            calls.append((query, variables))
            return next(responses)

        with mock.patch.object(pr_guard_threads, "gh_graphql", side_effect=fake_graphql):
            threads, _ = pr_guard_threads.fetch_threads(68)
        self.assertEqual(threads[0].last_body, "after")
        self.assertEqual(len(calls), 6)

    def test_stable_body_hash_snapshot_does_not_retry(self) -> None:
        # Given: a fixed snapshot whose bodies remain unchanged. When: revalidated.
        # Then: it completes the one-walk fast path.
        calls: list[tuple[str, dict]] = []
        responses = iter([snapshot_response()] * 3)

        def fake_graphql(query: str, variables: dict) -> dict:
            calls.append((query, variables))
            return next(responses)

        with mock.patch.object(pr_guard_threads, "gh_graphql", side_effect=fake_graphql):
            pr_guard_threads.fetch_threads(68)
        self.assertEqual(len(calls), 3)
        self.assertIn("nodes { databaseId updatedAt body }", IDENTITY_QUERY)
