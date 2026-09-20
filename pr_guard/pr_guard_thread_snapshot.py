from __future__ import annotations

from collections.abc import Callable
from typing import Final

from .pr_guard_common import REPO_NAME, REPO_OWNER, die

SNAPSHOT_ATTEMPTS: Final = 3
MutationIdentity = tuple

IDENTITY_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      updatedAt
      reviewThreads(first: 0) {
        totalCount
      }
      lastThread: reviewThreads(last: 1) {
        nodes {
          id
          isResolved
          isOutdated
          last: comments(last: 1) {
            nodes { databaseId author { login __typename } body }
          }
        }
      }
      comments(first: 0) {
        totalCount
      }
      lastComment: comments(last: 1) { nodes { databaseId } }
    }
  }
}
"""

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
        last_comment[-1]["databaseId"] if last_comment else None,
        (
            last_thread_node["id"],
            last_thread_node["isResolved"],
            last_thread_node["isOutdated"],
            (last_thread_comment or {}).get("databaseId"),
            last_thread_author.get("login"),
            last_thread_author.get("__typename"),
            (last_thread_comment or {}).get("body") or "",
        )
        if last_thread_node
        else None,
    )


def read_identity(pr: int, graphql: Callable[[str, dict], dict]) -> MutationIdentity:
    data = graphql(
        IDENTITY_QUERY,
        {"owner": REPO_OWNER, "name": REPO_NAME, "number": pr},
    )
    root = (data.get("repository") or {}).get("pullRequest")
    if root is None:
        die(f"PR #{pr} not found in {REPO_OWNER}/{REPO_NAME}")
    return identity_from_root(root)
