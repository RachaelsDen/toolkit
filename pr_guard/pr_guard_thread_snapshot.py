from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from .pr_guard_common import REPO_NAME, REPO_OWNER, die

if TYPE_CHECKING:
    from .pr_guard_classify import Thread
    from .pr_guard_issue_comments import IssueComment


PAGE_SIZE = 100
SNAPSHOT_ATTEMPTS: Final = 3
MutationIdentity = tuple[str, int, int, int | None, int | None]

REVISION_QUERY = f"""
query($owner: String!, $name: String!, $number: Int!, $cursor: String, $ccursor: String, $fetchThreads: Boolean!, $fetchComments: Boolean!) {{
  repository(owner: $owner, name: $name) {{
    pullRequest(number: $number) {{
      updatedAt
      reviewThreads(first: {PAGE_SIZE}, after: $cursor) @include(if: $fetchThreads) {{
        totalCount
        pageInfo {{ endCursor hasNextPage }}
        nodes {{
          id
          isResolved
          isOutdated
          last: comments(last: 1) {{ nodes {{ databaseId author {{ login __typename }} body }} }}
        }}
      }}
      comments(first: {PAGE_SIZE}, after: $ccursor) @include(if: $fetchComments) {{
        totalCount
        pageInfo {{ endCursor hasNextPage }}
        nodes {{ databaseId updatedAt }}
      }}
    }}
  }}
}}
"""


def mutation_identity(
    updated_at: str,
    comment_total_count: int,
    thread_total_count: int,
    comments: list[IssueComment],
    threads: list[Thread],
) -> MutationIdentity:
    return (
        updated_at,
        comment_total_count,
        thread_total_count,
        max((comment.id for comment in comments), default=None),
        max((thread.last_id for thread in threads if thread.last_id is not None), default=None),
    )


def connections_match(
    pr: int,
    graphql: Callable[[str, dict], dict],
    threads: list[Thread],
    comments: list[IssueComment],
) -> tuple[bool, MutationIdentity]:
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
    current_updated_at = ""
    current_comment_total_count = 0
    current_thread_total_count = 0
    current_max_comment_id: int | None = None
    current_max_thread_comment_id: int | None = None
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
        current_updated_at = root["updatedAt"]
        if fetch_threads:
            thread_connection = root["reviewThreads"]
            current_thread_total_count = thread_connection["totalCount"]
            for node in thread_connection["nodes"]:
                last = node["last"]["nodes"]
                last_comment = last[-1] if last else {}
                author = last_comment.get("author") or {}
                last_id = last_comment.get("databaseId")
                if last_id is not None and (
                    current_max_thread_comment_id is None
                    or last_id > current_max_thread_comment_id
                ):
                    current_max_thread_comment_id = last_id
                current_threads.add(
                    (
                        node["id"],
                        node["isResolved"],
                        node["isOutdated"],
                        last_id,
                        author.get("login"),
                        author.get("__typename"),
                        last_comment.get("body") or "",
                    )
                )
            fetch_threads = thread_connection["pageInfo"]["hasNextPage"]
            cursor = thread_connection["pageInfo"]["endCursor"]
        if fetch_comments:
            comment_connection = root["comments"]
            current_comment_total_count = comment_connection["totalCount"]
            for node in comment_connection["nodes"]:
                comment_id = node["databaseId"]
                if current_max_comment_id is None or comment_id > current_max_comment_id:
                    current_max_comment_id = comment_id
                current_comments.add((comment_id, node["updatedAt"]))
            fetch_comments = comment_connection["pageInfo"]["hasNextPage"]
            ccursor = comment_connection["pageInfo"]["endCursor"]
    return (
        held_threads == current_threads and held_comments == current_comments,
        (
            current_updated_at,
            current_comment_total_count,
            current_thread_total_count,
            current_max_comment_id,
            current_max_thread_comment_id,
        ),
    )
