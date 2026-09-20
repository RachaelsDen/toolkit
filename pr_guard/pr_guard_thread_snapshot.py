from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from .pr_guard_common import REPO_NAME, REPO_OWNER, die

if TYPE_CHECKING:
    from .pr_guard_classify import Thread
    from .pr_guard_issue_comments import IssueComment


PAGE_SIZE = 100

REVISION_QUERY = f"""
query($owner: String!, $name: String!, $number: Int!, $cursor: String, $ccursor: String, $fetchThreads: Boolean!, $fetchComments: Boolean!) {{
  repository(owner: $owner, name: $name) {{
    pullRequest(number: $number) {{
      reviewThreads(first: {PAGE_SIZE}, after: $cursor) @include(if: $fetchThreads) {{
        pageInfo {{ endCursor hasNextPage }}
        nodes {{
          id
          isResolved
          isOutdated
          last: comments(last: 1) {{ nodes {{ databaseId author {{ login __typename }} body }} }}
        }}
      }}
      comments(first: {PAGE_SIZE}, after: $ccursor) @include(if: $fetchComments) {{
        pageInfo {{ endCursor hasNextPage }}
        nodes {{ databaseId updatedAt }}
      }}
    }}
  }}
}}
"""


def connections_match(
    pr: int,
    graphql: Callable[[str, dict], dict],
    threads: list[Thread],
    comments: list[IssueComment],
) -> bool:
    held_threads = {
        (
            thread.node_id,
            thread.is_resolved,
            thread.is_outdated,
            thread.last_id,
            thread.last_author,
            thread.last_author_type,
            thread.last_body,
        )
        for thread in threads
    }
    held_comments = {(comment.id, comment.updated_at) for comment in comments}
    current_threads: set[tuple] = set()
    current_comments: set[tuple] = set()
    cursor: str | None = None
    ccursor: str | None = None
    fetch_threads = True
    fetch_comments = True
    while fetch_threads or fetch_comments:
        data = graphql(
            REVISION_QUERY,
            {
                "owner": REPO_OWNER,
                "name": REPO_NAME,
                "number": pr,
                "cursor": cursor,
                "ccursor": ccursor,
                "fetchThreads": fetch_threads,
                "fetchComments": fetch_comments,
            },
        )
        root = (data.get("repository") or {}).get("pullRequest")
        if root is None:
            die(f"PR #{pr} not found in {REPO_OWNER}/{REPO_NAME}")
        if fetch_threads:
            thread_connection = root["reviewThreads"]
            for node in thread_connection["nodes"]:
                last = node["last"]["nodes"]
                last_comment = last[-1] if last else {}
                author = last_comment.get("author") or {}
                current_threads.add(
                    (
                        node["id"],
                        node["isResolved"],
                        node["isOutdated"],
                        last_comment.get("databaseId"),
                        author.get("login"),
                        author.get("__typename"),
                        last_comment.get("body") or "",
                    )
                )
            fetch_threads = thread_connection["pageInfo"]["hasNextPage"]
            cursor = thread_connection["pageInfo"]["endCursor"]
        if fetch_comments:
            comment_connection = root["comments"]
            current_comments.update(
                (node["databaseId"], node["updatedAt"])
                for node in comment_connection["nodes"]
            )
            fetch_comments = comment_connection["pageInfo"]["hasNextPage"]
            ccursor = comment_connection["pageInfo"]["endCursor"]
    return held_threads == current_threads and held_comments == current_comments
