from __future__ import annotations

from collections.abc import Callable
from typing import Final

from .pr_guard_common import REPO_NAME, REPO_OWNER, die

SNAPSHOT_ATTEMPTS: Final = 3
MutationIdentity = tuple
PAGE_SIZE: Final = 100

IDENTITY_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $threadCursor: String, $commentCursor: String, $threadLimit: Int!, $commentLimit: Int!, $fetchThreads: Boolean!, $fetchComments: Boolean!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      updatedAt
      reviewThreads(first: 1) {
        totalCount
      }
      lastThread: reviewThreads(last: 1) {
        nodes {
          id
          isResolved
          isOutdated
          last: comments(last: 1) {
            nodes { databaseId updatedAt author { login __typename } body }
          }
        }
      }
      comments(first: 1) {
        totalCount
      }
      lastComment: comments(last: 1) { nodes { databaseId updatedAt } }
      heldThreads: reviewThreads(last: $threadLimit, before: $threadCursor) @include(if: $fetchThreads) {
        pageInfo { startCursor hasPreviousPage }
        nodes {
          id
          isResolved
          isOutdated
          last: comments(last: 1) {
            nodes { databaseId updatedAt author { login __typename } body }
          }
        }
      }
      heldComments: comments(last: $commentLimit, before: $commentCursor) @include(if: $fetchComments) {
        pageInfo { startCursor hasPreviousPage }
        nodes { databaseId updatedAt }
      }
    }
  }
}
"""


def thread_identity(node: dict) -> tuple:
    last = node["last"]["nodes"]
    comment = last[-1] if last else {}
    author = comment.get("author") or {}
    return (
        node["id"],
        node["isResolved"],
        node["isOutdated"],
        comment.get("databaseId"),
        comment.get("updatedAt"),
        author.get("login"),
        author.get("__typename"),
        comment.get("body") or "",
    )


def comment_identity(node: dict) -> tuple:
    return node["databaseId"], node.get("updatedAt")


def identity_from_root(root: dict) -> MutationIdentity:
    last_comment = root["lastComment"]["nodes"]
    last_thread = root["lastThread"]["nodes"]
    last_thread_node = last_thread[-1] if last_thread else None
    last_thread_comments = last_thread_node["last"]["nodes"] if last_thread_node else []
    last_thread_comment = last_thread_comments[-1] if last_thread_comments else None
    last_thread_author = (last_thread_comment or {}).get("author") or {}
    return (
        root["updatedAt"],
        root["comments"]["totalCount"],
        root["reviewThreads"]["totalCount"],
        comment_identity(last_comment[-1]) if last_comment else None,
        (
            last_thread_node["id"],
            last_thread_node["isResolved"],
            last_thread_node["isOutdated"],
            (last_thread_comment or {}).get("databaseId"),
            (last_thread_comment or {}).get("updatedAt"),
            last_thread_author.get("login"),
            last_thread_author.get("__typename"),
            (last_thread_comment or {}).get("body") or "",
        )
        if last_thread_node
        else None,
    )


def read_identity(
    pr: int,
    graphql: Callable[[str, dict], dict],
    held_thread_count: int = 0,
    held_comment_count: int = 0,
) -> tuple[MutationIdentity, set[tuple], set[tuple]]:
    thread_cursor: str | None = None
    comment_cursor: str | None = None
    fetch_threads = held_thread_count > 0
    fetch_comments = held_comment_count > 0
    current_threads: set[tuple] = set()
    current_comments: set[tuple] = set()
    identity: MutationIdentity | None = None
    while identity is None or fetch_threads or fetch_comments:
        data = graphql(
            IDENTITY_QUERY,
            {
                "owner": REPO_OWNER,
                "name": REPO_NAME,
                "number": pr,
                "threadCursor": thread_cursor,
                "commentCursor": comment_cursor,
                "threadLimit": min(max(held_thread_count, 1), PAGE_SIZE),
                "commentLimit": min(max(held_comment_count, 1), PAGE_SIZE),
                "fetchThreads": fetch_threads,
                "fetchComments": fetch_comments,
            },
        )
        root = (data.get("repository") or {}).get("pullRequest")
        if root is None:
            die(f"PR #{pr} not found in {REPO_OWNER}/{REPO_NAME}")
        if identity is None:
            identity = identity_from_root(root)
        if fetch_threads:
            connection = root["heldThreads"]
            current_threads.update(thread_identity(node) for node in connection["nodes"])
            fetch_threads = (
                len(current_threads) < held_thread_count
                and connection["pageInfo"]["hasPreviousPage"]
            )
            thread_cursor = connection["pageInfo"]["startCursor"]
        if fetch_comments:
            connection = root["heldComments"]
            current_comments.update(comment_identity(node) for node in connection["nodes"])
            fetch_comments = (
                len(current_comments) < held_comment_count
                and connection["pageInfo"]["hasPreviousPage"]
            )
            comment_cursor = connection["pageInfo"]["startCursor"]
    assert identity is not None
    # Thread 4057278844: bracket the validation walk with sentinel reads — fold the
    # post-walk check into the final page response and require first == last.
    if root["updatedAt"] != identity[0]:
        identity = (root["updatedAt"], *identity[1:])
    return identity, current_threads, current_comments
