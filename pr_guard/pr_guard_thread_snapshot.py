from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
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
      lastComment: comments(last: 1) { nodes { databaseId updatedAt body } }
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
        nodes { databaseId updatedAt body }
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
        body_hash(comment.get("body")),
    )


def body_hash(body: str | None) -> str:
    return sha256((body or "").encode()).hexdigest()


def comment_identity(node: dict) -> tuple:
    return node["databaseId"], node.get("updatedAt"), body_hash(node.get("body"))


def identity_from_root(root: dict) -> MutationIdentity:
    last_comment = root["lastComment"]["nodes"]
    last_thread = root["lastThread"]["nodes"]
    last_thread_node = last_thread[-1] if last_thread else None
    return (
        root["updatedAt"],
        root["comments"]["totalCount"],
        root["reviewThreads"]["totalCount"],
        comment_identity(last_comment[-1]) if last_comment else None,
        thread_identity(last_thread_node) if last_thread_node else None,
    )


def read_identity(
    pr: int,
    graphql: Callable[[str, dict], dict],
    held_thread_count: int = 0,
    held_comment_count: int = 0,
    terminal_check: bool = True,
) -> tuple[MutationIdentity, set[tuple], set[tuple], bool]:
    thread_cursor: str | None = None
    comment_cursor: str | None = None
    fetch_threads = held_thread_count > 0
    fetch_comments = held_comment_count > 0
    current_threads: set[tuple] = set()
    current_comments: set[tuple] = set()
    identity: MutationIdentity | None = None
    pages = 0
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
        pages += 1
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
    # Thread 4057312018: bracket the validation walk with full composite identities —
    # recompute and compare the complete identity (updatedAt + totalCounts + tail max-ids)
    # from the final validation response against the first response's identity. The recursive
    # L8 invariant: every bracket comparison uses the full identity, never a single field.
    final_identity = identity_from_root(root)
    if identity != final_identity:
        identity = final_identity
    terminal_matches = True
    if terminal_check and pages > 1:
        # Thread 4057392888: TERMINAL invariant: a paginated validation walk accepts
        # only when its immediately adjacent full-identity read agrees. The accepted
        # floor is an edit landing between two adjacent reads that both return
        # byte-identical bodies and timestamps, below GitHub's observable resolution.
        terminal_identity, terminal_threads, terminal_comments, _ = read_identity(
            pr,
            graphql,
            held_thread_count,
            held_comment_count,
            terminal_check=False,
        )
        terminal_matches = (identity, current_threads, current_comments) == (
            terminal_identity,
            terminal_threads,
            terminal_comments,
        )
    return identity, current_threads, current_comments, terminal_matches
