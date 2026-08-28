"""Review-thread retrieval and reporting for pr_guard.

Split from pr_guard.py at the 250 pure-LOC ceiling (PR #36 round 2,
thread 3827503028): the GraphQL fetch, survey report, and the resolve
mutations. PR #37 (thread 3828232337) moved the pure classification
core (Thread, classify, BOT_AUTHORS) to pr_guard_classify.py; this
module re-exports those names so existing imports keep working.

PR #48 (vault note 'Unified Realms/Notes/Codex Review Bot Reaction
Signal.md'): survey also prints the BOT REACTION line beside the
summary — the review bot's PR reaction is the DONE/ACTIVE signal
(the cheap wait signal); the banner lives in pr_guard_reaction and
fails OPEN so an unreadable reaction can never block the gate.
"""

import json
import subprocess

from .pr_guard_classify import BOT_AUTHORS, CLASSES, Thread, classify
from .pr_guard_common import REPO_NAME, REPO_OWNER, die, gh_env
# PR #49 round 11 (thread 3868979509's split): the banner lives in
# the sibling banner module now (reaction.py hit the 250 pure-LOC
# ceiling); imports still flow ONE way — threads FROM banner FROM
# reaction/latch.
from .pr_guard_reaction_banner import reaction_banner

__all__ = [
    "BOT_AUTHORS",
    "CLASSES",
    "Thread",
    "classify",
    "fetch_threads",
    "refetch_thread",
    "resolve_thread",
    "survey",
    "unresolve_thread",
]

PAGE_SIZE = 100

THREADS_QUERY = f"""
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {{
  repository(owner: $owner, name: $name) {{
    pullRequest(number: $number) {{
      reviewThreads(first: {PAGE_SIZE}, after: $cursor) {{
        pageInfo {{ endCursor hasNextPage }}
        nodes {{
          id
          isResolved
          isOutdated
          head: comments(first: 1) {{ nodes {{ databaseId }} }}
          last: comments(last: 1) {{ nodes {{ databaseId author {{ login __typename }} body }} }}
        }}
      }}
    }}
  }}
}}
"""

RESOLVE_MUTATION = """
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread { id isResolved }
  }
}
"""

# Thread 3827635810: resolve()'s per-target drift probe — refetches ONE
# thread immediately before its mutation so a bot follow-up that landed
# after the survey cannot be resolved away unanswered.
THREAD_QUERY = """
query($id: ID!) {
  node(id: $id) {
    ... on PullRequestReviewThread {
      isResolved
      isOutdated
      comments(last: 1) { nodes { databaseId author { login __typename } body } }
    }
  }
}
"""

# Thread 3827768016: the recovery arm of the post-mutation check — a
# thread resolved while a bot follow-up landed in the mutate window is
# REOPENED so the server ruleset blocks the merge again.
UNRESOLVE_MUTATION = """
mutation($threadId: ID!) {
  unresolveReviewThread(input: {threadId: $threadId}) {
    thread { id isResolved }
  }
}
"""


def gh_graphql(query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables})
    proc = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        input=payload,
        capture_output=True,
        text=True,
        env=gh_env(),
    )
    if proc.returncode != 0:
        die(f"gh api exited {proc.returncode}: {proc.stderr.strip()}")
    body = json.loads(proc.stdout)
    if body.get("errors"):
        die(f"GraphQL errors: {json.dumps(body['errors'])}")
    return body["data"]


def fetch_threads(pr: int) -> list[Thread]:
    threads: list[Thread] = []
    cursor: str | None = None
    while True:
        data = gh_graphql(
            THREADS_QUERY,
            {
                "owner": REPO_OWNER,
                "name": REPO_NAME,
                "number": pr,
                "cursor": cursor,
            },
        )
        root = (data.get("repository") or {}).get("pullRequest")
        if root is None:
            die(f"PR #{pr} not found in {REPO_OWNER}/{REPO_NAME}")
        conn = root["reviewThreads"]
        for node in conn["nodes"]:
            head = node["head"]["nodes"]
            last = node["last"]["nodes"]
            last_comment = last[-1] if last else {}
            author = last_comment.get("author") or {}
            threads.append(
                Thread(
                    node_id=node["id"],
                    head_id=head[0]["databaseId"] if head else None,
                    last_id=last_comment.get("databaseId"),
                    last_author=author.get("login"),
                    last_author_type=author.get("__typename"),
                    last_body=last_comment.get("body") or "",
                    is_resolved=node["isResolved"],
                    is_outdated=node["isOutdated"],
                )
            )
        if not conn["pageInfo"]["hasNextPage"]:
            return threads
        cursor = conn["pageInfo"]["endCursor"]


def excerpt(body: str, limit: int = 72) -> str:
    flat = " ".join(body.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def survey(pr: int, reaction: bool = True) -> list[Thread]:
    threads = fetch_threads(pr)
    for thread in threads:
        thread.classification = classify(thread)
        author = thread.last_author if thread.last_author is not None else "(unknown)"
        outdated = " [outdated]" if thread.is_outdated else ""
        print(
            f"{thread.classification:<10} thread={thread.label}{outdated}"
            f" last={thread.last_label} author={author}"
            f' "{excerpt(thread.last_body)}"'
        )
    counts = {name: 0 for name in CLASSES}
    for thread in threads:
        counts[thread.classification] += 1
    print(
        f"SUMMARY pr={pr} total={len(threads)}"
        + "".join(f" {name}={counts[name]}" for name in CLASSES)
    )
    # PR #48 (vault note 'Unified Realms/Notes/Codex Review Bot
    # Reaction Signal.md'): the bot's PR reaction beside the summary —
    # the DONE/ACTIVE wait signal, first-class but NEVER the merge
    # authority (the banner fails open on an unreadable reaction).
    # Thread 3867757449 (PR #49 round 4, P1): the banner rides AFTER
    # the summary, and only on surveys that gate NO decision. Thread
    # 3867897759 (round 5, P1) completed the rule: EVERY survey whose
    # snapshot feeds a gate decision — the guarded merge's closing
    # survey AND the post-merge quiet watch's cycles plus its final
    # MERGED CLEAN verdict — passes reaction=False, because the
    # banner's bounded 15s informational read between snapshot and
    # go/no-go let a bot follow-up land on an already-resolved thread
    # while the gate consumed the stale clean list. Thread 3868158297
    # (round 7, P1) added pre-merge's CLOSING survey to the bannerless
    # camp — its late-findings check is the last read before CLEAN,
    # the merge act's exact decision surface. Thread 3868979526
    # (round 11, P2) added resolve's FINAL AUDIT — its DANGER check
    # gates the RESOLVE DONE verdict, the same decision surface. The
    # banner's only home is the human-facing informational CLI surveys
    # (plain survey, harden, pre-merge's OPENING survey, resolve's
    # OPENING survey), where it delays no dispatch and its output has
    # a human reader.
    if reaction:
        reaction_banner(pr, [t.label for t in threads])
    return threads


def resolve_thread(thread: Thread) -> bool:
    data = gh_graphql(RESOLVE_MUTATION, {"threadId": thread.node_id})
    resolved = data["resolveReviewThread"]["thread"]
    if not resolved["isResolved"]:
        print(f"UNRESOLVED?! thread={thread.label} ({resolved['id']})")
        return False
    print(f"RESOLVED thread={thread.label} ({resolved['id']})")
    return True


def unresolve_thread(thread: Thread) -> bool:
    data = gh_graphql(UNRESOLVE_MUTATION, {"threadId": thread.node_id})
    reopened = data["unresolveReviewThread"]["thread"]
    if reopened["isResolved"]:
        print(f"STILL RESOLVED?! thread={thread.label} ({reopened['id']})")
        return False
    print(f"REOPENED thread={thread.label} ({reopened['id']})")
    return True


def refetch_thread(thread: Thread) -> Thread | None:
    """Fresh single-thread read for the pre-resolve drift check."""
    data = gh_graphql(THREAD_QUERY, {"id": thread.node_id})
    node = data.get("node")
    if node is None:
        return None
    last = node.get("comments", {}).get("nodes") or []
    last_comment = last[-1] if last else {}
    author = last_comment.get("author") or {}
    return Thread(
        node_id=thread.node_id,
        head_id=thread.head_id,
        last_id=last_comment.get("databaseId"),
        last_author=author.get("login"),
        last_author_type=author.get("__typename"),
        last_body=last_comment.get("body") or "",
        is_resolved=node["isResolved"],
        is_outdated=node["isOutdated"],
    )
