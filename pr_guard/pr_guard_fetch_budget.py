"""Deadline-aware GraphQL fetch timeout plumbing for pr_guard."""

from __future__ import annotations

import json
import subprocess
import time

from .pr_guard_common import die, gh_env
from .pr_guard_reaction_boundaries import probe_timeout_budget

__all__ = ["bounded_graphql", "gh_graphql"]


def gh_graphql(
    query: str, variables: dict, timeout_secs: float | None = None
) -> dict:
    payload = json.dumps({"query": query, "variables": variables})
    proc = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        input=payload,
        capture_output=True,
        text=True,
        env=gh_env(),
        timeout=timeout_secs,
    )
    if proc.returncode != 0:
        die(f"gh api exited {proc.returncode}: {proc.stderr.strip()}")
    body = json.loads(proc.stdout)
    if body.get("errors"):
        die(f"GraphQL errors: {json.dumps(body['errors'])}")
    return body["data"]


def bounded_graphql(
    query: str,
    variables: dict,
    deadline: float | None = None,
    fetch_fn=None,
) -> dict:
    if fetch_fn is None:
        fetch_fn = gh_graphql
    if deadline is None:
        return fetch_fn(query, variables)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(
            ["gh", "api", "graphql"], probe_timeout_budget(remaining)
        )
    return fetch_fn(query, variables, probe_timeout_budget(remaining))
